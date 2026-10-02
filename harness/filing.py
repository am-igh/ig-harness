"""Bank statement filing, step 1 (API side): receive a statement PDF, check it, show a preview, and on her approval hand a request to
the Mac-side filer (tools/filer.py), which alone can write into the audit folder. This module never writes into her folders:
the year folder is mounted read-only in the container. Staged copies live in ~/IG-Harness-data/filing/ (S2, stays on this Mac).

Rules (filingspec): UBS's own file name is kept; new files only; a file whose content is already in the folder is a duplicate
(also catches browser 're-download (1)' copies); a name already taken by DIFFERENT content, or a statement covering the same
account and period as an existing one, is never filed: she is told, and decides outside the harness."""
import json
import re
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path

from harness import audit, filingspec as fs
from harness.config import DATA_DIR, now_local

STAGING, OUTBOX, DONE = "filing/staging", "filing/outbox", "filing/done"


def _dirs(data_dir: Path) -> tuple[Path, Path, Path]:
    out = tuple(data_dir / d for d in (STAGING, OUTBOX, DONE))
    for d in out:
        d.mkdir(parents=True, exist_ok=True)
    return out


def pdf_first_page(path: Path) -> str:
    try:
        r = subprocess.run(["pdftotext", "-q", "-l", "1", "-layout", str(path), "-"], capture_output=True, text=True, timeout=30)
        return r.stdout if r.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _existing_statements(year_dir: Path) -> list[dict]:
    out = []
    for p in sorted(year_dir.rglob("*.pdf")):
        if re.match(r"^0240.*Relev", p.name, re.I):
            out.append({"name": p.name, "sha": fs.sha256_file(p), "account": fs.account_key(p.name), "period": fs.period_from_text(pdf_first_page(p))})
    return out


def _judge(name: str, sha: str, size: int, period: dict | None, year_dir: Path, existing: list[dict]) -> tuple[str, str]:
    """The state of a candidate statement and a plain-language line about it."""
    if not fs.valid_name(name):
        return "not_statement", "This is not a UBS account statement (its name must look like 0240…_Relevé_de_compte_….pdf). Other documents will be handled by the scan inbox later."
    if period is None:
        return "unreadable", "I could not read the period (dates) on the first page, so I will not file it. Is it a complete UBS statement PDF?"
    if str(period["to"])[:4] != year_dir.name:
        return "wrong_year", f"This statement ends in {period['to'][:4]}, but only the {year_dir.name} folder is connected. Not filed."
    for e in existing:
        if e["sha"] == sha:
            return "duplicate", f"Already in the folder (identical content): {e['name']}. Nothing to do."
    for e in existing:
        if e["name"] == name:
            return "name_taken", f"A different file with the same name is already in the folder ({e['name']}). I never overwrite; not filed."
    for e in existing:
        if e["account"] == fs.account_key(name) and e["period"] and e["period"]["from"] == period["from"] and e["period"]["to"] == period["to"]:
            return "same_period", f"This account already has a statement for the same period ({e['name']}). Not filed, in case it is a re-issued copy; tell me if you want it filed anyway."
    return "new", f"New statement. It will be added to the {year_dir.name} folder as a new file, named exactly as UBS named it."


def stage(conn: sqlite3.Connection, raw_name: str, content: bytes, data_dir: Path | None = None, root: Path | None = None, year: str | None = None) -> dict:
    data_dir, root = data_dir or DATA_DIR, root or audit.ROOT
    name = fs.clean_upload_name(raw_name)
    years = audit.years_available(root)
    if not years:
        raise audit.AuditError("The audit folder is not connected")
    year_dir = root / (year or years[-1])
    if len(content) > fs.MAX_BYTES:
        raise ValueError("File too large for a bank statement (limit 25 MB)")
    if not content.startswith(b"%PDF"):
        raise ValueError("That file is not a PDF")
    staging, _, _ = _dirs(data_dir)
    sha = fs.sha256_bytes(content)
    tmp = staging / f"incoming-{sha[:12]}.pdf"
    tmp.write_bytes(content)
    period = fs.period_from_text(pdf_first_page(tmp))
    state, detail = _judge(name, sha, len(content), period, year_dir, _existing_statements(year_dir))
    with conn:
        fid = conn.execute("INSERT INTO filings (original_name, sha256, size, state, detail, account, period_from, period_to, period_kind, year) VALUES (?,?,?,?,?,?,?,?,?,?)",
                           (name[:200], sha, len(content), state, detail, fs.account_key(name)[:40] if fs.valid_name(name) else None,
                            period and period["from"], period and period["to"], period and period["kind"], year_dir.name)).lastrowid
    if state == "new":
        tmp.replace(staging / f"{fid}.pdf")
    else:
        tmp.unlink(missing_ok=True)
    return get(conn, fid)


def _row(r: sqlite3.Row) -> dict:
    d = dict(r)
    acc = d.get("account")
    d.pop("account", None)                                                                       # the full account prefix stays in the database
    d["account_label"] = ("…" + acc[-9:-4] if acc else None)          # short label only, never the full number
    return d


def get(conn: sqlite3.Connection, fid: int) -> dict:
    return _row(conn.execute("SELECT * FROM filings WHERE id = ?", (fid,)).fetchone())


def approve(conn: sqlite3.Connection, fid: int, data_dir: Path | None = None, now: datetime | None = None) -> dict:
    data_dir = data_dir or DATA_DIR
    r = conn.execute("SELECT * FROM filings WHERE id = ?", (fid,)).fetchone()
    if r is None:
        raise KeyError(fid)
    if r["state"] != "new" or r["status"] != "staged":
        raise ValueError("Only a new, not yet decided statement can be approved")
    staging, outbox, _ = _dirs(data_dir)
    if not (staging / f"{fid}.pdf").is_file() or fs.sha256_file(staging / f"{fid}.pdf") != r["sha256"]:
        raise ValueError("The staged copy is missing or changed; upload the file again")
    when = (now or now_local()).isoformat(timespec="seconds")
    with conn:
        conn.execute("UPDATE filings SET status='approved', decided_at=? WHERE id=?", (when, fid))
    (outbox / f"{fid}.json").write_text(json.dumps({"id": fid, "sha256": r["sha256"], "dest_name": r["original_name"], "year": r["year"], "approved_at": when}))
    return get(conn, fid)


def skip(conn: sqlite3.Connection, fid: int, data_dir: Path | None = None) -> dict:
    data_dir = data_dir or DATA_DIR
    r = conn.execute("SELECT status FROM filings WHERE id = ?", (fid,)).fetchone()
    if r is None:
        raise KeyError(fid)
    if r["status"] in ("approved", "filed"):
        raise ValueError("Already approved or filed")
    with conn:
        conn.execute("UPDATE filings SET status='skipped', decided_at=datetime('now') WHERE id=?", (fid,))
    (data_dir / STAGING / f"{fid}.pdf").unlink(missing_ok=True)
    return get(conn, fid)


def reconcile(conn: sqlite3.Connection, data_dir: Path | None = None) -> list[int]:
    """Read the filer's result files; mark rows filed/failed; remove our own staged copy. Returns ids newly filed."""
    data_dir = data_dir or DATA_DIR
    _, _, done = _dirs(data_dir)
    newly = []
    for f in sorted(p for p in done.glob("*.json") if not p.name.startswith("doc-")):      # doc-*.json belong to scans.reconcile
        try:
            res = json.loads(f.read_text())
            fid = int(res["id"])
        except (ValueError, KeyError, OSError):
            continue
        with conn:
            ok = conn.execute("UPDATE filings SET status=?, result=?, filed_at=datetime('now') WHERE id=? AND status='approved'",
                              ("filed" if res.get("ok") else "failed", str(res.get("message", ""))[:300], fid)).rowcount
        if ok and res.get("ok"):
            newly.append(fid)
        if res.get("ok"):
            (data_dir / STAGING / f"{fid}.pdf").unlink(missing_ok=True)
        f.unlink(missing_ok=True)
    return newly


def recent(conn: sqlite3.Connection, limit: int = 30) -> list[dict]:
    return [_row(r) for r in conn.execute("SELECT * FROM filings ORDER BY id DESC LIMIT ?", (limit,))]
