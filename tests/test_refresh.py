"""The refresh agent: schedule rules, resilient cycles, honest status, and no draft/send capability."""
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from harness import refresh as R
from tools import refresh_worker as W

ROOT = Path(__file__).resolve().parent.parent
GENEVA = timezone(timedelta(hours=2))
T = lambda h, m=0, day=1: datetime(2026, 10, day, h, m, tzinfo=GENEVA)


# ---------------------------------------------------------------- schedule rules
@pytest.mark.parametrize("h,m,expected", [(6, 29, False), (6, 30, True), (12, 0, True), (21, 0, True), (21, 1, False), (3, 0, False), (23, 59, False)])
def test_scheduled_refreshes_only_happen_in_working_hours(h, m, expected):
    assert R.in_window(T(h, m)) is expected


def test_a_refresh_is_due_every_30_minutes_inside_the_window_only():
    assert R.scheduled_due(None, T(8)) is True
    assert R.scheduled_due({"started_at": T(8, 0).isoformat()}, T(8, 29)) is False
    assert R.scheduled_due({"started_at": T(8, 0).isoformat()}, T(8, 30)) is True
    assert R.scheduled_due({"started_at": T(8, 0).isoformat()}, T(22, 0)) is False
    assert R.scheduled_due(None, T(2, 0)) is False


def test_correspondence_is_read_when_missing_or_about_daily():
    assert R.correspondence_due({}, T(8), None) is True
    assert R.correspondence_due({}, T(8), timedelta(hours=3)) is False
    assert R.correspondence_due({}, T(8), timedelta(hours=21)) is True
    assert R.correspondence_due({}, T(2), timedelta(hours=40)) is False          # not at night


def test_the_request_file_is_taken_once(tmp_path):
    assert R.take_request(tmp_path) is False
    R.request_refresh(tmp_path, T(9))
    assert R.take_request(tmp_path) is True and R.take_request(tmp_path) is False


def test_status_files_roundtrip_and_survive_junk(tmp_path):
    assert R.read_status(tmp_path) is None
    R.write_status(tmp_path, {"a": 1}); assert R.read_status(tmp_path) == {"a": 1}
    (tmp_path / R.STATUS_FILE).write_text("{ broken"); assert R.read_status(tmp_path) is None


def test_agent_heartbeat(tmp_path):
    assert R.agent_alive(tmp_path) is False
    (tmp_path / R.HEARTBEAT_FILE).touch()
    assert R.agent_alive(tmp_path) is True
    assert R.agent_alive(tmp_path, now=datetime.now() + timedelta(minutes=5)) is False


# ---------------------------------------------------------------- what the screen is told
def test_summary_states():
    assert R.summary(None, T(9), False)["state"] == "never"
    ok = {"running": False, "finished_at": T(9, 5).isoformat(), "last_success_at": T(9, 5).isoformat(), "steps": [{"name": "gmail", "state": "ok"}]}
    s = R.summary(ok, T(9, 40), True)
    assert s["state"] == "ok" and s["label"] == "Updated 09:05" and s["problems"] == []
    assert R.summary({**ok, "running": True}, T(9, 40), True)["label"] == "Refreshing…"
    bad = {**ok, "steps": [{"name": "gmail", "state": "error", "note": "Not logged in. Run: login-gmail"}]}
    sb = R.summary(bad, T(9, 40), True)
    assert sb["state"] == "error" and sb["problems"] == ["gmail: Not logged in. Run: login-gmail"]
    assert R.summary(ok, T(12, 0), True)["state"] == "stale"                          # nothing succeeded for 2h55 in working hours
    assert R.summary(ok, T(23, 0), True)["state"] == "ok"                             # at night, old is normal
    assert R.summary(ok, T(23, 0, day=3), True)["label"] == "Updated 01 Oct 09:05"    # an older day shows the date (at night nothing is stale)
    assert R.summary(ok, T(9, 40, day=3), True)["label"] == "Last update 01 Oct 09:05" and R.summary(ok, T(9, 40, day=3), True)["state"] == "stale"


def test_times_are_shown_in_the_viewers_timezone():
    utc = timezone.utc
    st = {"running": False, "finished_at": datetime(2026, 10, 1, 7, 5, tzinfo=utc).isoformat(), "last_success_at": datetime(2026, 10, 1, 7, 5, tzinfo=utc).isoformat(), "steps": []}
    assert R.summary(st, T(9, 30), True)["label"] == "Updated 09:05"                  # 07:05 UTC is 09:05 in Geneva


# ---------------------------------------------------------------- a refresh cycle
class Fakes:
    def __init__(self, fail=(), api=True, import_reports=None, backup_note="saved harness-x.db"):
        self.fail, self.api, self.calls, self.http_calls = set(fail), api, [], []
        self.reports = import_reports or [{"source": "suivi:commitments", "added": 2, "updated": 1}, {"source": "gmail:threads", "added": 3, "updated": 0}]
        self.backup_note = backup_note

    def sub(self, args, timeout):
        cmd = args[-1]; self.calls.append(cmd)
        return (1, "Not logged in. Run: login-gmail") if cmd in self.fail else (0, f"Wrote {cmd}")

    def call(self, method, path, timeout=60):
        self.http_calls.append((method, path))
        if path == "/api/health":
            return (200, {}) if self.api else (0, None)
        if path == "/api/import":
            return 200, {"reports": self.reports}
        if path == "/api/triage/run":
            return 200, {"started": True}
        return 404, None

    def backup(self):
        if isinstance(self.backup_note, Exception):
            raise self.backup_note
        return self.backup_note


def cycle(tmp_path, f, **kw):
    kw.setdefault("age", lambda: timedelta(hours=1))
    return W.run_cycle(tmp_path, "manual", sub=f.sub, call=f.call, backup=f.backup, now=lambda: T(9), **{"event_age_fn": lambda: timedelta(hours=1), **kw})


def test_a_full_cycle_runs_every_step_in_order_and_records_success(tmp_path):
    f = Fakes()
    st = cycle(tmp_path, f)
    assert [s["name"] for s in st["steps"]] == ["calendar", "gmail", "suivi", "import", "triage", "backup"]    # correspondence not due (read 1h ago)
    assert f.calls == ["sync", "sync-gmail", "run"] and ("POST", "/api/import") in f.http_calls and ("POST", "/api/triage/run") in f.http_calls
    assert st["ok"] is True and st["running"] is False and st["last_success_at"] == st["finished_at"]
    assert st["steps"][3]["note"] == "6 change(s)" and st["backup"]["note"] == "saved harness-x.db"
    assert R.read_status(tmp_path) == st


def test_correspondence_runs_when_due_or_forced(tmp_path):
    f = Fakes(); cycle(tmp_path, f, age=lambda: None)
    assert "sync-correspondence" in f.calls
    f2 = Fakes(); cycle(tmp_path, f2, force_correspondence=True)
    assert "sync-correspondence" in f2.calls


def test_one_failing_step_never_stops_the_others(tmp_path):
    f = Fakes(fail={"sync-gmail"})
    st = cycle(tmp_path, f)
    states = {s["name"]: s["state"] for s in st["steps"]}
    assert states == {"calendar": "ok", "gmail": "error", "suivi": "ok", "import": "ok", "triage": "ok", "backup": "ok"}
    assert st["ok"] is False and st["last_success_at"] is None
    assert "Not logged in" in st["steps"][1]["note"]


def test_last_success_is_kept_when_a_later_cycle_fails(tmp_path):
    cycle(tmp_path, Fakes())
    first = R.read_status(tmp_path)["last_success_at"]
    st = W.run_cycle(tmp_path, "schedule", sub=Fakes(fail={"sync"}).sub, call=Fakes().call, backup=Fakes().backup, now=lambda: T(10), age=lambda: timedelta(hours=1), event_age_fn=lambda: timedelta(hours=1))
    assert st["ok"] is False and st["last_success_at"] == first


def test_when_the_harness_is_not_running_the_fetches_still_happen_and_the_rest_is_skipped_not_failed(tmp_path):
    f = Fakes(api=False)
    st = cycle(tmp_path, f)
    states = {s["name"]: s["state"] for s in st["steps"]}
    assert states["calendar"] == "ok" and states["gmail"] == "ok" and states["import"] == "skipped" and states["triage"] == "skipped"
    assert st["ok"] is True and "make up" in st["steps"][3]["note"]


def test_import_problems_are_reported_by_name(tmp_path):
    f = Fakes(import_reports=[{"source": "suivi", "error": "FileNotFoundError: Suivi.xlsx"}, {"source": "calendar:events", "added": 0, "updated": 0}])
    st = cycle(tmp_path, f)
    imp = next(s for s in st["steps"] if s["name"] == "import")
    assert imp["state"] == "error" and "suivi: FileNotFoundError" in imp["note"] and st["ok"] is False


def test_a_crash_inside_a_step_is_caught(tmp_path):
    st = cycle(tmp_path, Fakes(backup_note=RuntimeError("disk full")))
    assert next(s for s in st["steps"] if s["name"] == "backup") == {"name": "backup", "state": "error", "note": "RuntimeError: disk full", "seconds": 0.0} | {"seconds": st["steps"][-1]["seconds"]}
    assert st["ok"] is False and st["finished_at"]


def test_the_status_shows_progress_while_a_cycle_is_running(tmp_path):
    seen = []
    f = Fakes()
    orig = f.sub
    f.sub = lambda args, timeout: (seen.append(R.read_status(tmp_path)), orig(args, timeout))[1]
    cycle(tmp_path, f)
    assert seen[0]["running"] is True and seen[0]["steps"][-1] == {"name": "calendar", "state": "running", "note": "", "seconds": 0}
    assert [len(x["steps"]) for x in seen][:2] == [1, 2]


# ---------------------------------------------------------------- this agent can read Google data and nothing else
def test_the_refresh_agent_has_no_draft_or_send_capability():
    src = (ROOT / "tools" / "refresh_worker.py").read_text()
    assert not re.search(r"draft_worker|gmail\.compose|gmail\.modify|messages/send|drafts/send|smtplib", src.replace("tools/draft_worker.py, a separate agent", ""), re.I)
    commands = set(re.findall(r'helper\("([a-z-]+)"', src))
    assert commands == {"sync", "sync-gmail", "sync-correspondence", "sync-events"}      # read-only subcommands only (each only reads; the helper holds read-only Google scopes)


def test_the_refresh_agent_writes_to_suivi_only_through_the_suivi_writer():
    src = (ROOT / "tools" / "refresh_worker.py").read_text()
    assert 'TOOLS / "suivi_writer.py", "run"' in src
    assert not re.search(r"openpyxl|zipfile|Suivi\.xlsx", src.split("def main")[0].replace("Suivi.xlsx", ""), re.I)       # no file-editing code of its own


def test_the_install_scripts_start_only_the_refresh_worker():
    text = (ROOT / "scripts" / "install_refresh_agent.sh").read_text()
    assert "refresh_worker.py" in text and "draft_worker" not in text


# ---------------------------------------------------------------- API
def test_refresh_api_endpoints(tmp_path):
    from fastapi.testclient import TestClient
    from harness.config import DATA_DIR
    from harness.main import app
    with TestClient(app) as cl:
        (DATA_DIR / R.STATUS_FILE).unlink(missing_ok=True)
        assert cl.get("/api/refresh/status").json()["state"] == "never"
        r = cl.post("/api/refresh/now").json()
        assert r["requested"] is True and (DATA_DIR / R.REQUEST_FILE).exists()
        R.take_request(DATA_DIR)
        R.write_status(DATA_DIR, {"running": False, "finished_at": datetime.now().astimezone().isoformat(), "last_success_at": datetime.now().astimezone().isoformat(), "steps": []})
        assert cl.get("/api/refresh/status").json()["state"] == "ok"


def test_event_emails_are_read_when_missing_or_older_than_six_hours(tmp_path):
    for age, expect in ((None, True), (timedelta(hours=7), True), (timedelta(hours=2), False)):
        f = Fakes()
        st = W.run_cycle(tmp_path, "manual", sub=f.sub, call=f.call, backup=f.backup, now=lambda: T(9), age=lambda: timedelta(hours=1), event_age_fn=lambda a=age: a)
        assert ("events" in [s["name"] for s in st["steps"]]) is expect
