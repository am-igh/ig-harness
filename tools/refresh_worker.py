#!/usr/bin/env python3
"""Mac-side refresh agent. Standard library only.

Keeps the harness current without you running anything: every 30 minutes between 06:30 and 21:00 (and
whenever you press "Refresh now" in the app) it
  1. fetches your Google Calendar and recent Gmail            (read-only; tokens stay in the Keychain)
  2. reads your past correspondence with each person           (about once a day)
  3. tells the harness to import everything and triage new emails
  4. makes the daily backup of the harness database
It runs on the Mac, outside Docker, because the Google tokens live in the Keychain. It holds only the READ-ONLY
Google permissions: it has no draft or send capability (those live in tools/draft_worker.py, a separate agent).
Each step is recorded in ~/IG-Harness-data/refresh_status.json, which the app shows. A step that fails never
stops the others.

  python3 tools/refresh_worker.py run      keep running (used by the background agent)
  python3 tools/refresh_worker.py once     refresh now and print each step
  python3 tools/refresh_worker.py status   show the last refresh
"""
import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from harness import refresh as R                      # noqa: E402  (pure standard library)

DATA = Path(os.environ.get("IG_DATA_DIR", Path.home() / "IG-Harness-data"))
API = os.environ.get("IG_API", "http://127.0.0.1:5173")
TOOLS = ROOT / "tools"
CORR_FILE = DATA / "correspondence.json"


def _now() -> datetime:
    return datetime.now().astimezone()


def run_sub(args: list[str], timeout: int) -> tuple[int, str]:
    """Run one of our helper scripts; return its exit code and its last line of output (no email text is ever printed by them)."""
    try:
        r = subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, f"timed out after {timeout // 60} min"
    lines = [ln.strip() for ln in (r.stdout + "\n" + r.stderr).splitlines() if ln.strip()]
    return r.returncode, (lines[-1] if lines else "")[:200]


def http(method: str, path: str, timeout: int = 60) -> tuple[int, dict | None]:
    try:
        req = urllib.request.Request(API + path, method=method, data=b"" if method == "POST" else None)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception:
        return 0, None


def backup_daily() -> str:
    import backup as bk
    p = bk.ensure_daily()
    bk.prune()
    return f"saved {p.name}" if p else "today's backup already exists"


def corr_age() -> timedelta | None:
    try:
        return datetime.now() - datetime.fromtimestamp(CORR_FILE.stat().st_mtime)
    except OSError:
        return None


def run_cycle(data_dir: Path, trigger: str, *, sub=run_sub, call=http, backup=backup_daily, age=corr_age, now=_now, force_correspondence: bool = False) -> dict:
    """One refresh. Every step is recorded as it happens; one failing step never stops the next."""
    prev = R.read_status(data_dir) or {}
    status = {"running": True, "trigger": trigger, "started_at": now().isoformat(timespec="seconds"), "finished_at": None, "ok": None,
              "steps": [], "last_success_at": prev.get("last_success_at"), "backup": prev.get("backup")}

    def step(name: str, fn):
        entry = {"name": name, "state": "running", "note": "", "seconds": 0}
        status["steps"].append(entry)
        R.write_status(data_dir, status)
        t0 = time.time()
        try:
            state, note = fn()
        except Exception as e:                       # a bug in one step must not stop the rest
            state, note = "error", f"{type(e).__name__}: {e}"
        entry.update(state=state, note=note, seconds=round(time.time() - t0, 1))
        R.write_status(data_dir, status)
        return state

    def helper(cmd: str, timeout: int):
        def go():
            rc, line = sub([TOOLS / "google_helper.py", cmd], timeout)
            return ("ok" if rc == 0 else "error"), line
        return go

    api_up = call("GET", "/api/health", 10)[0] == 200
    step("calendar", helper("sync", 240))
    step("gmail", helper("sync-gmail", 480))
    if force_correspondence or R.correspondence_due(prev, now(), age()):
        step("correspondence", helper("sync-correspondence", 1800))

    def do_import():
        if not api_up:
            return "skipped", "the harness is not running (make up)"
        code, body = call("POST", "/api/import", 180)
        if code != 200 or body is None:
            return "error", f"import failed (HTTP {code})"
        bad = [r for r in body.get("reports", []) if "error" in r]
        changed = sum(r.get("added", 0) + r.get("updated", 0) for r in body.get("reports", []))
        return ("error", f"{bad[0]['source']}: {bad[0]['error'][:120]}") if bad else ("ok", f"{changed} change(s)")

    def do_triage():
        if not api_up:
            return "skipped", "the harness is not running"
        code, body = call("POST", "/api/triage/run", 30)
        return ("ok", "started" if (body or {}).get("started") else "already running") if code == 200 else ("error", f"HTTP {code}")

    step("import", do_import)
    step("triage", do_triage)

    def do_backup():
        note = backup()
        status["backup"] = {"last_ok_at": now().isoformat(timespec="seconds"), "note": note}
        return "ok", note
    step("backup", do_backup)

    status.update(running=False, finished_at=now().isoformat(timespec="seconds"))
    status["ok"] = all(s["state"] != "error" for s in status["steps"])
    if status["ok"]:
        status["last_success_at"] = status["finished_at"]
    R.write_status(data_dir, status)
    return status


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else ""
    DATA.mkdir(parents=True, exist_ok=True)
    if cmd == "status":
        st = R.read_status(DATA)
        print(json.dumps(R.summary(st, _now(), R.agent_alive(DATA)), indent=1) if st else "No refresh has run yet.")
        return 0
    if cmd == "once":
        st = run_cycle(DATA, "manual")
        for s in st["steps"]:
            print(f"{s['name']:15} {s['state']:8} {s['seconds']:>6}s  {s['note']}")
        print("OK" if st["ok"] else "Some steps failed.")
        return 0 if st["ok"] else 1
    if cmd == "run":
        first = True
        while True:
            (DATA / R.HEARTBEAT_FILE).touch()
            now, st = _now(), R.read_status(DATA)
            trigger = "manual" if R.take_request(DATA) else ("start" if first and (st is None or R.scheduled_due(st, now)) else ("schedule" if R.scheduled_due(st, now) else None))
            first = False
            if trigger:
                try:
                    res = run_cycle(DATA, trigger)
                    bad = [s["name"] for s in res["steps"] if s["state"] == "error"]
                    print(f"{now:%H:%M:%S} refresh ({trigger}): " + ("ok" if not bad else "problems in " + ", ".join(bad)), flush=True)
                except Exception as e:
                    print(f"refresh error: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
            time.sleep(5)
    sys.exit(__doc__)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
