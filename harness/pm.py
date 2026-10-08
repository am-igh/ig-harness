"""Project and contract management: projects, funders and partners, contracts (kept in her folders; only a path and hash here), obligations with the deadlines they generate,
transfers with the bank's exchange rate, and a crosswalk that compares what different funders ask for. Plain rules throughout: nothing here calls a model, and any mapping that
was only proposed stays marked unconfirmed until she confirms it. Deadlines feed the core `deadlines` table (source 'pm') so they appear on the Today lake."""
import re
import sqlite3
from datetime import date, datetime, timedelta

from harness.config import now_local

CANON = {
    "narrative_report": "Narrative report", "financial_report": "Financial report", "milestone_report": "Milestone report", "audit": "External audit",
    "partner_report": "Partner (sub-grantee) report", "notification": "Notification or declaration", "visibility": "Visibility and acknowledgement",
    "budget_approval": "Budget changes (prior approval)", "overhead": "Overhead cap", "procurement": "Procurement rules",
}
REPORT_TYPES = {"narrative_report", "financial_report", "milestone_report", "audit", "partner_report", "notification"}
DETAIL = ["summary", "standard", "detailed", "line-by-line"]
STATUSES = ("todo", "drafting", "submitted", "accepted")
STEP = {"quarterly": 3, "semiannual": 6, "annual": 12}
RECURRENCE_WORDS = {"none": "no schedule", "once": "once", "quarterly": "every quarter", "semiannual": "every six months", "annual": "every year"}


class PMError(ValueError):
    pass


def _d(v) -> date | None:
    return date.fromisoformat(v[:10]) if v else None


def add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    y += d.year
    m += 1
    last = [31, 29 if y % 4 == 0 and (y % 100 or y % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
    return date(y, m, min(d.day, last))


def periods(start: date, end: date, recurrence: str) -> list[tuple[int, date, date]]:
    out, cur, n = [], start, 1
    while cur <= end:
        nxt = add_months(start, STEP[recurrence] * n)
        out.append((n, cur, min(nxt - timedelta(days=1), end)))
        cur, n = nxt, n + 1
    return out


def rule_label(o) -> str:
    if o["recurrence"] == "none" or o["anchor"] == "none":
        return "ongoing rule"
    when = {"period_end": "after each period end", "end": "after the end date", "start": "after the start date", "fixed": ""}[o["anchor"]]
    if o["anchor"] == "fixed":
        return f"on {o['fixed_date']}"
    off = o["offset_days"]
    return f"{RECURRENCE_WORDS[o['recurrence']]}, {off} days {when}" if off else f"{RECURRENCE_WORDS[o['recurrence']]}, at the {when.replace('after ', '')}"


# ---------------------------------------------------------------- adding things
def _need(v, what):
    if v is None or (isinstance(v, str) and not v.strip()):
        raise PMError(f"{what} is required")
    return v.strip() if isinstance(v, str) else v


def add_funder(conn, name: str, short: str | None = None, role: str = "funder", currency: str = "CHF", contact: str | None = None, notes: str | None = None) -> int:
    name = _need(name, "A name")
    if conn.execute("SELECT 1 FROM pm_funders WHERE name = ?", (name,)).fetchone():
        raise PMError(f"“{name}” is already in the list")
    cur = conn.execute("INSERT INTO pm_funders (name, short, role, currency, contact, notes) VALUES (?,?,?,?,?,?)",
                       (name, (short or name)[:12], role if role in ("funder", "partner") else "funder", (currency or "CHF").upper()[:3], contact, notes))
    conn.commit()
    return cur.lastrowid


def add_project(conn, code: str, name: str, start_date=None, end_date=None, lead=None, summary=None, demo: bool = False, status: str = "active") -> int:
    code = re.sub(r"[^A-Z0-9]", "", _need(code, "A project code").upper())
    if not code:
        raise PMError("The project code needs letters or digits")
    if conn.execute("SELECT 1 FROM pm_projects WHERE code = ?", (code,)).fetchone():
        raise PMError(f"{code} is already a project here")
    cur = conn.execute("INSERT INTO pm_projects (code, name, status, start_date, end_date, lead, summary, demo) VALUES (?,?,?,?,?,?,?,?)",
                       (code, _need(name, "A name"), status, start_date, end_date, lead, summary, int(demo)))
    conn.execute("INSERT OR IGNORE INTO project_codes (code, name, domain, kind) VALUES (?,?,'W','project')", (code, name))
    conn.commit()
    return cur.lastrowid


def add_contract(conn, project_id: int, funder_id: int, title: str, kind: str = "grant", amount=None, currency: str | None = None, budget_rate=None,
                 signed_date=None, start_date=None, end_date=None, file_path=None, file_hash=None, summary=None, parent_id=None) -> int:
    f = conn.execute("SELECT * FROM pm_funders WHERE id = ?", (funder_id,)).fetchone()
    if f is None or conn.execute("SELECT 1 FROM pm_projects WHERE id = ?", (project_id,)).fetchone() is None:
        raise PMError("Unknown project or funder")
    cur_ = (currency or f["currency"]).upper()
    rate = 1.0 if cur_ == "CHF" else float(budget_rate or 0)
    if rate <= 0:
        raise PMError(f"A contract in {cur_} needs the budget exchange rate (CHF per 1 {cur_})")
    if start_date and end_date and _d(end_date) < _d(start_date):
        raise PMError("The end date is before the start date")
    cur = conn.execute("INSERT INTO pm_contracts (project_id, funder_id, parent_id, kind, title, signed_date, start_date, end_date, amount, currency, budget_rate, file_path, file_hash, summary) "
                       "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (project_id, funder_id, parent_id, kind, _need(title, "A title"), signed_date, start_date, end_date, amount, cur_, rate, file_path, file_hash, summary))
    conn.commit()
    return cur.lastrowid


def add_obligation(conn, contract_id: int, canon: str, title: str, clause=None, anchor="period_end", offset_days=0, recurrence="once", fixed_date=None,
                   format=None, language=None, detail=None, note=None, confirmed=True, source="manual") -> int:
    if canon not in CANON:
        raise PMError("Unknown requirement type")
    if detail and detail not in DETAIL:
        raise PMError("The level of detail must be one of: " + ", ".join(DETAIL))
    if anchor == "fixed" and not fixed_date:
        raise PMError("A fixed deadline needs its date")
    if recurrence in STEP and anchor != "period_end":
        raise PMError("A repeating report is due relative to the end of each period")
    c = conn.execute("SELECT * FROM pm_contracts WHERE id = ?", (contract_id,)).fetchone()
    if c is None:
        raise PMError("Unknown contract")
    cur = conn.execute("INSERT INTO pm_obligations (contract_id, canon, title, clause, anchor, offset_days, recurrence, fixed_date, format, language, detail, note, confirmed, source) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       (contract_id, canon, _need(title, "A title"), clause, anchor, int(offset_days or 0), recurrence, fixed_date, format, language, detail, note, int(confirmed), source))
    conn.commit()
    generate(conn, cur.lastrowid)
    return cur.lastrowid


def generate(conn, obligation_id: int) -> int:
    """Create the deadlines this obligation implies (those not yet present). Returns how many were added."""
    o = conn.execute("SELECT o.*, c.start_date AS cs, c.end_date AS ce FROM pm_obligations o JOIN pm_contracts c ON c.id = o.contract_id WHERE o.id = ?", (obligation_id,)).fetchone()
    due: list[tuple[str, date]] = []
    off = timedelta(days=o["offset_days"])
    if o["anchor"] == "none" or o["recurrence"] == "none":
        return 0
    if o["anchor"] == "fixed":
        due.append((o["title"], _d(o["fixed_date"])))
    elif o["recurrence"] in STEP:
        if not (o["cs"] and o["ce"]):
            return 0
        for n, a, b in periods(_d(o["cs"]), _d(o["ce"]), o["recurrence"]):
            due.append((f"{a:%b %Y}–{b:%b %Y}", b + off))
    else:
        base = _d(o["ce"] if o["anchor"] == "end" else o["cs"])
        if base is None:
            return 0
        due.append(("final" if o["anchor"] == "end" else "start", base + off))
    added = 0
    for label, when in due:
        if conn.execute("INSERT OR IGNORE INTO pm_deadlines (obligation_id, period_label, due_date) VALUES (?,?,?)", (obligation_id, label, when.isoformat())).rowcount:
            added += 1
    conn.commit()
    return added


def extend_contract(conn, contract_id: int, new_end: str, title: str, signed_date: str | None = None, summary: str | None = None) -> int:
    """A no-cost extension: records the amendment, moves the contract's end date, adds the deadlines for the new periods and moves the final-report deadline that has not been done."""
    c = conn.execute("SELECT * FROM pm_contracts WHERE id = ?", (contract_id,)).fetchone()
    if c is None or c["kind"] == "amendment":
        raise PMError("Choose the contract itself, not an amendment")
    if _d(new_end) <= _d(c["end_date"]):
        raise PMError("The new end date must be later than the current one")
    amend = add_contract(conn, c["project_id"], c["funder_id"], title, kind="amendment", currency=c["currency"], budget_rate=c["budget_rate"] if c["currency"] != "CHF" else None,
                         signed_date=signed_date, start_date=c["end_date"], end_date=new_end, summary=summary, parent_id=contract_id)
    with conn:
        conn.execute("UPDATE pm_contracts SET end_date = ?, status = 'amended' WHERE id = ?", (new_end, contract_id))
        for o in conn.execute("SELECT * FROM pm_obligations WHERE contract_id = ? AND anchor = 'end'", (contract_id,)).fetchall():
            conn.execute("UPDATE pm_deadlines SET due_date = ? WHERE obligation_id = ? AND status IN ('todo','drafting')", ((_d(new_end) + timedelta(days=o["offset_days"])).isoformat(), o["id"]))
    for o in conn.execute("SELECT id FROM pm_obligations WHERE contract_id = ?", (contract_id,)).fetchall():
        generate(conn, o["id"])
    return amend


def set_deadline_status(conn, deadline_id: int, status: str, on: str | None = None) -> bool:
    if status not in STATUSES:
        raise PMError("Unknown status")
    done = status in ("submitted", "accepted")
    with conn:
        ok = conn.execute("UPDATE pm_deadlines SET status = ?, submitted_on = CASE WHEN ? THEN coalesce(submitted_on, ?) ELSE NULL END WHERE id = ?",
                          (status, int(done), on or now_local().date().isoformat(), deadline_id)).rowcount > 0
    if ok:
        sync_core(conn)
    return ok


def confirm_mapping(conn, obligation_id: int, canon: str | None = None) -> bool:
    """She confirms a proposed mapping (optionally correcting the requirement type)."""
    if canon is not None and canon not in CANON:
        raise PMError("Unknown requirement type")
    with conn:
        return conn.execute("UPDATE pm_obligations SET confirmed = 1, canon = coalesce(?, canon) WHERE id = ?", (canon, obligation_id)).rowcount > 0


# ---------------------------------------------------------------- transfers and exchange rates
def _complete_money(currency: str, amount, chf, rate):
    """Two of amount, CHF credited and bank rate give the third; all three must agree (to the rounding of a bank)."""
    if currency == "CHF":
        a = amount if amount is not None else chf
        if a is None:
            raise PMError("Enter the amount received")
        if chf is not None and amount is not None and abs(chf - amount) > 0.5:
            raise PMError("A CHF transfer has no exchange rate: the amounts must be the same")
        return float(a), float(a), 1.0
    given = [x is not None for x in (amount, chf, rate)]
    if sum(given) < 2:
        raise PMError(f"For a transfer in {currency}, enter two of: the amount received, the CHF the bank credited, the bank's exchange rate")
    if amount is None:
        amount = chf / rate
    elif chf is None:
        chf = amount * rate
    elif rate is None:
        rate = chf / amount
    elif abs(amount * rate - chf) > 0.005 * chf + 1:
        raise PMError(f"These do not agree: {amount:,.2f} {currency} × {rate} is {amount * rate:,.2f} CHF, not {chf:,.2f}")
    if amount <= 0 or rate <= 0:
        raise PMError("Amounts and rates must be positive")
    return round(float(amount), 2), round(float(chf), 2), round(float(rate), 6)


def add_transfer(conn, contract_id: int, label: str, expected_date=None, expected_amount=None, received_date=None, received_amount=None, chf_received=None, bank_rate=None,
                 bank_ref=None, note=None) -> int:
    c = conn.execute("SELECT * FROM pm_contracts WHERE id = ?", (contract_id,)).fetchone()
    if c is None:
        raise PMError("Unknown contract")
    if c["kind"] == "amendment":
        raise PMError("Transfers belong to the contract itself, not an amendment")
    amount = chf = rate = None
    if received_date:
        amount, chf, rate = _complete_money(c["currency"], received_amount, chf_received, bank_rate)
    elif expected_amount is None and expected_date is None:
        raise PMError("Give the expected date and amount, or the receipt")
    cur = conn.execute("INSERT INTO pm_transfers (contract_id, label, expected_date, expected_amount, received_date, received_amount, chf_received, bank_rate, bank_ref, note) VALUES (?,?,?,?,?,?,?,?,?,?)",
                       (contract_id, _need(label, "A label"), expected_date, expected_amount, received_date, amount, chf, rate, bank_ref, note))
    conn.commit()
    return cur.lastrowid


def receive_transfer(conn, transfer_id: int, received_date: str, received_amount=None, chf_received=None, bank_rate=None, bank_ref=None) -> bool:
    t = conn.execute("SELECT t.*, c.currency FROM pm_transfers t JOIN pm_contracts c ON c.id = t.contract_id WHERE t.id = ?", (transfer_id,)).fetchone()
    if t is None:
        return False
    if t["received_date"]:
        raise PMError("This transfer is already recorded as received")
    amount, chf, rate = _complete_money(t["currency"], received_amount if received_amount is not None else (t["expected_amount"] if chf_received is None or bank_rate is None else None), chf_received, bank_rate)
    with conn:
        conn.execute("UPDATE pm_transfers SET received_date=?, received_amount=?, chf_received=?, bank_rate=?, bank_ref=coalesce(?, bank_ref) WHERE id=?", (received_date, amount, chf, rate, bank_ref, transfer_id))
    return True


def _transfer_view(t, today: date) -> dict:
    received = bool(t["received_date"])
    late = (not received) and t["expected_date"] and _d(t["expected_date"]) < today
    status = "received" if received else "late" if late else "expected"
    delay = (_d(t["received_date"]) - _d(t["expected_date"])).days if received and t["expected_date"] else (today - _d(t["expected_date"])).days if late else 0
    fx = None
    if received and t["currency"] != "CHF":
        fx = round(t["chf_received"] - t["received_amount"] * t["budget_rate"], 2)
    return {"id": t["id"], "contract_id": t["contract_id"], "funder": t["funder_short"], "currency": t["currency"], "label": t["label"], "expected_date": t["expected_date"],
            "expected_amount": t["expected_amount"], "received_date": t["received_date"], "received_amount": t["received_amount"], "chf_received": t["chf_received"], "bank_rate": t["bank_rate"],
            "budget_rate": t["budget_rate"], "fx_difference": fx, "status": status, "days_late": max(delay, 0), "bank_ref": t["bank_ref"], "note": t["note"]}


# ---------------------------------------------------------------- views
def _deadline_rows(conn, project_id: int, today: date) -> list[dict]:
    out = []
    for r in conn.execute("SELECT d.*, o.title AS otitle, o.canon, o.recurrence, f.short AS funder, f.role, c.kind AS ckind FROM pm_deadlines d JOIN pm_obligations o ON o.id = d.obligation_id "
                          "JOIN pm_contracts c ON c.id = o.contract_id JOIN pm_funders f ON f.id = c.funder_id WHERE c.project_id = ? ORDER BY d.due_date, d.id", (project_id,)):
        left = (_d(r["due_date"]) - today).days
        late = left < 0 and r["status"] in ("todo", "drafting")
        out.append({"id": r["id"], "obligation_id": r["obligation_id"], "title": r["otitle"], "canon": r["canon"], "funder": r["funder"], "role": r["role"], "period": r["period_label"], "due_date": r["due_date"],
                    "status": r["status"], "days_left": left, "overdue": late, "submitted_on": r["submitted_on"]})
    return out


def crunches(deadlines: list[dict], gap: int = 7, size: int = 3) -> list[dict]:
    """Stretches where several open deadlines fall within a few days of each other."""
    open_ = [d for d in deadlines if d["status"] in ("todo", "drafting")]
    groups, cur = [], []
    for d in open_:
        if cur and (_d(d["due_date"]) - _d(cur[-1]["due_date"])).days > gap:
            groups.append(cur); cur = []
        cur.append(d)
    if cur:
        groups.append(cur)
    return [{"from": g[0]["due_date"], "to": g[-1]["due_date"], "count": len(g), "items": [f"{x['funder']}: {x['title']}" for x in g]} for g in groups if len(g) >= size]


def finance(conn, project_id: int, today: date) -> dict:
    rows = conn.execute("SELECT t.*, c.currency, c.budget_rate, c.kind, f.short AS funder_short FROM pm_transfers t JOIN pm_contracts c ON c.id = t.contract_id JOIN pm_funders f ON f.id = c.funder_id "
                        "WHERE c.project_id = ? ORDER BY coalesce(t.received_date, t.expected_date), t.id", (project_id,)).fetchall()
    transfers = [_transfer_view(t, today) for t in rows]
    per = []
    for c in conn.execute("SELECT c.*, f.short AS funder FROM pm_contracts c JOIN pm_funders f ON f.id = c.funder_id WHERE c.project_id = ? AND c.kind != 'amendment' ORDER BY c.id", (project_id,)):
        ts = [t for t in transfers if t["contract_id"] == c["id"]]
        got = sum(t["received_amount"] or 0 for t in ts)
        chf = sum(t["chf_received"] or 0 for t in ts)
        rate_avg = round(chf / got, 4) if got and c["currency"] != "CHF" else (1.0 if got else None)
        per.append({"contract_id": c["id"], "funder": c["funder"], "kind": c["kind"], "currency": c["currency"], "amount": c["amount"], "budget_rate": c["budget_rate"],
                    "committed_chf_budget": round((c["amount"] or 0) * c["budget_rate"], 2), "received": round(got, 2), "outstanding": round((c["amount"] or 0) - got, 2),
                    "chf_received": round(chf, 2), "average_rate": rate_avg, "fx_difference": round(chf - got * c["budget_rate"], 2) if c["currency"] != "CHF" else 0.0})
    grants = [p for p in per if p["kind"] == "grant"]
    return {"transfers": transfers, "contracts": per,
            "totals": {"committed_chf_budget": round(sum(p["committed_chf_budget"] for p in grants), 2), "chf_received": round(sum(p["chf_received"] for p in grants), 2),
                       "fx_difference": round(sum(p["fx_difference"] for p in grants), 2), "late_transfers": sum(1 for t in transfers if t["status"] == "late"),
                       "passed_to_partners_chf_budget": round(sum(p["committed_chf_budget"] for p in per if p["kind"] == "subgrant"), 2)}}


def _obligation_view(o) -> dict:
    return {"id": o["id"], "contract_id": o["contract_id"], "funder": o["funder"], "canon": o["canon"], "canon_label": CANON[o["canon"]], "title": o["title"], "clause": o["clause"], "rule": rule_label(o),
            "format": o["format"], "language": o["language"], "detail": o["detail"], "note": o["note"], "confirmed": bool(o["confirmed"]), "source": o["source"]}


def obligations(conn, project_id: int) -> list[dict]:
    return [_obligation_view(o) for o in conn.execute("SELECT o.*, f.short AS funder FROM pm_obligations o JOIN pm_contracts c ON c.id = o.contract_id JOIN pm_funders f ON f.id = c.funder_id "
                                                     "WHERE c.project_id = ? ORDER BY o.canon, f.short, o.id", (project_id,))]


def crosswalk(conn, project_id: int) -> list[dict]:
    """For each requirement type: what each funder asks, what is the same and what differs, and a combined plan."""
    groups: dict[str, list[dict]] = {}
    for o in obligations(conn, project_id):
        groups.setdefault(o["canon"], []).append(o)
    out = []
    for canon, items in groups.items():
        funders = sorted({i["funder"] for i in items})
        diff, same = [], []
        if len(funders) > 1:
            for k, label in (("rule", "timing"), ("language", "language"), ("format", "format"), ("detail", "level of detail")):
                vals = {(i[k] or "not specified") for i in items}
                (diff if len(vals) > 1 else same).append(label)
        out.append({"canon": canon, "label": CANON[canon], "funders": funders, "items": items, "same": same, "differs": diff, "unconfirmed": sum(1 for i in items if not i["confirmed"]),
                    "plan": _plan(canon, items, funders, diff)})
    order = list(CANON)
    out.sort(key=lambda g: order.index(g["canon"]))
    return out


def _plan(canon: str, items: list[dict], funders: list[str], diff: list[str]) -> str:
    if len(funders) < 2:
        return f"Only {funders[0]} asks for this." if funders else ""
    if not diff:
        return "Identical across funders: one document can serve all."
    langs = sorted({l.strip() for i in items for l in (i["language"] or "").split(",") if l.strip()})
    best = max(items, key=lambda i: DETAIL.index(i["detail"]) if i["detail"] in DETAIL else -1)
    bits = []
    if "level of detail" in diff and best["detail"]:
        bits.append(f"write it at the {best['detail']} level ({best['funder']}'s), and derive the shorter versions")
    if "language" in diff and langs:
        bits.append("deliver in " + " and ".join(langs))
    if "format" in diff:
        bits.append("one content, separate templates")
    if "timing" in diff:
        bits.append("work to the earliest deadline")
    text = "; ".join(bits)
    return text[:1].upper() + text[1:] + "."


_RANK = lambda d: DETAIL.index(d) if d in DETAIL else -1


def translate(conn, project_id: int, from_funder: str, to_funder: str) -> dict:
    """What the work done for `from_funder` already covers for `to_funder`, requirement by requirement."""
    by = {}
    for o in conn.execute("SELECT o.*, f.short AS funder FROM pm_obligations o JOIN pm_contracts c ON c.id = o.contract_id JOIN pm_funders f ON f.id = c.funder_id WHERE c.project_id = ? AND c.kind != 'subgrant'", (project_id,)):
        by.setdefault((o["funder"], o["canon"]), []).append(o)
    rows = []
    for canon in CANON:
        want = by.get((to_funder, canon))
        if not want:
            continue
        have = by.get((from_funder, canon))
        for w in want:
            if not have:
                rows.append({"canon": canon, "label": CANON[canon], "verdict": "gap", "reasons": [f"{from_funder} does not ask for this: it has to be produced for {to_funder}."], "to": _obligation_view({**dict(w), "funder": to_funder}), "from": None})
                continue
            h = have[0]
            why = []
            if _RANK(h["detail"]) < _RANK(w["detail"]):
                why.append(f"{from_funder}'s is less detailed ({h['detail'] or 'not specified'}) than {to_funder} requires ({w['detail']}).")
            wl = {x.strip() for x in (w["language"] or "").split(",") if x.strip()}
            hl = {x.strip() for x in (h["language"] or "").split(",") if x.strip()}
            if wl and not wl <= hl:
                why.append(f"It must also be in {', '.join(sorted(wl - hl))}.")
            if (w["format"] or "") != (h["format"] or "") and w["format"]:
                why.append(f"{to_funder} wants its own template ({w['format']}).")
            if h["recurrence"] != w["recurrence"]:
                why.append(f"{from_funder} asks {RECURRENCE_WORDS[h['recurrence']]}; {to_funder} asks {RECURRENCE_WORDS[w['recurrence']]}: split or combine the periods.")
            elif h["offset_days"] > w["offset_days"]:
                why.append(f"{from_funder}'s deadline ({h['offset_days']} days) is later than {to_funder}'s ({w['offset_days']} days): deliver earlier.")
            rows.append({"canon": canon, "label": CANON[canon], "verdict": "partly" if why else "covers", "reasons": why or ["The same piece of work satisfies both."],
                         "to": _obligation_view({**dict(w), "funder": to_funder}), "from": _obligation_view({**dict(h), "funder": from_funder})})
    n = lambda v: sum(1 for r in rows if r["verdict"] == v)
    return {"from": from_funder, "to": to_funder, "rows": rows, "summary": {"covers": n("covers"), "partly": n("partly"), "gap": n("gap")}}


def project_overview(conn, today: date | None = None) -> list[dict]:
    today = today or now_local().date()
    sync_core(conn, today)
    out = []
    for p in conn.execute("SELECT * FROM pm_projects ORDER BY status = 'closed', code"):
        fin = finance(conn, p["id"], today)
        dls = _deadline_rows(conn, p["id"], today)
        nxt = next((d for d in dls if d["status"] in ("todo", "drafting")), None)
        funders = [r["short"] for r in conn.execute("SELECT DISTINCT f.short FROM pm_contracts c JOIN pm_funders f ON f.id = c.funder_id WHERE c.project_id = ? AND c.kind = 'grant' ORDER BY f.short", (p["id"],))]
        out.append({"id": p["id"], "code": p["code"], "name": p["name"], "status": p["status"], "start_date": p["start_date"], "end_date": p["end_date"], "demo": bool(p["demo"]), "funders": funders,
                    "committed_chf": fin["totals"]["committed_chf_budget"], "received_chf": fin["totals"]["chf_received"], "late_transfers": fin["totals"]["late_transfers"],
                    "overdue": sum(1 for d in dls if d["overdue"]), "next": nxt, "crunches": len(crunches(dls))})
    return out


def project_detail(conn, project_id: int, today: date | None = None) -> dict | None:
    today = today or now_local().date()
    p = conn.execute("SELECT * FROM pm_projects WHERE id = ?", (project_id,)).fetchone()
    if p is None:
        return None
    sync_core(conn, today)
    contracts = []
    for c in conn.execute("SELECT c.*, f.name AS funder_name, f.short AS funder, f.role FROM pm_contracts c JOIN pm_funders f ON f.id = c.funder_id WHERE c.project_id = ? ORDER BY c.parent_id IS NOT NULL, c.id", (project_id,)):
        contracts.append({"id": c["id"], "parent_id": c["parent_id"], "kind": c["kind"], "title": c["title"], "funder": c["funder"], "funder_name": c["funder_name"], "role": c["role"], "signed_date": c["signed_date"],
                          "start_date": c["start_date"], "end_date": c["end_date"], "amount": c["amount"], "currency": c["currency"], "budget_rate": c["budget_rate"], "file_path": c["file_path"],
                          "file_hash": (c["file_hash"] or "")[:12] or None, "status": c["status"], "summary": c["summary"]})
    dls = _deadline_rows(conn, project_id, today)
    return {"project": {k: p[k] for k in ("id", "code", "name", "status", "start_date", "end_date", "lead", "summary")} | {"demo": bool(p["demo"])},
            "contracts": contracts, "obligations": obligations(conn, project_id), "deadlines": dls, "crunches": crunches(dls), "finance": finance(conn, project_id, today),
            "crosswalk": crosswalk(conn, project_id), "funders": sorted({c["funder"] for c in contracts if c["kind"] == "grant"}), "canon": CANON}


def funders(conn) -> list[dict]:
    return [dict(r) for r in conn.execute("SELECT * FROM pm_funders ORDER BY role, name")]


# ---------------------------------------------------------------- feeding Today
def sync_core(conn, today: date | None = None, horizon_days: int = 150) -> int:
    """Put open reporting deadlines (due within `horizon_days`) on the core deadlines table, so they show on the Today lake; close those that were submitted or accepted."""
    today = today or now_local().date()
    horizon = (today + timedelta(days=horizon_days)).isoformat()
    n = 0
    with conn:
        for r in conn.execute("SELECT d.id, d.due_date, d.status, d.period_label, o.title, o.canon, f.short, p.code FROM pm_deadlines d JOIN pm_obligations o ON o.id = d.obligation_id JOIN pm_contracts c ON c.id = o.contract_id "
                              "JOIN pm_funders f ON f.id = c.funder_id JOIN pm_projects p ON p.id = c.project_id").fetchall():
            ref = f"pm:{r['id']}"
            if r["status"] in ("submitted", "accepted"):
                conn.execute("UPDATE deadlines SET status='done', done_at=coalesce(done_at, datetime('now')) WHERE source='pm' AND source_ref=? AND status='open'", (ref,))
                continue
            if r["due_date"] > horizon:
                continue
            title = f"{r['short']}: {r['title']} ({r['period_label']})"[:160]
            conn.execute("INSERT INTO deadlines (title, due_date, kind, importance, project_code, status, source, source_ref, sensitivity) VALUES (?,?,'reporting',?,?, 'open','pm',?, 'S2') "
                         "ON CONFLICT (source, source_ref) DO UPDATE SET title=excluded.title, due_date=excluded.due_date, importance=excluded.importance, updated_at=datetime('now') WHERE deadlines.status='open'",
                         (title, r["due_date"], "major" if r["canon"] in ("financial_report", "narrative_report", "milestone_report", "audit") else "normal", r["code"], ref))
            n += 1
    return n
