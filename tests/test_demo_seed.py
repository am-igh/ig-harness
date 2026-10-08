"""The AURORA demo data: refuses to run outside the demo instance, is invented throughout, and tells a coherent, complicated story."""
import os
from datetime import date, timedelta
from pathlib import Path

import pytest

from harness import db, demo_seed, pm

TODAY = date(2026, 10, 14)


@pytest.fixture
def c(tmp_path, monkeypatch):
    monkeypatch.setenv("IG_DEMO", "1")
    c = db.connect(tmp_path / "t.db"); db.migrate(c)
    return c


def test_it_refuses_outside_the_demo_instance_and_on_real_looking_data(tmp_path, monkeypatch):
    c = db.connect(tmp_path / "t.db"); db.migrate(c)
    monkeypatch.delenv("IG_DEMO", raising=False)
    with pytest.raises(demo_seed.NotDemo):
        demo_seed.seed(c, TODAY)
    monkeypatch.setenv("IG_DEMO", "1")
    c.execute("INSERT INTO emails (thread_id, message_id, from_email, received_at) VALUES ('t','m','someone@real-org.org','2026-10-01T10:00:00+02:00')"); c.commit()
    with pytest.raises(demo_seed.NotDemo, match="not demo data"):
        demo_seed.seed(c, TODAY)
    assert c.execute("SELECT COUNT(*) FROM pm_projects").fetchone()[0] == 0
    c2 = db.connect(tmp_path / "u.db"); db.migrate(c2)
    pm.add_project(c2, "REAL", "A real one")
    with pytest.raises(demo_seed.NotDemo):
        demo_seed.seed(c2, TODAY)


def test_the_story_is_complicated_and_adds_up(c):
    assert demo_seed.seed(c, TODAY)["seeded"] and not demo_seed.seed(c, TODAY)["seeded"]               # a second run changes nothing
    d = pm.project_detail(c, c.execute("SELECT id FROM pm_projects WHERE code='AURORA'").fetchone()[0], TODAY)
    assert d["project"]["demo"] and len(d["funders"]) == 4
    assert {x["currency"] for x in d["contracts"] if x["kind"] == "grant"} == {"CHF", "EUR", "USD", "GBP"}
    assert sum(1 for x in d["contracts"] if x["kind"] == "subgrant") == 2 and sum(1 for x in d["contracts"] if x["kind"] == "amendment") == 1
    nda = next(x for x in d["contracts"] if x["funder"] == "NDA" and x["kind"] == "grant")
    assert nda["end_date"] == "2029-06-30" and nda["status"] == "amended"
    fin = d["finance"]
    assert fin["totals"]["late_transfers"] == 1 and fin["totals"]["chf_received"] > 0 and fin["totals"]["fx_difference"] != 0
    assert fin["totals"]["committed_chf_budget"] == round(600000 + 450000 * 0.94 + 380000 * 0.88 + 200000 * 1.10, 2)
    late = next(t for t in fin["transfers"] if t["status"] == "late")
    assert late["funder"] == "PDFF" and "results report" in late["note"]
    nda_f = next(x for x in fin["contracts"] if x["funder"] == "NDA" and x["kind"] == "grant")
    assert nda_f["received"] == 300000.0 and nda_f["chf_received"] == round(150000 * 0.9412 + 150000 * 0.9318, 2) and nda_f["fx_difference"] < 0
    assert len(d["crunches"]) >= 1 and d["crunches"][0]["count"] >= 3                                   # several reports fall due in the same fortnight
    assert any(g["canon"] == "narrative_report" and len(g["funders"]) >= 3 and "timing" in g["differs"] for g in d["crosswalk"])
    assert sum(g["unconfirmed"] for g in d["crosswalk"]) >= 3                                          # proposed mappings waiting for her confirmation
    t = pm.translate(c, d["project"]["id"], "NDA", "HDTF")
    assert t["summary"]["partly"] >= 1 and t["summary"]["gap"] >= 1


def test_statuses_follow_the_date_and_the_core_deadlines_feed_today(c):
    demo_seed.seed(c, TODAY)
    statuses = {r["status"] for r in c.execute("SELECT status FROM pm_deadlines")}
    assert {"accepted", "submitted", "drafting", "todo"} <= statuses
    assert c.execute("SELECT COUNT(*) FROM deadlines WHERE source='pm' AND status='open'").fetchone()[0] >= 5
    assert c.execute("SELECT COUNT(*) FROM deadlines WHERE source='pm' AND status='done'").fetchone()[0] == 0
    assert c.execute("SELECT COUNT(*) FROM tasks WHERE source='demo'").fetchone()[0] == 4 and c.execute("SELECT COUNT(*) FROM emails").fetchone()[0] == 14


def test_everything_is_invented(c):
    demo_seed.seed(c, TODAY)
    addrs = [r[0] for r in c.execute("SELECT email FROM people") ] + [r[0] for r in c.execute("SELECT from_email FROM emails")] + [r[0] for r in c.execute("SELECT value FROM draft_settings WHERE key='my_address'")]
    assert addrs and all(a.endswith(".example") for a in addrs)
    assert all((r[0] or "").startswith("Contracts/AURORA/") for r in c.execute("SELECT file_path FROM pm_contracts"))


def test_the_demo_instance_cannot_see_real_data():
    text = (Path(__file__).resolve().parent.parent / "docker-compose.demo.yml").read_text()
    code = "\n".join(ln for ln in text.splitlines() if not ln.strip().startswith("#"))
    assert "IG-Harness-Demo-data" in code and "IG-Harness-data" not in code and 'IG_DEMO: "1"' in code
    for forbidden in ("SUIVI_DIR", "PROJETS_DIR", "SCAN_INBOX_DIR", "AUDIT_YEAR_DIR", "AUDIT_TOOLS_DIR", "Tresors", "Scan-Inbox", "Backups"):
        assert forbidden not in code, forbidden
    assert code.count("/data") >= 2                                                                   # api and worker both get the demo folder


def test_the_invented_mail_is_varied_and_shows_off_the_features(c):
    from datetime import datetime
    from harness import chat, replies
    from harness.config import TZ
    demo_seed.seed(c, TODAY)
    rows = c.execute("SELECT subject, triage_status, needs_reply, last_from_me, bulk, body FROM emails").fetchall()
    assert sum(1 for r in rows if r["needs_reply"]) >= 8 and any(r["triage_status"] == "skipped" for r in rows) and any(r["last_from_me"] for r in rows) and any(r["bulk"] for r in rows)
    assert any("journée" in r["subject"] for r in rows) and all(len(r["body"]) > 60 for r in rows)                  # a French one, and real-looking bodies
    now = datetime(2026, 10, 14, 9, 0, tzinfo=TZ)
    hits = replies.find(c, datetime.fromtimestamp(datetime.now(TZ).timestamp(), TZ), hours=24 * 30)
    assert any("Hana Petrov" in r["reasons"][0] for r in hits)                                                       # a reply on an open item that asks for nothing


def test_the_invented_events_cover_each_status(c):
    demo_seed.seed(c, TODAY)
    st = {r["derived_status"] for r in c.execute("SELECT derived_status FROM events WHERE source_kind = 'demo'")}
    assert {"confirmed", "tentative", "invited", "none"} <= st
    assert c.execute("SELECT COUNT(*) FROM events WHERE source_kind = 'demo' AND geneva = 1").fetchone()[0] >= 1 and c.execute("SELECT COUNT(*) FROM events WHERE source_kind = 'demo' AND geneva = 0").fetchone()[0] >= 2
