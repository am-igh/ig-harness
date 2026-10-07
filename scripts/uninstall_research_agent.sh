#!/bin/sh
LABEL="org.ict4peace.igharness.research"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
rm -f "$HOME/Library/LaunchAgents/$LABEL.plist"
echo "Research agent removed."
