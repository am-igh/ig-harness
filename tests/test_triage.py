

def test_context_lists_everyone_on_the_thread_so_rules_about_a_person_can_match(tmp_path):
    import json, sqlite3
    from harness import db
    from harness.triage import _context
    c = db.connect(tmp_path / "t.db"); db.migrate(c)
    c.execute("INSERT INTO emails (thread_id, message_id, from_email, received_at, to_addrs, cc_addrs, history) VALUES ('t','m','a@x.org','2026-10-01T10:00:00+02:00',?,?,?)",
              (json.dumps(["felix.staehli@example.org"]), json.dumps(["b@x.org"]), json.dumps([{"from_name": "Orsen Okami", "from_email": "o@y.org", "body": "SECRET BODY"}])))
    c.commit(); c.row_factory = sqlite3.Row
    ctx, _ = _context(c, c.execute("SELECT * FROM emails").fetchone())
    assert "felix.staehli@example.org" in ctx and "Orsen Okami" in ctx and "b@x.org" in ctx and "SECRET BODY" not in ctx
