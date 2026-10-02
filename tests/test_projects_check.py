"""Project checks (the harness's controle_projets) and the costs / budget-line importers. Synthetic data only."""
from datetime import date

import pytest

from harness import db
from harness.importers.costs import import_costs
from harness.importers.hours import import_hours
from harness.projects_check import build_checks

TODAY = date(2026, 10, 2)


@pytest.fixture
def c(tmp_path):
    c = db.connect(tmp_path / "t.db"); db.migrate(c)
    c.executemany("INSERT INTO project_codes (code, name, domain, kind) VALUES (?,?,?,?)", [("GPF", "Forum", "W", "project"), ("TK", "Toolkit", "W", "project"), ("MDH", "Course", "W", "project")])
    c.commit()
    return c


def hr(c, day, project, hours=1, ev="e", ent=None, desc="d", line=None):
    c.execute("INSERT INTO hours (row_key, date, project, budget_line, hours, description, evidence, entered_on) VALUES (?,?,?,?,?,?,?,?)", (f"{day}{project}{desc}{ev}{line}", day, project, line, hours, desc, ev, ent or day))
    c.commit()


def msgs(c):
    return {f["message"]: f for f in build_checks(c, TODAY)["findings"]}


def test_clean_hours_give_no_findings_beyond_register_notes(c):
    hr(c, "2026-09-28", "GPF")
    r = build_checks(c, TODAY)
    assert r["counts"]["error"] == 0 and r["counts"]["warning"] == 0 and r["ok"] and r["checked"]["hours"] == 1
    assert {f["code"] for f in r["findings"]} == {"GPF", "TK", "MDH"} and all(f["area"] == "register" for f in r["findings"])


def test_each_hours_problem_is_named_with_a_count_and_examples(c):
    hr(c, "2026-09-28", "GPF", ev="")
    hr(c, "2026-09-29", "GPF", ent="2026-10-20", desc="late")
    hr(c, "2026-09-30", "ZZZ", desc="x")
    hr(c, "2026-09-30", "TK", hours=0, desc="y")
    hr(c, "2026-09-26", "TK", desc="dup"); hr(c, "2026-09-26", "TK", desc="dup", ev="other evidence")
    m = msgs(c)
    assert m["Hours without an evidence pointer"]["severity"] == "error" and m["Hours without an evidence pointer"]["refs"] == ["2026-09-28 GPF"]
    assert m[f"Hours entered more than 7 days after the day they are for"]["severity"] == "warning"
    assert m["Hours for a project code that Suivi's Codes sheet does not know"]["count"] == 1
    assert m["Hours entries with zero or missing hours"]["count"] == 1
    assert m["The same hours entry appears twice (same day, project and description)"]["count"] == 1


def test_budget_lines_and_mandate_period_are_checked_when_the_register_has_them(c):
    c.execute("INSERT INTO register_mandates (code, name, funder, signature, activity_start, activity_end, reporting_deadline, status) VALUES ('TK','Toolkit','FDFA','2025-12-01','2026-01-01','2026-12-31','2027-01-31','Active')")
    c.executemany("INSERT INTO register_budget (bkey, code, budget_line) VALUES (?,?,?)", [("TK|Staff", "TK", "Staff"), ("TK|Travel", "TK", "Travel")])
    c.commit()
    hr(c, "2026-09-28", "TK", line="Staff"); hr(c, "2026-09-29", "TK", line="Catering", desc="a"); hr(c, "2026-09-30", "TK", desc="b"); hr(c, "2025-12-15", "TK", line="Staff", desc="early")
    m = msgs(c)
    assert m["Hours charged to a budget line that is not in the register's Budget sheet"]["count"] == 1
    assert m["Hours without a budget line, for a project that has budget lines"]["count"] == 1
    assert m["Hours outside the mandate's activity period"]["refs"] == ["2025-12-15 TK"]
    assert not any(f["code"] == "TK" and f["area"] == "mandates" for f in build_checks(c, TODAY)["findings"])


def test_mandate_gaps_ended_periods_and_reporting_deadlines(c):
    c.execute("INSERT INTO register_mandates (code, name) VALUES ('TK','Toolkit')")
    c.execute("INSERT INTO register_mandates (code, name, funder, signature, activity_start, activity_end, reporting_deadline, status) VALUES ('MDH','Course','G','2025-01-01','2025-02-01','2026-06-30','2026-09-30','Active')")
    c.execute("INSERT INTO register_mandates (code, name, funder, signature, activity_start, activity_end, reporting_deadline, status) VALUES ('GPF','Forum','G','2025-01-01','2025-02-01','2026-12-31','2026-10-20','Active')")
    c.commit()
    f = build_checks(c, TODAY)["findings"]
    by = {(x["code"], x["message"][:30]): x for x in f if x["area"] == "mandates"}
    assert any(k[0] == "TK" and "still empty" in x["message"] for k, x in by.items()) and "funder" in next(x for x in f if x["code"] == "TK" and x["area"] == "mandates")["message"]
    mdh = [x for x in f if x["code"] == "MDH" and x["area"] == "mandates"]
    assert any("ended on 2026-06-30" in x["message"] for x in mdh) and any(x["severity"] == "error" and "passed 2 days ago" in x["message"] for x in mdh)
    assert any(x["code"] == "GPF" and "is in 18 days" in x["message"] and x["severity"] == "warning" for x in f)
    c.execute("UPDATE register_mandates SET close_out_state='submitted' WHERE code='MDH'"); c.commit()
    assert not any(x["code"] == "MDH" and "passed" in x["message"] for x in build_checks(c, TODAY)["findings"])


def test_costs_are_checked_for_justificatif_currency_and_payment_details(tmp_path, c):
    folder = tmp_path / "p"; folder.mkdir()
    (folder / "costs.csv").write_text("date,project,budget_line,supplier,amount,currency,amount_chf,invoice_reference,payment_date,account,justificatif,entered_on\n"
                                      "2026-09-01,TK,,Acme,100,CHF,100,INV1,2026-09-02,CH93 0076 2011 6238 5295 7,Expenses/a.pdf,2026-09-03\n"
                                      "2026-09-02,TK,,Beta,50,USD,,,,UBS 5501,,\n")
    r = import_costs(c, folder)[0]
    assert r.added == 2 and import_costs(c, folder)[0].unchanged == 2
    assert c.execute("SELECT account FROM costs WHERE supplier='Acme'").fetchone()[0] == "…2957"                    # an IBAN is reduced to its last four
    assert "CH93" not in str([tuple(x) for x in c.execute("SELECT * FROM costs")])
    m = msgs(c)
    assert m["Costs without a justificatif (supporting document)"]["refs"] == ["2026-09-02 Beta"]
    assert m["Costs in another currency without the CHF amount"]["count"] == 1 and m["Costs without a payment date"]["count"] == 1
    assert m["Costs without an invoice reference"]["count"] == 1 and m["Costs without an entered_on date"]["count"] == 1


def test_importers_tolerate_missing_files_and_budget_lines_come_from_the_register(tmp_path, c):
    assert "no costs.csv" in import_costs(c, tmp_path)[0].notes[0] and "no hours.csv" in import_hours(c, tmp_path)[0].notes[0]
    import openpyxl
    from harness.importers.registre import import_registre
    wb = openpyxl.Workbook(); wb.remove(wb.active)
    for name, cols in {"Mandates": ["code", "name", "funder", "signature", "activity start", "activity end", "reporting deadline", "interim reports", "status", "close-out state"], "Instalments": ["code", "instalment", "expected date", "received date"],
                       "Budget": ["code", "budget line", "phase", "funder amount", "own amount", "total"], "Initiatives": ["code", "name", "status", "next touchpoint"]}.items():
        wb.create_sheet(name).append(cols)
    wb["Budget"].append(["TK", "Staff", "Phase 1", 5000, 0, 5000])
    folder = tmp_path / "reg"; folder.mkdir(); wb.save(folder / "Registre_Projets.xlsx")
    import_registre(c, folder)
    assert [tuple(r)[:3] for r in c.execute("SELECT code, budget_line, phase FROM register_budget")] == [("TK", "Staff", "Phase 1")]
    assert "5000" not in str([tuple(r) for r in c.execute("SELECT * FROM register_budget")])                      # amounts are never read


def test_api(c):
    from fastapi.testclient import TestClient
    from harness.main import app
    with TestClient(app) as cl:
        r = cl.get("/api/projects-check").json()
        assert {"findings", "counts", "checked", "ok"} <= set(r)
