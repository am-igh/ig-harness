"""Audit readiness: Anne-Marie's own checker, `controle_justificatifs.py`, run UNCHANGED inside the harness.

How it works, as chosen by her on 2 Oct 2026 (option A):
  * the checker script and the year folder are mounted read-only (docker-compose.yml); nothing is installed on her Mac;
  * the script is imported from its own file and its `main()` is called; the one thing replaced is `ecrire_xlsx`, so its
    report is captured into the database instead of being written into her audit folder (nothing in her folders is written);
  * statements, receipts and amounts are confidential (S2): they stay on this Mac, and no IBAN is stored (only the short account label).
The result is compared with her existing report (Controle_justificatifs_<year>.xlsx), which is the 'same results as today' test."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import re
import sqlite3
import sys
import threading
from datetime import date, datetime
from pathlib import Path

from harness.config import now_local

ROOT = Path(os.environ.get("IG_AUDIT_DIR", "/sources/audit"))
SCRIPT_REL = "Outils/controle_justificatifs.py"
STATUSES = ("À JUSTIFIER", "justifié", "couvert")
KEEP_RUNS = 5
_lock = threading.Lock()


class AuditError(Exception):
    pass


def years_available(root: Path = ROOT) -> list[str]:
    return sorted(d.name for d in root.glob("[0-9][0-9][0-9][0-9]") if d.is_dir()) if root.is_dir() else []


def script_path(root: Path = ROOT) -> Path:
    return root / SCRIPT_REL


def configured(root: Path = ROOT, year: str | None = None) -> bool:
    return script_path(root).is_file() and bool(years_available(root)) and (year is None or year in years_available(root))


def input_signature(root: Path, year: str) -> str:
    """A fingerprint of everything the check reads: the PDFs under the year folder and the script itself."""
    h = hashlib.sha256()
    entries = sorted((str(p.relative_to(root)), p.stat().st_size, p.stat().st_mtime_ns) for p in (root / year).rglob("*.pdf"))
    sp = script_path(root)
    entries.append((SCRIPT_REL, sp.stat().st_size, sp.stat().st_mtime_ns))
    for e in entries:
        h.update(repr(e).encode())
    return h.hexdigest()


def _iso(d: str | None) -> str | None:
    m = re.match(r"^(\d{2})\.(\d{2})\.(\d{4})$", d or "")
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else None


def run_checker(root: Path, year: str, seuil: float = 0.0) -> tuple[list[dict], str]:
    """Run her script exactly as `python3 controle_justificatifs.py --annee Y`, capturing its lines instead of letting it write its report."""
    path = script_path(root)
    if not path.is_file():
        raise AuditError(f"The checker script was not found ({SCRIPT_REL})")
    spec = importlib.util.spec_from_file_location("controle_justificatifs", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)                                  # only defines functions: its main() runs only when called below
    captured: dict = {}
    mod.ecrire_xlsx = lambda lignes, racine, annee: captured.update(lignes=lignes)       # the one change: keep the result, write no file
    out, old_argv = io.StringIO(), sys.argv
    try:
        sys.argv = [str(path), "--annee", year, "--dossier", str(root), "--seuil", str(seuil)]
        with contextlib.redirect_stdout(out):
            mod.main()
    except SystemExit as e:                                       # her script exits with a message when it finds nothing to check
        if e.code not in (None, 0):
            raise AuditError(str(e.code))
    finally:
        sys.argv = old_argv
    if "lignes" not in captured:
        raise AuditError("The checker finished without producing a result")
    return captured["lignes"], out.getvalue()


def summarise(lines: list[dict]) -> dict:
    counts = {s: {"n": 0, "total": 0.0} for s in STATUSES}
    for l in lines:
        c = counts.setdefault(l["statut"], {"n": 0, "total": 0.0})
        c["n"] += 1
        c["total"] = round(c["total"] + (l["montant"] or 0), 2)
    n = len(lines)
    ok = counts["justifié"]["n"] + counts["couvert"]["n"]
    dates = sorted(d for d in (_iso(l["date"]) for l in lines) if d)
    ends = []
    for l in lines:
        m = re.search(r"(\d{2}\.\d{2}\.\d{4})\s*[–-]\s*(\d{2}\.\d{2}\.\d{4})", l.get("periode") or "")
        if m and _iso(m.group(2)):
            ends.append(_iso(m.group(2)))
    return {"counts": counts, "debits": n, "pct_ok": round(100 * ok / n, 1) if n else None,
            "period_from": dates[0] if dates else None, "period_to": dates[-1] if dates else None,
            "statements_to": max(ends) if ends else None, "accounts": sorted({l["compte"] for l in lines})}


def run_and_store(conn: sqlite3.Connection, root: Path, year: str, seuil: float = 0.0) -> int:
    """One check, recorded in audit_runs / audit_lines. Never raises: a failure is stored as the run's error."""
    now = now_local().isoformat(timespec="seconds")
    sig = input_signature(root, year)
    with conn:
        rid = conn.execute("INSERT INTO audit_runs (year, started_at, input_signature) VALUES (?,?,?)", (year, now, sig)).lastrowid
    try:
        lines, out = run_checker(root, year, seuil)
        n_st = re.search(r"Relevés trouvés\s*:\s*(\d+)", out)
        n_pc = re.search(r"Pièces indexées\s*:\s*(\d+)", out)
        with conn:
            conn.executemany(
                "INSERT INTO audit_lines (run_id, compte, periode, date_raw, date_iso, beneficiaire, devise, montant, statut, source, groupe) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                [(rid, l.get("compte"), l.get("periode"), l.get("date"), _iso(l.get("date")), l.get("beneficiaire"), l.get("devise"),
                  l.get("montant"), l.get("statut"), l.get("source"), l.get("groupe")) for l in lines])
            conn.execute("UPDATE audit_runs SET status='done', finished_at=?, n_statements=?, n_pieces=?, n_lines=?, summary=? WHERE id=?",
                         (now_local().isoformat(timespec="seconds"), int(n_st.group(1)) if n_st else None, int(n_pc.group(1)) if n_pc else None,
                          len(lines), json.dumps(summarise(lines)), rid))
    except Exception as e:
        with conn:
            conn.execute("UPDATE audit_runs SET status='error', finished_at=?, error=? WHERE id=?",
                         (now_local().isoformat(timespec="seconds"), f"{type(e).__name__}: {e}"[:400], rid))
    with conn:                                                    # keep the last few runs per year
        old = [r[0] for r in conn.execute("SELECT id FROM audit_runs WHERE year=? ORDER BY id DESC LIMIT -1 OFFSET ?", (year, KEEP_RUNS))]
        for o in old:
            conn.execute("DELETE FROM audit_lines WHERE run_id=?", (o,))
            conn.execute("DELETE FROM audit_runs WHERE id=?", (o,))
    return rid


def start_background(connect, root: Path, year: str) -> bool:
    """Start a check in the background unless one is already running. `connect` gives a fresh database connection."""
    if not _lock.acquire(blocking=False):
        return False
    def work():
        conn = connect()
        try:
            run_and_store(conn, root, year)
        finally:
            conn.close()
            _lock.release()
    threading.Thread(target=work, daemon=True).start()
    return True


def is_running() -> bool:
    return _lock.locked()


def status(conn: sqlite3.Connection, root: Path, year: str) -> dict:
    ok = configured(root, year)
    out = {"configured": ok, "year": year, "years": years_available(root), "running": is_running(), "latest": None, "last_error": None, "stale": False}
    if not ok:
        return out
    row = conn.execute("SELECT * FROM audit_runs WHERE year=? AND status='done' ORDER BY id DESC LIMIT 1", (year,)).fetchone()
    err = conn.execute("SELECT error, finished_at FROM audit_runs WHERE year=? AND status='error' ORDER BY id DESC LIMIT 1", (year,)).fetchone()
    if row:
        out["latest"] = {"id": row["id"], "finished_at": row["finished_at"], "n_statements": row["n_statements"], "n_pieces": row["n_pieces"], "n_lines": row["n_lines"], **json.loads(row["summary"])}
        out["stale"] = row["input_signature"] != input_signature(root, year)
    if err and (not row or err["finished_at"] > row["finished_at"]):
        out["last_error"] = err["error"]
    return out


def lines(conn: sqlite3.Connection, year: str, statut: str | None = None) -> list[dict]:
    row = conn.execute("SELECT id FROM audit_runs WHERE year=? AND status='done' ORDER BY id DESC LIMIT 1", (year,)).fetchone()
    if row is None:
        return []
    q, args = "SELECT compte, periode, date_raw, date_iso, beneficiaire, devise, montant, statut, source, groupe FROM audit_lines WHERE run_id=?", [row["id"]]
    if statut:
        q += " AND statut=?"; args.append(statut)
    q += " ORDER BY montant DESC, date_iso"
    return [dict(r) for r in conn.execute(q, args)]


def compare_with_report(conn: sqlite3.Connection, root: Path, year: str) -> dict:
    """Compare the latest run with her own report file (the 'same results as today' test). The report is only read."""
    report = root / year / f"Controle_justificatifs_{year}.xlsx"
    if not report.is_file():
        return {"report_found": False}
    import openpyxl
    wb = openpyxl.load_workbook(report, read_only=True, data_only=True)
    try:
        rows = list(wb["Tous les débits"].iter_rows(min_row=2, values_only=True))
    except KeyError:
        return {"report_found": True, "readable": False}
    finally:
        wb.close()
    key = lambda c, d, m, b, s: (str(c or ""), str(d or ""), round(float(m or 0), 2), str(b or ""), str(s or ""))
    theirs = [key(r[0], r[2], r[5], r[3], r[6]) for r in rows if r and r[0] is not None]
    mine = [key(l["compte"], l["date_raw"], l["montant"], l["beneficiaire"], l["statut"]) for l in lines(conn, year)]
    from collections import Counter
    a, b = Counter(theirs), Counter(mine)
    only_report, only_run = list((a - b).elements()), list((b - a).elements())
    count = lambda ks: {s: sum(1 for k in ks if k[4] == s) for s in STATUSES}
    return {"report_found": True, "readable": True, "report": report.name,
            "report_modified": datetime.fromtimestamp(report.stat().st_mtime).astimezone().isoformat(timespec="minutes"),
            "same": not only_report and not only_run, "report_counts": count(theirs), "run_counts": count(mine),
            "only_in_report": [dict(zip(("compte", "date", "montant", "beneficiaire", "statut"), k)) for k in only_report[:40]],
            "only_in_run": [dict(zip(("compte", "date", "montant", "beneficiaire", "statut"), k)) for k in only_run[:40]]}
