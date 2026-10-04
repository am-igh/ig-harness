#!/usr/bin/env python3
"""Mac-side Reminders reader: your phone to-dos. Standard library only. READ-ONLY: it never changes, completes or deletes a reminder.

You say to Siri "add call Daniel on Friday to my Harness list" (or type it in Reminders); iCloud syncs it to this Mac; this helper reads the list named
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

JXA = r"""
const R = Application("Reminders");
const name = %s;
const l = R.lists().find(x => x.name() === name);
const pad = n => (n < 10 ? "0" : "") + n;
const ymd = d => d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate());
if (!l) { JSON.stringify({error: "no list named " + name}); }
else {
  JSON.stringify({items: l.reminders().map(r => {
    const d = r.dueDate();
    const hasTime = d && (d.getHours() !== 0 || d.getMinutes() !== 0);
    const c = r.creationDate();
    return {id: r.id(), name: r.name(), body: r.body() || "", due_date: d ? ymd(d) : null, due_time: hasTime ? pad(d.getHours()) + ":" + pad(d.getMinutes()) : null,
            created: c ? c.toISOString() : null, completed: r.completed()};
  })});
}
"""


def run_jxa(list_name: str, runner=subprocess.run) -> dict:
    r = runner(["osascript", "-l", "JavaScript", "-e", JXA % json.dumps(list_name)], capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        msg = (r.stderr or "").strip().splitlines()[-1:] or ["osascript failed"]
        return {"error": ("macOS has not allowed this program to control Reminders yet. In System Settings > Privacy & Security > Automation, allow it." if "not allowed" in msg[0].lower() or "-1743" in msg[0] else msg[0][:200])}
    try:
        return json.loads(r.stdout.strip() or "{}")
    except ValueError:
        return {"error": "could not read the answer from Reminders"}


def pull(out: Path = OUT, list_name: str = LIST_NAME, runner=subprocess.run) -> str:
    data = run_jxa(list_name, runner)
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
