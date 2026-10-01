"""The ONE definition of a draft request: its fields, its validation, its hash and its RFC 822 form.

Pure standard library. Shared by the API (which writes a request after Anne-Marie approves a draft) and by
the Mac-side draft worker (which re-validates everything before touching Gmail). A draft is a message that
is saved, never sent: there is nothing in this module, or anywhere in the harness, that sends mail."""
import base64
import hashlib
import json
import re
from email.message import EmailMessage
from email.utils import formataddr

FIELDS = ("kind", "thread_id", "to", "cc", "subject", "in_reply_to", "references", "body")
MAX_BODY = 20_000
MAX_SUBJECT = 300
MAX_RECIPIENTS = 10
_EMAIL = re.compile(r"^[A-Za-z0-9._%+\-']+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
_MSGID = re.compile(r"^<[^<>\s\r\n]{3,300}>$")
_THREAD = re.compile(r"^[A-Za-z0-9]{6,64}$")


class InvalidDraft(ValueError):
    pass


def _no_newlines(name: str, v: str) -> str:
    if "\r" in v or "\n" in v or "\x00" in v:
        raise InvalidDraft(f"{name} contains a line break")      # blocks header injection (e.g. a hidden Bcc)
    return v


def validate(f: dict) -> dict:
    """Return a clean copy of the fields or raise InvalidDraft. Unknown fields are refused, never ignored."""
    extra = set(f) - set(FIELDS)
    if extra:
        raise InvalidDraft(f"unknown field(s): {', '.join(sorted(extra))}")
    kind = f.get("kind", "reply")
    if kind not in ("reply", "reminder", "new"):
        raise InvalidDraft("kind must be reply, reminder or new")
    out = {"kind": kind}
    for key in ("to", "cc"):
        addrs = f.get(key) or []
        if not isinstance(addrs, list) or not all(isinstance(a, str) for a in addrs):
            raise InvalidDraft(f"{key} must be a list of addresses")
        for a in addrs:
            if not _EMAIL.match(_no_newlines(key, a)):
                raise InvalidDraft(f"{key}: not a valid address")
        out[key] = [a.lower() for a in addrs]
    if not out["to"]:
        raise InvalidDraft("a draft needs at least one recipient")
    if len(out["to"]) + len(out["cc"]) > MAX_RECIPIENTS:
        raise InvalidDraft("too many recipients")
    subject = _no_newlines("subject", str(f.get("subject", "")))
    if not subject.strip() or len(subject) > MAX_SUBJECT:
        raise InvalidDraft("the subject is empty or too long")
    out["subject"] = subject.strip()
    body = str(f.get("body", ""))
    if not body.strip() or len(body) > MAX_BODY or "\x00" in body:
        raise InvalidDraft("the body is empty or too long")
    out["body"] = body
    for key in ("in_reply_to",):
        v = f.get(key)
        out[key] = None if not v else (v if _MSGID.match(_no_newlines(key, str(v))) else _bad(key))
    refs = f.get("references")
    if refs:
        parts = _no_newlines("references", str(refs)).split()
        if not parts or len(parts) > 50 or not all(_MSGID.match(p) for p in parts):
            raise InvalidDraft("references is not a list of message ids")
        out["references"] = " ".join(parts)
    else:
        out["references"] = None
    t = f.get("thread_id")
    out["thread_id"] = None if not t else (t if _THREAD.match(str(t)) else _bad("thread_id"))
    if kind == "reply" and not out["thread_id"]:
        raise InvalidDraft("a reply needs the thread it belongs to")
    return out


def _bad(name: str):
    raise InvalidDraft(f"{name} is not valid")


def content_hash(fields: dict) -> str:
    """Hash of the validated fields. The approved text is bound to this: change one character and it differs."""
    canon = json.dumps({k: fields.get(k) for k in FIELDS}, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canon.encode()).hexdigest()


def to_raw(fields: dict) -> str:
    """The message as Gmail expects it for a DRAFT: base64url RFC 822. No Bcc, ever."""
    msg = EmailMessage()
    msg["To"] = ", ".join(fields["to"])
    if fields.get("cc"):
        msg["Cc"] = ", ".join(fields["cc"])
    msg["Subject"] = fields["subject"]
    if fields.get("in_reply_to"):
        msg["In-Reply-To"] = fields["in_reply_to"]
    if fields.get("references"):
        msg["References"] = fields["references"]
    msg["X-IG-Harness"] = "draft"
    msg.set_content(fields["body"])
    return base64.urlsafe_b64encode(msg.as_bytes()).decode()
