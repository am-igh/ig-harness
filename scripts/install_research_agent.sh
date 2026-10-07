#!/bin/sh
# Installs the background agent that reads public web pages for the chat box's Research mode (it fetches only pages found by your own search, and sends nothing).
# It starts at login and restarts if it stops. Remove it any time with: make research-uninstall
set -e
REPO="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="$(command -v python3)"
LABEL="org.ict4peace.igharness.research"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOGDIR="$HOME/IG-Harness-data/logs"
mkdir -p "$HOME/Library/LaunchAgents" "$LOGDIR"
cat > "$PLIST" <<PLISTEND
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array><string>$PYTHON</string><string>$REPO/tools/research_helper.py</string><string>run</string></array>
  <key>WorkingDirectory</key><string>$REPO</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>10</integer>
  <key>StandardOutPath</key><string>$LOGDIR/research_helper.log</string>
  <key>StandardErrorPath</key><string>$LOGDIR/research_helper.log</string>
  <key>EnvironmentVariables</key><dict><key>PATH</key><string>/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin</string></dict>
</dict></plist>
PLISTEND
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl kickstart -k "gui/$(id -u)/$LABEL"
echo "Research agent installed and started. It only searches and reads public pages for questions you ask in Research mode."
echo "Log (no page text): $LOGDIR/research_helper.log"
