"""The no-send guarantee (CLAUDE.md rule 1). The harness creates Gmail drafts and can never send.

Layers proved here: (1) the code has no send function and the draft worker's Gmail door is a strict
allow-list of ONE operation; (2) a draft is only created for text Anne-Marie approved (status + hash);
(3) static scans of the whole code base. The network layer is proved by `make check-network`."""
import ast
import base64
import json
import re
import sqlite3
from email import message_from_bytes
from pathlib import Path

import pytest

from harness import db, draftspec
from harness.draftspec import InvalidDraft
from tools import draft_worker as dw
from tools.draft_worker import ForbiddenOperation, GuardedGmail, NotApproved

ROOT = Path(__file__).resolve().parent.parent
GOOD_URL = "https://gmail.googleapis.com/gmail/v1/users/me/drafts"
GOOD_BODY = {"message": {"raw": "UmVwbHk", "threadId": "18c0ffee12345678"}}


class Recorder:
    def __init__(self):
        self.calls = []

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url))
        return {"id": "r-123"}


# ------------------------------------------------------------------ layer 1: the allow-list
def test_creating_a_draft_is_the_one_allowed_operation():
    rec = Recorder()
    out = GuardedGmail(rec).request("POST", GOOD_URL, {"Authorization": "Bearer x"}, GOOD_BODY)
    assert out == {"id": "r-123"} and rec.calls == [("POST", GOOD_URL)]


SEND_ROUTES = [
    ("POST", "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"),
    ("POST", "https://gmail.googleapis.com/gmail/v1/users/me/drafts/send"),
    ("POST", "https://gmail.googleapis.com/gmail/v1/users/me/drafts/r-123/send"),
    ("POST", "https://gmail.googleapis.com/gmail/v1/users/me/messages/import"),
    ("POST", "https://gmail.googleapis.com/gmail/v1/users/me/messages/insert"),
    ("POST", "https://gmail.googleapis.com/gmail/v1/users/me/messages/batchDelete"),
    ("POST", "https://gmail.googleapis.com/gmail/v1/users/me/messages/r-123/trash"),
    ("POST", "https://gmail.googleapis.com/gmail/v1/users/me/threads/18c0ffee/modify"),
    ("POST", "https://gmail.googleapis.com/gmail/v1/users/me/settings/forwardingAddresses"),
    ("POST", "https://gmail.googleapis.com/gmail/v1/users/me/settings/filters"),
    ("POST", "https://gmail.googleapis.com/gmail/v1/users/me/settings/autoForwarding"),
    ("POST", "https://www.googleapis.com/upload/gmail/v1/users/me/messages/send"),
    ("POST", "https://www.googleapis.com/upload/gmail/v1/users/me/drafts?uploadType=media"),
    ("PUT", "https://gmail.googleapis.com/gmail/v1/users/me/drafts/r-123"),
    ("DELETE", "https://gmail.googleapis.com/gmail/v1/users/me/drafts/r-123"),
    ("GET", "https://gmail.googleapis.com/gmail/v1/users/me/messages"),
    ("PATCH", GOOD_URL), ("GET", GOOD_URL), ("HEAD", GOOD_URL), ("OPTIONS", GOOD_URL), ("post", GOOD_URL),
    # tricks on the allowed route
    ("POST", GOOD_URL + "/"),
    ("POST", GOOD_URL + "?alt=json"),
    ("POST", GOOD_URL + "?send=true"),
    ("POST", GOOD_URL + "#send"),
    ("POST", GOOD_URL + ";x=1"),
    ("POST", "https://gmail.googleapis.com/gmail/v1/users/me/%64rafts"),
    ("POST", "https://gmail.googleapis.com/gmail/v1/users/me/drafts/../messages/send"),
    ("POST", "https://gmail.googleapis.com/gmail/v1/users/me//drafts"),
    ("POST", "https://gmail.googleapis.com/gmail/v1/users/me/Drafts"),
    ("POST", "https://gmail.googleapis.com/gmail/v1/users/anyone@example.com/drafts"),
    ("POST", "http://gmail.googleapis.com/gmail/v1/users/me/drafts"),
    ("POST", "https://gmail.googleapis.com.evil.example/gmail/v1/users/me/drafts"),
    ("POST", "https://evil.example/gmail.googleapis.com/gmail/v1/users/me/drafts"),
    ("POST", "https://gmail.googleapis.com@evil.example/gmail/v1/users/me/drafts"),
    ("POST", "https://user:pw@gmail.googleapis.com/gmail/v1/users/me/drafts"),
    ("POST", "https://gmail.googleapis.com:8443/gmail/v1/users/me/drafts"),
    ("POST", "https://mail.google.com/gmail/v1/users/me/drafts"),
    ("POST", "gmail.googleapis.com/gmail/v1/users/me/drafts"),
    ("POST", ""),
]


@pytest.mark.parametrize("method,url", SEND_ROUTES)
def test_everything_except_creating_a_draft_is_refused_and_never_transmitted(method, url):
    rec = Recorder()
    with pytest.raises(ForbiddenOperation):
        GuardedGmail(rec).request(method, url, {"Authorization": "Bearer x"}, GOOD_BODY)
    assert rec.calls == []


@pytest.mark.parametrize("header", ["X-HTTP-Method-Override", "x-http-method", "X-Method-Override"])
def test_method_override_headers_cannot_turn_a_draft_call_into_something_else(header):
    rec = Recorder()
    with pytest.raises(ForbiddenOperation):
        GuardedGmail(rec).request("POST", GOOD_URL, {header: "DELETE"}, GOOD_BODY)
    assert rec.calls == []


@pytest.mark.parametrize("body", [
    None, {}, [], "raw", {"message": "x"}, {"message": {}}, {"message": {"threadId": "x"}},
    {"message": {"raw": "x", "labelIds": ["SENT"]}}, {"message": {"raw": "x", "send": True}},
    {"message": {"raw": 5}}, {"message": {"raw": "x"}, "send": True}, {"message": {"raw": "x"}, "draft": {"id": "1"}},
    {"id": "r-1", "message": {"raw": "x"}},
])
def test_the_request_body_may_only_contain_a_message(body):
    rec = Recorder()
    with pytest.raises(ForbiddenOperation):
        GuardedGmail(rec).request("POST", GOOD_URL, {}, body)
    assert rec.calls == []


# ------------------------------------------------------------------ the draft itself
FIELDS = {"kind": "reply", "thread_id": "18c0ffee12345678", "to": ["Dan@Org.ch"], "cc": [], "subject": "Re: Plan",
          "in_reply_to": "<abc123@mail.example>", "references": "<abc123@mail.example>", "body": "Bonjour Daniel,\n\nMerci.\n"}


@pytest.mark.parametrize("change,msg", [
    ({"subject": "Hi\nBcc: boss@evil.com"}, "line break"),
    ({"to": ["a@b.org\nBcc: x@y.org"]}, "line break"),
    ({"to": ["a@b.org", "not an address"]}, "valid address"),
    ({"to": []}, "recipient"),
    ({"to": [f"u{i}@x.org" for i in range(11)]}, "too many"),
    ({"bcc": ["x@y.org"]}, "unknown field"),
    ({"send": True}, "unknown field"),
    ({"labelIds": ["SENT"]}, "unknown field"),
    ({"body": ""}, "body"),
    ({"body": "x" * 20_001}, "body"),
    ({"subject": ""}, "subject"),
    ({"kind": "send"}, "kind"),
    ({"thread_id": None}, "thread"),
    ({"thread_id": "../x"}, "thread_id"),
    ({"in_reply_to": "no-brackets"}, "in_reply_to"),
    ({"references": "<a@b> evil"}, "references"),
])
def test_invalid_or_sneaky_drafts_are_refused(change, msg):
    with pytest.raises(InvalidDraft, match=msg):
        draftspec.validate({**FIELDS, **change})


def test_the_message_built_for_gmail_is_a_plain_draft_with_no_hidden_recipients():
    clean = draftspec.validate(FIELDS)
    m = message_from_bytes(base64.urlsafe_b64decode(draftspec.to_raw(clean)))
    assert m["To"] == "dan@org.ch" and m["Subject"] == "Re: Plan" and m["In-Reply-To"] == "<abc123@mail.example>"
    assert m["Bcc"] is None and m["X-IG-Harness"] == "draft"
    assert "Merci." in m.get_payload(decode=True).decode()


def test_the_hash_changes_with_a_single_character():
    a = draftspec.validate(FIELDS)
    b = draftspec.validate({**FIELDS, "body": FIELDS["body"] + "."})
    assert draftspec.content_hash(a) != draftspec.content_hash(b)


# ------------------------------------------------------------------ layer 2: only approved text is ever drafted
@pytest.fixture
def world(tmp_path):
    dbfile = tmp_path / "harness.db"
    c = db.connect(dbfile); db.migrate(c)
    outbox = tmp_path / "draft_outbox"; outbox.mkdir()
    fields = draftspec.validate(FIELDS)
    c.execute("INSERT INTO draft_requests (id, status, body_hash, created_at) VALUES ('req-ok','approved',?, '2026-10-01')", (draftspec.content_hash(fields),))
    c.execute("INSERT INTO draft_requests (id, status, body_hash, created_at) VALUES ('req-pending','draft',?, '2026-10-01')", (draftspec.content_hash(fields),))
    c.commit()
    ro = dw._db(dbfile)
    rec = Recorder()
    return {"ro": ro, "outbox": outbox, "rec": rec, "gmail": GuardedGmail(rec), "fields": fields, "c": c}


def put(world, rid, fields=None, h=None):
    f = fields if fields is not None else world["fields"]
    (world["outbox"] / f"{rid}.json").write_text(json.dumps({"request_id": rid, "fields": f, "hash": h or draftspec.content_hash(f)}))


def run(world):
    return dw.process_outbox(world["outbox"], world["ro"], world["gmail"], lambda: "token")


def test_an_approved_draft_creates_exactly_one_gmail_draft_and_never_a_second(world):
    put(world, "req-ok")
    assert run(world) == {"created": 1, "refused": 0, "skipped": 0}
    assert world["rec"].calls == [("POST", GOOD_URL)]
    assert json.loads((world["outbox"] / "req-ok.result.json").read_text())["gmail_draft_id"] == "r-123"
    assert run(world)["skipped"] == 1 and len(world["rec"].calls) == 1


def test_a_draft_that_was_not_approved_never_reaches_gmail(world):
    put(world, "req-pending")
    assert run(world)["refused"] == 1 and world["rec"].calls == []
    put(world, "req-unknown")
    assert run(world)["refused"] == 1 and world["rec"].calls == []


def test_text_changed_after_approval_is_refused(world):
    edited = {**world["fields"], "body": "Please wire the money to this account."}
    put(world, "req-ok", edited)                                    # hash recomputed by the attacker: still not the approved one
    assert run(world)["refused"] == 1 and world["rec"].calls == []


def test_a_forged_hash_in_the_file_is_refused(world):
    edited = {**world["fields"], "to": ["attacker@evil.com"]}
    put(world, "req-ok", edited, h=draftspec.content_hash(world["fields"]))
    assert run(world)["refused"] == 1 and world["rec"].calls == []


def test_a_request_file_with_a_send_flag_or_extra_fields_is_refused(world):
    put(world, "req-ok", {**world["fields"], "send": True})
    assert run(world)["refused"] == 1 and world["rec"].calls == []
    (world["outbox"] / "req-ok.result.json").unlink()
    (world["outbox"] / "req-ok.json").write_text(json.dumps({"request_id": "req-ok", "fields": world["fields"], "hash": "x", "send": True}))
    assert run(world)["refused"] == 1 and world["rec"].calls == []


def test_garbage_files_are_refused_without_a_crash(world):
    (world["outbox"] / "junk.json").write_text("{not json")
    (world["outbox"] / "list.json").write_text("[1,2,3]")
    assert run(world)["refused"] == 2 and world["rec"].calls == []


def test_the_worker_reads_the_database_read_only(world):
    with pytest.raises(sqlite3.OperationalError):
        world["ro"].execute("UPDATE draft_requests SET status='approved'")


# ------------------------------------------------------------------ layer 3: static scans of the whole code base
def _py_files(*dirs):
    for d in dirs:
        assert (ROOT / d).is_dir(), f"{d}/ is not visible to the tests, so it would not be scanned (check docker-compose mounts)"
        yield from (ROOT / d).rglob("*.py")


def test_no_code_anywhere_mentions_a_gmail_send_route():
    pat = re.compile(r"(messages|drafts)/(\{?\w*\}?/)?send|/send\b|users/me/messages/(import|insert)", re.I)
    hits = [f"{p.relative_to(ROOT)}: {m.group(0)}" for p in _py_files("harness", "tools", "worker", "scripts")
            for m in pat.finditer(p.read_text())]
    assert hits == []


def test_no_function_or_import_that_sends_mail_exists():
    bad_imports = {"smtplib", "aiosmtplib", "imaplib", "poplib", "yagmail", "sendgrid", "mailjet_rest", "mailgun", "emails", "zmail"}
    offenders = []
    for p in _py_files("harness", "tools", "worker"):
        for node in ast.walk(ast.parse(p.read_text())):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and re.search(r"send|smtp|deliver", node.name, re.I):
                offenders.append(f"{p.relative_to(ROOT)}: def {node.name}")
            if isinstance(node, ast.Import):
                offenders += [f"{p.relative_to(ROOT)}: import {a.name}" for a in node.names if a.name.split(".")[0] in bad_imports]
            if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] in bad_imports:
                offenders.append(f"{p.relative_to(ROOT)}: from {node.module}")
    assert offenders == []


def test_the_ui_calls_no_send_endpoint():
    api = (ROOT / "ui" / "src" / "api.ts").read_text()
    assert not re.search(r"/send|sendMail|send_email", api, re.I)


def test_the_draft_worker_has_exactly_one_network_call():
    src = (ROOT / "tools" / "draft_worker.py").read_text()
    assert len(re.findall(r"urlopen\(", src)) == 1 and "def _transmit" in src
    assert src.count("_transmit") == 3          # its definition, the docstring mention and the one place it is handed to GuardedGmail


def test_only_the_draft_worker_may_know_the_compose_permission():
    for p in _py_files("harness", "tools", "worker"):
        text = p.read_text()
        if p.name == "draft_worker.py":
            continue
        assert not re.search(r"gmail\.compose|gmail\.modify|auth/gmail\.send|mail\.google\.com/\"", text), p.name


def test_the_read_only_google_helper_only_ever_posts_to_googles_token_endpoint():
    tree = ast.parse((ROOT / "tools" / "google_helper.py").read_text())
    posts = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "_post"]
    assert posts and all(isinstance(c.args[0], ast.Name) and c.args[0].id == "TOKEN_URL" for c in posts)
