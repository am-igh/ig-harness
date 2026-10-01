"""Shared pieces of the refresh agent: its status file, the 'refresh now' request, and the schedule rules.

The agent itself (tools/refresh_worker.py) runs on the Mac, because the Google tokens live in the Keychain.
It writes `refresh_status.json` into the data directory; the API reads it so the screen can say when things
were last updated. The screen's 'Refresh now' button drops a request file that the agent picks up.
Pure standard library: no network and no Gmail here."""
import json
import os
from datetime import datetime, time, timedelta
from pathlib import Path

STATUS_FILE = "refresh_status.json"
REQUEST_FILE = "refresh_request"
HEARTBEAT_FILE = ".refresh_heartbeat"
INTERVAL = timedelta(minutes=30)
WINDOW_START, WINDOW_END = time(6, 30), time(21, 0)       # scheduled refreshes only happen between these local times
CORRESPONDENCE_EVERY = timedelta(hours=20)                 # the heavy 'who do I write to how' read: about once a day
STALE_AFTER = timedelta(hours=2, minutes=30)


def in_window(now: datetime) -> bool:
    return WINDOW_START <= now.time() <= WINDOW_END


def read_status(data_dir: Path) -> dict | None:
    try:
        return json.loads((data_dir / STATUS_FILE).read_text())
    except (OSError, ValueError):
        return None


def write_status(data_dir: Path, status: dict) -> None:
    """Atomic: the screen never reads half a file."""
    tmp = data_dir / f".{STATUS_FILE}.tmp"
    tmp.write_text(json.dumps(status, indent=1))
    tmp.replace(data_dir / STATUS_FILE)


def request_refresh(data_dir: Path, now: datetime | None = None) -> None:
    (data_dir / REQUEST_FILE).write_text((now or datetime.now()).isoformat(timespec="seconds"))


def take_request(data_dir: Path) -> bool:
    f = data_dir / REQUEST_FILE
    if f.exists():
        f.unlink(missing_ok=True)
        return True
    return False


def agent_alive(data_dir: Path, now: datetime | None = None, max_age: float = 20.0) -> bool:
    try:
        return ((now or datetime.now()).timestamp() - (data_dir / HEARTBEAT_FILE).stat().st_mtime) < max_age
    except OSError:
        return False


def _t(value: str | None, tz=None) -> datetime | None:
    """Parse a timestamp the agent wrote (with an offset); show it in `tz` (Geneva time) when given."""
    try:
        d = datetime.fromisoformat(value) if value else None
    except ValueError:
        return None
    return d.astimezone(tz) if d and d.tzinfo and tz else d


def scheduled_due(status: dict | None, now: datetime) -> bool:
    """A scheduled refresh is due inside the window when the last one started 30+ minutes ago (or none exists)."""
    if not in_window(now):
        return False
    last = _t((status or {}).get("started_at"))
    return last is None or now - last >= INTERVAL


def correspondence_due(status: dict | None, now: datetime, file_age: timedelta | None) -> bool:
    """Read past correspondence when there is no file yet, or about once a day inside the window."""
    if file_age is None:
        return True
    return in_window(now) and file_age >= CORRESPONDENCE_EVERY


def summary(status: dict | None, now: datetime, alive: bool) -> dict:
    """What the screen needs: the last update, whether it is fresh, and anything that went wrong."""
    if not status:
        return {"state": "never", "label": "Not refreshed yet", "problems": [], "alive": alive}
    problems = [f"{s['name']}: {s.get('note') or 'failed'}" for s in status.get("steps", []) if s.get("state") == "error"]
    done = _t(status.get("finished_at"), now.tzinfo)
    last_ok = _t(status.get("last_success_at"), now.tzinfo)
    if status.get("running"):
        state, label = "running", "Refreshing…"
    elif last_ok and (now - last_ok) > STALE_AFTER and in_window(now):
        state, label = "stale", f"Last update {last_ok:%H:%M}" if last_ok.date() == now.date() else f"Last update {last_ok:%d %b %H:%M}"
    else:
        state = "error" if problems else "ok"
        label = f"Updated {done:%H:%M}" if done and done.date() == now.date() else (f"Updated {done:%d %b %H:%M}" if done else "Updated")
    return {"state": state, "label": label, "problems": problems, "alive": alive, "steps": status.get("steps", []),
            "backup": status.get("backup"), "trigger": status.get("trigger")}
