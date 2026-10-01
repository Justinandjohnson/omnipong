#!/usr/bin/env bash
#
# Remove the OmniPong daily-check launchd agent installed by
# ops/install_daily_check.sh.
#
set -euo pipefail

LABEL="com.omnipong.dailycheck"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
DOMAIN="gui/$(id -u)"

launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
rm -f "$PLIST"
echo "Removed $LABEL."
