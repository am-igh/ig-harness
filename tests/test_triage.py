

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


def _watch_conn(tmp_path, **kw):
    import json, sqlite3
    from harness import db
    c = db.connect(tmp_path / "w.db"); db.migrate(c)
    row = dict(thread_id="t", message_id="m", from_name="Michael Meier", from_email="m@etat.ge.ch", received_at="2026-10-01T10:00:00+02:00", subject="Thanks",
               body="Dear all, thanks.", to_addrs=json.dumps(["felix.staehli@example.org", "x@y.org"]), cc_addrs="[]", history="[]", last_from_me=0)
    row.update(kw)
    c.execute(f"INSERT INTO emails ({','.join(row)}) VALUES ({','.join('?' * len(row))})", list(row.values()))
    c.commit(); c.row_factory = sqlite3.Row
    return c


def test_watch_hit_matches_cc_addresses_accents_and_text_but_not_partial_names(tmp_path):
    from harness.triage import watch_hit
    c = _watch_conn(tmp_path)
    e = c.execute("SELECT * FROM emails").fetchone()
    assert watch_hit(e, ["Felix Staehli"]) == "Felix Staehli" and watch_hit(e, ["Félix STAEHLI"]) == "Félix STAEHLI"
    assert watch_hit(e, ["Felix Staehil"]) is None and watch_hit(e, ["Felix Meier"]) is None and watch_hit(e, ["Anna Schmidt"]) is None
    assert watch_hit(e, []) is None
    c2 = _watch_conn(tmp_path / "b" if False else tmp_path, thread_id="t2", to_addrs="[]", body="Please ask Yannick Heiniger about the venue.")
    assert watch_hit(c2.execute("SELECT * FROM emails WHERE thread_id='t2'").fetchone(), ["Yannick Heiniger"]) == "Yannick Heiniger"


def test_watched_name_forces_needs_reply_even_when_the_model_says_no_or_fails(tmp_path):
    from harness.triage import triage_pending

    class NoGateway:
        def complete(self, *a, **k):
            from types import SimpleNamespace
            return SimpleNamespace(ok=False, text="", reason="down", model=None)
    c = _watch_conn(tmp_path, bulk=1)
    c.execute("INSERT INTO watch_names (name) VALUES ('Felix Staehli')"); c.commit()
    triage_pending(c, NoGateway())
    r = c.execute("SELECT triage_status, needs_reply, why FROM emails").fetchone()
    assert (r["triage_status"], r["needs_reply"]) == ("done", 1) and "Felix Staehli" in r["why"]


def test_watch_does_not_override_her_own_last_word(tmp_path):
    from harness.triage import triage_pending
    c = _watch_conn(tmp_path, last_from_me=1)
    c.execute("INSERT INTO watch_names (name) VALUES ('Felix Staehli')"); c.commit()
    triage_pending(c, None.__class__ and type("G", (), {"complete": lambda *a, **k: None})())
    assert c.execute("SELECT triage_status FROM emails").fetchone()[0] == "skipped"


def test_watch_api(tmp_path):
    from fastapi.testclient import TestClient
    from harness.main import app
    with TestClient(app) as cl:
        i = cl.post("/api/triage/watch", json={"text": "  Zz  Test Person "}).json()["id"]
        assert "Zz Test Person" in [w["name"] for w in cl.get("/api/triage/watch").json()["items"]]
        assert cl.post("/api/triage/watch", json={"text": "ab"}).status_code == 422
        cl.delete(f"/api/triage/watch/{i}")
        assert "Zz Test Person" not in [w["name"] for w in cl.get("/api/triage/watch").json()["items"]]


def test_the_cap_counts_model_reads_not_emails_skipped_by_rule(tmp_path):
    """Regression: 60 newsletters at the top used to use up the whole cap and leave real emails pending."""
    from harness import db, triage
    c = db.connect(tmp_path / "t.db"); db.migrate(c)
    for i in range(8):
        c.execute("INSERT INTO emails (thread_id, message_id, from_name, from_email, subject, received_at, triage_status, in_window, direct, bulk) VALUES (?,?,?,?,?,?, 'pending', 1, ?, ?)",
                  (f"t{i}", f"m{i}", "N", "news@x.org", "Newsletter", f"2026-10-06T1{i}:00:00+02:00", 0, 1))
    c.execute("INSERT INTO emails (thread_id, message_id, from_name, from_email, subject, received_at, triage_status, in_window, direct) VALUES ('r','r','Real','real@x.org','Please reply','2026-10-01T10:00:00+02:00','pending',1,1)")
    c.commit()
    class G:
        def complete(self, *a, **k):
            class R: ok = False; text = ""; reason = "down"; model = "m"
            return R()
    out = triage.triage_pending(c, G(), limit=3)
    assert out["skipped"] >= 1 and out["error"] == 1                      # the real one was reached (and failed only because this fake model is down)
