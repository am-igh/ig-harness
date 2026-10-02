"""Scanned invoices and receipts: reading, proposals, duplicates/versions, payment matching, approval, and the filer's folder rules."""
import json
import os
import shutil
import sqlite3
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from harness import db, filingspec as fs, scans

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import filer  # noqa: E402
from test_filing import pdf  # noqa: E402


class FakeGateway:
    def __init__(self, answer=None, ok=True):
        self.answer, self.ok, self.calls = answer, ok, []

    def complete(self, prompt, **kw):
        self.calls.append((prompt, kw))
        return SimpleNamespace(ok=self.ok, text=json.dumps(self.answer) if isinstance(self.answer, dict) else (self.answer or ""), reason="" if self.ok else "down", model="fake")


ANSWER = {"type": "invoice_received", "supplier": "Alber Rolle SA", "number": "002131", "amount": "2'972.75", "currency": "chf", "date": "2026-01-20"}


@pytest.fixture
def env(tmp_path, monkeypatch):
    root = tmp_path / "audit"; year = root / "2026"
    (year / "Expenses").mkdir(parents=True); (year / "Income").mkdir()
    data = tmp_path / "data"; data.mkdir()
    inbox = tmp_path / "inbox"; inbox.mkdir()
    c = db.connect(data / "harness.db"); db.migrate(c)
    monkeypatch.setattr(scans, "extract_text", lambda p, pages=3: "Facture 002131 Alber Rolle SA total CHF 2'972.75 " * 3)
    return SimpleNamespace(c=c, root=root, year=year, data=data, inbox=inbox)


def new_scan(env, content=None, name="Scan.pdf"):
    content = content or pdf("a scanned invoice " + os.urandom(4).hex())
    sid, _ = scans.register(env.c, name, content, "folder", env.data)
    return sid, content


def read(env, sid, answer=ANSWER):
    return scans.read_scan(env.c, FakeGateway(answer), sid, env.root, env.data)


# ------------------------------------------------------------------ naming (pure)
def test_names_follow_her_convention():
    assert fs.doc_name("invoice_received", "Alber Rolle SA", "002131", 2972.75, "CHF", "2026-01-29", "Expenses") == "Alber_Rolle_SA_Facture_002131_CHF2972.75_paye_29.01.2026.pdf"
    assert fs.doc_name("invoice_issued", "Gablinger", None, 20000, "CHF", "2026-01-17", "Income") == "Gablinger_Facture_CHF20000.00_recu_17.01.2026.pdf"
    assert fs.doc_name("receipt", "Société Générale", "A/12", 9.5, "EUR", None, "Expenses") == "Societe_Generale_Recu_A12_EUR9.50.pdf"
    assert fs.doc_name("invoice_received", "X", None, 5, "CHF", None, "Expenses", 2) == "X_Facture_CHF5.00_v2.pdf"


def test_incomplete_or_dangerous_inputs_give_no_name():
    assert fs.doc_name("invoice_received", "", None, 5, "CHF", None, "Expenses") is None
    assert fs.doc_name("invoice_received", "X", None, None, "CHF", None, "Expenses") is None
    assert fs.doc_name("invoice_received", "X", None, 5, "JPY", None, "Expenses") is None
    assert fs.doc_name("contract", "X", None, 5, "CHF", None, "Expenses") is None
    n = fs.doc_name("receipt", "../../etc/passwd", "a/b", 5, "CHF", None, "Expenses")
    assert n and "/" not in n and ".." not in n and fs.valid_doc_name(n)


@pytest.mark.parametrize("bad", ["../x.pdf", "a/b.pdf", ".hidden.pdf", "x.exe", "a b.pdf", "x" * 200 + ".pdf", ""])
def test_unsafe_document_names_are_invalid(bad):
    assert not fs.valid_doc_name(bad)


def test_type_decides_folder_and_unclear_types_wait():
    assert [fs.folder_for_type(t) for t in ("invoice_received", "receipt", "invoice_issued", "contract", "other", None)] == ["Expenses", "Expenses", "Income", None, None, None]


# ------------------------------------------------------------------ reading and proposing
def test_a_scan_is_read_and_proposed_without_filing_anything(env):
    sid, _ = new_scan(env)
    before = sorted(p.name for p in env.root.rglob("*"))
    s = read(env, sid)
    assert (s["status"], s["supplier"], s["amount"], s["currency"], s["folder"]) == ("proposed", "Alber Rolle SA", 2972.75, "CHF", "Expenses")
    assert s["proposed_name"] == "Alber_Rolle_SA_Facture_002131_CHF2972.75.pdf" and "No audit check yet" in s["note"]
    assert sorted(p.name for p in env.root.rglob("*")) == before


def test_the_model_is_called_through_the_gateway_with_the_local_only_job_and_source(env):
    sid, _ = new_scan(env)
    gw = FakeGateway(ANSWER)
    scans.read_scan(env.c, gw, sid, env.root, env.data)
    kw = gw.calls[0][1]
    assert kw["job"] == "doc_read" and kw["source"] == "invoice" and "untrusted" in gw.calls[0][0]


def test_document_text_and_ibans_are_never_stored(env, monkeypatch):
    monkeypatch.setattr(scans, "extract_text", lambda p, pages=3: "IBAN CH93 0076 2011 6238 5295 7 SECRET-LINE total 10.00 " * 3)
    sid, _ = new_scan(env)
    read(env, sid)
    dump = json.dumps([tuple(r) for r in env.c.execute("SELECT * FROM scans")])
    assert "CH93" not in dump and "SECRET-LINE" not in dump


def test_payment_date_is_filled_from_the_unjustified_payment_that_matches(env):
    cols = [r[1] for r in env.c.execute("PRAGMA table_info(audit_runs)")]
    vals = {"year": "2026", "root": "x", "started_at": "2026-10-02", "finished_at": "2026-10-02", "status": "done", "input_signature": "s", "counts": "{}"}
    use = {k: v for k, v in vals.items() if k in cols}
    rid = env.c.execute(f"INSERT INTO audit_runs ({','.join(use)}) VALUES ({','.join('?' * len(use))})", list(use.values())).lastrowid
    env.c.execute("INSERT INTO audit_lines (run_id, date_iso, beneficiaire, devise, montant, statut) VALUES (?,?,?,?,?,?)", (rid, "2026-01-29", "ALBER ROLLE SA", "CHF", 2972.75, "À JUSTIFIER"))
    env.c.execute("INSERT INTO audit_lines (run_id, date_iso, beneficiaire, devise, montant, statut) VALUES (?,?,?,?,?,?)", (rid, "2026-02-02", "OTHER", "CHF", 2972.75, "justifié"))
    env.c.commit()
    sid, _ = new_scan(env)
    s = read(env, sid)
    assert s["paid_date"] == "2026-01-29" and s["proposed_name"].endswith("_paye_29.01.2026.pdf") and "Matches the unjustified payment" in s["note"]
    # two equal payments: the supplier's name picks the right one; with no name match she is asked
    env.c.execute("INSERT INTO audit_lines (run_id, date_iso, beneficiaire, devise, montant, statut) VALUES (?,?,?,?,?,?)", (rid, "2026-03-05", "SOMEONE", "CHF", 2972.75, "À JUSTIFIER")); env.c.commit()
    assert scans.suggest_payment(env.c, 2972.75, "CHF", "Alber Rolle SA")[0] == "2026-01-29"
    assert scans.suggest_payment(env.c, 2972.75, "CHF", "Unknown Co")[0] is None
    assert scans.suggest_payment(env.c, 1.0, "CHF", "Alber Rolle SA")[0] is None


def test_identical_content_already_in_the_folder_is_a_duplicate_and_not_read(env):
    content = pdf("already filed")
    (env.year / "Expenses" / "Old_Name.pdf").write_bytes(content)
    sid, _ = new_scan(env, content)
    gw = FakeGateway(ANSWER)
    s = scans.read_scan(env.c, gw, sid, env.root, env.data)
    assert s["status"] == "duplicate" and "Old_Name.pdf" in s["note"] and gw.calls == []


def test_a_different_file_with_the_same_name_becomes_a_new_version_never_an_overwrite(env):
    (env.year / "Expenses" / "Alber_Rolle_SA_Facture_002131_CHF2972.75.pdf").write_bytes(b"%PDF other")
    sid, _ = new_scan(env)
    s = read(env, sid)
    assert s["proposed_name"] == "Alber_Rolle_SA_Facture_002131_CHF2972.75_v2.pdf" and "_v2" in s["note"]
    (env.year / "Expenses" / s["proposed_name"]).write_bytes(b"%PDF other 2")
    assert scans.propose(env.c, sid, env.root)["proposed_name"].endswith("_v3.pdf")


def test_contracts_and_unclear_documents_wait_for_her_folder_choice(env):
    sid, _ = new_scan(env)
    s = read(env, sid, dict(ANSWER, type="contract"))
    assert s["folder"] is None and s["proposed_name"] is None and "Choose the folder" in s["note"]
    with pytest.raises(ValueError):
        scans.approve(env.c, sid, env.data)
    s = scans.edit(env.c, sid, {"folder": "Expenses", "doc_type": "receipt"}, env.root)
    assert s["proposed_name"] == "Alber_Rolle_SA_Recu_002131_CHF2972.75.pdf"


def test_a_model_failure_or_unreadable_page_leaves_a_scan_she_can_fill_in(env):
    sid, _ = new_scan(env)
    s = scans.read_scan(env.c, FakeGateway(None, ok=False), sid, env.root, env.data)
    assert s["status"] == "proposed" and "Fill in" in s["note"] and s["proposed_name"] is None
    s = scans.edit(env.c, sid, {"doc_type": "receipt", "supplier": "Kiosk", "amount": "12.5", "currency": "chf"}, env.root)
    assert s["proposed_name"] == "Kiosk_Recu_CHF12.50.pdf"


def test_edits_are_validated(env):
    sid, _ = new_scan(env); read(env, sid)
    for bad in ({"currency": "JPY"}, {"amount": "-3"}, {"amount": "abc"}, {"doc_date": "yesterday"}, {"folder": "Contracts"}, {"doc_type": "x"}):
        with pytest.raises(ValueError):
            scans.edit(env.c, sid, bad, env.root)
    assert scans.edit(env.c, sid, {"paid_date": "2026-02-01"}, env.root)["proposed_name"].endswith("_paye_01.02.2026.pdf")


# ------------------------------------------------------------------ finding scans
def test_the_scan_folder_is_only_read_and_unfinished_or_hidden_files_are_skipped(env):
    (env.inbox / "Scan.pdf").write_bytes(pdf("one")); (env.inbox / ".DS_Store").write_bytes(b"x"); (env.inbox / "notes.txt").write_text("t")
    (env.inbox / "Scan 2.jpeg").write_bytes(b"\xff\xd8jpeg")
    before = {p.name: p.read_bytes() for p in env.inbox.iterdir()}
    assert scans.discover(env.c, env.inbox, env.data, now=time.time()) == []                         # just written: wait
    ids = scans.discover(env.c, env.inbox, env.data, now=time.time() + 60)
    assert len(ids) == 2 and scans.discover(env.c, env.inbox, env.data, now=time.time() + 60) == []   # nothing registered twice
    assert {p.name: p.read_bytes() for p in env.inbox.iterdir()} == before                              # untouched
    jpeg = env.c.execute("SELECT status, note FROM scans WHERE original_name='Scan 2.jpeg'").fetchone()
    assert jpeg["status"] == "unreadable" and "PDF" in jpeg["note"]


def test_the_same_content_scanned_twice_is_one_scan(env):
    a, new_a = scans.register(env.c, "Scan.pdf", pdf("same"), "folder", env.data)
    b, new_b = scans.register(env.c, "Scan 2.pdf", pdf("same"), "folder", env.data)
    assert a == b and (new_a, new_b) == (True, False)


def test_tick_reads_one_waiting_scan_per_pass(env):
    (env.inbox / "a.pdf").write_bytes(pdf("a")); (env.inbox / "b.pdf").write_bytes(pdf("b"))
    old = time.time() - 100
    for p in env.inbox.iterdir():
        os.utime(p, (old, old))
    gw = FakeGateway(ANSWER)
    assert scans.tick(env.c, gw, env.inbox, env.data, env.root) == 1
    assert sorted(r[0] for r in env.c.execute("SELECT status FROM scans")) == ["found", "proposed"]


# ------------------------------------------------------------------ approval and the filer
def approved(env, **edits):
    sid, content = new_scan(env); read(env, sid)
    if edits:
        scans.edit(env.c, sid, edits, env.root)
    return sid, content, scans.approve(env.c, sid, env.data)


def test_approval_writes_only_a_request_and_nothing_into_her_folders(env):
    before = sorted(p.name for p in env.root.rglob("*"))
    sid, _, s = approved(env)
    assert s["status"] == "approved" and (env.data / "filing/outbox" / f"doc-{sid}.json").is_file()
    assert sorted(p.name for p in env.root.rglob("*")) == before


def test_filer_adds_the_document_as_a_new_file_in_expenses_and_reconcile_records_it(env):
    sid, content, s = approved(env)
    out = filer.run_once(env.data, env.year)
    assert out == [(sid, True, "filed")] and (env.year / "Expenses" / s["proposed_name"]).read_bytes() == content
    assert scans.reconcile(env.c, env.data) == [sid] and scans.get(env.c, sid)["status"] == "filed"
    assert scans.summary(env.c)["filed_this_week"] == 1


def test_income_documents_go_to_income(env):
    sid, content, s = approved(env, doc_type="invoice_issued")
    filer.run_once(env.data, env.year)
    assert (env.year / "Income" / s["proposed_name"]).is_file() and not list((env.year / "Expenses").iterdir())


@pytest.mark.parametrize("tamper", ["name", "hash", "year", "folder", "path", "own_copy", "kind_statement"])
def test_filer_refuses_tampered_document_requests(env, tamper):
    sid, _, s = approved(env)
    req = env.data / "filing/outbox" / f"doc-{sid}.json"
    r = json.loads(req.read_text())
    if tamper == "name": r["dest_name"] = "Other_Facture_CHF1.00.pdf"
    if tamper == "hash": r["sha256"] = "0" * 64
    if tamper == "year": r["year"] = "2025"
    if tamper == "folder": r["folder"] = "Reference"
    if tamper == "path": r["dest_name"] = "../x.pdf"
    if tamper == "own_copy": (env.data / "filing/scans" / f"{sid}.pdf").write_bytes(pdf("swapped"))
    if tamper == "kind_statement": r.pop("kind")
    req.write_text(json.dumps(r))
    (env.year / "Reference").mkdir(exist_ok=True)
    before = sorted(p.name for p in env.root.rglob("*"))
    assert filer.run_once(env.data, env.year)[0][1] is False
    assert sorted(p.name for p in env.root.rglob("*")) == before


def test_filer_refuses_a_folder_that_is_a_symlink_or_missing(env):
    sid, _, s = approved(env)
    shutil.rmtree(env.year / "Expenses"); (env.year / "Elsewhere").mkdir(); os.symlink(env.year / "Elsewhere", env.year / "Expenses")
    assert filer.run_once(env.data, env.year)[0][1] is False and not list((env.year / "Elsewhere").iterdir())


def test_filer_never_overwrites_a_file_that_appeared_after_approval(env):
    sid, _, s = approved(env)
    (env.year / "Expenses" / s["proposed_name"]).write_bytes(b"%PDF someone else's")
    assert filer.run_once(env.data, env.year)[0][1] is False
    assert (env.year / "Expenses" / s["proposed_name"]).read_bytes() == b"%PDF someone else's"


def test_a_skipped_or_unapproved_scan_is_never_filed_even_with_a_request_file(env):
    sid, _ = new_scan(env); s = read(env, sid)
    (env.data / "filing/outbox").mkdir(parents=True, exist_ok=True)
    (env.data / "filing/outbox" / f"doc-{sid}.json").write_text(json.dumps({"kind": "document", "id": sid, "sha256": s["sha256"], "dest_name": s["proposed_name"], "folder": "Expenses", "year": "2026"}))
    assert filer.run_once(env.data, env.year)[0][1] is False and not list((env.year / "Expenses").iterdir())


def test_statement_and_document_results_do_not_mix(env):
    from harness import filing
    sid, _, s = approved(env)
    filer.run_once(env.data, env.year)
    assert filing.reconcile(env.c, env.data) == []                                   # leaves doc-*.json for scans.reconcile
    assert scans.reconcile(env.c, env.data) == [sid]


def test_api_roundtrip(env, monkeypatch):
    from fastapi.testclient import TestClient
    from harness import main as m
    monkeypatch.setattr(m, "_with_conn", lambda fn: fn(db.connect(env.data / "harness.db")))
    monkeypatch.setattr(scans, "DATA_DIR", env.data); monkeypatch.setattr(scans.audit, "ROOT", env.root)
    sid, _ = new_scan(env); read(env, sid)
    with TestClient(m.app) as cl:
        assert cl.get("/api/scans").json()["summary"]["to_confirm"] == 1
        assert cl.post(f"/api/scans/{sid}/edit", json={"supplier": "New Co"}).json()["supplier"] == "New Co"
        assert cl.post(f"/api/scans/{sid}/edit", json={"currency": "JPY"}).status_code == 422
        assert cl.post(f"/api/scans/{sid}/approve").json()["status"] == "approved"
        assert cl.post(f"/api/scans/{sid}/approve").status_code == 409 and cl.post(f"/api/scans/{sid}/skip").status_code == 409
        assert cl.post("/api/scans/999/skip").status_code == 404
        assert cl.post("/api/scans/upload", content=b"nope", headers={"x-filename": "a.pdf"}).status_code == 422


# ------------------------------------------------------------------ Image Capture "combine into single document" appends a page to Scan.pdf
def pdf_pages(*lines):
    """A multi-page PDF built by joining one-page PDFs with poppler (pdfunite)."""
    import subprocess, tempfile
    with tempfile.TemporaryDirectory() as t:
        names = []
        for i, ln in enumerate(lines):
            p = Path(t) / f"{i}.pdf"; p.write_bytes(pdf(ln)); names.append(str(p))
        out = Path(t) / "out.pdf"
        subprocess.run(["pdfunite", *names, str(out)], check=True)
        return out.read_bytes()


def test_a_page_appended_to_an_already_seen_scan_is_split_at_once_and_the_folder_file_is_untouched(env):
    old = time.time() - 100
    first = env.inbox / "Scan.pdf"; first.write_bytes(pdf("invoice page one")); os.utime(first, (old, old))
    ids1 = scans.discover(env.c, env.inbox, env.data)
    assert len(ids1) == 1
    combined = pdf_pages("invoice page one", "Swiss Life statement")
    first.write_bytes(combined); os.utime(first, (old + 5, old + 5))                    # Image Capture appended a page to the same file
    ids2 = scans.discover(env.c, env.inbox, env.data)
    parent = env.c.execute("SELECT * FROM scans WHERE id=?", (ids2[0],)).fetchone()
    assert parent["pages"] == 2 and parent["status"] == "skipped" and "2 pages" in parent["note"]
    kids = env.c.execute("SELECT * FROM scans WHERE parent_id=? ORDER BY id", (ids2[0],)).fetchall()
    assert [k["original_name"] for k in kids] == ["Scan.pdf (page 1)", "Scan.pdf (page 2)"] and all(k["pages"] == 1 for k in kids)
    assert [k["status"] for k in kids] == ["skipped", "found"]                          # page 1 is the scan already seen; only the new page is offered
    assert first.read_bytes() == combined                                                 # the file in Scan-Inbox is exactly as Image Capture left it
    assert env.c.execute("SELECT status FROM scans WHERE id=?", (ids1[0],)).fetchone()[0] == "found"       # the first scan's own copy is intact


def test_a_new_multi_page_file_with_a_new_name_is_kept_whole_and_can_be_split_by_hand(env):
    sid, _ = scans.register(env.c, "Scan 2.pdf", pdf_pages("a", "b", "c"), "folder", env.data)
    assert env.c.execute("SELECT pages, status FROM scans WHERE id=?", (sid,)).fetchone()[:] == (3, "found")
    ids = scans.split_pages(env.c, sid, env.data)
    assert len(ids) == 3 and env.c.execute("SELECT status FROM scans WHERE id=?", (sid,)).fetchone()[0] == "skipped"
    with pytest.raises(ValueError):
        scans.split_pages(env.c, ids[0], env.data)                                         # one page: nothing to split


def test_a_scan_that_looks_like_another_one_is_flagged(env):
    a, _ = new_scan(env); b, _ = new_scan(env)
    read(env, a); s = read(env, b)
    assert f"same document as scan #{a}" in s["note"]


def test_a_page_that_comes_back_unchanged_is_not_offered_twice_and_only_the_new_page_remains(env):
    old = time.time() - 100
    f = env.inbox / "Scan.pdf"; f.write_bytes(pdf("invoice page one")); os.utime(f, (old, old))
    first = scans.discover(env.c, env.inbox, env.data)[0]
    f.write_bytes(pdf_pages("invoice page one", "Swiss Life page one")); os.utime(f, (old + 5, old + 5))
    parent = scans.discover(env.c, env.inbox, env.data)[0]
    kids = {k["original_name"]: k for k in env.c.execute("SELECT * FROM scans WHERE parent_id=?", (parent,))}
    assert kids["Scan.pdf (page 1)"]["status"] == "skipped" and f"scan #{first}" in kids["Scan.pdf (page 1)"]["note"]
    assert kids["Scan.pdf (page 2)"]["status"] == "found"
    f.write_bytes(pdf_pages("invoice page one", "Swiss Life page one", "Swiss Life page two")); os.utime(f, (old + 9, old + 9))
    parent3 = scans.discover(env.c, env.inbox, env.data)[0]
    st = {k["original_name"]: k["status"] for k in env.c.execute("SELECT * FROM scans WHERE parent_id=?", (parent3,))}
    assert st == {"Scan.pdf (page 1)": "skipped", "Scan.pdf (page 2)": "skipped", "Scan.pdf (page 3)": "found"}


def test_several_scans_can_be_combined_into_one_document_in_the_order_given(env):
    a, _ = scans.register(env.c, "p1.pdf", pdf("statement page one"), "folder", env.data)
    b, _ = scans.register(env.c, "p2.pdf", pdf("statement page two"), "folder", env.data)
    new = scans.merge_scans(env.c, [b, a], env.data)
    row = env.c.execute("SELECT * FROM scans WHERE id=?", (new,)).fetchone()
    assert row["pages"] == 2 and row["status"] == "found"
    import subprocess
    txt = subprocess.run(["pdftotext", "-layout", str(env.data / "filing/scans" / f"{new}.pdf"), "-"], capture_output=True, text=True).stdout
    assert txt.index("page two") < txt.index("page one")
    assert [env.c.execute("SELECT status FROM scans WHERE id=?", (i,)).fetchone()[0] for i in (a, b)] == ["skipped", "skipped"]
    with pytest.raises(ValueError):
        scans.merge_scans(env.c, [new], env.data)
    with pytest.raises(ValueError):
        scans.merge_scans(env.c, [a, new], env.data)                                      # a is already combined away


def test_merge_endpoint(env, monkeypatch):
    from fastapi.testclient import TestClient
    from harness import main as m
    monkeypatch.setattr(m, "_with_conn", lambda fn: fn(db.connect(env.data / "harness.db")))
    monkeypatch.setattr(scans, "DATA_DIR", env.data)
    a, _ = scans.register(env.c, "p1.pdf", pdf("one"), "folder", env.data); b, _ = scans.register(env.c, "p2.pdf", pdf("two"), "folder", env.data)
    with TestClient(m.app) as cl:
        assert cl.post("/api/scans/merge", json={"ids": [a]}).status_code == 409
        assert cl.post("/api/scans/merge", json={"ids": [a, 9999]}).status_code == 404
        assert "id" in cl.post("/api/scans/merge", json={"ids": [a, b]}).json()


def test_a_statement_and_a_document_with_the_same_id_never_confuse_each_other(env):
    """Regression (2 Oct 2026): result files were named by id only, so a document result overwrote a bank statement's status."""
    from harness import filing
    stmt_name = "0240000022575501J0000_Relev__de_compte_20261001150231837768.pdf"
    f = filing.stage(env.c, stmt_name, pdf("01.07.2026 - 30.09.2026 / Trimestrielle"), data_dir=env.data, root=env.root)
    filing.approve(env.c, f["id"], data_dir=env.data)
    sid, content, s = approved(env)
    assert f["id"] == sid == 1
    results = filer.run_once(env.data, env.year)
    assert sorted(r[1] for r in results) == [True, True]
    assert filing.reconcile(env.c, env.data) == [1] and scans.reconcile(env.c, env.data) == [1]
    assert filing.get(env.c, 1)["status"] == "filed" and scans.get(env.c, 1)["status"] == "filed"
    assert (env.year / stmt_name).is_file() and (env.year / "Expenses" / s["proposed_name"]).is_file()


def test_a_picture_of_each_page_is_available_and_only_for_real_pages(env):
    sid, _ = scans.register(env.c, "two.pdf", pdf_pages("a", "b"), "folder", env.data)
    png = scans.page_image(env.c, sid, 1, 300, env.data)
    assert png and png.startswith(b"\x89PNG") and scans.page_image(env.c, sid, 2, 300, env.data)
    assert scans.page_image(env.c, sid, 3, 300, env.data) is None and scans.page_image(env.c, 999, 1, 300, env.data) is None
