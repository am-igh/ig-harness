#!/usr/bin/env python3
"""Mac-side Reminders reader: your phone to-dos. Standard library only. READ-ONLY: it never changes, completes or deletes a reminder.

You say to Siri "add call Daniel on Friday to my Harness list" (or type it in Reminders); iCloud syncs it to this Mac; this helper (AppleScript, read-only) reads the list named
"Harness" (change it with IG_REMINDERS_LIST) and writes ~/IG-Harness-data/phone_todos.json, which the harness imports into a short "From your phone"
list on Today for you to confirm. macOS asks once for permission to let this program control Reminders (System Settings > Privacy & Security > Automation).

  python3 tools/reminders_helper.py pull      read the list now (the refresh agent does this every few minutes)
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

DATA = Path(os.environ.get("IG_DATA_DIR", Path.home() / "IG-Harness-data"))
OUT = DATA / "phone_todos.json"
LIST_NAME = os.environ.get("IG_REMINDERS_LIST", "Harness")

# AppleScript, reading each property for the whole list at once (a handful of fast calls). Reading reminder by reminder, or through JXA, can hang for minutes.
SCRIPT = r"""
on stamp(dd, sep)
	if dd is missing value then return ""
	return (year of dd as string) & "-" & text -2 thru -1 of ("0" & ((month of dd) as integer)) & "-" & text -2 thru -1 of ("0" & (day of dd)) & sep & text -2 thru -1 of ("0" & (hours of dd)) & ":" & text -2 thru -1 of ("0" & (minutes of dd))
end stamp
set RS to character id 30
set US to character id 31
tell application "Reminders"
	set theList to list "%s"
	set idL to id of every reminder of theList
	set nameL to name of every reminder of theList
	set bodyL to body of every reminder of theList
	set dueL to due date of every reminder of theList
	set createL to creation date of every reminder of theList
	set doneL to completed of every reminder of theList
end tell
set out to ""
repeat with i from 1 to (count of idL)
	set b to item i of bodyL
	if b is missing value then set b to ""
	set out to out & (item i of idL) & US & (item i of nameL) & US & b & US & my stamp(item i of dueL, " ") & US & my stamp(item i of createL, "T") & US & (item i of doneL) & RS
end repeat
return out
"""
RS, US = "\x1e", "\x1f"


def parse_output(text: str) -> list[dict]:
    items = []
    for rec in text.strip("\n").split(RS):
        f = rec.strip("\n").split(US)
        if len(f) < 6 or not f[0].strip():
            continue
        due = f[3].strip()
        items.append({"id": f[0].strip(), "name": f[1].strip(), "body": f[2].strip(), "due_date": due[:10] or None,
                      "due_time": (due[11:16] if len(due) >= 16 and due[11:16] != "00:00" else None), "created": f[4].strip() or None, "completed": f[5].strip().lower() == "true"})
    return items


def run_reminders(list_name: str, runner=subprocess.run) -> dict:
    safe = list_name.replace("\\", "\\\\").replace('"', '\\"')
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".applescript", delete=False) as f:           # a file, not stdin: piping the script made osascript 5-10x slower
        f.write(SCRIPT % safe)
    try:
        r = runner(["osascript", f.name], capture_output=True, text=True, timeout=200)
    finally:
        Path(f.name).unlink(missing_ok=True)
    if r.returncode != 0:
        err = (r.stderr or "").strip().splitlines()[-1:] or ["osascript failed"]
        low = err[0].lower()
        if "-1743" in err[0] or "not authorized" in low or "not allowed" in low:
            return {"error": "macOS has not allowed this program to control Reminders yet. In System Settings > Privacy & Security > Automation, allow it."}
        if "-1728" in err[0] or "can't get list" in low:
            return {"error": f"no list named {list_name}"}
        return {"error": err[0][:200]}
    return {"items": parse_output(r.stdout)}


def pull(out: Path = OUT, list_name: str = LIST_NAME, runner=subprocess.run) -> str:
    data = run_reminders(list_name, runner)
    doc = {"fetched_at": datetime.now(timezone.utc).isoformat(), "list": list_name, "error": data.get("error"), "items": data.get("items", [])}
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False))
    tmp.replace(out)
    out.chmod(0o600)
    return f"read {len(doc['items'])} reminder(s) from '{list_name}'" if not doc["error"] else f"{doc['error']}"


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "pull":
        msg = pull()
        print(msg)
        sys.exit(0 if not msg.startswith(("no list", "macOS", "could not")) else 1)
    sys.exit(__doc__)
