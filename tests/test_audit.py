"""Audit readiness: her checker runs unchanged, its report is captured (never written), results are stored and compared."""
import re
import time
from pathlib import Path

import openpyxl
import pytest

from harness import audit, db

FAKE = '''
import argparse, sys, time
from pathlib import Path

def ecrire_xlsx(lignes, racine, annee):
    (racine / f"Controle_justificatifs_{annee}.xlsx").write_text("THIS FILE MUST NEVER BE WRITTEN")

def resume(lignes):
    print("resume:", len(lignes))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--annee", default="2026"); ap.add_argument("--dossier"); ap.add_argument("--seuil", type=float, default=0.0)
    a = ap.parse_args()
    racine = Path(a.dossier) / a.annee
    if not racine.is_dir():
        sys.exit(f"Dossier introuvable : {racine}")
    {BODY}
    print("Relevés trouvés : 2"); print("Pièces indexées : 3")
    lignes = [
        dict(compte="0240 2257", iban="CH93 0076 2011 6238 5295 7", periode="01.04.2026 – 30.06.2026", devise="CHF", date="05.04.2026", beneficiaire="Printer Inc", montant=120.5, statut="justifié", source="Expenses/p.pdf", groupe=""),
        dict(compte="0240 2257", iban="CH93 0076 2011 6238 5295 7", periode="01.04.2026 – 30.06.2026", devise="CHF", date="20.04.2026", beneficiaire="Mystery Ltd", montant=999.0, statut="À JUSTIFIER", source="", groupe=""),
        dict(compte="0240 2258", iban="CH11 0000", periode="01.07.2026 – 30.09.2026", devise="EUR", date="02.07.2026", beneficiaire="Bank fees", montant=10.0, statut="couvert", source="Frais bancaires", groupe=""),
        dict(compte="0240 2258", iban="CH11 0000", periode="01.07.2026 – 30.09.2026", devise="EUR", date="15.08.2026", beneficiaire="Cloud service", montant=45.25, statut="justifié", source="Expenses/c.pdf", groupe="oui"),
    ]
    ecrire_xlsx(lignes, racine, a.annee)
    resume(lignes)
'''


def make_root(tmp_path, body="pass", pdfs=("a.pdf", "b.pdf")):
    root = tmp_path / "audit"
    (root / "Outils").mkdir(parents=True); (root / "2026" / "Expenses").mkdir(parents=True)
    (root / "Outils" / "controle_justificatifs.py").write_text(FAKE.replace("{BODY}", body))
    for n in pdfs:
        (root / "2026" / "Expenses" / n).write_bytes(b"%PDF-1.4 " + n.encode())
    return root


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db"); db.migrate(c)
    return c


@pytest.fixture
def root(tmp_path):
    return make_root(tmp_path)


def test_her_script_runs_unchanged_and_its_report_is_captured_not_written(conn, root):
    rid = audit.run_and_store(conn, root, "2026")
    assert conn.execute("SELECT status, n_statements, n_pieces, n_lines FROM audit_runs WHERE id=?", (rid,)).fetchone()[:] == ("done", 2, 3, 4)
    assert list((root / "2026").glob("Controle_justificatifs_*.xlsx")) == []                       # nothing written into her folder
    assert (root / "Outils" / "controle_justificatifs.py").read_text() == FAKE.replace("{BODY}", "pass")      # and the script itself untouched


def test_no_iban_is_stored(conn, root):
    audit.run_and_store(conn, root, "2026")
    cols = [r[1] for r in conn.execute("PRAGMA table_info(audit_lines)")]
    assert "iban" not in cols and "CH93" not in str([tuple(r) for r in conn.execute("SELECT * FROM audit_lines")])


def test_summary_counts_totals_percentage_and_periods(conn, root):
    audit.run_and_store(conn, root, "2026")
    s = audit.status(conn, root, "2026")["latest"]
    assert s["counts"]["À JUSTIFIER"] == {"n": 1, "total": 999.0} and s["counts"]["justifié"] == {"n": 2, "total": 165.75} and s["counts"]["couvert"]["n"] == 1
    assert s["debits"] == 4 and s["pct_ok"] == 75.0
    assert (s["period_from"], s["period_to"], s["statements_to"]) == ("2026-04-05", "2026-08-15", "2026-09-30")
    assert s["accounts"] == ["0240 2257", "0240 2258"] and (s["n_statements"], s["n_pieces"]) == (2, 3)


def test_lines_are_listed_biggest_first_and_can_be_filtered(conn, root):
    audit.run_and_store(conn, root, "2026")
    assert [l["beneficiaire"] for l in audit.lines(conn, "2026")] == ["Mystery Ltd", "Printer Inc", "Cloud service", "Bank fees"]
    unmatched = audit.lines(conn, "2026", "À JUSTIFIER")
    assert [(l["beneficiaire"], l["montant"], l["date_iso"]) for l in unmatched] == [("Mystery Ltd", 999.0, "2026-04-20")]
    assert audit.lines(conn, "2025") == []


# ---------------------------------------------------------------- freshness
def test_the_result_is_marked_stale_when_a_receipt_or_the_script_changes(conn, root):
    audit.run_and_store(conn, root, "2026")
    assert audit.status(conn, root, "2026")["stale"] is False
    (root / "2026" / "Expenses" / "new_invoice.pdf").write_bytes(b"%PDF new")
    assert audit.status(conn, root, "2026")["stale"] is True
    audit.run_and_store(conn, root, "2026")
    assert audit.status(conn, root, "2026")["stale"] is False
    (root / "Outils" / "controle_justificatifs.py").write_text(FAKE.replace("{BODY}", "pass") + "\n# edited\n")
    assert audit.status(conn, root, "2026")["stale"] is True


def test_non_pdf_files_do_not_make_it_stale(conn, root):
    audit.run_and_store(conn, root, "2026")
    (root / "2026" / "notes.docx").write_text("x"); (root / "2026" / "Controle_justificatifs_2026.xlsx").write_text("report")
    assert audit.status(conn, root, "2026")["stale"] is False


# ---------------------------------------------------------------- failures are recorded, never raised
def test_her_script_stopping_with_a_message_is_recorded_as_an_error(conn, tmp_path):
    root = make_root(tmp_path, body='sys.exit("Aucun relevé de compte trouvé dans " + str(racine))')
    rid = audit.run_and_store(conn, root, "2026")
    r = conn.execute("SELECT status, error FROM audit_runs WHERE id=?", (rid,)).fetchone()
    assert r["status"] == "error" and "Aucun relevé" in r["error"]
    assert audit.status(conn, root, "2026")["last_error"].startswith("AuditError: Aucun relevé")


def test_a_crash_in_her_script_is_recorded_as_an_error(conn, tmp_path):
    root = make_root(tmp_path, body="raise ValueError('boom')")
    rid = audit.run_and_store(conn, root, "2026")
    assert conn.execute("SELECT status, error FROM audit_runs WHERE id=?", (rid,)).fetchone()[:] == ("error", "ValueError: boom")


def test_a_script_that_exits_cleanly_without_a_result_is_an_error(conn, tmp_path):
    root = make_root(tmp_path, body="sys.exit(0)")
    assert conn.execute("SELECT error FROM audit_runs WHERE id=?", (audit.run_and_store(conn, root, "2026"),)).fetchone()[0].endswith("without producing a result")


def test_sys_argv_is_restored_after_a_run(conn, root):
    import sys
    before = list(sys.argv)
    audit.run_and_store(conn, root, "2026")
    assert sys.argv == before


def test_not_configured_when_the_folders_are_missing(conn, tmp_path):
    empty = tmp_path / "none"
    assert audit.configured(empty) is False and audit.status(conn, empty, "2026")["configured"] is False
    half = tmp_path / "half"; (half / "2026").mkdir(parents=True)
    assert audit.configured(half) is False                                                           # no script


def test_only_the_last_five_runs_are_kept(conn, root):
    for _ in range(7):
        audit.run_and_store(conn, root, "2026")
    assert conn.execute("SELECT COUNT(*) FROM audit_runs").fetchone()[0] == 5 and conn.execute("SELECT COUNT(DISTINCT run_id) FROM audit_lines").fetchone()[0] == 5


def test_a_second_check_cannot_start_while_one_runs(tmp_path):
    root = make_root(tmp_path, body="time.sleep(0.6)")
    path = tmp_path / "bg.db"; c = db.connect(path); db.migrate(c); c.close()
    assert audit.start_background(lambda: db.connect(path), root, "2026") is True
    assert audit.is_running() and audit.start_background(lambda: db.connect(path), root, "2026") is False
    for _ in range(40):
        if not audit.is_running():
            break
        time.sleep(0.1)
    assert not audit.is_running()
    c = db.connect(path)
    assert c.execute("SELECT COUNT(*), MIN(status) FROM audit_runs").fetchone()[:] == (1, "done")


# ---------------------------------------------------------------- the 'same as today' comparison with her own report
def write_report(path, lines, sheet="Tous les débits"):
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = sheet
    ws.append(["Compte", "Période", "Date", "Bénéficiaire / objet", "Devise", "Montant", "Statut", "Pièce ou source", "Ordre groupé"])
    for l in lines:
        ws.append([l["compte"], l["periode"], l["date"], l["beneficiaire"], l["devise"], l["montant"], l["statut"], l["source"], l["groupe"]])
    wb.save(path)


def fake_lines():
    ns = {}
    exec(FAKE.replace("{BODY}", "pass").split("def main")[0], ns)                                   # just to keep the definitions in one place
    return [dict(compte="0240 2257", periode="01.04.2026 – 30.06.2026", devise="CHF", date="05.04.2026", beneficiaire="Printer Inc", montant=120.5, statut="justifié", source="x", groupe=""),
            dict(compte="0240 2257", periode="01.04.2026 – 30.06.2026", devise="CHF", date="20.04.2026", beneficiaire="Mystery Ltd", montant=999.0, statut="À JUSTIFIER", source="", groupe=""),
            dict(compte="0240 2258", periode="01.07.2026 – 30.09.2026", devise="EUR", date="02.07.2026", beneficiaire="Bank fees", montant=10.0, statut="couvert", source="y", groupe=""),
            dict(compte="0240 2258", periode="01.07.2026 – 30.09.2026", devise="EUR", date="15.08.2026", beneficiaire="Cloud service", montant=45.25, statut="justifié", source="z", groupe="oui")]


def test_the_comparison_says_same_when_her_report_matches(conn, root):
    audit.run_and_store(conn, root, "2026")
    write_report(root / "2026" / "Controle_justificatifs_2026.xlsx", fake_lines())
    c = audit.compare_with_report(conn, root, "2026")
    assert c["report_found"] and c["readable"] and c["same"] is True and c["only_in_report"] == [] and c["only_in_run"] == []
    assert c["report_counts"] == c["run_counts"] == {"À JUSTIFIER": 1, "justifié": 2, "couvert": 1}


def test_the_comparison_names_every_difference(conn, root):
    audit.run_and_store(conn, root, "2026")
    ls = fake_lines()
    ls[1]["statut"] = "justifié"                                                                      # she had justified it since
    ls.append(dict(ls[0], date="09.09.2026", beneficiaire="Only in her report", montant=7.0))
    write_report(root / "2026" / "Controle_justificatifs_2026.xlsx", ls)
    c = audit.compare_with_report(conn, root, "2026")
    assert c["same"] is False
    assert {(d["beneficiaire"], d["statut"]) for d in c["only_in_report"]} == {("Mystery Ltd", "justifié"), ("Only in her report", "justifié")}
    assert [(d["beneficiaire"], d["statut"]) for d in c["only_in_run"]] == [("Mystery Ltd", "À JUSTIFIER")]


def test_comparison_without_or_with_an_unreadable_report(conn, root):
    audit.run_and_store(conn, root, "2026")
    assert audit.compare_with_report(conn, root, "2026") == {"report_found": False}
    write_report(root / "2026" / "Controle_justificatifs_2026.xlsx", fake_lines(), sheet="Other")
    assert audit.compare_with_report(conn, root, "2026") == {"report_found": True, "readable": False}


def test_her_report_file_is_only_read(conn, root):
    audit.run_and_store(conn, root, "2026")
    rp = root / "2026" / "Controle_justificatifs_2026.xlsx"
    write_report(rp, fake_lines()); before = (rp.read_bytes(), rp.stat().st_mtime_ns)
    audit.compare_with_report(conn, root, "2026")
    assert (rp.read_bytes(), rp.stat().st_mtime_ns) == before


# ---------------------------------------------------------------- API and mounts
def test_api(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from harness.main import app
    monkeypatch.setattr(audit, "ROOT", make_root(tmp_path))
    with TestClient(app) as cl:
        s = cl.get("/api/audit/status").json()
        assert s["configured"] and s["years"] == ["2026"] and s["latest"] is None and s["running"] is False
        assert cl.post("/api/audit/run").json() == {"started": True, "year": "2026"}
        for _ in range(60):
            s = cl.get("/api/audit/status").json()
            if s["latest"]:
                break
            time.sleep(0.1)
        assert s["latest"]["pct_ok"] == 75.0 and len(cl.get("/api/audit/lines?statut=À JUSTIFIER").json()["items"]) == 1
        assert cl.get("/api/audit/compare").json() == {"report_found": False}
        assert cl.get("/api/audit/status?year=1999").status_code == 404


def test_api_reports_not_connected(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from harness.main import app
    monkeypatch.setattr(audit, "ROOT", tmp_path / "nothing")
    with TestClient(app) as cl:
        assert cl.get("/api/audit/status").json()["configured"] is False
        assert cl.post("/api/audit/run").status_code == 404


def test_the_compose_file_mounts_only_the_year_folder_and_the_script_read_only():
    text = (Path(__file__).resolve().parent.parent / "docker-compose.yml").read_text()
    mounts = [ln.strip() for ln in text.splitlines() if "/sources/audit" in ln and ln.strip().startswith("- ")]
    assert len(mounts) == 2 and all(m.endswith(":ro") for m in mounts)
    assert any(m.endswith("/sources/audit/2026:ro") for m in mounts) and any(m.endswith("/sources/audit/Outils:ro") for m in mounts)
