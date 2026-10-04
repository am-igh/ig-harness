#!/usr/bin/env python3
"""Mac-side register writer: adds NEW rows to Registre_Projets.xlsx and does nothing else. Standard library only.

Decided with Anne-Marie on 4 Oct 2026 (a one-off, then available whenever she asks): rows are added only after she has seen the exact preview and approved it.
  - it only APPENDS rows below the existing ones; every existing row, cell, style and column width stays byte for byte as it was;
  - a row whose key already exists (code; code + instalment; code + budget line) is skipped, never overwritten;
  - before writing: a backup copy (~/IG-Harness-data/register_backups), and it refuses while Excel has the file open (~$ lock file) or the file changed in the last 90 s;
  - the new file is built beside the original and verified (everything else identical, new rows present, header untouched) BEFORE it replaces the original;
  - after the swap it re-checks; if anything is off her original is put back from the backup.

  python3 tools/register_writer.py preview rows.json     show exactly what would be added
  python3 tools/register_writer.py apply rows.json       add it (after she approved the preview)
rows.json looks like {"Mandates": [{"code": "TK", "funder": "...", ...}], "Instalments": [...], "Budget": [...], "Initiatives": [...]}; keys are the sheets' own column names.
"""
import html
import json
import os
import re
import shutil
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path

DATA = Path(os.environ.get("IG_DATA_DIR", Path.home() / "IG-Harness-data"))
KEYS = {"Mandates": ("code",), "Instalments": ("code", "instalment"), "Budget": ("code", "budget line"), "Initiatives": ("code",)}
QUIET_SECONDS = 90
NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


class RegisterError(Exception):
    pass


def projets_file() -> Path:
    v = os.environ.get("PROJETS_DIR")
    root = Path(__file__).resolve().parent.parent
    if not v and (root / ".env").is_file():
        for line in (root / ".env").read_text().splitlines():
            if line.startswith("PROJETS_DIR="):
                v = line.split("=", 1)[1].strip().strip('"\'')
    if not v:
        raise RegisterError("PROJETS_DIR is not set in .env")
    return Path(v).expanduser() / "Registre_Projets.xlsx"


def _col(n: int) -> str:
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def sheet_parts(z: zipfile.ZipFile) -> dict[str, str]:
    wb = z.read("xl/workbook.xml").decode("utf8")
    rels = z.read("xl/_rels/workbook.xml.rels").decode("utf8")
    target = {m.group(2): m.group(1) for m in re.finditer(r'<Relationship [^>]*?Target="([^"]+)"[^>]*?Id="([^"]+)"', rels)}
    target.update({m.group(1): m.group(2) for m in re.finditer(r'<Relationship [^>]*?Id="([^"]+)"[^>]*?Target="([^"]+)"', rels)})
    out = {}
    for m in re.finditer(r'<sheet\b[^>]*?name="([^"]+)"[^>]*?r:id="([^"]+)"', wb):
        t = target.get(m.group(2), "")
        out[html.unescape(m.group(1))] = t.lstrip("/") if t.startswith("/") else "xl/" + t
    return out


def _shared(z: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in z.namelist():
        return []
    x = z.read("xl/sharedStrings.xml").decode("utf8")
    return [html.unescape("".join(re.findall(r"<t[^>]*>([^<]*)</t>", si))) for si in re.findall(r"<si>.*?</si>", x, re.S)]


def read_rows(xml: str, shared: list[str]) -> list[dict[int, str]]:
    """Every row as {column number: text}; handles inline strings, shared strings and numbers."""
    rows = []
    for rm in re.finditer(r'<row\b[^>]*?\br="(\d+)"[^>]*?(?:/>|>(.*?)</row>)', xml, re.S):
        cells = {}
        for cm in re.finditer(r'<c\b([^>]*?)(?:/>|>(.*?)</c>)', rm.group(2) or "", re.S):
            attrs, inner = cm.group(1), cm.group(2) or ""
            ref = re.search(r'\br="([A-Z]+)\d+"', attrs)
            if not ref:
                continue
            n = 0
            for ch in ref.group(1):
                n = n * 26 + ord(ch) - 64
            t = re.search(r'\bt="(\w+)"', attrs)
            if t and t.group(1) == "inlineStr":
                val = html.unescape("".join(re.findall(r"<t[^>]*>([^<]*)</t>", inner)))
            elif t and t.group(1) == "s":
                v = re.search(r"<v>(\d+)</v>", inner)
                val = shared[int(v.group(1))] if v and int(v.group(1)) < len(shared) else ""
            else:
                v = re.search(r"<v>([^<]*)</v>", inner)
                val = html.unescape(v.group(1)) if v else ""
            cells[n] = val
        rows.append((int(rm.group(1)), cells))
    return rows


def cell_xml(col: int, r: int, value, style: str) -> str:
    ref = f"{_col(col)}{r}"
    if value is None or value == "":
        return ""
    if isinstance(value, bool):
        value = str(value)
    if isinstance(value, (int, float)):
        return f'<c r="{ref}"{style}><v>{value}</v></c>'
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", str(value))
    sp = ' xml:space="preserve"' if text != text.strip() or "\n" in text else ""
    return f'<c r="{ref}"{style} t="inlineStr"><is><t{sp}>{html.escape(text, quote=False)}</t></is></c>'


def plan_sheet(xml: str, shared: list[str], sheet: str, new_rows: list[dict]) -> tuple[str, list[str], list[str]]:
    """Returns (new sheet XML, lines that will be added, lines skipped because the key exists)."""
    rows = read_rows(xml, shared)
    if not rows:
        raise RegisterError(f"{sheet}: no header row")
    header = {n: v.strip() for n, v in rows[0][1].items()}
    by_name = {v: n for n, v in header.items()}
    missing = [k for k in KEYS[sheet] if k not in by_name]
    if missing:
        raise RegisterError(f"{sheet}: the sheet has no column {missing[0]!r}")
    existing = {tuple(r[1].get(by_name[k], "").strip().lower() for k in KEYS[sheet]) for r in rows[1:] if any(r[1].values())}
    last = max(r[0] for r in rows)
    style = re.search(r'<row r="2"[^>]*>.*?<c [^>]*?\bs="(\d+)"', xml, re.S)
    st = f' s="{style.group(1)}"' if style else ""
    added, skipped, out = [], [], []
    for row in new_rows:
        unknown = [k for k in row if k not in by_name]
        if unknown:
            raise RegisterError(f"{sheet}: unknown column(s) {unknown}")
        key = tuple(str(row.get(k, "")).strip().lower() for k in KEYS[sheet])
        label = " / ".join(str(row.get(k, "")) for k in KEYS[sheet])
        if not all(key):
            raise RegisterError(f"{sheet}: a row has no {', '.join(KEYS[sheet])}")
        if key in existing:
            skipped.append(f"{sheet}: {label} is already there")
            continue
        existing.add(key)
        last += 1
        cells = "".join(cell_xml(by_name[k], last, v, st) for k, v in sorted(row.items(), key=lambda kv: by_name[kv[0]]))
        out.append(f'<row r="{last}">{cells}</row>')
        filled = [k for k, v in row.items() if v not in (None, "")]
        added.append(f"{sheet}: row {last}: {label}  ({len(filled)} cells filled)")
    if out:
        xml = xml.replace("</sheetData>", "".join(out) + "</sheetData>", 1)
        width = max(header)
        xml = re.sub(r'<dimension ref="A1:[A-Z]+\d+"', f'<dimension ref="A1:{_col(width)}{last}"', xml, 1)
    return xml, added, skipped


def build(path: Path, rows: dict[str, list[dict]]) -> tuple[bytes | None, list[str], list[str]]:
    """The new workbook bytes (None when nothing is to be added), what is added, what is skipped."""
    z = zipfile.ZipFile(path)
    parts, shared = sheet_parts(z), _shared(z)
    changes: dict[str, bytes] = {}
    added, skipped = [], []
    for sheet, new_rows in rows.items():
        if sheet not in parts:
            raise RegisterError(f"the register has no sheet called {sheet!r}")
        xml, a, s = plan_sheet(z.read(parts[sheet]).decode("utf8"), shared, sheet, new_rows)
        added += a
        skipped += s
        if a:
            changes[parts[sheet]] = xml.encode("utf8")
    if not changes:
        return None, added, skipped
    import io
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as out:
        for info in z.infolist():
            data = changes.get(info.filename, z.read(info.filename))
            ni = zipfile.ZipInfo(info.filename, info.date_time)
            ni.compress_type, ni.external_attr = info.compress_type, info.external_attr
            out.writestr(ni, data)
    return buf.getvalue(), added, skipped


def verify(original: Path, new_bytes: bytes, rows: dict[str, list[dict]], added: list[str]) -> None:
    import io
    a, b = zipfile.ZipFile(original), zipfile.ZipFile(io.BytesIO(new_bytes))
    if sorted(a.namelist()) != sorted(b.namelist()):
        raise RegisterError("the new file has different parts than the original")
    parts = sheet_parts(a)
    touched = {parts[s] for s, r in rows.items() if r and s in parts}
    for name in a.namelist():
        if name in touched:
            old, new = a.read(name).decode("utf8"), b.read(name).decode("utf8")
            o, n = old.split("</sheetData>")[0], new.split("</sheetData>")[0]
            if not n.startswith(o) and not re.sub(r'<dimension[^>]*/>', "", n).startswith(re.sub(r'<dimension[^>]*/>', "", o)):
                raise RegisterError(f"{name}: the existing rows changed")
            if old.split("</sheetData>")[1] != new.split("</sheetData>")[1]:
                raise RegisterError(f"{name}: something after the data changed")
        elif a.read(name) != b.read(name):
            raise RegisterError(f"{name} changed but should not have")
    shared = _shared(b)
    for sheet, new_rows in rows.items():
        got = read_rows(b.read(parts[sheet]).decode("utf8"), shared)
        header = {v.strip(): n for n, v in got[0][1].items()}
        keys = {tuple(r[1].get(header[k], "").strip().lower() for k in KEYS[sheet]) for r in got[1:]}
        for row in new_rows:
            if tuple(str(row.get(k, "")).strip().lower() for k in KEYS[sheet]) not in keys:
                raise RegisterError(f"{sheet}: a new row is missing after writing")


def check_free(path: Path, now: float | None = None) -> None:
    if (path.parent / f"~${path.name}").exists():
        raise RegisterError("Excel has the register open (a ~$ lock file is next to it): close it and try again")
    if (now if now is not None else time.time()) - path.stat().st_mtime < QUIET_SECONDS:
        raise RegisterError(f"the register changed in the last {QUIET_SECONDS} seconds; try again in a moment")


def apply(path: Path, rows: dict[str, list[dict]], *, backups: Path | None = None, now: float | None = None, dry_run: bool = False) -> dict:
    new, added, skipped = build(path, rows)
    if new is None or dry_run:
        return {"added": added, "skipped": skipped, "written": False}
    check_free(path, now)
    verify(path, new, rows, added)
    backups = backups or DATA / "register_backups"
    backups.mkdir(parents=True, exist_ok=True)
    backup = backups / f"Registre_Projets.{datetime.now().strftime('%Y%m%d-%H%M%S')}.xlsx"
    shutil.copy2(path, backup)
    tmp = path.with_name(f".{path.name}.new")
    tmp.write_bytes(new)
    shutil.copymode(path, tmp)
    try:
        verify(path, tmp.read_bytes(), rows, added)
        check_free(path, now)                                              # nothing opened it while we worked
        os.replace(tmp, path)
        verify(backup, path.read_bytes(), rows, added)                     # the file now on disk, against the backup of the original
    except Exception as e:
        tmp.unlink(missing_ok=True)
        if path.read_bytes() != backup.read_bytes():
            shutil.copy2(backup, path)                                     # put her original back
        raise RegisterError(f"nothing was changed ({e})")
    return {"added": added, "skipped": skipped, "written": True, "backup": str(backup)}


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[1] not in ("preview", "apply"):
        sys.exit(__doc__)
    rows = json.loads(Path(argv[2]).read_text())
    try:
        r = apply(projets_file(), rows, dry_run=(argv[1] == "preview"))
    except RegisterError as e:
        print(f"Not written: {e}", file=sys.stderr)
        return 1
    for line in r["added"]:
        print(("added  " if r["written"] else "would add  ") + line)
    for line in r["skipped"]:
        print("skipped  " + line)
    if r["written"]:
        print(f"Backup of your original: {r['backup']}")
    elif argv[1] == "apply":
        print("Nothing to add.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
