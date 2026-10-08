"""Project and contract management rules: deadline generation, amendments, transfers and exchange rates, the crosswalk and translation. Synthetic funders only."""
from datetime import date

import pytest

from harness import db, pm

TODAY = date(2026, 10, 14)


@pytest.fixture
def c(tmp_path):
    c = db.connect(tmp_path / "t.db"); db.migrate(c)
    return c


@pytest.fixture
def proj(c):
    p = pm.add_project(c, "demo-x", "Demo X", "2026-01-01", "2027-12-31")
    a = pm.add_funder(c, "Alpha Fund", "Alpha", currency="EUR")
    b = pm.add_funder(c, "Beta Trust", "Beta", currency="CHF")
    ca = pm.add_contract(c, p, a, "Alpha grant", amount=100000, budget_rate=0.94, start_date="2026-01-01", end_date="2027-12-31")
    cb = pm.add_contract(c, p, b, "Beta grant", amount=50000, start_date="2026-01-01", end_date="2027-12-31")
    return {"p": p, "a": a, "b": b, "ca": ca, "cb": cb}


def test_dates_and_periods():
    assert pm.add_months(date(2026, 1, 31), 1) == date(2026, 2, 28) and pm.add_months(date(2026, 11, 15), 3) == date(2027, 2, 15)
    ps = pm.periods(date(2026, 1, 1), date(2026, 12, 31), "quarterly")
    assert [(a.isoformat(), b.isoformat()) for _, a, b in ps] == [("2026-01-01", "2026-03-31"), ("2026-04-01", "2026-06-30"), ("2026-07-01", "2026-09-30"), ("2026-10-01", "2026-12-31")]
    assert len(pm.periods(date(2026, 1, 1), date(2027, 12, 31), "semiannual")) == 4 and len(pm.periods(date(2026, 1, 1), date(2028, 12, 31), "annual")) == 3


def test_a_repeating_obligation_generates_a_deadline_per_period(c, proj):
    o = pm.add_obligation(c, proj["ca"], "financial_report", "Quarterly financial report", recurrence="quarterly", offset_days=30, language="en", detail="detailed")
    rows = c.execute("SELECT period_label, due_date FROM pm_deadlines WHERE obligation_id = ? ORDER BY due_date", (o,)).fetchall()
    assert len(rows) == 8 and rows[0]["due_date"] == "2026-04-30" and rows[-1]["due_date"] == "2028-01-30"
    assert pm.generate(c, o) == 0                                                           # idempotent
    f = pm.add_obligation(c, proj["cb"], "narrative_report", "Final narrative report", anchor="end", offset_days=60, recurrence="once")
    assert c.execute("SELECT due_date FROM pm_deadlines WHERE obligation_id = ?", (f,)).fetchone()[0] == "2028-02-29"
    m = pm.add_obligation(c, proj["cb"], "milestone_report", "Milestone 1", anchor="fixed", fixed_date="2026-11-05", recurrence="once")
    assert c.execute("SELECT due_date FROM pm_deadlines WHERE obligation_id = ?", (m,)).fetchone()[0] == "2026-11-05"
    r = pm.add_obligation(c, proj["ca"], "overhead", "Overhead cap 7%", anchor="none", recurrence="none")
    assert c.execute("SELECT COUNT(*) FROM pm_deadlines WHERE obligation_id = ?", (r,)).fetchone()[0] == 0     # a rule, not a report


def test_a_no_cost_extension_adds_periods_and_moves_the_final_report(c, proj):
    q = pm.add_obligation(c, proj["ca"], "financial_report", "Quarterly", recurrence="quarterly", offset_days=30)
    fin = pm.add_obligation(c, proj["ca"], "narrative_report", "Final report", anchor="end", offset_days=60, recurrence="once")
    pm.set_deadline_status(c, c.execute("SELECT id FROM pm_deadlines WHERE obligation_id = ? ORDER BY due_date LIMIT 1", (q,)).fetchone()[0], "accepted")
    before = c.execute("SELECT COUNT(*) FROM pm_deadlines WHERE obligation_id = ?", (q,)).fetchone()[0]
    amend = pm.extend_contract(c, proj["ca"], "2028-06-30", "No-cost extension 1", signed_date="2026-09-10")
    assert c.execute("SELECT kind, parent_id FROM pm_contracts WHERE id = ?", (amend,)).fetchone()[:] == ("amendment", proj["ca"])
    assert c.execute("SELECT end_date, status FROM pm_contracts WHERE id = ?", (proj["ca"],)).fetchone()[:] == ("2028-06-30", "amended")
    assert c.execute("SELECT COUNT(*) FROM pm_deadlines WHERE obligation_id = ?", (q,)).fetchone()[0] == before + 2                  # two more quarters
    assert c.execute("SELECT due_date FROM pm_deadlines WHERE obligation_id = ?", (fin,)).fetchone()[0] == "2028-08-29"
    assert c.execute("SELECT status FROM pm_deadlines WHERE obligation_id = ? ORDER BY due_date LIMIT 1", (q,)).fetchone()[0] == "accepted"      # history kept
    with pytest.raises(pm.PMError):
        pm.extend_contract(c, proj["ca"], "2028-01-01", "Earlier")
    with pytest.raises(pm.PMError):
        pm.extend_contract(c, amend, "2029-01-01", "Of an amendment")


def test_validation_of_projects_funders_contracts_and_obligations(c, proj):
    with pytest.raises(pm.PMError, match="already"):
        pm.add_project(c, "DEMO-X", "Again")
    with pytest.raises(pm.PMError, match="already"):
        pm.add_funder(c, "Alpha Fund")
    with pytest.raises(pm.PMError, match="exchange rate"):
        pm.add_contract(c, proj["p"], proj["a"], "No rate", amount=1)
    with pytest.raises(pm.PMError):
        pm.add_contract(c, proj["p"], proj["b"], "Backwards", start_date="2027-01-01", end_date="2026-01-01")
    with pytest.raises(pm.PMError):
        pm.add_obligation(c, proj["ca"], "nonsense", "x")
    with pytest.raises(pm.PMError):
        pm.add_obligation(c, proj["ca"], "narrative_report", "x", anchor="fixed")
    with pytest.raises(pm.PMError):
        pm.add_obligation(c, proj["ca"], "narrative_report", "x", detail="huge")
    assert c.execute("SELECT name FROM project_codes WHERE code = 'DEMOX'").fetchone()[0] == "Demo X"


def test_transfers_keep_the_banks_rate_and_the_difference_from_the_budget_rate(c, proj):
    t1 = pm.add_transfer(c, proj["ca"], "Instalment 1", expected_date="2026-02-10", expected_amount=50000, received_date="2026-02-12", received_amount=50000, bank_rate=0.9412, bank_ref="B-1")
    row = c.execute("SELECT * FROM pm_transfers WHERE id = ?", (t1,)).fetchone()
    assert (row["chf_received"], row["bank_rate"]) == (47060.0, 0.9412)
    t2 = pm.add_transfer(c, proj["ca"], "Instalment 2", received_date="2026-08-27", chf_received=46500, bank_rate=0.93)              # amount derived from CHF and rate
    assert c.execute("SELECT received_amount FROM pm_transfers WHERE id = ?", (t2,)).fetchone()[0] == 50000.0
    pm.add_transfer(c, proj["cb"], "Instalment 1", received_date="2026-01-15", received_amount=25000)
    pm.add_transfer(c, proj["ca"], "Instalment 3", expected_date="2026-09-01", expected_amount=50000)                                # expected, now late
    f = pm.finance(c, proj["p"], TODAY)
    a = next(x for x in f["contracts"] if x["funder"] == "Alpha")
    assert (a["received"], a["chf_received"], a["outstanding"], a["average_rate"]) == (100000.0, 93560.0, 0.0, 0.9356) and a["fx_difference"] == round(93560 - 100000 * 0.94, 2)
    assert next(x for x in f["contracts"] if x["funder"] == "Beta")["fx_difference"] == 0.0
    assert [t["status"] for t in f["transfers"]].count("late") == 1 and f["totals"]["late_transfers"] == 1
    late = next(t for t in f["transfers"] if t["status"] == "late")
    assert late["days_late"] == 43
    first = next(t for t in f["transfers"] if t["label"] == "Instalment 1" and t["funder"] == "Alpha")
    assert first["days_late"] == 2 and first["fx_difference"] == round(47060 - 50000 * 0.94, 2)


def test_transfer_money_checks(c, proj):
    with pytest.raises(pm.PMError, match="two of"):
        pm.add_transfer(c, proj["ca"], "x", received_date="2026-01-01", received_amount=100)
    with pytest.raises(pm.PMError, match="do not agree"):
        pm.add_transfer(c, proj["ca"], "x", received_date="2026-01-01", received_amount=100, chf_received=50, bank_rate=0.94)
    with pytest.raises(pm.PMError, match="same"):
        pm.add_transfer(c, proj["cb"], "x", received_date="2026-01-01", received_amount=100, chf_received=90)
    with pytest.raises(pm.PMError):
        pm.add_transfer(c, proj["ca"], "x")
    am = pm.extend_contract(c, proj["ca"], "2028-06-30", "NCE")
    with pytest.raises(pm.PMError, match="amendment"):
        pm.add_transfer(c, am, "x", expected_date="2026-01-01", expected_amount=1)
    t = pm.add_transfer(c, proj["ca"], "Later", expected_date="2026-12-01", expected_amount=1000)
    assert pm.receive_transfer(c, t, "2026-12-05", chf_received=930, bank_rate=0.93) and c.execute("SELECT received_amount FROM pm_transfers WHERE id=?", (t,)).fetchone()[0] == 1000.0
    with pytest.raises(pm.PMError, match="already"):
        pm.receive_transfer(c, t, "2026-12-06", received_amount=1000, bank_rate=0.9)


def test_the_crosswalk_shows_what_is_common_and_what_differs(c, proj):
    pm.add_obligation(c, proj["ca"], "narrative_report", "Annual narrative", recurrence="annual", offset_days=45, language="en", format="Alpha template", detail="detailed")
    pm.add_obligation(c, proj["cb"], "narrative_report", "Annual narrative", recurrence="annual", offset_days=60, language="fr,en", format="free form", detail="summary")
    pm.add_obligation(c, proj["ca"], "visibility", "Acknowledge Alpha", anchor="none", recurrence="none", language="en")
    pm.add_obligation(c, proj["cb"], "visibility", "Acknowledge Beta", anchor="none", recurrence="none", language="en")
    cw = {g["canon"]: g for g in pm.crosswalk(c, proj["p"])}
    n = cw["narrative_report"]
    assert set(n["differs"]) == {"timing", "language", "format", "level of detail"} and n["same"] == []
    assert "detailed level (Alpha's)" in n["plan"] and "en and fr" in n["plan"] and "earliest deadline" in n["plan"]
    v = cw["visibility"]
    assert "language" in v["same"] and "timing" in v["same"]


def test_translating_one_funders_requirements_into_anothers(c, proj):
    pm.add_obligation(c, proj["ca"], "narrative_report", "Annual narrative", recurrence="annual", offset_days=45, language="en", format="Alpha template", detail="detailed")
    pm.add_obligation(c, proj["cb"], "narrative_report", "Annual narrative", recurrence="annual", offset_days=60, language="fr", format="free form", detail="summary")
    pm.add_obligation(c, proj["cb"], "audit", "Audit", anchor="end", offset_days=90, recurrence="once")
    pm.add_obligation(c, proj["ca"], "financial_report", "Quarterly", recurrence="quarterly", offset_days=30, detail="detailed", language="en")
    pm.add_obligation(c, proj["cb"], "financial_report", "Annual financial", recurrence="annual", offset_days=90, detail="standard", language="en")
    t = pm.translate(c, proj["p"], "Alpha", "Beta")
    rows = {r["canon"]: r for r in t["rows"]}
    assert rows["narrative_report"]["verdict"] == "partly" and any("French" not in x and "fr" in x for x in rows["narrative_report"]["reasons"])
    assert rows["audit"]["verdict"] == "gap" and rows["financial_report"]["verdict"] == "partly" and any("every quarter" in x for x in rows["financial_report"]["reasons"])
    assert t["summary"] == {"covers": 0, "partly": 2, "gap": 1}
    back = {r["canon"]: r for r in pm.translate(c, proj["p"], "Beta", "Alpha")["rows"]}
    assert any("less detailed" in x for x in back["narrative_report"]["reasons"])


def test_crunches_and_the_core_deadlines_that_feed_today(c, proj):
    for d, t in (("2026-10-27", "A"), ("2026-10-28", "B"), ("2026-10-30", "C"), ("2026-12-15", "D")):
        pm.add_obligation(c, proj["cb"], "notification", t, anchor="fixed", fixed_date=d, recurrence="once")
    dl = pm._deadline_rows(c, proj["p"], TODAY)
    cr = pm.crunches(dl)
    assert len(cr) == 1 and cr[0]["count"] == 3 and (cr[0]["from"], cr[0]["to"]) == ("2026-10-27", "2026-10-30")
    assert pm.sync_core(c, TODAY) == 4
    core = c.execute("SELECT title, due_date, kind, project_code, sensitivity FROM deadlines WHERE source='pm' ORDER BY due_date").fetchall()
    assert [r["due_date"] for r in core][:3] == ["2026-10-27", "2026-10-28", "2026-10-30"] and core[0]["project_code"] == "DEMOX" and core[0]["kind"] == "reporting" and core[0]["sensitivity"] == "S2"
    first = c.execute("SELECT id FROM pm_deadlines ORDER BY due_date LIMIT 1").fetchone()[0]
    assert pm.set_deadline_status(c, first, "submitted")
    assert c.execute("SELECT status FROM deadlines WHERE source='pm' ORDER BY due_date LIMIT 1").fetchone()[0] == "done"
    with pytest.raises(pm.PMError):
        pm.set_deadline_status(c, first, "weird")


def test_overview_and_detail_assemble_everything(c, proj):
    pm.add_obligation(c, proj["ca"], "financial_report", "Quarterly", recurrence="quarterly", offset_days=30)
    pm.add_transfer(c, proj["ca"], "I1", received_date="2026-02-12", received_amount=50000, bank_rate=0.94)
    ov = pm.project_overview(c, TODAY)
    assert ov[0]["code"] == "DEMOX" and ov[0]["funders"] == ["Alpha", "Beta"] and ov[0]["received_chf"] == 47000.0 and ov[0]["next"]["status"] == "todo"
    d = pm.project_detail(c, proj["p"], TODAY)
    assert set(d) >= {"project", "contracts", "obligations", "deadlines", "crunches", "finance", "crosswalk", "funders", "canon"} and pm.project_detail(c, 999, TODAY) is None


# ---------------------------------------------------------------- endpoints and the harness chat
def test_pm_endpoints_round_trip(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from harness.main import app
    with TestClient(app) as cl:
        assert cl.get("/api/meta").json() == {"demo": False}
        code = "EP" + str(abs(hash(str(tmp_path))))[:5]
        p = cl.post("/api/pm/projects", json={"code": code, "name": "Endpoint project", "start_date": "2026-01-01", "end_date": "2026-12-31"}).json()["id"]
        assert cl.post("/api/pm/projects", json={"code": code, "name": "Again"}).status_code == 422
        f = cl.post("/api/pm/funders", json={"name": f"Funder {code}", "short": "EPF", "currency": "USD"}).json()["id"]
        bad = cl.post("/api/pm/contracts", json={"project_id": p, "funder_id": f, "title": "No rate", "amount": 100})
        assert bad.status_code == 422 and "exchange rate" in bad.json()["detail"]
        k = cl.post("/api/pm/contracts", json={"project_id": p, "funder_id": f, "title": "Grant", "amount": 1000, "budget_rate": 0.9, "start_date": "2026-01-01", "end_date": "2026-12-31"}).json()["id"]
        o = cl.post("/api/pm/obligations", json={"contract_id": k, "canon": "financial_report", "title": "Quarterly", "recurrence": "quarterly", "offset_days": 30}).json()["id"]
        t = cl.post("/api/pm/transfers", json={"contract_id": k, "label": "I1", "received_date": "2026-02-01", "received_amount": 500, "bank_rate": 0.91}).json()["id"]
        d = cl.get(f"/api/pm/projects/{p}").json()
        assert len(d["deadlines"]) == 4 and d["finance"]["totals"]["chf_received"] == 455.0 and cl.get("/api/pm/projects/999999").status_code == 404
        assert cl.post(f"/api/pm/deadlines/{d['deadlines'][0]['id']}/status", json={"status": "accepted"}).json() == {"ok": True}
        assert cl.post(f"/api/pm/deadlines/{d['deadlines'][0]['id']}/status", json={"status": "nope"}).status_code == 422
        assert cl.post(f"/api/pm/obligations/{o}/confirm", json={}).json() == {"ok": True} and cl.post("/api/pm/obligations/99999/confirm", json={}).status_code == 404
        assert cl.post(f"/api/pm/contracts/{k}/extend", json={"new_end": "2027-06-30", "title": "NCE"}).status_code == 200
        r = cl.post(f"/api/pm/transfers/{t}/receive", json={"received_date": "2026-03-01", "received_amount": 1})
        assert r.status_code == 422 and "already" in r.json()["detail"]
        assert any(x["id"] == p for x in cl.get("/api/pm/projects").json()) and any(x["id"] == f for x in cl.get("/api/pm/funders").json())
        assert cl.get(f"/api/pm/translate?project={p}&source=EPF&to=EPF").status_code == 200


def test_the_harness_chat_knows_about_funding_and_crunches(c, proj):
    from datetime import datetime
    from harness import chat
    from harness.config import TZ
    pm.add_transfer(c, proj["ca"], "Instalment 2", expected_date="2026-09-01", expected_amount=50000, note="Held by the fund")
    for d_, t in (("2026-10-27", "A"), ("2026-10-28", "B"), ("2026-10-30", "C")):
        pm.add_obligation(c, proj["cb"], "notification", t, anchor="fixed", fixed_date=d_, recurrence="once")
    facts = chat.facts(c, datetime(2026, 10, 14, 9, 0, tzinfo=TZ))
    assert any("Project DEMOX" in f and "Alpha" in f for f in facts)
    assert any("Expected transfer (DEMOX): Alpha Instalment 2" in f and "LATE by 43 days" in f and "Held by the fund" in f for f in facts)
    assert any("Reporting crunch (DEMOX): 3 deadlines" in f for f in facts)
