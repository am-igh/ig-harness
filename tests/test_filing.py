"""Bank statement filing: preview rules (API side) and the Mac-side filer's safeguards. Synthetic PDFs only."""
import json
import shutil
import sqlite3
import sys
from pathlib import Path

import pytest

from harness import db, filing, filingspec as fs

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import filer  # noqa: E402

pytestmark = pytest.mark.skipif(shutil.which("pdftotext") is None, reason="needs poppler's pdftotext (present in the container)")


def pdf(line: str) -> bytes:
    """A tiny valid one-page PDF whose first page holds `line`."""
    stream = f"BT /F1 12 Tf 50 750 Td ({line}) Tj ET".encode()
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
            b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream", b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offs = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offs.append(len(out)); out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    x = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode() + b"".join(f"{o:010d} 00000 n \n".encode() for o in offs)
    return out + f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{x}\n%%EOF\n".encode()


Q2 = "01.04.2026 - 30.06.2026 / Trimestrielle: numero 2"
Q3 = "01.07.2026 - 30.09.2026 / Trimestrielle: numero 3"
N_Q2 = "0240000022575501J0000_Relev__de_compte_20260701192239699372.pdf"
N_Q3 = "0240000022575501J0000_Relev__de_compte_20261001150231837768.pdf"


@pytest.fixture
def env(tmp_path):
    root = tmp_path / "audit"; year = root / "2026"; year.mkdir(parents=True)
    (year / N_Q2).write_bytes(pdf(Q2))
    (year / "Expenses").mkdir(); (year / "Expenses" / "invoice.pdf").write_bytes(b"%PDF other")
    data = tmp_path / "data"; data.mkdir()
    c = db.connect(data / "harness.db"); db.migrate(c)
    return c, root, year, data


def stage(env, name, content):
    c, root, year, data = env
    return filing.stage(c, name, content, data_dir=data, root=root)


def test_a_new_quarter_is_previewed_with_account_and_period(env):
    f = stage(env, N_Q3, pdf(Q3))
    assert f["state"] == "new" and (f["period_from"], f["period_to"], f["year"]) == ("2026-07-01", "2026-09-30", "2026")
    assert f["account_label"] == "…5501J" and "0240000022575501" not in json.dumps({k: v for k, v in f.items() if k != "original_name"})


def test_nothing_is_written_to_the_audit_folder_by_the_api_side(env):
    c, root, year, data = env
    before = sorted(p.name for p in year.rglob("*"))
    f = stage(env, N_Q3, pdf(Q3)); filing.approve(c, f["id"], data_dir=data)
    assert sorted(p.name for p in year.rglob("*")) == before


def test_identical_content_is_a_duplicate_even_under_a_browser_copy_name(env):
    f = stage(env, N_Q2.replace(".pdf", "(1).pdf"), pdf(Q2))
    assert f["state"] == "duplicate" and N_Q2 in f["detail"]


def test_same_name_different_content_is_refused_never_overwritten(env):
    f = stage(env, N_Q2, pdf(Q2 + " changed"))
    assert f["state"] == "name_taken"


def test_same_account_and_period_under_a_new_name_is_held_back(env):
    f = stage(env, "0240000022575501J0000_Relev__de_compte_20260801000000000000.pdf", pdf(Q2 + " reissued"))
    assert f["state"] == "same_period"


def test_other_files_years_and_unreadable_ones_are_not_filed(env):
    assert stage(env, "invoice_12.pdf", pdf(Q3))["state"] == "not_statement"
    assert stage(env, N_Q3, pdf("01.01.2027 - 31.03.2027 / Trimestrielle"))["state"] == "wrong_year"
    assert stage(env, N_Q3, pdf("no dates here"))["state"] == "unreadable"
    with pytest.raises(ValueError):
        stage(env, N_Q3, b"not a pdf")


def test_only_a_new_staged_statement_can_be_approved_and_skipped_ones_cannot(env):
    c, root, year, data = env
    d = stage(env, N_Q2, pdf(Q2))
    with pytest.raises(ValueError):
        filing.approve(c, d["id"], data_dir=data)
    n = stage(env, N_Q3, pdf(Q3))
    filing.skip(c, n["id"], data_dir=data)
    with pytest.raises(ValueError):
        filing.approve(c, n["id"], data_dir=data)


def test_approval_then_filer_creates_the_new_file_and_reconcile_records_it(env):
    c, root, year, data = env
    f = stage(env, N_Q3, pdf(Q3)); filing.approve(c, f["id"], data_dir=data)
    out = filer.run_once(data, year)
    assert out == [(f["id"], True, "filed")] and (year / N_Q3).read_bytes() == pdf(Q3)
    assert filing.reconcile(c, data) == [f["id"]]
    assert filing.get(c, f["id"])["status"] == "filed" and not (data / "filing/staging" / f"{f['id']}.pdf").exists()
    assert (year / N_Q2).read_bytes() == pdf(Q2)                         # the existing statement is untouched


def test_filer_does_nothing_without_a_matching_approval_in_the_database(env):
    c, root, year, data = env
    f = stage(env, N_Q3, pdf(Q3))                                        # staged, NOT approved
    (data / "filing/outbox").mkdir(parents=True, exist_ok=True)
    (data / "filing/outbox" / f"{f['id']}.json").write_text(json.dumps({"id": f["id"], "sha256": f["sha256"], "dest_name": N_Q3, "year": "2026"}))
    assert filer.run_once(data, year)[0][1] is False and not (year / N_Q3).exists()


@pytest.mark.parametrize("tamper", ["name", "hash", "year", "staged", "path"])
def test_filer_refuses_tampered_requests(env, tamper):
    c, root, year, data = env
    f = stage(env, N_Q3, pdf(Q3)); filing.approve(c, f["id"], data_dir=data)
    req = data / "filing/outbox" / f"{f['id']}.json"
    r = json.loads(req.read_text())
    if tamper == "name": r["dest_name"] = N_Q3.replace("1001", "1002")
    if tamper == "hash": r["sha256"] = "0" * 64
    if tamper == "year": r["year"] = "2025"
    if tamper == "path": r["dest_name"] = "../" + N_Q3
    if tamper == "staged": (data / "filing/staging" / f"{f['id']}.pdf").write_bytes(pdf(Q3 + " swapped"))
    req.write_text(json.dumps(r))
    before = sorted(p.name for p in root.rglob("*"))
    assert filer.run_once(data, year)[0][1] is False
    assert sorted(p.name for p in root.rglob("*")) == before


def test_filer_never_overwrites_a_file_that_appeared_after_the_preview(env):
    c, root, year, data = env
    f = stage(env, N_Q3, pdf(Q3)); filing.approve(c, f["id"], data_dir=data)
    (year / N_Q3).write_bytes(b"%PDF someone else's file")
    res = filer.run_once(data, year)[0]
    assert res[1] is False and (year / N_Q3).read_bytes() == b"%PDF someone else's file"


def test_an_identical_file_already_there_counts_as_done_without_writing(env):
    c, root, year, data = env
    f = stage(env, N_Q3, pdf(Q3)); filing.approve(c, f["id"], data_dir=data)
    (year / N_Q3).write_bytes(pdf(Q3))
    assert filer.run_once(data, year)[0][1] is True


def test_create_new_file_refuses_to_overwrite(tmp_path):
    p = tmp_path / "x.pdf"; p.write_bytes(b"old")
    with pytest.raises(FileExistsError):
        fs.create_new_file(p, b"new")
    assert p.read_bytes() == b"old"


def test_filer_source_contains_no_delete_rename_or_overwrite_calls():
    src = Path(filer.__file__).read_text() + Path(fs.__file__).read_text()
    for banned in ("unlink(", "os.remove", "os.rename", "shutil.", "rmtree", ".replace(", ".rename(", "write_bytes(", 'open(dest, "w', "O_TRUNC"):
        body = [ln for ln in src.splitlines() if banned in ln and not ln.lstrip().startswith(("#", '"""'))]
        allowed = {"req_file.unlink(missing_ok=True)"}      # the filer removes only its own request file in the harness data folder
        assert all(any(a in ln for a in allowed) for ln in body), (banned, body)


def test_the_api_roundtrip(env, monkeypatch):
    from fastapi.testclient import TestClient
    from harness import main as m
    c, root, year, data = env
    monkeypatch.setattr(filing, "DATA_DIR", data)
    monkeypatch.setattr(filing.audit, "ROOT", root)
    monkeypatch.setattr(m, "_with_conn", lambda fn: fn(db.connect(data / "harness.db")))
    with TestClient(m.app) as cl:
        assert cl.post("/api/filing/upload", content=b"not a pdf", headers={"x-filename": "a.pdf"}).status_code == 422
        r = cl.post("/api/filing/upload", content=pdf(Q3), headers={"x-filename": N_Q3})
        assert r.status_code == 200 and r.json()["state"] == "new" and "account" not in r.json()
        fid = r.json()["id"]
        assert cl.post(f"/api/filing/{fid}/approve").json()["status"] == "approved"
        assert cl.post(f"/api/filing/{fid}/approve").status_code == 409
        filer.run_once(data, year)
        listed = cl.get("/api/filing").json()["items"]
        assert listed[0]["status"] == "filed" and (year / N_Q3).is_file()
        assert cl.post("/api/filing/999/skip").status_code == 404
