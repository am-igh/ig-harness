"""Style profiles: learned from past messages with plain rules, transparent and correctable."""
import json

import pytest

from harness import db, style
from harness.importers.correspondence import import_correspondence
from tools.google_helper import normalize_correspondence, strip_quoted

FR = "Bonjour Daniel,\n\nMerci beaucoup pour votre message. Nous vous confirmons que la réunion aura lieu jeudi avec vos collègues.\n\nBien cordialement,\nAnne-Marie Buzatu\nExecutive Director\nICT4Peace Foundation"
EN_FORMAL = "Dear Ambassador Smith,\n\nThank you for your letter. We would be pleased to join the panel and will confirm the details shortly.\n\nKind regards,\nAnne-Marie Buzatu\nExecutive Director\nICT4Peace Foundation"
EN_CASUAL = "Hi Sam,\n\nThanks! That works for me, see you on Thursday :)\n\nCheers,\nAM"
DE = "Sehr geehrte Frau Keller,\n\nvielen Dank für Ihre Nachricht. Wir bestätigen Ihnen den Termin und senden Ihnen die Unterlagen.\n\nFreundliche Grüsse\nAnne-Marie Buzatu"


# ---------- language
@pytest.mark.parametrize("text,lang", [(FR, "fr"), (EN_FORMAL, "en"), (DE, "de"),
    ("Buongiorno, grazie per la vostra email. Siamo lieti di confermare che la riunione è per giovedì.", "it"),
    ("Hola, gracias por su mensaje. Estamos muy contentos de confirmar la reunión para el jueves.", "es")])
def test_language_detection(text, lang):
    assert style.detect_language(text)[0] == lang


def test_too_short_or_unclear_text_gives_no_language():
    assert style.detect_language("ok")[0] is None and style.detect_language("12345 67890 !!! ???")[0] is None


# ---------- greeting, closing, signature
def test_greeting_replaces_the_recipients_name():
    assert style.greeting_of(FR, ["Daniel", "Stauffacher"]) == "Bonjour {name},"
    assert style.greeting_of(EN_FORMAL, ["Smith"]) == "Dear Ambassador {name},"
    assert style.greeting_of("Thanks for the note, I will check.", ["Sam"]) is None          # not a greeting


def test_closing_and_signature_are_found():
    c, sig = style.closing_and_signature(FR)
    assert c == "Bien cordialement," and sig == ["Anne-Marie Buzatu", "Executive Director", "ICT4Peace Foundation"]
    assert style.closing_and_signature(DE)[0] == "Freundliche Grüsse"
    assert style.closing_and_signature("No closing at all here")[0] is None


def test_the_signature_is_the_most_common_block():
    assert style.learned_signature([FR, EN_FORMAL, EN_CASUAL]).startswith("Anne-Marie Buzatu\nExecutive Director")


# ---------- formality
def test_french_vous_is_formal_and_tu_is_informal():
    assert style.build_profile([{"body": FR, "language": "fr"}], [], ["Daniel"]) | {} and \
        style.build_profile([{"body": FR, "language": "fr"}], [], ["Daniel"])["pronoun"] == "vous"
    tu = "Salut Marc,\n\nMerci pour ton message, je te confirme que ta proposition me convient. À bientôt,\nAM"
    p = style.build_profile([{"body": tu, "language": "fr"}], [], ["Marc"])
    assert (p["formality"], p["pronoun"]) == ("informal", "tu")


def test_english_formality_from_greeting_and_closing():
    assert style.build_profile([{"body": EN_FORMAL, "language": "en"}], [], ["Smith"])["formality"] == "formal"
    assert style.build_profile([{"body": EN_CASUAL, "language": "en"}], [], ["Sam"])["formality"] == "informal"


def test_german_sie_is_formal():
    p = style.build_profile([{"body": DE, "language": "de"}], [], ["Keller"])
    assert (p["language"], p["formality"], p["pronoun"]) == ("de", "formal", "Sie")


def test_profile_summary_and_confidence_levels():
    mine = [{"body": FR, "language": "fr"}] * 5
    p = style.build_profile(mine, [{"body": "Merci", "language": None}], ["Daniel"])
    assert p["greeting"] == "Bonjour {name}," and p["closing"] == "Bien cordialement," and p["n_mine"] == 5 and p["confidence"] == "high" and p["avg_words"] > 15
    assert style.build_profile(mine[:2], [], ["D"])["confidence"] == "low" and style.build_profile(mine[:4], [], ["D"])["confidence"] == "medium"


def test_a_person_she_never_wrote_to_has_no_formality_and_uses_their_language():
    p = style.build_profile([], [{"body": FR, "language": "fr"}], [])
    assert p["confidence"] == "none" and p["formality"] == "neutral" and p["language"] == "fr" and p["n_mine"] == 0


# ---------- helper: only the author's new text
def test_quoted_replies_and_forwarded_headers_are_stripped():
    txt = "Thanks, confirmed.\n\nBest,\nAM\n\nOn Mon, 28 Sep 2026 at 10:00, Sam <sam@x.org> wrote:\n> Can you confirm?\n> Thanks"
    assert strip_quoted(txt) == "Thanks, confirmed.\n\nBest,\nAM"
    assert strip_quoted("Merci.\n\nLe lun. 28 sept. 2026 à 10:00, Sam <s@x.org> a écrit :\n> blabla") == "Merci."
    assert strip_quoted("Hi\n> quoted\nreal line") == "Hi\nreal line"
    assert strip_quoted("OK\n\n-----Original Message-----\nFrom: x") == "OK"
    assert strip_quoted("OK\n\nSent from my iPhone") == "OK"


def test_correspondence_normalisation_keeps_only_messages_with_that_person():
    import base64
    b = lambda t: base64.urlsafe_b64encode(t.encode()).decode()
    mk = lambda id, frm, to, text, ms: {"id": id, "internalDate": str(ms), "payload": {"mimeType": "text/plain", "body": {"data": b(text)},
        "headers": [{"name": "From", "value": frm}, {"name": "To", "value": to}, {"name": "Subject", "value": "Plan"}, {"name": "Message-ID", "value": f"<{id}@x>"}]}}
    t = {"id": "T1", "messages": [mk("m1", "dan@org.ch", "me@x.org", "Hello?", 1), mk("m2", "me@x.org", "dan@org.ch", "Hi Dan,\n\nYes.\n\nBest,\nAM\n\nOn Mon Dan wrote:\n> Hello?", 2),
                                  mk("m3", "other@y.org", "me@x.org", "unrelated", 3)]}
    n = normalize_correspondence(t, "me@x.org", "dan@org.ch")
    assert [m["from_me"] for m in n["messages"]] == [False, True] and n["messages"][1]["body"] == "Hi Dan,\n\nYes.\n\nBest,\nAM"
    assert n["last_from_me"] is True and n["last_rfc_id"] == "<m2@x>"
    assert normalize_correspondence(t, "me@x.org", "nobody@z.org") is None


# ---------- importer + profiles end to end
def corr_file(folder, people):
    (folder / "correspondence.json").write_text(json.dumps({"fetched_at": "x", "me": "me@x.org", "people": people}))


def msg(id, from_me, body, ms):
    return {"msg_id": id, "ms": ms, "from_me": from_me, "from_email": "x", "subject": "S", "body": body, "rfc_id": f"<{id}@x>", "references": ""}


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db"); db.migrate(c)
    c.execute("INSERT INTO people (slug, name, org, role, email) VALUES ('dan','Daniel Stauffacher','Org','Ambassador','dan@org.ch')"); c.commit()
    return c


def test_import_learns_profiles_and_a_signature_and_is_idempotent(conn, tmp_path):
    corr_file(tmp_path, {"dan@org.ch": [{"thread_id": "T1", "subject": "S", "last_ms": 3000, "last_from_me": True, "last_rfc_id": "<m3@x>", "last_references": "",
                                         "messages": [msg("m1", False, "Bonjour Anne-Marie, pouvez-vous confirmer ?", 1000), msg("m2", True, FR, 2000), msg("m3", True, FR + " ", 3000)]}]})
    r = import_correspondence(conn, tmp_path)[0]
    assert r.added == 3
    p = dict(conn.execute("SELECT * FROM style_profiles WHERE person_email='dan@org.ch'").fetchone())
    assert (p["language"], p["formality"], p["pronoun"], p["greeting"], p["n_mine"], p["n_threads"]) == ("fr", "formal", "vous", "Bonjour {name},", 2, 1)
    assert conn.execute("SELECT value FROM draft_settings WHERE key='signature'").fetchone()[0].startswith("Anne-Marie Buzatu")
    r2 = import_correspondence(conn, tmp_path)[0]
    assert r2.added == 0 and r2.unchanged == 3


def test_her_edits_survive_relearning_but_counts_refresh(conn, tmp_path):
    corr_file(tmp_path, {"dan@org.ch": [{"thread_id": "T1", "subject": "S", "last_ms": 2000, "last_from_me": True, "last_rfc_id": "<m2@x>", "last_references": "",
                                         "messages": [msg("m2", True, FR, 2000)]}]})
    import_correspondence(conn, tmp_path)
    conn.execute("UPDATE style_profiles SET formality='informal', pronoun='tu', source='edited'"); conn.commit()
    corr_file(tmp_path, {"dan@org.ch": [{"thread_id": "T1", "subject": "S", "last_ms": 3000, "last_from_me": True, "last_rfc_id": "<m3@x>", "last_references": "",
                                         "messages": [msg("m2", True, FR, 2000), msg("m3", True, FR + " ", 3000)]}]})
    r = import_correspondence(conn, tmp_path)[0]
    p = dict(conn.execute("SELECT * FROM style_profiles").fetchone())
    assert (p["formality"], p["pronoun"], p["source"], p["n_mine"]) == ("informal", "tu", "edited", 2)
    assert "1 kept" in r.notes[-1]


def test_missing_file_is_a_note(conn, tmp_path):
    assert "make correspondence" in import_correspondence(conn, tmp_path)[0].notes[0]


def test_profile_api_edit_validation_and_signature():
    from fastapi.testclient import TestClient
    from harness.main import app
    with TestClient(app) as cl:
        assert cl.patch("/api/style/profiles/new@person.org", json={"language": "fr", "formality": "formal", "pronoun": "vous", "greeting": "Bonjour {name},"}).json() == {"ok": True}
        items = cl.get("/api/style/profiles").json()["items"]
        p = next(i for i in items if i["person_email"] == "new@person.org")
        assert (p["language"], p["source"], p["greeting"]) == ("fr", "edited", "Bonjour {name},")
        assert cl.patch("/api/style/profiles/new@person.org", json={"language": "klingon"}).status_code == 422
        assert cl.patch("/api/style/profiles/new@person.org", json={"formality": "rude"}).status_code == 422
        assert cl.patch("/api/style/profiles/new@person.org", json={"pronoun": "ihr"}).status_code == 422
        assert cl.put("/api/style/signature", json={"signature": "AM\nICT4Peace"}).json() == {"ok": True}
        s = cl.get("/api/style/signature").json()
        assert s["signature"] == "AM\nICT4Peace" and s["source"] == "edited"
        assert cl.put("/api/style/signature", json={"signature": "x" * 601}).status_code == 422
