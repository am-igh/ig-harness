"""The report workspace: templates made by rules from the requirement and the harness's own records, drafts saved as new versions, references to forms that stay in her folders."""
from datetime import date

import pytest

from harness import db, pm, pm_reports as R

TODAY = date(2026, 10, 14)


@pytest.fixture
def w(tmp_path):
    c = db.connect(tmp_path / "t.db"); db.migrate(c)
    p = pm.add_project(c, "DEMOX", "Demo X", "2026-01-01", "2027-12-31")
    nda = pm.add_funder(c, "Nordland Agency", "NDA", currency="EUR", contact="Ingrid")
    hd = pm.add_funder(c, "Helvetia Trust", "HDTF")
    cn = pm.add_contract(c, p, nda, "NDA grant", amount=100000, budget_rate=0.94, start_date="2026-01-01", end_date="2027-12-31")
    ch = pm.add_contract(c, p, hd, "HDTF grant", amount=50000, start_date="2026-01-01", end_date="2027-12-31")
    fin = pm.add_obligation(c, cn, "financial_report", "Quarterly financial report", recurrence="quarterly", offset_days=30, language="en", format="NDA workbook", detail="detailed", clause="Sect. 4.2")
    pm.add_obligation(c, cn, "overhead", "Overhead capped at 7%", anchor="none", recurrence="none", clause="Sect. 6.4")
    nar = pm.add_obligation(c, ch, "narrative_report", "Annual narrative report", recurrence="annual", offset_days=60, language="fr,en", detail="standard", clause="Art. 7.1")
    pm.add_transfer(c, cn, "Instalment 1", received_date="2026-02-12", received_amount=50000, bank_rate=0.9412)
    pm.add_transfer(c, cn, "Instalment 2", received_date="2026-08-27", received_amount=50000, bank_rate=0.93)
    c.execute("INSERT INTO journal_entries (entry_date, text, project_code, source, source_ref) VALUES ('2026-02-20', 'Kick-off workshop held with partners', 'DEMOX', 't', 'j1')")
    c.execute("INSERT INTO journal_entries (entry_date, text, project_code, space, source, source_ref) VALUES ('2026-02-21', 'PRIVATE appointment', 'DEMOX', 'personal', 't', 'j2')")
    c.execute("INSERT INTO journal_entries (entry_date, text, project_code, source, source_ref) VALUES ('2026-06-01', 'Outside the period', 'DEMOX', 't', 'j3')")
    c.execute("INSERT INTO tasks (title, project_code, status, done_at, source, source_ref) VALUES ('Reconcile the January expenses', 'DEMOX', 'done', '2026-03-05 10:00:00', 't', 'k1')")
    c.execute("INSERT INTO hours (row_key, date, project, hours, evidence, entered_on) VALUES ('h1','2026-03-01','DEMOX',6.5,'e','2026-03-01')")
    c.commit()
    q1 = c.execute("SELECT id FROM pm_deadlines WHERE obligation_id = ? ORDER BY due_date LIMIT 1", (fin,)).fetchone()[0]
    return {"c": c, "q1": q1, "fin": fin, "nar": c.execute("SELECT id FROM pm_deadlines WHERE obligation_id = ? ORDER BY due_date LIMIT 1", (nar,)).fetchone()[0]}


def test_periods_are_remembered_on_the_deadlines(w):
    r = w["c"].execute("SELECT period_start, period_end FROM pm_deadlines WHERE id = ?", (w["q1"],)).fetchone()
    assert (r[0], r[1]) == ("2026-01-01", "2026-03-31")


def test_the_workspace_shows_the_requirement_and_the_rules_of_the_same_contract(w):
    ws = R.workspace(w["c"], w["q1"], TODAY)
    assert ws["deadline"]["funder"] == "NDA" and ws["deadline"]["due_date"] == "2026-04-30" and ws["deadline"]["days_left"] == (date(2026, 4, 30) - TODAY).days
    assert ws["requirement"]["clause"] == "Sect. 4.2" and ws["requirement"]["language"] == "en" and ws["requirement"]["detail"] == "detailed"
    assert [x["canon"] for x in ws["rules"]] == ["overhead"] and ws["documents"] == [] and ws["has_template"] is False
    assert R.workspace(w["c"], 99999, TODAY) is None


def test_a_financial_template_carries_the_period_the_bank_rates_and_the_rules_but_not_personal_notes(w):
    doc = R.make_template(w["c"], w["q1"])
    t = doc["content"]
    assert doc["kind"] == "template" and doc["author"] == "rules" and doc["version"] == 1
    assert "Period covered:** 2026-01-01 to 2026-03-31" in t and "NDA workbook" in t and "Overhead capped at 7%" in t and "Sect. 4.2" in t
    assert "| 2026-02-12 | Instalment 1 | 50,000.00 EUR | 0.9412 | 47,060.00 CHF |" in t and "Instalment 2" not in t        # only the transfer inside the period
    assert "Budget rate in the contract: 0.94 CHF per 1 EUR" in t
    assert "Kick-off workshop held with partners" in t and "Reconcile the January expenses" in t and "Hours logged on DEMOX in the period:** 6.5" in t
    assert "PRIVATE appointment" not in t and "Outside the period" not in t


def test_a_narrative_template_follows_the_funders_language_and_level_of_detail(w):
    t = R.make_template(w["c"], w["nar"])["content"]
    assert "## Résumé de la période" in t and "## Avancement par rapport au plan et au cadre de résultats" in t           # fr first: French headings
    assert "about 4 to 6 pages" in t and "Art. 7.1" in t
    w["c"].execute("UPDATE pm_obligations SET language = 'en' WHERE canon = 'narrative_report'"); w["c"].commit()
    assert "## Summary of the period" in R.make_template(w["c"], w["nar"])["content"]


def test_other_requirement_types_get_their_own_skeletons(w):
    c = w["c"]
    cn = c.execute("SELECT id FROM pm_contracts WHERE title = 'NDA grant'").fetchone()[0]
    ids = {k: pm.add_obligation(c, cn, k, f"{k} item", anchor="fixed", fixed_date="2026-11-01", recurrence="once") for k in ("milestone_report", "audit", "partner_report", "notification")}
    for k, i in ids.items():
        did = c.execute("SELECT id FROM pm_deadlines WHERE obligation_id = ?", (i,)).fetchone()[0]
        t = R.make_template(c, did)["content"]
        assert {"milestone_report": "Evidence the funder can verify", "audit": "Audit checklist", "partner_report": "What the partner must send", "notification": "To: Ingrid"}[k] in t


def test_a_draft_starts_from_the_template_and_every_save_is_a_new_version(w):
    c = w["c"]
    with pytest.raises(pm.PMError, match="template"):
        R.start_draft(c, w["q1"])
    tpl = R.make_template(c, w["q1"])
    d = R.start_draft(c, w["q1"])
    assert d["kind"] == "draft" and d["version"] == 1 and d["content"] == tpl["content"]
    assert c.execute("SELECT status FROM pm_deadlines WHERE id = ?", (w["q1"],)).fetchone()[0] == "drafting"                # working on it means drafting
    with pytest.raises(pm.PMError, match="already"):
        R.start_draft(c, w["q1"])
    v2 = R.save_version(c, d["id"], d["content"] + "\n\nMy edit.")
    assert v2["version"] == 2 and "My edit." in v2["content"]
    with pytest.raises(pm.PMError, match="newer"):
        R.save_version(c, d["id"], "stale")                                                                                  # cannot overwrite from an old version
    vs = R.versions(c, v2["id"])
    assert [x["version"] for x in vs] == [2, 1] and "My edit." not in vs[1]["content"]                                       # version 1 is untouched
    with pytest.raises(pm.PMError, match="Only a working draft"):
        R.save_version(c, tpl["id"], "x")
    with pytest.raises(pm.PMError):
        R.save_version(c, v2["id"], "   ")
    docs = R.documents(c, w["q1"])
    assert [x["kind"] for x in docs] == ["template", "draft"] and docs[1]["versions"] == 2 and docs[1]["version"] == 2


def test_regenerating_a_template_adds_a_version_and_references_stay_in_her_folders(w):
    c = w["c"]
    R.make_template(c, w["q1"]); R.make_template(c, w["q1"])
    assert R.documents(c, w["q1"])[0]["version"] == 2 and R.documents(c, w["q1"])[0]["versions"] == 2
    ref = R.attach_reference(c, w["q1"], "funder_form", "NDA financial workbook v4", "Funder forms/NDA/NDA_workbook_v4.xlsx", "Use v4, not v3")
    docs = R.documents(c, w["q1"])
    assert docs[0]["kind"] == "funder_form" and docs[0]["file_path"].endswith("NDA_workbook_v4.xlsx") and docs[0]["content"] is None
    for bad in (("draft", "x", "p"), ("funder_form", "", "p"), ("funder_form", "t", " ")):
        with pytest.raises(pm.PMError):
            R.attach_reference(c, w["q1"], *bad)
    with pytest.raises(pm.PMError):
        R.attach_reference(c, 99999, "other", "t", "p")


def test_workspace_endpoints(w, monkeypatch):
    from fastapi.testclient import TestClient
    from harness.main import app
    with TestClient(app) as cl:
        pid = cl.post("/api/pm/projects", json={"code": "WSEP" + str(abs(hash(str(w["c"]))))[:4], "name": "WS endpoint", "start_date": "2026-01-01", "end_date": "2026-12-31"}).json()["id"]
        fid = cl.post("/api/pm/funders", json={"name": "WS funder " + str(abs(hash(str(w["c"]))))[:5], "currency": "CHF"}).json()["id"]
        k = cl.post("/api/pm/contracts", json={"project_id": pid, "funder_id": fid, "title": "G", "amount": 1000, "start_date": "2026-01-01", "end_date": "2026-12-31"}).json()["id"]
        cl.post("/api/pm/obligations", json={"contract_id": k, "canon": "narrative_report", "title": "Annual", "recurrence": "annual", "offset_days": 30, "language": "en"})
        dl = cl.get(f"/api/pm/projects/{pid}").json()["deadlines"][0]["id"]
        ws = cl.get(f"/api/pm/deadlines/{dl}").json()
        assert ws["deadline"]["id"] == dl and ws["documents"] == [] and cl.get("/api/pm/deadlines/999999").status_code == 404
        tpl = cl.post(f"/api/pm/deadlines/{dl}/template").json()
        assert tpl["kind"] == "template" and "## Summary of the period" in tpl["content"]
        dr = cl.post(f"/api/pm/deadlines/{dl}/draft").json()
        assert cl.post(f"/api/pm/deadlines/{dl}/draft").status_code == 422
        v2 = cl.post(f"/api/pm/documents/{dr['id']}/version", json={"content": "# Edited\n\ntext"}).json()
        assert v2["version"] == 2 and len(cl.get(f"/api/pm/documents/{v2['id']}/versions").json()) == 2
        dl_resp = cl.get(f"/api/pm/documents/{v2['id']}/download")
        assert dl_resp.status_code == 200 and dl_resp.text.startswith("# Edited") and "attachment" in dl_resp.headers["content-disposition"] and dl_resp.headers["content-disposition"].endswith('_v2.md"')
        ref = cl.post(f"/api/pm/deadlines/{dl}/documents", json={"kind": "funder_form", "title": "Form", "file_path": "Forms/x.docx"}).json()["id"]
        assert cl.get(f"/api/pm/documents/{ref}/download").status_code == 404
