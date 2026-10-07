"""The morning brief the harness writes for Anne-Marie: the same sections, in the same order, as her Claude brief, so the two can be compared side by side.
  1. CALENDAR   2. IMPORTANT MAIL   3. SUIVI (a due today or overdue, b next 7 days, c waiting on, d checks, f personal)   4. TO CONFIRM (not built here)   5. NEEDS YOUR ATTENTION
Plus what only the harness knows: this week's events, hours, scans and phone to-dos waiting. Built from the harness's own data (read-only, no AI); section 5 is
written by rules here and can be re-written by the local model (harness/brief_ai.py). Personal items are masked. Nothing here is sent anywhere."""
import json
import sqlite3
from datetime import date, datetime, timedelta

from harness import events as E, hours as H, phone, privacy, scans
from harness.config import TZ, now_local
from harness.today import build_today
from harness.triage import list_emails

WEEKDAY = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
MONTH = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December")


def long_date(d: date) -> str:
    return f"{WEEKDAY[d.weekday()]} {d.day} {MONTH[d.month - 1]} {d.year}"


def _hm(iso: str) -> str:
    return datetime.fromisoformat(iso).astimezone(TZ).strftime("%H:%M")


def _calendar(conn: sqlite3.Connection, day: date) -> list[dict]:
    d, nxt = day.isoformat(), (day + timedelta(days=1)).isoformat()
    out = []
    for r in conn.execute("SELECT * FROM calendar_events WHERE status != 'cancelled' ORDER BY all_day DESC, start"):
        if r["all_day"]:
            if not (r["start"][:10] <= d < (r["end"] or nxt)[:10] or r["start"][:10] == d):
                continue
            span = None
        else:
            if r["start"][:10] != d and not (r["end"] and r["start"][:10] < d <= r["end"][:10] and r["end"][:10] != d):
                continue
            span = (_hm(r["start"]), _hm(r["end"]) if r["end"] else None)
        personal = privacy.is_personal(r["space"])
        out.append({"title": privacy.label("event") if personal else r["title"], "all_day": bool(r["all_day"]), "start": span[0] if span else None, "end": span[1] if span else None,
                    "place": None if personal else r["location"], "masked": personal, "_s": r["start"], "_e": r["end"]})
    return out


def _clashes(events: list[dict]) -> list[tuple[str, str]]:
    timed = [e for e in events if not e["all_day"] and e["_e"]]
    out = []
    for i, a in enumerate(timed):
        for b in timed[i + 1:]:
            if datetime.fromisoformat(a["_s"]) < datetime.fromisoformat(b["_e"]) and datetime.fromisoformat(b["_s"]) < datetime.fromisoformat(a["_e"]):
                out.append((a["title"], b["title"]))
    return out


def _suivi(conn, tod: dict, day: date) -> dict:
    open_items = [i for i in tod["today_items"] if not i["done"]]
    key = lambda i: (0 if i["weight"] == "major" else 1 if i["weight"] == "hard" else 2, -i["days_overdue"], i["title"])
    work = [i for i in open_items if not i["masked"]]
    due_today = sorted((i for i in work if i["days_overdue"] == 0), key=key)
    overdue = sorted((i for i in work if i["days_overdue"] > 0), key=key)
    nxt = [i for i in tod["upcoming_items"] if not i["done"] and not i["masked"]]
    personal = [{"title": i["title"], "due": i["due"], "days_overdue": i["days_overdue"]} for i in open_items if i["masked"]]
    waiting = []
    for r in conn.execute("SELECT w.*, p.name AS pname FROM waiting_on w LEFT JOIN people p ON p.slug = w.person WHERE w.status='open' AND w.space='work' AND w.since_date <= ? ORDER BY w.since_date",
                          ((day - timedelta(days=7)).isoformat(),)):
        waiting.append({"what": r["description"], "who": r["pname"] or r["person"], "days": (day - date.fromisoformat(r["since_date"])).days})
    return {"due_today": due_today, "overdue": overdue, "next7": nxt, "waiting": waiting, "personal": personal,
            "checks": {"overdue_over_14": [i for i in overdue if i["days_overdue"] > 14], "undated_tasks": tod["undated_tasks"],
                       "major_within_14": [m for m in tod["lake"] if m["importance"] == "major" and not m["personal"] and 0 <= (date.fromisoformat(m["due"]) - day).days <= 14]}}


def rules_attention(b: dict) -> list[dict]:
    """The few things that need her attention today, by plain rules: the harness's fallback and the facts the model is given."""
    out = []
    for i in (b["suivi"]["due_today"] + b["suivi"]["overdue"]):
        if i["weight"] in ("major", "hard") and len(out) < 2:
            when = "due today" if i["days_overdue"] == 0 else f"{i['days_overdue']} days overdue"
            out.append({"title": i["title"], "why": f"{i['weight']} item, {when}."})
    if b["calendar"]["clashes"]:
        a, c = b["calendar"]["clashes"][0]
        out.append({"title": "A clash in today's calendar", "why": f"“{a}” overlaps “{c}”: one has to move."})
    for m in b["replies"][:2]:
        out.append({"title": f"{m['from']} replied: {m['subject']}", "why": m["why"]})
    for m in b["mail"][:6]:
        if m["deadline"] and m["deadline"] <= (date.fromisoformat(b["day"]) + timedelta(days=2)).isoformat() and len(out) < 4:
            out.append({"title": f"Reply to {m['from']}: {m['subject']}", "why": f"{m['action'] or 'A reply'} is wanted by {m['deadline']}."})
    for w in b["suivi"]["waiting"]:
        if w["days"] > 14 and len(out) < 4:
            out.append({"title": f"Chase {w['who'] or 'someone'}", "why": f"Waiting {w['days']} days for: {w['what']}"})
            break
    return out[:4]


def build(conn: sqlite3.Connection, now: datetime | None = None) -> dict:
    now = now or now_local()
    day = now.date()
    tod = build_today(conn, now)
    cal = _calendar(conn, day)
    tomorrow = _calendar(conn, day + timedelta(days=1))
    mail = [{"from": m["from_name"], "org": m["org"], "subject": m["subject"], "why": m["why"], "action": m["action"], "deadline": m["deadline"], "hours_ago": m["hours_ago"], "known": m["known"]}
            for m in list_emails(conn, 72, now)["needs_reply"][:8]]
    on_items = [{"from": m["from_name"], "subject": m["subject"], "why": m["why"], "item": m["open_item"], "hours_ago": m["hours_ago"]}
                for m in list_emails(conn, 72, now)["on_open_items"]]
    week_end = (day + timedelta(days=7)).isoformat()
    evs = [e for e in E.list_events(conn, day, "upcoming")["items"] if e["status"] in ("confirmed", "tentative", "invited") and day.isoformat() < e["start"][:10] <= week_end][:8]
    hw = H.week_summary(conn, day)
    b = {"day": day.isoformat(), "title": long_date(day), "calendar": {"today": [{k: v for k, v in e.items() if not k.startswith("_")} for e in cal],
                                                                        "clashes": _clashes(cal), "tomorrow": [{k: v for k, v in e.items() if not k.startswith("_")} for e in tomorrow]},
         "mail": mail, "replies": on_items, "suivi": _suivi(conn, tod, day),
         "events_week": [{"title": e["title"], "when": e["start"][:10], "status": e["status"], "role": e["role"], "place": e["venue"], "rsvp_by": e["rsvp_by"]} for e in evs],
         "harness": {"hours_week": hw["total"], "hours_days_without": hw["days_without"], "scans_to_confirm": scans.summary(conn)["to_confirm"], "phone_waiting": len(phone.list_new(conn)["items"]),
                     "friday": day.weekday() == 4}}
    b["attention"], b["attention_source"] = rules_attention(b), "rules"
    return b


# ---------------------------------------------------------------- the plain-text version (what goes into the Gmail draft)
def _line(i: dict) -> str:
    when = "" if not i.get("due") else (f" — {i['days_overdue']}d overdue" if i["days_overdue"] else "")
    return f"- ({i['weight']}{', ' + i['code'] if i.get('code') else ''}) {i['title']}{when}" + (f" [{i['person']}]" if i.get("person") else "")


def render_text(b: dict) -> str:
    L = [f"Morning brief by the IG Harness — {b['title']}", "Same sections as your Claude brief, built from the harness's own data on your Mac. Section 4 (proposed Suivi entries) is not part of this brief.", ""]
    L.append(f"1. CALENDAR — {b['title']}")
    if not b["calendar"]["today"]:
        L.append("Nothing in the calendar today.")
    for e in b["calendar"]["today"]:
        t = "All day" if e["all_day"] else f"{e['start']}-{e['end'] or ''}".rstrip("-")
        L.append(f"{t} — {e['title']}" + (f" ({e['place']})" if e.get("place") else ""))
    for a, c in b["calendar"]["clashes"]:
        L.append(f"  CLASH: “{a}” overlaps “{c}”.")
    if b["calendar"]["tomorrow"]:
        L.append("TOMORROW: " + "; ".join(("all day " if e["all_day"] else f"{e['start']} ") + e["title"] for e in b["calendar"]["tomorrow"][:6]))
    if b["events_week"]:
        L.append("EVENTS THIS WEEK: " + "; ".join(f"{e['when'][5:]} {e['title']} ({'you are in' if e['status'] == 'confirmed' else e['status']}{', ' + e['role'] if e['role'] else ''})" for e in b["events_week"]))
    L += ["", "2. IMPORTANT MAIL"]
    L += [f"- {m['from']}{' (' + m['org'] + ')' if m['org'] else ''} — {m['subject']}: {m['why'] or m['action'] or 'needs a reply'}" + (f" (by {m['deadline']})" if m["deadline"] else "") for m in b["mail"]] or ["- Nothing needs a reply."]
    L += ["", "2b. REPLIES ON OPEN ITEMS (new mail that answers something you wait for, even when it asks nothing)"]
    L += [f"- {m['from']} — {m['subject']}: {m['why']}" for m in b["replies"]] or ["- None."]
    s = b["suivi"]
    L += ["", "3. SUIVI", "a. Due today or overdue (open)"] + ([_line(i) for i in s["due_today"] + s["overdue"]] or ["- Nothing."])
    L += ["b. Due in the next 7 days"] + ([f"- {i['due']} {_line(i)[2:]}" for i in s["next7"]] or ["- Nothing."])
    L += ["c. Waiting on (over 7 days)"] + ([f"- {w['who'] or '?'}: {w['what']} — {w['days']}d" for w in s["waiting"]] or ["- Nothing."])
    ck = s["checks"]
    L.append("d. Checks")
    L.append(f"- Overdue more than 14 days: {', '.join(i['title'] for i in ck['overdue_over_14']) or 'none'}")
    L.append(f"- Major deadlines in the next 14 days: {', '.join(m['title'] + ' (' + m['due'] + ')' for m in ck['major_within_14']) or 'none'}")
    L.append(f"- Open tasks without a date: {ck['undated_tasks']}")
    L.append("e. Relationship nudges — not part of this brief yet.")
    L.append("f. Personal — " + (", ".join(f"{p['title']} ({p['due']})" for p in s["personal"]) or "nothing."))
    h = b["harness"]
    L += ["", "4. TO CONFIRM — not part of this brief (your Claude brief proposes the Suivi entries).", "", "5. NEEDS YOUR ATTENTION" + ("" if b["attention_source"] == "rules" else " (written by your local model: check it against the lists above)")]
    L += [f"{n}. {a['title']} {a['why']}".strip() for n, a in enumerate(b["attention"], 1)] or ["Nothing stands out."]
    L += ["", "ALSO IN THE HARNESS", f"- Hours this week: {h['hours_week']} h" + (f"; nothing logged on {', '.join(d[5:] for d in h['hours_days_without'])}" if h["hours_days_without"] else "") + ("; it is Friday: run the hours pass." if h["friday"] else ""),
          f"- Scans waiting for you: {h['scans_to_confirm']}; phone to-dos waiting: {h['phone_waiting']}"]
    return "\n".join(L)


def save(conn: sqlite3.Connection, b: dict, text: str | None = None, model: str | None = None) -> None:
    text = text or render_text(b)
    with conn:
        conn.execute("INSERT INTO briefs (day, created_at, data, text, attention_source, model) VALUES (?,?,?,?,?,?) ON CONFLICT (day) DO UPDATE SET created_at=excluded.created_at, data=excluded.data, "
                     "text=excluded.text, attention_source=excluded.attention_source, model=excluded.model",
                     (b["day"], now_local().isoformat(timespec="seconds"), json.dumps(b, ensure_ascii=False), text, b["attention_source"], model))


def latest(conn: sqlite3.Connection, day: str | None = None) -> dict | None:
    r = conn.execute("SELECT * FROM briefs WHERE day = ?" if day else "SELECT * FROM briefs ORDER BY day DESC LIMIT 1", (day,) if day else ()).fetchone()
    return {"day": r["day"], "created_at": r["created_at"], "data": json.loads(r["data"]), "text": r["text"], "attention_source": r["attention_source"], "draft_status": r["draft_status"], "draft_note": r["draft_note"]} if r else None
