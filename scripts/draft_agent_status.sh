#!/bin/sh
LABEL="org.ict4peace.igharness.drafts"
if launchctl print "gui/$(id -u)/$LABEL" >/dev/null 2>&1; then echo "Draft agent: installed"; else echo "Draft agent: NOT installed (run: make agent-install)"; fi
HB="$HOME/IG-Harness-data/draft_outbox/.heartbeat"
if [ -f "$HB" ]; then
  age=$(( $(date +%s) - $(stat -f %m "$HB") ))
  if [ "$age" -lt 25 ]; then echo "Heartbeat: running ($age s ago)"; else echo "Heartbeat: stale ($age s ago): the agent is not running"; fi
else
  echo "Heartbeat: none yet"
fi
