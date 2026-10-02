"""Event emails and the Genève internationale newsletter -> events: rules, merging across sources, evidence-based status, candidates."""
import json
from datetime import date

import pytest

from harness import db, events as E
from harness.importers.event_mail import import_event_mail
from test_event_parsers import GI_HTML

TODAY = date(2026, 10, 2)


@pytest.fixture
def c(tmp_path):
    c = db.connect(tmp_path / "t.db"); db.migrate(c)
    return c


def msg(i, sender, subject, snippet="", date_ms=1790900000000, **kw):          # 2026-10-02
    return {"id": i, "thread_id": "t" + i, "date_ms": date_ms, "from_email": sender, "from_name": "", "subject": subject, "snippet": snippet, "bulk": False, "direct": True, **kw}


def write(folder, msgs, me="me@org.ch"):
    (folder / "event_mail.json").write_text(json.dumps({"fetched_at": "2026-10-02T08:00:00+00:00", "me": me, "messages": msgs}))


LUMA = ("Registration approved for Digital International Geneva - Monthly Thematic Session", "Some Person You've got a spot at Digital International Geneva - Monthly Thematic Session OCT 5 Monday, October 5 5:15 PM - 6:45 PM GMT+2 Giga Connectivity Centre ↗ Genève, Switzerland Event Page")


def test_each_kind_of_mail_becomes_an_event_with_the_right_status_and_evidence(c, tmp_path):
    write(tmp_path, [
        msg("m1", "secretariat@clubdiplomatique.ch", "📨 Invitation | Anticipatory Leadership Lab with GESDA, 17 September 2026 at 16:30"),
        msg("m2", "usr-x@user.luma-mail.com", LUMA[0], LUMA[1]),
        msg("m3", "summit@gesda.global", "Registration Confirmed - GESDA - The Anticipation Summit 2026", "Dates: 14-15 October 2026 Venue: PALEXPO", date_ms=1782912922000),
        msg("m4", "info@geneve-int.ch", "Genève internationale - Upcoming events", listing=[]),
        msg("m5", "secretariat@clubdiplomatique.ch", "📬 Newsletter | Upcoming Events | New Articles"),
        msg("m6", "me@org.ch", "Re: something"),
    ])
    r = import_event_mail(c, tmp_path)[0]
    ev = {e["title"]: e for e in c.execute("SELECT * FROM events")}
    assert set(ev) == {"Anticipatory Leadership Lab with GESDA", "Digital International Geneva - Monthly Thematic Session", "GESDA - The Anticipation Summit 2026"}
    assert ev["Anticipatory Leadership Lab with GESDA"]["derived_status"] == "invited" and ev["Anticipatory Leadership Lab with GESDA"]["start"] == "2026-09-17T16:30:00+02:00"
    luma = ev["Digital International Geneva - Monthly Thematic Session"]
    assert (luma["derived_status"], luma["geneva"], luma["venue"]) == ("confirmed", 1, "Giga Connectivity Centre")
    assert ev["GESDA - The Anticipation Summit 2026"]["derived_status"] == "confirmed" and ev["GESDA - The Anticipation Summit 2026"]["start"] == "2026-10-14"
    assert r.added == 3 and r.skipped == 1
    assert [tuple(x) for x in c.execute("SELECT kind, signal FROM event_evidence WHERE event_id=?", (luma["id"],))] == [("email-luma", "registration approved")]
    assert import_event_mail(c, tmp_path)[0].added == 0 and c.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 3                  # idempotent


def test_an_invitation_then_a_reminder_then_a_registration_are_one_event_and_the_strongest_evidence_wins(c, tmp_path):
    write(tmp_path, [
        msg("a", "secretariat@clubdiplomatique.ch", "📨 Invitation | Luncheon-debate with Dr Someone, 25 August 2026 at 12:00"),
        msg("b", "secretariat@clubdiplomatique.ch", "📨 Reminder | Luncheon-debate with Dr Someone, 25 August 2026 at 12:00"),
        msg("c", "x@user.luma-mail.com", "Registration confirmed for Luncheon-debate with Dr Someone", "A B You've got a spot at Luncheon-debate with Dr Someone AUG 25 Tuesday, August 25 12:00 PM - 2:00 PM GMT+2 Club ↗"),
    ])
    import_event_mail(c, tmp_path)
    assert c.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 1
    e = c.execute("SELECT * FROM events").fetchone()
    assert e["derived_status"] == "confirmed"
    assert sorted(x["kind"] for x in c.execute("SELECT kind FROM event_evidence")) == ["email-club", "email-club", "email-luma"]


def test_email_evidence_attaches_to_the_calendar_event_and_a_late_calendar_entry_absorbs_an_earlier_email_event(c, tmp_path):
    c.execute("INSERT INTO calendar_events (title, start, end, all_day, status, space, source, source_ref, my_response, location, self_organizer, attendee_count) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
              ("GESDA - The Anticipation Summit 2026", "2026-10-14", "2026-10-16", 1, "confirmed", "work", "google", "g1", "accepted", "Palexpo, Geneva", 0, 9)); c.commit()
    E.sync_calendar(c)
    write(tmp_path, [msg("m3", "summit@gesda.global", "Registration Confirmed - GESDA - The Anticipation Summit 2026", "Dates: 14-15 October 2026")])
    import_event_mail(c, tmp_path)
    assert c.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 1
    assert sorted(x["kind"] for x in c.execute("SELECT kind FROM event_evidence")) == ["calendar", "email-registration"]
    # the other order: the email event exists first, the calendar entry arrives later
    c.execute("DELETE FROM events"); c.execute("DELETE FROM calendar_events"); c.commit()
    import_event_mail(c, tmp_path)
    assert c.execute("SELECT source_kind FROM events").fetchone()[0] == "email-registration"
    c.execute("INSERT INTO calendar_events (title, start, end, all_day, status, space, source, source_ref, my_response, location, self_organizer, attendee_count) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
              ("GESDA - The Anticipation Summit 2026", "2026-10-14", "2026-10-16", 1, "confirmed", "work", "google", "g1", "needsAction", "Palexpo", 0, 9)); c.commit()
    E.sync_calendar(c)
    rows = c.execute("SELECT * FROM events").fetchall()
    assert len(rows) == 1 and rows[0]["source_kind"] == "calendar" and rows[0]["venue"] == "Palexpo"
    assert rows[0]["derived_status"] == "confirmed"                                                          # the registration email outranks "not yet answered"


def test_her_override_and_hide_survive_a_merge(c, tmp_path):
    write(tmp_path, [msg("a", "secretariat@clubdiplomatique.ch", "📨 Invitation | Closed-door Discussion at the GCSP, 1st October 2026 at 12:30")])
    import_event_mail(c, tmp_path)
    eid = c.execute("SELECT id FROM events").fetchone()[0]
    E.set_status(c, eid, "declined")
    c.execute("INSERT INTO calendar_events (title, start, end, all_day, status, space, source, source_ref, my_response, location, self_organizer, attendee_count) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
              ("Closed-door Discussion at the GCSP", "2026-10-01T12:30:00+02:00", "2026-10-01T14:00:00+02:00", 0, "confirmed", "work", "google", "g2", "needsAction", "GCSP", 0, 5)); c.commit()
    E.sync_calendar(c)
    row = c.execute("SELECT user_status, source_kind FROM events").fetchone()
    assert (row["user_status"], row["source_kind"]) == ("declined", "calendar")


def test_the_newsletter_tables_become_listing_events_and_only_topic_matches_are_shown_by_default(c, tmp_path):
    from harness.event_parsers import parse_geneve_int
    write(tmp_path, [msg("n1", "info@geneve-int.ch", "Genève internationale - Upcoming events", listing=parse_geneve_int(GI_HTML)),
                     msg("n2", "info@geneve-int.ch", "Genève internationale - Upcoming events", listing=parse_geneve_int(GI_HTML))])        # the same events again next week
    import_event_mail(c, tmp_path)
    ev = {e["title"]: e for e in c.execute("SELECT * FROM events")}
    assert len(ev) == 3 and all(e["source_kind"] == "listing-geneve-int" and e["tier"] == "S0" and e["geneva"] == 1 for e in ev.values())
    assert ev["AI Governance Day"]["relevant"] == 1 and ev["AI Governance Day"]["topics"] == "digital & AI"
    assert ev["11th Expert Group Meeting on DDT"]["relevant"] == 0
    shown = E.list_events(c, date(2026, 9, 1), "upcoming")
    assert [i["title"] for i in shown["items"]] == ["AI Governance Day"] and shown["other_listings"] == 2
    assert E.list_events(c, date(2026, 9, 1), "upcoming", include_other=True)["total"] == 3
    d = ev["WMO High-level Dialogue on Climate Science"]
    assert (d["start"], d["end"], d["all_day"], d["online"], d["organizer"]) == ("2026-09-14", "2026-09-19", 1, 1, "WMO")                   # inclusive dd.mm.yyyy end -> exclusive all-day end
    assert c.execute("SELECT COUNT(*) FROM event_evidence").fetchone()[0] == 6                                                              # one per message and event


def test_unreadable_invitations_become_candidates_and_a_missing_file_is_a_note(c, tmp_path):
    assert "sync-events" in import_event_mail(c, tmp_path)[0].notes[0]
    write(tmp_path, [msg("i1", "someone@university.edu", "Speaking Invitation: The 5th Academic Symposium on Global Security Governance", "Dear Anne-Marie, we would like to invite you"),
                     msg("i2", "shop@vendor.com", "Design rework after launch costs 10x more", bulk=True),
                     msg("i3", "o@org.org", "Registration Confirmed - Some Event", "no date in here at all")])
    import_event_mail(c, tmp_path)
    cand = [(r["subject"][:20], r["bulk"]) for r in c.execute("SELECT * FROM event_candidates ORDER BY id")]
    assert ("Speaking Invitation:", 0) in cand and ("Design rework after ", 1) in cand
    assert ("Registration Confirmed ", 0) in [(r["subject"][:23], r["bulk"]) for r in c.execute("SELECT * FROM event_candidates")]          # confirmed, but no date to read
    assert c.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0
    assert E.list_events(c, TODAY)["candidates"] == 3
