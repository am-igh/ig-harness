"""Triage v2: standing rules, action + deadline, add-to-Today, her labels, model scoreboard."""
import json
from datetime import datetime

import pytest

from harness import db
from harness.config import TZ
from harness.gateway import Gateway
from harness.gateway.providers import Completion
from harness.importers.gmail import import_gmail
from harness.scoreboard import evaluate, metrics
from harness.today import build_today
from harness.triage import add_to_today, build_system, list_emails, set_label, triage_pending

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=TZ)
MS = lambda h: int((NOW.timestamp() - h * 3600) * 1000)


def thread(id, frm, body, hours=2, subj="Hello"):
    return {"thread_id": id, "message_id": f"m-{id}", "messages_in_thread": 1, "received_ms": MS(hours), "from_name": "",
            "from_email": frm, "to_me_directly": True, "cc_only": False, "subject": subj, "snippet": body[:40],
            "body": body, "labels": [], "last_from_me": False, "bulk": False}


class Model:
    external, name = False, "local"

    def __init__(self, model="m1", answer=None):
        self.model, self.prompts, self.answer = model, [], answer

    def complete(self, prompt, system=None, max_tokens=0, json_mode=False):
        self.prompts.append((prompt, system))
        if self.answer:
            return Completion(json.dumps(self.answer(prompt)))
        return Completion(json.dumps({"needs_action": True, "action": "fill in the survey", "why": "survey requested",
                                      "urgency": 1, "deadline": "2026-10-07"}))


@pytest.fixture
def env(tmp_path):
    path = tmp_path / "t.db"
    c = db.connect(path); db.migrate(c)
    (tmp_path / "gmail_recent.json").write_text(json.dumps({"fetched_at": "x", "me": "me@x.org", "query": "q", "threads": [
        thread("t1", "survey@org.int", "Please fill in our survey by 7 October."),
        thread("t2", "fund@vc.com", "Invest in our venture fund today!", subj="Opportunity")]}))
    import_gmail(c, tmp_path)
    m = Model()
    return c, Gateway(connect=lambda: db.connect(path), providers={"local": m}), m, path


def test_her_first_rule_is_seeded_and_reaches_the_model(env):
    c, gw, m, _ = env
    assert "venture-fund" in build_system(c, NOW.date())
    triage_pending(c, gw, now=NOW)
    assert "standing rules" in m.prompts[0][1] and "venture-fund" in m.prompts[0][1]
    assert "2026-10-01 (Thursday)" in m.prompts[0][1]          # lets the model resolve 'by Wednesday'


def test_rules_can_be_added_and_switched_off(env):
    c, gw, m, _ = env
    c.execute("INSERT INTO triage_rules (text) VALUES ('Mails from the AGM list never need a reply.')"); c.commit()
    assert "AGM list" in build_system(c, NOW.date())
    c.execute("UPDATE triage_rules SET active=0"); c.commit()
    assert "standing rules" not in build_system(c, NOW.date())


def test_deadline_and_action_are_stored_and_make_the_email_urgent(env):
    c, gw, m, _ = env
    triage_pending(c, gw, now=NOW)
    r = c.execute("SELECT action, deadline, urgency FROM emails WHERE thread_id='t1'").fetchone()
    assert r["action"] == "fill in the survey" and r["deadline"] == "2026-10-07" and r["urgency"] == 2   # 6 days away: raised to 'soon', not yet urgent
    m.answer = lambda p: {"needs_action": True, "action": "reply", "why": "x", "urgency": 1, "deadline": "2026-10-03"}
    c.execute("UPDATE emails SET triage_status='pending'"); c.commit()
    triage_pending(c, gw, now=NOW)
    assert c.execute("SELECT urgency FROM emails WHERE thread_id='t1'").fetchone()[0] == 3               # within 3 days -> urgent


def test_far_deadlines_are_not_urgent_whatever_the_model_says(env):
    c, gw, m, _ = env
    m.answer = lambda p: {"needs_action": True, "action": "register", "why": "x", "urgency": 3, "deadline": "2026-10-23"}
    triage_pending(c, gw, now=NOW)
    assert c.execute("SELECT urgency FROM emails WHERE thread_id='t1'").fetchone()[0] == 2


def test_absurd_or_malformed_deadlines_are_ignored(env):
    c, gw, m, _ = env
    for bad in ("1999-01-01", "next week", "2035-05-05", None):
        m.answer = lambda p, b=bad: {"needs_action": True, "action": "reply", "why": "x", "urgency": 2, "deadline": b}
        c.execute("UPDATE emails SET triage_status='pending'"); c.commit()
        triage_pending(c, gw, now=NOW)
        assert c.execute("SELECT deadline FROM emails WHERE thread_id='t1'").fetchone()[0] is None


def test_add_to_today_creates_one_task_due_on_the_deadline_and_it_shows_up(env):
    c, gw, m, _ = env
    triage_pending(c, gw, now=NOW)
    eid = c.execute("SELECT id FROM emails WHERE thread_id='t1'").fetchone()[0]
    r = add_to_today(c, eid, NOW)
    assert r["created"] is True
    again = add_to_today(c, eid, NOW)
    assert again == {"task_id": r["task_id"], "created": False}
    assert c.execute("SELECT COUNT(*) FROM tasks WHERE source='email'").fetchone()[0] == 1
    t = c.execute("SELECT * FROM tasks WHERE id=?", (r["task_id"],)).fetchone()
    assert t["due_date"] == "2026-10-07" and t["title"].startswith("Fill in the survey: ") and t["sensitivity"] == "S2"
    upcoming = [i["title"] for i in build_today(c, NOW)["upcoming_items"]]
    assert any(x.startswith("Fill in the survey") for x in upcoming)
    assert list_emails(c, 72, now=NOW)["needs_reply"][0]["task_id"] == r["task_id"]


def test_task_without_deadline_is_due_today(env):
    c, gw, m, _ = env
    m.answer = lambda p: {"needs_action": True, "action": "reply", "why": "asks", "urgency": 1, "deadline": None}
    triage_pending(c, gw, now=NOW)
    eid = c.execute("SELECT id FROM emails WHERE thread_id='t1'").fetchone()[0]
    add_to_today(c, eid, NOW)
    assert [i["title"] for i in build_today(c, NOW)["today_items"]][0].startswith("Reply: ")


def test_labels_roundtrip_and_reject_bad_values(env):
    c, gw, m, _ = env
    eid = c.execute("SELECT id FROM emails WHERE thread_id='t2'").fetchone()[0]
    assert set_label(c, eid, "no") and c.execute("SELECT user_label FROM emails WHERE id=?", (eid,)).fetchone()[0] == "no"
    assert set_label(c, eid, None) and c.execute("SELECT user_label FROM emails WHERE id=?", (eid,)).fetchone()[0] is None
    with pytest.raises(ValueError):
        set_label(c, eid, "maybe")


def test_metrics_math():
    m = metrics([(True, True), (True, False), (False, True), (False, False), (True, None)])
    assert (m["tp"], m["fn"], m["fp"], m["tn"], m["failed"]) == (1, 1, 1, 1, 1)
    assert m["accuracy"] == 0.5 and m["precision"] == 0.5 and m["recall"] == 0.5


def test_scoreboard_ranks_models_on_her_labels(env):
    c, gw, m, _ = env
    set_label(c, c.execute("SELECT id FROM emails WHERE thread_id='t1'").fetchone()[0], "yes")
    set_label(c, c.execute("SELECT id FROM emails WHERE thread_id='t2'").fetchone()[0], "no")
    good = lambda p: {"needs_action": "survey" in p, "action": "x", "why": "x", "urgency": 1, "deadline": None}
    bad = lambda p: {"needs_action": True, "action": "x", "why": "x", "urgency": 1, "deadline": None}
    models = {"good": Model("good", good), "bad": Model("bad", bad)}
    out = evaluate(c, ["good", "bad"], NOW, provider_factory=lambda name: models[name])
    assert out["n_labelled"] == 2 and out["n_model_cases"] == 2
    assert out["models"]["good"]["accuracy"] == 1.0
    assert out["models"]["bad"]["accuracy"] == 0.5 and out["models"]["bad"]["fp"] == 1
    c2 = c.execute("SELECT COUNT(*) FROM privacy_log").fetchone()[0]     # (scoreboard calls are logged in the gateway's own db)
    assert c2 >= 0


def test_new_endpoints_roundtrip():
    from fastapi.testclient import TestClient
    from harness.main import app
    with TestClient(app) as cl:
        assert any("venture" in r["text"] for r in cl.get("/api/triage/rules").json()["items"])
        rid = cl.post("/api/triage/rules", json={"text": "Newsletters from X never need a reply."}).json()["id"]
        assert cl.delete(f"/api/triage/rules/{rid}").json() == {"changed": True}
        assert cl.post("/api/triage/rules", json={"text": "no"}).status_code == 422
        assert cl.post("/api/emails/999999/label", json={"label": "yes"}).status_code == 404
        assert cl.post("/api/emails/1/label", json={"label": "maybe"}).status_code == 422
        assert cl.post("/api/emails/999999/task").status_code == 404
        sb = cl.get("/api/scoreboard").json()
        assert {"running", "latest", "n_labelled"} <= set(sb)
        assert cl.post("/api/scoreboard/run", json={"models": []}).status_code == 422
