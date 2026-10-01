#!/usr/bin/env bash
#
# Install a macOS launchd agent that runs the OmniPong daily tournament scout
# (daily_check.py) once a day. Re-running this script is safe: it unloads any
# existing copy first.
#
# Usage:
#   ops/install_daily_check.sh              # daily at 09:00
#   DAILY_CHECK_HOUR=7 DAILY_CHECK_MINUTE=30 ops/install_daily_check.sh
#
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$REPO_DIR/.venv/bin/python"
LABEL="com.omnipong.dailycheck"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG_DIR="$REPO_DIR/logs"
HOUR="${DAILY_CHECK_HOUR:-9}"
MINUTE="${DAILY_CHECK_MINUTE:-0}"
DOMAIN="gui/$(id -u)"

if [[ ! -x "$PYTHON" ]]; then
  echo "error: $PYTHON not found or not executable." >&2
  echo "Create the venv first:  python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi

mkdir -p "$HOME/Library/LaunchAgents" "$LOG_DIR"

cat > "$PLIST" <<PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON</string>
        <string>$REPO_DIR/daily_check.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$REPO_DIR</string>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key><integer>$HOUR</integer>
        <key>Minute</key><integer>$MINUTE</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>$LOG_DIR/daily_check.out.log</string>
    <key>StandardErrorPath</key>
    <string>$LOG_DIR/daily_check.err.log</string>
    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
PLIST_EOF

# Reload cleanly (ignore "not currently loaded").
launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
launchctl bootstrap "$DOMAIN" "$PLIST"
launchctl enable "$DOMAIN/$LABEL" 2>/dev/null || true

echo "Installed $LABEL -> runs daily at $(printf '%02d:%02d' "$HOUR" "$MINUTE")."
echo "  plist: $PLIST"
echo "  logs:  $LOG_DIR/daily_check.{out,err}.log"
echo "Verify:  launchctl list | grep omnipong"
echo "Run now: launchctl kickstart -k $DOMAIN/$LABEL"
