#!/bin/sh
LABEL="org.ict4peace.igharness.drafts"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
rm -f "$HOME/Library/LaunchAgents/$LABEL.plist"
echo "Draft agent removed. (Drafts already saved in Gmail stay there.)"
