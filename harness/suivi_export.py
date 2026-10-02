"""Notes -> rows in Suivi.xlsx's Journal sheet. The pure rules; the Mac-side writer (tools/suivi_writer.py) does the file work.

Decided with Anne-Marie on 2 Oct 2026: her notes also go into Suivi's journal. Rules, from her Suivi specification:
  - a journal row needs a date, domain, type (meeting, call, email, work, decision, event, admin, document), a short summary,
    EVIDENCE (a pointer), a source (here 'capture': a quick capture by her) and a status;
  - ids look like J-2026-021 and run on from the highest one;
  - her own typed note is 'confirmed' (she wrote it), not a Claude-drafted 'proposed' row.
Only WORK notes go: Suivi lives in Google Drive, and personal items never leave the Mac (rule 10).
Pure standard library, no file access except the small state file the writer keeps."""
import json
import re
from datetime import date
from pathlib import Path

COLUMNS = ["id", "date", "domain", "code", "type", "summary", "people", "evidence", "hours", "source", "status", "entered_on"]
STATE_DIR = "suivi_export"
STATE_FILE = "exported.json"
DISABLED_FILE = "DISABLED"
SUMMARY_LIMIT = 600
_ID = re.compile(r"^J-(\d{4})-(\d{3,})$")


def eligible(space: str, deleted: bool) -> bool:
    return space == "work" and not deleted


def read_state(data_dir: Path) -> dict:
    try:
        s = json.loads((data_dir / STATE_DIR / STATE_FILE).read_text())
        s.setdefault("notes", {})
        s.setdefault("docs", {})
        return s
    except (OSError, ValueError):
        return {"notes": {}, "docs": {}, "last_run": None, "last_error": None}


def write_state(data_dir: Path, state: dict) -> None:
    folder = data_dir / STATE_DIR
    folder.mkdir(parents=True, exist_ok=True)
    tmp = folder / f".{STATE_FILE}.tmp"
    tmp.write_text(json.dumps(state, indent=1))
    tmp.replace(folder / STATE_FILE)


def is_paused(data_dir: Path) -> bool:
    return (data_dir / STATE_DIR / DISABLED_FILE).exists()


def note_status(note_id: int, space: str, deleted: bool, state: dict, paused: bool = False) -> dict:
    """What the screen says about a note: in Suivi (with its id), waiting, paused, or not eligible."""
    done = state.get("notes", {}).get(str(note_id))
    if done:
        return {"state": "exported", "journal_id": done["journal_id"]}
    if space == "personal":
        return {"state": "excluded", "reason": "personal notes are never sent to Suivi"}
    if deleted:
        return {"state": "none"}
    return {"state": "paused" if paused else "pending"}


def next_journal_id(existing: list[str], year: int) -> str:
    """J-YYYY-NNN one above the highest number already used for that year (gaps are never reused)."""
    top = max((int(m.group(2)) for i in existing if (m := _ID.match(str(i).strip())) and int(m.group(1)) == year), default=0)
    return f"J-{year}-{top + 1:03d}"


def clean_summary(text: str, followup_due: str | None = None) -> str:
    """One line, one or two sentences' worth: line breaks become ' / ', long text is cut with an ellipsis."""
    flat = " / ".join(part.strip() for part in text.strip().splitlines() if part.strip())
    flat = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", flat)                 # characters XML cannot hold
    if followup_due:
        flat = f"Follow-up (due {followup_due}): {flat}"
    return flat if len(flat) <= SUMMARY_LIMIT else flat[:SUMMARY_LIMIT - 1].rstrip() + "…"


def build_row(note: dict, journal_id: str, today: date, status: str = "confirmed") -> list[str]:
    """The twelve cells of the journal row, in column order. `note` carries the note and what it is attached to."""
    if note["parent_type"] == "email":
        evidence = note.get("thread_id") or f"harness-note:{note['id']}"
    else:
        evidence = f"harness-note:{note['id']}" + (f"; {note['source_ref']}" if note.get("source") == "suivi" and note.get("source_ref") else "")
    return [
        journal_id,
        note["created_at"][:10],
        "W",
        note.get("project_code") or "",
        "email" if note["parent_type"] == "email" else "work",
        clean_summary(note["text"], note.get("due_date") if note["kind"] == "followup" else None),
        note.get("person") or "",
        evidence,
        "",                                   # hours: only for rows that should flow into the hours log
        "capture",
        status,
        today.isoformat(),
    ]


# ---- Filed documents (scanned invoices, receipts...): one journal row each, after the file really exists in her audit folder ----
DOC_CODE = "FIN"                                  # "Foundation finance and banking" in her Codes sheet
_DOC_LABEL = {"invoice_received": "invoice", "receipt": "receipt", "invoice_issued": "invoice issued by ICT4Peace", "contract": "contract", "other": "document"}
AUDIT_PREFIX = "Admin/ICT4Peace Audit"


def document_evidence(doc: dict) -> str:
    return f"{AUDIT_PREFIX}/{doc['year']}/{doc['folder']}/{doc['proposed_name']}"


def document_summary(doc: dict) -> str:
    who = doc.get("supplier") or "unknown"
    parts = [f"Filed {_DOC_LABEL.get(doc.get('doc_type') or '', 'document')}: {who}"]
    if doc.get("number"):
        parts.append(f"no. {doc['number']}")
    if doc.get("amount") is not None and doc.get("currency"):
        parts.append(f"{doc['currency']} {doc['amount']:.2f}")
    if doc.get("paid_date"):
        y, m, d = doc["paid_date"].split("-")
        parts.append(f"{'received' if doc.get('folder') == 'Income' else 'paid'} {d}.{m}.{y}")
    return clean_summary(", ".join(parts) + f" (in {doc['year']}/{doc['folder']})")


def build_document_row(doc: dict, journal_id: str, today: date, status: str = "confirmed") -> list[str]:
    """The twelve cells for a document she approved and the filer wrote. Evidence is the file's place in her audit folder."""
    return [journal_id, (doc.get("filed_at") or today.isoformat())[:10], "W", DOC_CODE, "document", document_summary(doc), "", document_evidence(doc), "", "capture", status, today.isoformat()]
