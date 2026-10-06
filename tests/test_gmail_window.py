"""When the Gmail fetch hits its 100-thread limit (a burst of automated mail fills it), real emails older than the fetched range must not be retired from the list."""
import json
import time

from harness import db
from harness.importers.gmail import import_gmail


def t(id, hours_ago):
    return {"thread_id": id, "message_id": f"m-{id}", "messages_in_thread": 1, "received_ms": int((time.time() - hours_ago * 3600) * 1000), "from_name": "A", "from_email": f"{id}@x.org",
            "to_me_directly": True, "cc_only": False, "subject": id, "snippet": "s", "body": "b", "labels": [], "last_from_me": False, "bulk": False}


def write(folder, threads):
    (folder / "gmail_recent.json").write_text(json.dumps({"fetched_at": "x", "me": "me@x.org", "query": "q", "threads": threads}))


def test_a_full_fetch_does_not_retire_older_real_emails_and_restores_ones_wrongly_retired(tmp_path):
    c = db.connect(tmp_path / "t.db"); db.migrate(c)
    write(tmp_path, [t("real1", 20), t("real2", 30)])
    import_gmail(c, tmp_path)
    burst = [t(f"auto{i}", 0.1 + i / 1000) for i in range(100)]                  # 100 automated threads in the last minutes: the limit is reached
    write(tmp_path, burst)
    rep = import_gmail(c, tmp_path)[0]
    assert c.execute("SELECT COUNT(*) FROM emails WHERE in_window=1 AND thread_id LIKE 'real%'").fetchone()[0] == 2 and rep.retired == 0
    c.execute("UPDATE emails SET in_window=0 WHERE thread_id LIKE 'real%'"); c.commit()       # what the old code had done
    import_gmail(c, tmp_path)
    assert c.execute("SELECT COUNT(*) FROM emails WHERE in_window=1 AND thread_id LIKE 'real%'").fetchone()[0] == 2


def test_a_normal_fetch_still_retires_threads_that_left_the_inbox(tmp_path):
    c = db.connect(tmp_path / "t.db"); db.migrate(c)
    write(tmp_path, [t("a", 2), t("b", 3)])
    import_gmail(c, tmp_path)
    write(tmp_path, [t("a", 2)])
    assert import_gmail(c, tmp_path)[0].retired == 1 and c.execute("SELECT in_window FROM emails WHERE thread_id='b'").fetchone()[0] == 0


def test_inside_a_full_fetch_a_missing_thread_has_really_left(tmp_path):
    c = db.connect(tmp_path / "t.db"); db.migrate(c)
    write(tmp_path, [t("gone", 0.5)])
    import_gmail(c, tmp_path)
    write(tmp_path, [t(f"auto{i}", 0.1 + i / 100) for i in range(100)])        # spans a longer range than "gone"'s age? gone is at 0.5h, range reaches 1.09h: it was inside the range
    assert import_gmail(c, tmp_path)[0].retired == 1
