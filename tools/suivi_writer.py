#!/usr/bin/env python3
"""Mac-side writer: adds the harness notes to the Journal sheet of Suivi.xlsx. Standard library only.

This is the ONLY place the harness writes to one of Anne-Marie's own files, by her explicit decision on
2 Oct 2026 ("the notes go into Suivi's journal as well"). Her other sources stay read-only, and the harness
container still sees the Suivi folder read-only. How it keeps her file safe:

  * it only writes WORK notes (Suivi is in Google Drive; personal items never leave the Mac);
  * it does nothing while Excel has the file open (a ~$Suivi.xlsx lock file) or if the file changed in the
    last 90 seconds (Drive may still be syncing, or she may be saving);
  * it changes ONE thing: it fills the next empty, already-formatted rows of the Journal sheet. Every other
    byte of the workbook (other sheets, styles, filters, dropdowns) is copied unchanged;
  * before swapping the new file in, it checks that nothing but those rows differs and that it is well-formed;
    right before swapping, that her file has not changed; right after, that the result is still sound;
  * a backup of Suivi.xlsx is kept before every write (last 30, in ~/IG-Harness-Backups/suivi/) and the
    original is put back if any check after the swap fails;
  * a note is exported once (state in ~/IG-Harness-data/suivi_export/exported.json).

  suivi_writer.py run [--dry-run]     add the pending notes (dry run: show the rows, change nothing)
  suivi_writer.py status              what is pending, what was exported
Pause without uninstalling anything: make suivi-export-pause (resume: make suivi-export-resume).
"""
import hashlib
import io
import os
import re
import shutil
import sqlite3
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path
from xml.dom import minidom
from xml.sax.saxutils import escape, unescape

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from harness import suivi_export as SE                    # noqa: E402  (pure standard library)

DATA = Path(os.environ.get("IG_DATA_DIR", Path.home() / "IG-Harness-data"))
BACKUPS = Path(os.environ.get("IG_BACKUP_DIR", Path.home() / "IG-Harness-Backups")) / "suivi"
FILE_NAME = "Suivi.xlsx"
SHEET_NAME = "Journal"
MIN_AGE_SECONDS = 90
KEEP_BACKUPS = 30
COLS = "ABCDEFGHIJKL"
ROW_RE = re.compile(r'<row r="(\d+)"([^>]*?)(?:/>|>(.*?)</row>)', re.S)
CELL_RE = re.compile(r'<c r="([A-Z]+)(\d+)"([^>]*?)(?:/>|>(.*?)</c>)', re.S)


class SuiviBusy(Exception):
    """Not an error: the file is in use right now. The notes stay pending and are tried again next time."""


class SuiviError(Exception):
    pass


# ---------------------------------------------------------------- locating things
def suivi_dir() -> Path:
    if os.environ.get("IG_SUIVI_DIR"):
        return Path(os.environ["IG_SUIVI_DIR"])
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("SUIVI_DIR="):
                return Path(line.split("=", 1)[1].strip().strip('"').strip("'"))
    raise SuiviError("SUIVI_DIR is not set (see .env.example)")


def journal_part(z: zipfile.ZipFile) -> str:
    wb = z.read("xl/workbook.xml").decode("utf8")
    rels = z.read("xl/_rels/workbook.xml.rels").decode("utf8")
    m = re.search(rf'<sheet [^>]*name="{SHEET_NAME}"[^>]*r:id="([^"]+)"', wb)
    if not m:
        raise SuiviError(f"there is no sheet named {SHEET_NAME} in {FILE_NAME}")
    rid = m.group(1)
    t = re.search(rf'<Relationship [^>]*Id="{rid}"[^>]*Target="([^"]+)"', rels) or re.search(rf'<Relationship [^>]*Target="([^"]+)"[^>]*Id="{rid}"', rels)
    if not t:
        raise SuiviError("cannot find the Journal sheet's file inside the workbook")
    target = t.group(1)
    return target.lstrip("/") if target.startswith("/") else "xl/" + target


# ---------------------------------------------------------------- reading the sheet XML
def _has_value(inner: str | None) -> bool:
    return bool(inner and re.search(r"<v>|<is>", inner))


def scan_rows(xml: str) -> list[dict]:
    return [{"r": int(m.group(1)), "attrs": m.group(2), "inner": m.group(3), "start": m.start(), "end": m.end()} for m in ROW_RE.finditer(xml)]


def cells_of(inner: str | None) -> dict[str, dict]:
    out = {}
    for m in CELL_RE.finditer(inner or ""):
        s = re.search(r's="(\d+)"', m.group(3))
        t = re.search(r"<t[^>]*>(.*?)</t>", m.group(4) or "", re.S) or re.search(r"<v>(.*?)</v>", m.group(4) or "", re.S)
        out[m.group(1)] = {"s": s.group(1) if s else None, "text": unescape(t.group(1)) if t else None}
    return out


def existing_ids(rows: list[dict]) -> list[str]:
    return [c["A"]["text"] for r in rows if r["r"] > 1 and (c := cells_of(r["inner"])).get("A") and c["A"]["text"]]


def last_filled_index(rows: list[dict]) -> int:
    idx = [i for i, r in enumerate(rows) if _has_value(r["inner"])]
    if not idx:
        raise SuiviError("the Journal sheet looks empty: refusing to guess its layout")
    return max(idx)


def _xml_safe(value: str) -> str:
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]", "", value)


def cell_xml(col: str, r: int, style: str, value: str) -> str:
    if value == "":
        return f'<c r="{col}{r}" s="{style}"/>'
    return f'<c r="{col}{r}" s="{style}" t="inlineStr"><is><t xml:space="preserve">{escape(_xml_safe(value))}</t></is></c>'


def fill_rows(xml: str, new_rows: list[list[str]]) -> tuple[str, list[int], str]:
    """Put each new row into the next empty pre-formatted row. Returns the new xml, the row numbers used, and the row-less remainder for checking."""
    rows = scan_rows(xml)
    last = last_filled_index(rows)
    template = cells_of(rows[last]["inner"])                              # styles of the last real row
    targets = rows[last + 1:last + 1 + len(new_rows)]
    if len(targets) < len(new_rows):
        raise SuiviError("the Journal sheet has no empty rows left: add rows to it first")
    out, pos, used = [], 0, []
    for row, values in zip(targets, new_rows):
        if _has_value(row["inner"]):
            raise SuiviError(f"row {row['r']} is not empty")
        blank = cells_of(row["inner"])
        inner = "".join(cell_xml(col, row["r"], (blank.get(col) or {}).get("s") or (template.get(col) or {}).get("s") or "0", values[i]) for i, col in enumerate(COLS))
        out.append(xml[pos:row["start"]])
        out.append(f'<row r="{row["r"]}"{row["attrs"]}>{inner}</row>')
        pos = row["end"]
        used.append(row["r"])
    out.append(xml[pos:])
    return "".join(out), used, strip_rows(xml, set(used))


def strip_rows(xml: str, row_numbers: set[int]) -> str:
    """The sheet with the given rows cut out: used to prove that everything else is untouched."""
    out, pos = [], 0
    for r in scan_rows(xml):
        if r["r"] in row_numbers:
            out.append(xml[pos:r["start"]])
            pos = r["end"]
    out.append(xml[pos:])
    return "".join(out)


# ---------------------------------------------------------------- the file work
def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_free(path: Path, now: float | None = None) -> None:
    for lock in (path.with_name(f"~${path.name}"), path.with_name(f".~lock.{path.name}#")):
        if lock.exists():
            raise SuiviBusy(f"{path.name} is open in a spreadsheet program ({lock.name}); will retry later")
    age = (now or time.time()) - path.stat().st_mtime
    if age < MIN_AGE_SECONDS:
        raise SuiviBusy(f"{path.name} changed {int(age)} s ago (syncing or being saved); will retry later")


def rewrite_zip(src: Path, dst: Path, part: str, new_xml: str) -> None:
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w") as zout:
        for info in zin.infolist():
            data = new_xml.encode("utf8") if info.filename == part else zin.read(info.filename)
            zi = zipfile.ZipInfo(info.filename, info.date_time)
            zi.compress_type, zi.external_attr, zi.create_system = info.compress_type, info.external_attr, info.create_system
            zout.writestr(zi, data)


def verify_result(original: Path, result: Path, part: str, used: list[int], expected: list[list[str]]) -> None:
    """Raises SuiviError unless `result` is the original plus exactly the expected rows."""
    with zipfile.ZipFile(original) as a, zipfile.ZipFile(result) as b:
        if b.testzip() is not None:
            raise SuiviError("the new workbook is damaged (zip check failed)")
        if [i.filename for i in a.infolist()] != [i.filename for i in b.infolist()]:
            raise SuiviError("the new workbook has different parts")
        for name in a.namelist():
            if name != part and a.read(name) != b.read(name):
                raise SuiviError(f"{name} changed, and it must not")
        old_xml, new_xml = a.read(part).decode("utf8"), b.read(part).decode("utf8")
    minidom.parseString(new_xml.encode("utf8"))                                  # well-formed XML
    if strip_rows(old_xml, set(used)) != strip_rows(new_xml, set(used)):
        raise SuiviError("something outside the new rows changed in the Journal sheet")
    rows = {r["r"]: cells_of(r["inner"]) for r in scan_rows(new_xml) if r["r"] in used}
    for r, values in zip(used, expected):
        got = [(rows[r].get(col) or {}).get("text") or "" for col in COLS]
        if got != [_xml_safe(v) for v in values]:
            raise SuiviError(f"row {r} does not contain what was meant to be written")


def prune_backups(folder: Path) -> None:
    for old in sorted(folder.glob("Suivi-*.xlsx"))[:-KEEP_BACKUPS]:
        old.unlink(missing_ok=True)


def append_to_suivi(path: Path, new_rows: list[list[str]], *, now: float | None = None, backups: Path | None = None, _sabotage=None) -> list[int]:
    """Add rows to the Journal sheet. All-or-nothing; returns the sheet row numbers used."""
    if not new_rows:
        return []
    backups = backups or BACKUPS
    check_free(path, now)
    before = _sha(path)
    with zipfile.ZipFile(path) as z:
        part = journal_part(z)
        xml = z.read(part).decode("utf8")
    new_xml, used, _ = fill_rows(xml, new_rows)
    tmp = path.with_name(f".{path.name}.harness-tmp")
    try:
        rewrite_zip(path, tmp, part, new_xml)
        verify_result(path, tmp, part, used, new_rows)                              # 1. the new file is the old one plus our rows
        check_free(path, now)
        if _sha(path) != before:                                                    # 2. she (or Drive) changed it meanwhile: do not overwrite
            raise SuiviBusy(f"{path.name} changed while preparing the update; will retry later")
        backups.mkdir(parents=True, exist_ok=True)
        backup = backups / f"Suivi-{datetime.now():%Y%m%d-%H%M%S}.xlsx"
        shutil.copy2(path, backup)
        os.replace(tmp, path)                                                       # 3. swap in
        try:
            if _sabotage:
                _sabotage(path)
            verify_result(backup, path, part, used, new_rows)                       # 4. still sound after the swap?
        except Exception:
            shutil.copy2(backup, path)                                              #    no: put her original back
            raise
        prune_backups(backups)
    finally:
        tmp.unlink(missing_ok=True)
    return used


# ---------------------------------------------------------------- which notes
PENDING_SQL = """
SELECT n.id, n.created_at, n.text, n.kind, n.parent_type, n.parent_id, n.due_date, n.project_code,
       e.thread_id AS thread_id, COALESCE(e.person_slug, w.person) AS person,
       COALESCE(t.source, d.source) AS source, COALESCE(t.source_ref, d.source_ref) AS source_ref
FROM notes n
LEFT JOIN emails e ON n.parent_type = 'email' AND e.id = n.parent_id
LEFT JOIN waiting_on w ON n.parent_type = 'waiting_on' AND w.id = n.parent_id
LEFT JOIN tasks t ON n.parent_type = 'task' AND t.id = n.parent_id
LEFT JOIN deadlines d ON n.parent_type = 'deadline' AND d.id = n.parent_id
WHERE n.deleted_at IS NULL AND n.space = 'work'
ORDER BY n.id
"""


def pending_notes(db_path: Path, state: dict) -> list[dict]:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(PENDING_SQL) if str(r["id"]) not in state["notes"]]
    finally:
        conn.close()


def run(dry_run: bool = False, *, data: Path | None = None, suivi: Path | None = None, today=None, status: str = "confirmed") -> str:
    data = data or DATA
    if SE.is_paused(data):
        return "paused (make suivi-export-resume to continue)"
    state = SE.read_state(data)
    notes = pending_notes(data / "harness.db", state)
    if not notes:
        return "nothing to add"
    path = (suivi or suivi_dir()) / FILE_NAME
    if not path.exists():
        raise SuiviError(f"{path} not found")
    with zipfile.ZipFile(path) as z:
        xml = z.read(journal_part(z)).decode("utf8")
    ids, today = existing_ids(scan_rows(xml)), today or datetime.now().astimezone().date()
    rows, mapping, year = [], {}, today.year
    for n in notes:
        jid = SE.next_journal_id(ids + [m for m in mapping.values()], year)
        mapping[n["id"]] = jid
        rows.append(SE.build_row(n, jid, today, status))
    if dry_run:
        return "would add:\n" + "\n".join("  " + " | ".join(r[:2] + r[3:6] + r[7:8]) for r in rows)
    used = append_to_suivi(path, rows)
    stamp = datetime.now().astimezone().isoformat(timespec="seconds")
    for n, r in zip(notes, used):
        state["notes"][str(n["id"])] = {"journal_id": mapping[n["id"]], "exported_at": stamp, "row": r}
    state.update(last_run=stamp, last_error=None)
    SE.write_state(data, state)
    return f"added {len(rows)} note(s) to Suivi: " + ", ".join(mapping.values())


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else ""
    try:
        if cmd == "run":
            print(run("--dry-run" in argv))
            return 0
        if cmd == "status":
            state = SE.read_state(DATA)
            pend = pending_notes(DATA / "harness.db", state) if (DATA / "harness.db").exists() else []
            print(f"exported: {len(state['notes'])} | pending: {len(pend)} | paused: {SE.is_paused(DATA)} | last run: {state.get('last_run')}")
            return 0
    except SuiviBusy as e:
        print(f"waiting: {e}")
        return 0
    except SuiviError as e:
        print(f"Suivi export problem: {e}", file=sys.stderr)
        return 1
    sys.exit(__doc__)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
