#!/usr/bin/env python3
"""Mac-side filer: the ONLY thing that can write into her audit folder. Standard library only.

It files bank statements (into the year folder) and scanned invoices/receipts (into its Expenses or Income folder). It creates NEW files and nothing else: no overwrite (O_EXCL), no delete, no rename, no folders. It acts only on a request that
Anne-Marie approved in the app, and re-checks everything itself before writing:
  - the harness database (opened read-only) says this filing is 'approved', with the same hash;
  - the staged copy still has that hash;
  - the file name passes the shared rules (harness/filingspec.py) and is a plain name (no path);
  - the destination folder is exactly the connected year folder (AUDIT_YEAR_DIR in .env), nothing else;
  - nothing exists at the destination (an identical file already there counts as done; a different one is a failure).
After writing it re-reads the new file and compares its hash. The result goes to ~/IG-Harness-data/filing/done/<id>.json.

  python3 tools/filer.py once     file whatever is approved now (also run by the refresh agent every few seconds)
"""
import json
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from harness import filingspec as fs      # noqa: E402

DATA = Path(os.environ.get("IG_DATA_DIR", Path.home() / "IG-Harness-data"))


def year_dir_from_env(root: Path = ROOT) -> Path | None:
    v = os.environ.get("AUDIT_YEAR_DIR")
    if not v and (root / ".env").is_file():
        for line in (root / ".env").read_text().splitlines():
            if line.startswith("AUDIT_YEAR_DIR="):
                v = line.split("=", 1)[1].strip().strip('"\'')
    return Path(v).expanduser() if v else None


def _result(data: Path, fid: int, ok: bool, message: str, prefix: str = "") -> None:
    done = data / "filing" / "done"
    done.mkdir(parents=True, exist_ok=True)
    (done / f"{prefix}{fid}.json").write_text(json.dumps({"id": fid, "ok": ok, "message": message}))


def process_document(data: Path, year_dir: Path | None, req_file: Path, req: dict) -> tuple[int | None, bool, str]:
    """A scanned invoice or receipt: a NEW file inside <year>/Expenses or <year>/Income, nowhere else."""
    fid = int(req["id"])

    def fail(msg: str):
        _result(data, fid, False, msg, "doc-")
        req_file.unlink(missing_ok=True)
        return fid, False, msg
    name, folder = str(req.get("dest_name", "")), str(req.get("folder", ""))
    if year_dir is None or not year_dir.is_dir():
        return fail("the audit folder is not available on the Mac")
    if str(req.get("year")) != year_dir.name:
        return fail("the request is for a different year than the connected folder")
    if folder not in fs.DOC_FOLDERS:
        return fail("this folder is not one that documents may be added to")
    if not fs.valid_doc_name(name) or Path(name).name != name:
        return fail("the file name is not acceptable")
    target = year_dir / folder
    if not target.is_dir() or target.is_symlink() or target.resolve().parent != year_dir.resolve():
        return fail(f"there is no {folder} folder in {year_dir.name}")
    try:
        db = sqlite3.connect(f"file:{data / 'harness.db'}?mode=ro", uri=True)
        row = db.execute("SELECT status, sha256, proposed_name, folder FROM scans WHERE id = ?", (fid,)).fetchone()
        db.close()
    except sqlite3.Error:
        return fail("could not confirm your approval in the database")
    if not row or row[0] != "approved" or row[1] != req.get("sha256") or row[2] != name or row[3] != folder:
        return fail("no matching approval found; nothing was filed")
    own = data / "filing" / "scans" / f"{fid}.pdf"
    if not own.is_file() or fs.sha256_file(own) != row[1]:
        return fail("the stored copy is missing or changed; nothing was filed")
    dest = target / name
    if dest.exists():
        if dest.is_file() and fs.sha256_file(dest) == row[1]:
            _result(data, fid, True, "already in the folder with identical content; nothing written", "doc-")
            req_file.unlink(missing_ok=True)
            return fid, True, "already there"
        return fail("a different file with this name already exists; nothing was overwritten")
    try:
        fs.create_new_file(dest, own.read_bytes())
    except FileExistsError:
        return fail("a file with this name appeared just now; nothing was overwritten")
    except OSError as e:
        return fail(f"could not write: {e.strerror or type(e).__name__}")
    if fs.sha256_file(dest) != row[1]:
        return fail("the new file did not verify after writing; it was left in place for you to check")
    _result(data, fid, True, f"filed in {year_dir.name}/{folder}/", "doc-")
    req_file.unlink(missing_ok=True)
    return fid, True, "filed"


def process(data: Path, year_dir: Path | None, req_file: Path) -> tuple[int | None, bool, str]:
    try:
        req = json.loads(req_file.read_text())
        fid = int(req["id"])
    except (ValueError, KeyError, OSError):
        return None, False, "unreadable request"
    if req.get("kind") == "document":
        return process_document(data, year_dir, req_file, req)

    def fail(msg: str):
        _result(data, fid, False, msg, "st-")
        req_file.unlink(missing_ok=True)
        return fid, False, msg
    name = str(req.get("dest_name", ""))
    if year_dir is None or not year_dir.is_dir():
        return fail("the audit folder is not available on the Mac")
    if str(req.get("year")) != year_dir.name:
        return fail("the request is for a different year than the connected folder")
    if not fs.valid_name(name) or Path(name).name != name:
        return fail("the file name is not an acceptable UBS statement name")
    try:
        db = sqlite3.connect(f"file:{data / 'harness.db'}?mode=ro", uri=True)
        row = db.execute("SELECT status, sha256, original_name FROM filings WHERE id = ?", (fid,)).fetchone()
        db.close()
    except sqlite3.Error:
        return fail("could not confirm your approval in the database")
    if not row or row[0] != "approved" or row[1] != req.get("sha256") or row[2] != name:
        return fail("no matching approval found; nothing was filed")
    staged = data / "filing" / "staging" / f"{fid}.pdf"
    if not staged.is_file() or fs.sha256_file(staged) != row[1]:
        return fail("the staged copy is missing or changed; nothing was filed")
    content = staged.read_bytes()
    dest = year_dir / name
    if dest.exists():
        if dest.is_file() and fs.sha256_file(dest) == row[1]:
            _result(data, fid, True, "already in the folder with identical content; nothing written", "st-")
            req_file.unlink(missing_ok=True)
            return fid, True, "already there"
        return fail("a different file with this name already exists; nothing was overwritten")
    try:
        fs.create_new_file(dest, content)
    except FileExistsError:
        return fail("a file with this name appeared just now; nothing was overwritten")
    except OSError as e:
        return fail(f"could not write: {e.strerror or type(e).__name__}")
    if fs.sha256_file(dest) != row[1]:
        return fail("the new file did not verify after writing; it was left in place for you to check")
    _result(data, fid, True, f"filed in {year_dir.name}/", "st-")
    req_file.unlink(missing_ok=True)
    return fid, True, "filed"


def run_once(data: Path = DATA, year_dir: Path | None = None) -> list[tuple]:
    year_dir = year_dir or year_dir_from_env()
    box = data / "filing" / "outbox"
    return [process(data, year_dir, f) for f in sorted(box.glob("*.json"))] if box.is_dir() else []


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "once":
        res = run_once()
        for r in res:
            print(r)
        print(f"{len(res)} request(s) processed.")
    else:
        sys.exit(__doc__)
