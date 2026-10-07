"""Replies on open items: mail that answers something she waits for is surfaced even when it asks nothing and the item is filed under someone else. Synthetic people only."""
import json
from datetime import datetime

import pytest

from harness import brief, db, replies
from harness.config import TZ
from harness.triage import list_emails

NOW = datetime(2026, 10, 7, 9, 0, tzinfo=TZ)


@pytest.fixture
def c(tmp_path):
    c = db.connect(tmp_path / "t.db"); db.migrate(c)
    c.execute("INSERT INTO draft_settings (key, value, source) VALUES ('my_address', 'me@ict4peace.org', 'learned')")
    c.execute("INSERT INTO people (slug, name, org, email, space) VALUES ('kim-oster', 'Kim Oster', 'Org A', 'kim@a.org', 'work')")
    c.execute("INSERT INTO waiting_on (description, person, since_date, space) VALUES ('Org B to confirm Dana Stone or Sue Wilder and in person or online', 'kim-oster', '2026-10-01', 'work')")
    c.execute("INSERT INTO waiting_on (description, person, since_date, space) VALUES ('Budget comments', 'kim-oster; lee-park', '2026-10-01', 'work')")
    c.commit()
    return c


def mail(c, tid, name, addr, subject="Hello", hours_ago=10, to=None, cc=None, history=None, bulk=0, status="skipped", last_from_me=0, slug=None):
    rec = datetime.fromtimestamp(NOW.timestamp() - hours_ago * 3600, TZ).isoformat(timespec="seconds")
    c.execute("INSERT INTO emails (thread_id, message_id, from_name, from_email, subject, received_at, snippet, body, direct, bulk, last_from_me, triage_status, needs_reply, why, to_addrs, cc_addrs, history, person_slug) "
              "VALUES (?,?,?,?,?,?,?,?,1,?,?,?,0,'asks nothing',?,?,?,?)",
              (tid, "m" + tid, name, addr, subject, rec, "s", "We will revert soonest.", bulk, last_from_me, status, json.dumps(to or ["me@ict4peace.org"]), json.dumps(cc or []), json.dumps(history or []), slug))
    c.commit()


def test_a_reply_from_someone_named_in_the_description_is_caught_even_though_it_asks_nothing(c):
    mail(c, "t1", "Sue Wilder", "sue@b.org", subject="Re: save the date")         # a different thread, filed under Kim in Suivi; nothing is asked
    out = replies.find(c, NOW)
    assert [r["email"]["thread_id"] for r in out] == ["t1"] and "Sue Wilder (sender) is named in: Org B to confirm" in out[0]["reasons"][0]
    assert out[0]["item"].startswith("Org B to confirm")


def test_the_recorded_counterparty_and_a_second_person_in_the_person_field_both_match_by_address_and_name(c):
    mail(c, "t2", "Kim Oster", "kim@a.org")
    mail(c, "t3", "Lee Park", "lee@c.org")                                         # 'lee-park' is not in People but is named in the person field
    got = {r["email"]["thread_id"] for r in replies.find(c, NOW)}
    assert got == {"t2", "t3"}


def test_someone_copied_who_is_named_in_an_item_counts_too(c):
    mail(c, "t4", "Random Sender", "random@x.org", cc=["Dana Stone <dana@b.org>"])
    r = replies.find(c, NOW)
    assert len(r) == 1 and "Dana Stone (on the thread)" in r[0]["reasons"][0]


def test_a_thread_where_she_wrote_earlier_qualifies_with_no_open_item_at_all(c):
    mail(c, "t5", "Someone Else", "else@x.org", history=[{"from_me": True, "from_email": "me@ict4peace.org", "from_name": "Me", "body": "hi"}])
    r = replies.find(c, NOW)
    assert len(r) == 1 and r[0]["reasons"] == ["you wrote earlier in this thread"] and r[0]["item_id"] is None


def test_things_that_never_qualify(c):
    mail(c, "a1", "Sue Wilder", "no-reply@b.org", bulk=1)                           # automated sender
    mail(c, "a2", "Google", "no-reply@accounts.google.com", history=[{"from_me": True}])
    mail(c, "a3", "Sue Wilder", "sue@b.org", last_from_me=1)                         # she wrote last
    mail(c, "a4", "Unrelated Person", "u@x.org")                                     # nothing links it
    mail(c, "a5", "Sue Wilder", "sue@b.org", hours_ago=100)                          # too old for the window
    mail(c, "a6", "Sue Wilder", "sue@b.org")
    c.execute("UPDATE emails SET handled_at = datetime('now') WHERE thread_id='a6'")
    c.execute("UPDATE waiting_on SET space='personal' WHERE person='kim-oster'")      # personal items are not matched against
    c.commit()
    assert replies.find(c, NOW) == []


def test_they_appear_in_the_email_list_response_apart_from_the_list_and_not_twice(c):
    mail(c, "t1", "Sue Wilder", "sue@b.org")
    mail(c, "t9", "Kim Oster", "kim@a.org", status="done")
    c.execute("UPDATE emails SET needs_reply=1, score=5 WHERE thread_id='t9'"); c.commit()
    r = list_emails(c, 72, NOW)
    assert [m["thread_id"] for m in r["needs_reply"]] == ["t9"] and [m["thread_id"] for m in r["on_open_items"]] == ["t1"]      # t9 is already in the list: not repeated
    assert r["on_open_items"][0]["open_item"].startswith("Org B")


def test_the_brief_has_the_section_and_puts_it_in_the_attention_facts(c):
    from harness import brief_ai
    mail(c, "t1", "Sue Wilder", "sue@b.org", subject="Re: save the date")
    b = brief.build(c, NOW)
    text = brief.render_text(b)
    assert "2b. REPLIES ON OPEN ITEMS" in text and "- Sue Wilder — Re: save the date" in text
    assert text.index("2. IMPORTANT MAIL") < text.index("2b. REPLIES") < text.index("3. SUIVI")
    assert any("Sue Wilder replied" in f["title"] for f in brief_ai.facts(b)) and any("Sue Wilder replied" in a["title"] for a in b["attention"])
