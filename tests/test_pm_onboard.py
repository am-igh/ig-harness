"""Contract onboarding: validation, a preview that matches what is created, the all-or-nothing create step, and the endpoints. Synthetic data only."""
import json
from copy import deepcopy

import pytest

from harness import db, pm, pm_onboard as O

BASE = {
    "project": {"mode": "new", "code": "demo-o", "name": "Onboarding project", "lead": "Lead", "summary": ""},
    "funder": {"mode": "new", "name": "Example Foundation", "short": "EXF", "role": "funder", "currency": "EUR"},
    "contract": {"title": "Grant agreement", "kind": "grant", "reference": "EXF/2026/001", "signed_date": "2025-12-01", "start_date": "2026-01-01", "end_date": "2027-12-31",
                 "amount": 300000, "currency": "EUR", "budget_rate": 0.94, "file_path": "Contracts/Example/grant.pdf", "summary": "Core funding"},
    "payments": [{"label": "Instalment 1", "expected_date": "2026-02-01", "expected_amount": 100000, "condition": ""},
                 {"label": "Instalment 2", "expected_date": "2026-09-01", "expected_amount": 100000, "condition": "After the first report is accepted"},
                 {"label": "Instalment 3", "expected_date": "2027-03-01", "expected_amount": 100000, "condition": ""}],
    "reports": [
        {"canon": "financial_report", "title": "Quarterly financial report", "recurrence": "quarterly", "anchor": "period_end", "offset_days": 30, "language": "en", "format": "Funder workbook", "detail": "detailed", "clause": "4.2"},
        {"canon": "narrative_report", "title": "Annual narrative report", "recurrence": "annual", "anchor": "period_end", "offset_days": 60, "language": "fr,en", "detail": "standard", "clause": "4.3"},
        {"canon": "audit", "title": "External audit", "recurrence": "once", "anchor": "end", "offset_days": 120, "detail": "line-by-line"},
        {"canon": "milestone_report", "title": "Milestone 1", "recurrence": "once", "anchor": "fixed", "fixed_date": "2026-06-30", "offset_days": 0},
    ],
    "rules": {"overhead_pct": 7, "overhead_clause": "6.4", "approval_pct": 10, "procurement_threshold": 5000, "procurement_quotes": 3, "visibility": "Acknowledge the funder in all outputs", "eligible_costs": "Costs incurred in the period"},
    "terms": {"termination_notice_days": 90, "governing_law": "Swiss law, Geneva courts", "ownership": "The Grantee owns the outputs", "data_protection": "Personal data stays in Switzerland",
              "special_conditions": "Prior approval to subcontract", "contacts": [{"name": "Ingrid Example", "role": "Programme officer", "email": "ingrid@example.org", "phone": ""}]},
}


@pytest.fixture
def c(tmp_path):
    c = db.connect(tmp_path / "t.db"); db.migrate(c)
    return c


def data(**over):
    d = deepcopy(BASE)
    for k, v in over.items():
        d[k] = v
    return d


def test_options_offer_presets_types_and_what_already_exists(c):
    pm.add_project(c, "OLD", "An old project"); pm.add_funder(c, "Some Funder", "SF")
    o = O.options(c)
    assert {p["id"] for p in o["presets"]} >= {"financial_quarterly", "narrative_annual", "audit_final", "milestone", "partner_quarterly"} and "narrative_report" in o["canon"]
    assert [p["code"] for p in o["projects"]] == ["OLD"] and o["funders"][0]["short"] == "SF" and o["detail"][0] == "summary"
    q = next(p for p in o["presets"] if p["id"] == "financial_quarterly")
    assert (q["recurrence"], q["offset_days"], q["canon"]) == ("quarterly", 30, "financial_report")


def test_a_complete_contract_has_no_errors_and_the_preview_says_what_will_be_created(c):
    pv = O.preview(c, data())
    assert pv["errors"] == [] and pv["warnings"] == []
    assert pv["summary"] == {"funder": "EXF", "requirements": 4, "deadlines": 8 + 2 + 1 + 1, "rules": 4, "payments": 3}
    assert [d["due_date"] for d in pv["deadlines"]][:3] == ["2026-04-30", "2026-06-30", "2026-07-30"] and pv["more_deadlines"] == 0 and len(pv["deadlines"]) == 12
    assert pv["rules"][0] == "Overhead capped at 7%" and "Prior written approval for reallocations above 10% of a budget line" in pv["rules"] and "3 written quotes above EUR 5,000" in pv["rules"]
    assert c.execute("SELECT COUNT(*) FROM pm_projects").fetchone()[0] == 0                              # a preview creates nothing


def test_missing_and_wrong_things_are_named_in_plain_words(c):
    bad = data(project={"mode": "new", "code": "", "name": ""}, funder={"mode": "existing", "id": 99})
    bad["contract"] = {"title": "", "kind": "loan", "currency": "EUR", "amount": "", "start_date": "2027-01-01", "end_date": "2026-01-01", "signed_date": "tomorrow"}
    bad["payments"] = [{"label": "", "expected_date": "", "expected_amount": -5}]
    bad["reports"] = [{"canon": "nonsense", "title": "", "recurrence": "quarterly", "anchor": "end"}, {"canon": "audit", "title": "Audit", "recurrence": "once", "anchor": "fixed"}]
    bad["rules"] = {"overhead_pct": 150, "procurement_threshold": "lots"}
    bad["terms"] = {"termination_notice_days": "soon", "contacts": [{"name": "X", "email": "not-an-email"}]}
    errs = " | ".join(O.validate(c, bad)["errors"])
    for want in ("new project needs a code", "needs a name", "Choose the funder", "contract needs a title", "grant (money in) or a sub-grant", "contract amount", "exchange rate (CHF per 1 EUR)", "end date is before the start date",
                 "signing date is not a valid date", "Payment 1 needs a label", "date of payment 1 is required", "needs a positive amount", "choose what kind of requirement", "a repeating report is due after the end",
                 "The date of “Audit” is required", "overhead cap must be a percentage", "procurement threshold must be a number", "notice period must be a number", "not a valid email"):
        assert want in errs, want


def test_warnings_for_things_that_are_possible_but_probably_unintended(c):
    d = data()
    d["contract"]["file_path"] = ""
    d["payments"][2]["expected_amount"] = 50000
    d["terms"]["contacts"] = []
    w = " | ".join(O.validate(c, d)["warnings"])
    assert "No location for the signed contract" in w and "payments add up to EUR 250,000.00, not the contract amount of EUR 300,000.00" in w and "No contact person" in w
    d2 = data(payments=[], reports=[])
    w2 = " | ".join(O.validate(c, d2)["warnings"])
    assert "No payment schedule" in w2 and "No reporting requirements" in w2
    d3 = data(); d3["payments"][0]["expected_date"] = "2031-01-01"
    assert "falls well outside the contract period" in " | ".join(O.validate(c, d3)["warnings"])


def test_creating_builds_everything_in_one_go(c):
    out = O.create(c, data())
    assert (out["obligations"], out["deadlines"], out["payments"]) == (8, 12, 3)
    p = c.execute("SELECT * FROM pm_projects").fetchone(); f = c.execute("SELECT * FROM pm_funders").fetchone(); k = c.execute("SELECT * FROM pm_contracts").fetchone()
    assert (p["code"], p["lead"]) == ("DEMOO", "Lead") and (f["short"], f["currency"], f["contact"]) == ("EXF", "EUR", "Ingrid Example")
    assert (k["reference"], k["amount"], k["currency"], k["budget_rate"], k["file_path"]) == ("EXF/2026/001", 300000.0, "EUR", 0.94, "Contracts/Example/grant.pdf")
    terms = json.loads(k["terms"])
    assert terms["termination_notice_days"] == 90 and terms["governing_law"] == "Swiss law, Geneva courts" and terms["contacts"][0]["email"] == "ingrid@example.org" and terms["eligible_costs"] == "Costs incurred in the period"
    assert c.execute("SELECT COUNT(*) FROM pm_deadlines").fetchone()[0] == 12 and c.execute("SELECT COUNT(*) FROM pm_obligations WHERE recurrence = 'none'").fetchone()[0] == 4
    tr = c.execute("SELECT label, expected_date, expected_amount, note FROM pm_transfers ORDER BY expected_date").fetchall()
    assert [t["label"] for t in tr] == ["Instalment 1", "Instalment 2", "Instalment 3"] and tr[1]["note"] == "After the first report is accepted"
    assert c.execute("SELECT name FROM project_codes WHERE code = 'DEMOO'").fetchone() is not None
    assert c.execute("SELECT COUNT(*) FROM deadlines WHERE source = 'pm'").fetchone()[0] >= 1                  # the deadlines feed Today
    d = pm.project_detail(c, p["id"])
    assert d["contracts"][0]["terms"]["ownership"] == "The Grantee owns the outputs" and d["contracts"][0]["reference"] == "EXF/2026/001" and len(d["deadlines"]) == 12


def test_it_can_use_an_existing_project_and_funder_and_a_subgrant_has_no_expected_income(c):
    pid = pm.add_project(c, "EXIST", "Existing", "2026-01-01", "2027-12-31"); fid = pm.add_funder(c, "Partner Org", "PO", role="partner", currency="USD")
    d = data(project={"mode": "existing", "id": pid}, funder={"mode": "existing", "id": fid})
    d["contract"].update(kind="subgrant", currency="USD", budget_rate=0.88, title="Sub-grant")
    out = O.create(c, d)
    assert out["project_id"] == pid and out["funder_id"] == fid and out["payments"] == 0                           # money going out is not an expected transfer
    assert c.execute("SELECT COUNT(*) FROM pm_projects").fetchone()[0] == 1 and c.execute("SELECT COUNT(*) FROM pm_funders").fetchone()[0] == 1


def test_a_problem_halfway_undoes_everything(c, monkeypatch):
    calls = {"n": 0}
    real = pm.add_transfer
    def flaky(*a, **k):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("disk problem")
        return real(*a, **k)
    monkeypatch.setattr(pm, "add_transfer", flaky)
    with pytest.raises(RuntimeError):
        O.create(c, data())
    for table in ("pm_projects", "pm_funders", "pm_contracts", "pm_obligations", "pm_deadlines", "pm_transfers"):
        assert c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0, table
    assert c.execute("SELECT COUNT(*) FROM project_codes WHERE code = 'DEMOO'").fetchone()[0] == 0
    monkeypatch.setattr(pm, "add_transfer", real)
    assert O.create(c, data())["contract_id"] == 1                                                                 # and it can simply be tried again


def test_invalid_data_is_refused_before_anything_is_written(c):
    bad = data(); bad["contract"]["amount"] = ""
    with pytest.raises(pm.PMError, match="contract amount"):
        O.create(c, bad)
    assert c.execute("SELECT COUNT(*) FROM pm_projects").fetchone()[0] == 0


def test_the_batch_never_leaks_into_ordinary_use(c):
    O.create(c, data())
    c.rollback()
    assert c.execute("SELECT COUNT(*) FROM pm_contracts").fetchone()[0] == 1                                      # it was really committed
    pid = pm.add_project(c, "AFTER", "After")                                                                      # an ordinary call after a batch commits by itself again
    c.rollback()
    assert c.execute("SELECT COUNT(*) FROM pm_projects WHERE id = ?", (pid,)).fetchone()[0] == 1


def test_endpoints(c):
    from fastapi.testclient import TestClient
    from harness.main import app
    d = data(project={"mode": "new", "code": "EPONB" + str(abs(hash(str(c))))[:4], "name": "Endpoint onboarding"}, funder={"mode": "new", "name": "EP funder " + str(abs(hash(str(c))))[:6], "short": "EPF", "currency": "EUR"})
    with TestClient(app) as cl:
        assert "presets" in cl.get("/api/pm/onboarding/options").json()
        pv = cl.post("/api/pm/onboarding/preview", json=d).json()
        assert pv["errors"] == [] and pv["summary"]["deadlines"] == 12
        r = cl.post("/api/pm/onboarding/create", json=d)
        assert r.status_code == 200 and r.json()["deadlines"] == 12
        assert cl.post("/api/pm/onboarding/create", json=d).status_code == 422                                      # the same project code and funder again are refused
        bad = deepcopy(d); bad["contract"]["amount"] = ""
        assert cl.post("/api/pm/onboarding/create", json=bad).status_code == 422
