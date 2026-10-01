#!/bin/sh
LABEL="org.ict4peace.igharness.refresh"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
rm -f "$HOME/Library/LaunchAgents/$LABEL.plist"
echo "Refresh agent removed. (Your data and backups are untouched.)"
