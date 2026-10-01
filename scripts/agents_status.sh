#!/bin/sh
# Shows both background agents: the one that saves approved drafts, and the one that keeps the harness current.
check() { # label, heartbeat-file, install-hint
  if launchctl print "gui/$(id -u)/$1" >/dev/null 2>&1; then inst="installed"; else inst="NOT installed ($3)"; fi
  if [ -f "$2" ]; then
    age=$(( $(date +%s) - $(stat -f %m "$2") ))
    if [ "$age" -lt 25 ]; then hb="running (heartbeat $age s ago)"; else hb="NOT running (last heartbeat $age s ago)"; fi
  else
    hb="no heartbeat yet"
  fi
  echo "  $4: $inst; $hb"
}
echo "Background agents"
check org.ict4peace.igharness.drafts "$HOME/IG-Harness-data/draft_outbox/.heartbeat" "run: make agent-install" "Draft agent  "
check org.ict4peace.igharness.refresh "$HOME/IG-Harness-data/.refresh_heartbeat" "run: make refresh-install" "Refresh agent"
python3 "$(dirname "$0")/../tools/refresh_worker.py" status 2>/dev/null | python3 -c "
import sys, json
t = sys.stdin.read().strip()
try:
    d = json.loads(t)
    print('  Last refresh:', d.get('label'), '(' + d.get('state', '?') + ')' + ('; problems: ' + ' | '.join(d['problems']) if d.get('problems') else ''))
except Exception:
    print('  Last refresh:', t or 'none yet')
"
B=$(ls -1 "$HOME/IG-Harness-Backups"/harness-*.db 2>/dev/null | tail -1)
if [ -n "$B" ]; then echo "  Latest backup: $(basename "$B")"; else echo "  Latest backup: none yet (run: make backup)"; fi
