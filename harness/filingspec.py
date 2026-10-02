"""Rules for filing a bank statement into the audit folder. Pure standard library: shared by the API (preview, approval) and by the
Mac-side filer (tools/filer.py), so both enforce the SAME rules. Decided with Anne-Marie on 2 Oct 2026: new files only, never overwrite
or delete, each file filed only after she approved its preview. The statement keeps UBS's own file name (her checker finds it by that name)."""
import hashlib
import re
from pathlib import Path

# The same pattern her checker uses (RELEVE_STEM = ^0240.*Relev), tightened to a plain PDF file name with no path in it.
NAME_RE = re.compile(r"^0240[0-9A-Za-z]{10,24}_Relev[A-Za-z0-9_ ().\-]{0,120}\.pdf$")
PERIOD_RE = re.compile(r"(\d{2})\.(\d{2})\.(\d{4})\s*-\s*(\d{2})\.(\d{2})\.(\d{4})\s*/\s*([A-Za-zéèÉ]+)")
MAX_BYTES = 25 * 1024 * 1024


def valid_name(name: str) -> bool:
    return bool(NAME_RE.match(name)) and "/" not in name and "\\" not in name and ".." not in name


def clean_upload_name(raw: str) -> str:
    """The browser's file name without any folder part (and without the browser's ' (1)' re-download suffix being treated specially)."""
    return re.split(r"[\\/]", raw)[-1]


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def account_key(name: str) -> str:
    """The account part of UBS's name: everything before '_Relev' ('0240000022575501J0000')."""
    return name.split("_Relev")[0]


def period_from_text(text: str) -> dict | None:
    """'01.04.2026 - 30.06.2026 / Trimestrielle' on the first page -> {'from': ISO, 'to': ISO, 'kind': 'Trimestrielle'}."""
    m = PERIOD_RE.search(text or "")
    if not m:
        return None
    d1, m1, y1, d2, m2, y2, kind = m.groups()
    return {"from": f"{y1}-{m1}-{d1}", "to": f"{y2}-{m2}-{d2}", "kind": kind}


def create_new_file(dest: Path, content: bytes) -> None:
    """Create `dest` with the content, refusing if anything already exists there (O_EXCL: no overwrite is possible)."""
    import os
    fd = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
    except BaseException:
        raise


# ---- Scanned invoices, receipts and other justificatifs ("documents") -------------------------------------------------
# Decided with Anne-Marie on 2 Oct 2026: a simple rule decides the folder (expenses -> Expenses, income -> Income); contracts and
# anything unclear wait for her choice. Only these two existing sub-folders of the connected year folder may ever be written to.
DOC_FOLDERS = ("Expenses", "Income")
DOC_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]{2,150}\.pdf$")
CURRENCIES = ("CHF", "EUR", "USD", "GBP")
_DOC_TYPE_FOLDER = {"invoice_received": "Expenses", "receipt": "Expenses", "invoice_issued": "Income"}
_DOC_KIND = {"invoice_received": "Facture", "receipt": "Recu", "invoice_issued": "Facture"}


def valid_doc_name(name: str) -> bool:
    return bool(DOC_NAME_RE.match(name)) and ".." not in name


def folder_for_type(doc_type: str | None) -> str | None:
    return _DOC_TYPE_FOLDER.get(doc_type or "")


def _ascii(text: str) -> str:
    import unicodedata
    return unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()


def doc_name(doc_type: str | None, supplier: str | None, number: str | None, amount: float | None, currency: str | None,
             paid_date_iso: str | None, folder: str | None, version: int = 1) -> str | None:
    """Her convention: Fournisseur_Facture_<n>_CHF<montant>_paye_JJ.MM.AAAA.pdf (income: _recu_). None when something needed is missing.
    The payment part is added only when the payment is known, so a document is tied to exactly one payment (one document, one payment)."""
    sup = re.sub(r"_+", "_", re.sub(r"[^A-Za-z0-9]+", "_", _ascii(supplier or ""))).strip("_")[:40]
    cur = (currency or "").upper()
    if not sup or amount is None or cur not in CURRENCIES or doc_type not in _DOC_KIND or amount <= 0:
        return None
    parts = [sup, _DOC_KIND[doc_type]]
    num = re.sub(r"[^A-Za-z0-9\-]+", "", _ascii(number or ""))[:30]
    if num:
        parts.append(num)
    parts.append(f"{cur}{amount:.2f}")
    if paid_date_iso and re.match(r"^\d{4}-\d{2}-\d{2}$", paid_date_iso):
        y, m, d = paid_date_iso.split("-")
        parts += ["recu" if folder == "Income" else "paye", f"{d}.{m}.{y}"]
    name = "_".join(parts) + (f"_v{version}" if version > 1 else "") + ".pdf"
    return name if valid_doc_name(name) else None
