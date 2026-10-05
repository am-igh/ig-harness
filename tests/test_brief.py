"""The harness's morning brief: sections, ordering, clashes, masking of personal items, the text version and the stored copy. Synthetic data only."""
import json
from datetime import date, datetime

import pytest

from harness import brief, db
from harness.config import TZ

NOW = datetime(2026, 10, 6, 8, 0, tzinfo=TZ)          # a Tuesday


@pytest.fixture
def c(tmp_path):
    c = db.connect(tmp_path / "t.db"); db.migrate(c)
    c.executemany("INSERT INTO project_codes (code, name, domain, kind) VALUES (?,?,?,?)", [("TK", "Toolkit", "W", "project"), ("IGCSC", "IG cyber", "W", "thread")])
    c.execute("INSERT INTO people (slug, name, org, space) VALUES ('regula-lenz', 'Regula Lenz', 'IG-CSC', 'work')")
    t = lambda title, due, code=None, space="work", status="open": c.execute("INSERT INTO tasks (title, due_date, project_code, space, status, source, source_ref) VALUES (?,?,?,?,?,?,?)", (title, due, code, space, status, "suivi", title))
    t("Overdue soft task", "2026-10-01"); t("Task due today", "2026-10-06", "TK"); t("Task next week", "2026-10-09"); t("Undated task", None); t("Personal passport", "2026-10-06", None, "personal"); t("Very overdue", "2026-09-10")
    c.execute("INSERT INTO deadlines (title, due_date, importance, kind, project_code, source, source_ref) VALUES ('Workshop proposal', '2026-10-06', 'major', 'deadline', 'IGCSC', 'suivi', 'd1')")
    c.execute("INSERT INTO deadlines (title, due_date, importance, kind, project_code, source, source_ref) VALUES ('ASF report', '2026-10-15', 'major', 'deadline', 'TK', 'suivi', 'd2')")
    c.execute("INSERT INTO waiting_on (description, person, since_date, space) VALUES ('2023 bordereaux chronology', 'regula-lenz', '2026-09-08', 'work')")
    c.execute("INSERT INTO waiting_on (description, person, since_date, space) VALUES ('Fresh thing', 'regula-lenz', '2026-10-04', 'work')")
    ev = lambda title, s, e, ad=0, loc=None, space="work": c.execute("INSERT INTO calendar_events (title, start, end, all_day, status, space, location, source, source_ref) VALUES (?,?,?,?,?,?,?,?,?)", (title, s, e, ad, "confirmed", space, loc, "g", title))
    ev("Admin block A", "2026-10-06T09:00:00+02:00", "2026-10-06T09:45:00+02:00"); ev("Admin block B", "2026-10-06T09:30:00+02:00", "2026-10-06T10:00:00+02:00")
    ev("Stand-up with Daniel", "2026-10-06T14:00:00+02:00", "2026-10-06T15:00:00+02:00", loc="Zoom"); ev("Private appointment", "2026-10-06T16:00:00+02:00", "2026-10-06T17:00:00+02:00", space="personal")
    ev("Deadline marker", "2026-10-06", "2026-10-07", ad=1); ev("Tomorrow call", "2026-10-07T10:00:00+02:00", "2026-10-07T11:00:00+02:00"); ev("Yesterday thing", "2026-10-05T10:00:00+02:00", "2026-10-05T11:00:00+02:00")
    c.execute("INSERT INTO emails (thread_id, message_id, from_name, from_email, subject, received_at, triage_status, needs_reply, why, action, deadline, urgency, score, person_slug, direct) VALUES ('t1','m1','Regula Lenz','r@x.org','Founding assembly slot','2026-10-05T18:00:00+02:00','done',1,'needs your slot and names','reply','2026-10-07',3,9,'regula-lenz',1)")
    c.execute("INSERT INTO emails (thread_id, message_id, from_name, from_email, subject, received_at, triage_status, needs_reply, why, urgency, score, direct) VALUES ('t2','m2','Someone','s@x.org','Newsletter-ish','2026-10-05T10:00:00+02:00','done',0,'no',1,1,0)")
    c.commit()
    return c


def test_sections_are_built_from_the_harnesss_own_data(c):
    b = brief.build(c, NOW)
    assert b["title"] == "Tuesday 6 October 2026"
    cal = b["calendar"]
    assert [e["title"] for e in cal["today"]] == ["Deadline marker", "Admin block A", "Admin block B", "Stand-up with Daniel", "Personal event"]       # all-day first, then by time; yesterday's is out
    assert cal["today"][3] == {"title": "Stand-up with Daniel", "all_day": False, "start": "14:00", "end": "15:00", "place": "Zoom", "masked": False} and cal["today"][4]["masked"] and cal["today"][4]["place"] is None
    assert cal["clashes"] == [("Admin block A", "Admin block B")] and [e["title"] for e in cal["tomorrow"]] == ["Tomorrow call"]
    assert [m["subject"] for m in b["mail"]] == ["Founding assembly slot"] and b["mail"][0]["from"] == "Regula Lenz" and b["mail"][0]["org"] == "IG-CSC"
    s = b["suivi"]
    assert [i["title"] for i in s["due_today"]] == ["Workshop proposal", "Task due today"]                                  # major first
    assert [i["title"] for i in s["overdue"]] == ["Very overdue", "Overdue soft task"] and [i["title"] for i in s["next7"]] == ["Task next week"]
    assert s["waiting"] == [{"what": "2023 bordereaux chronology", "who": "Regula Lenz", "days": 28}]                         # only items older than 7 days
    assert [i["title"] for i in s["checks"]["overdue_over_14"]] == ["Very overdue"] and s["checks"]["undated_tasks"] == 1
    assert [m["title"] for m in s["checks"]["major_within_14"]] == ["Workshop proposal", "ASF report"]


def test_personal_items_are_masked_everywhere_in_the_brief_and_its_text(c):
    b = brief.build(c, NOW)
    text = brief.render_text(b)
    assert "passport" not in json.dumps(b).lower() and "passport" not in text.lower() and "Private appointment" not in text and "Private appointment" not in json.dumps(b)
    assert b["suivi"]["personal"] == [{"title": "Personal task", "due": "2026-10-06", "days_overdue": 0}] and "f. Personal — Personal task (2026-10-06)" in text


def test_the_attention_list_by_rules_picks_what_is_due_clashing_or_wanted_soon(c):
    b = brief.build(c, NOW)
    titles = [a["title"] for a in b["attention"]]
    assert b["attention_source"] == "rules" and 1 <= len(titles) <= 4
    assert "Workshop proposal" in titles[0] and any("clash" in t.lower() for t in titles) and any("Regula Lenz" in t for t in titles)
    assert b["attention"][0]["why"] == "major item, due today."


def test_the_text_follows_her_brief_sections_in_order_and_says_what_it_leaves_out(c):
    text = brief.render_text(brief.build(c, NOW))
    heads = [h for h in ("1. CALENDAR", "2. IMPORTANT MAIL", "3. SUIVI", "a. Due today or overdue", "b. Due in the next 7 days", "c. Waiting on", "d. Checks", "e. Relationship nudges", "f. Personal",
                         "4. TO CONFIRM", "5. NEEDS YOUR ATTENTION", "ALSO IN THE HARNESS") if h in text]
    assert len(heads) == 12 and text.index("1. CALENDAR") < text.index("2. IMPORTANT MAIL") < text.index("3. SUIVI") < text.index("5. NEEDS YOUR ATTENTION")
    assert "CLASH: “Admin block A” overlaps “Admin block B”" in text and "14:00-15:00 — Stand-up with Daniel (Zoom)" in text and "All day — Deadline marker" in text
    assert "not part of this brief" in text and "- (major, IGCSC) Workshop proposal" in text and "Overdue soft task — 5d overdue" in text.replace("(soft) ", "") or "5d overdue" in text


def test_events_hours_and_waiting_counts_appear_in_the_harness_part(c):
    c.execute("INSERT INTO events (dedupe_key, title, start, end, all_day, derived_status, source_kind, geneva) VALUES ('k','Summit', '2026-10-09', '2026-10-10', 1, 'confirmed', 'calendar', 1)")
    c.execute("INSERT INTO hours (row_key, date, project, hours, evidence, entered_on) VALUES ('h','2026-10-05','TK',1.5,'e','2026-10-05')"); c.commit()
    b = brief.build(c, NOW)
    assert [e["title"] for e in b["events_week"]] == ["Summit"] and b["harness"]["hours_week"] == 1.5 and "2026-10-06" in b["harness"]["hours_days_without"]
    assert "EVENTS THIS WEEK: 10-09 Summit (you are in)" in brief.render_text(b)


def test_an_empty_database_still_gives_a_sensible_brief():
    import tempfile, pathlib
    d = pathlib.Path(tempfile.mkdtemp()); c = db.connect(d / "e.db"); db.migrate(c)
    text = brief.render_text(brief.build(c, NOW))
    assert "Nothing in the calendar today." in text and "Nothing stands out." in text and "- Nothing needs a reply." in text


def test_a_saved_brief_is_kept_per_day_and_replaced_when_rebuilt(c):
    b = brief.build(c, NOW)
    brief.save(c, b)
    assert brief.latest(c, "2026-10-06")["data"]["title"] == "Tuesday 6 October 2026" and brief.latest(c)["draft_status"] == "none"
    brief.save(c, {**b, "attention": [{"title": "X", "why": "y"}]})
    assert c.execute("SELECT COUNT(*) FROM briefs").fetchone()[0] == 1 and "1. X y" in brief.latest(c)["text"]


def test_api(c):
    from fastapi.testclient import TestClient
    from harness.main import app
    with TestClient(app) as cl:
        r = cl.get("/api/brief").json()
        assert r["data"]["title"] and "1. CALENDAR" in r["text"] and cl.get("/api/brief?fresh=true").status_code == 200


# ---- section 5 by the local model
class _R:
    def __init__(self, text, ok=True): self.text, self.ok, self.model, self.reason = text, ok, "m1", "down"


class _G:
    def __init__(self, text, ok=True): self.r, self.prompt = _R(text, ok), None
    def complete(self, prompt, **kw): self.prompt, self.kw = prompt, kw; return self.r


def test_the_model_only_picks_among_our_facts_and_its_reasons_are_kept(c):
    from harness import brief_ai
    b = brief.build(c, NOW)
    fs = brief_ai.facts(b)
    assert fs[0]["title"] == "Workshop proposal" and not any("passport" in json.dumps(f).lower() or "Private" in json.dumps(f) for f in fs)
    g = _G(json.dumps({"picks": [{"n": 2, "why": "Due today."}, {"n": 99, "why": "invented"}, {"n": 2, "why": "dup"}, {"n": 1, "why": "Major, and the clock is ticking."}]}))
    out = brief_ai.write_attention(b, g)
    assert [a["title"] for a in out["attention"]] == [fs[1]["title"], fs[0]["title"]] and out["attention_source"] == "model"
    assert g.kw["job"] == "brief_write" and "Today is Tuesday 6 October 2026" in g.prompt
    assert "(written by your local model" in brief.render_text(out)


def test_when_the_model_is_down_or_unclear_the_rules_list_stays(c):
    from harness import brief_ai
    b = brief.build(c, NOW)
    for g in (_G("", ok=False), _G("not json"), _G('{"picks": []}'), _G('{"picks": [{"n": 500}]}')):
        out = brief_ai.write_attention(b, g)
        assert out["attention"] == b["attention"] and out["attention_source"] == "rules"


def test_the_brief_job_is_local_only():
    from harness.gateway.settings import JOBS, SelectionRefused, set_selection
    assert JOBS["brief_write"]["tier"] == "S2" or str(JOBS["brief_write"]["tier"]).endswith("S2")
    with pytest.raises(SelectionRefused):
        set_selection(None, "brief_write", "anthropic", "x", {"anthropic"})
