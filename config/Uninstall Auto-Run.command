#!/bin/bash
# ══════════════════════════════════════════════════════════════════
#  Fantasy Baseball Daily Briefing — Auto-Run Uninstaller
#  Double-click to remove the 7 AM daily schedule.
# ══════════════════════════════════════════════════════════════════

PLIST_NAME="com.rory.fantasybriefing"
PLIST_DEST="$HOME/Library/LaunchAgents/${PLIST_NAME}.plist"

echo ""
echo "Uninstalling Fantasy Baseball auto-run..."

launchctl unload "$PLIST_DEST" 2>/dev/null
rm -f "$PLIST_DEST"

if [ ! -f "$PLIST_DEST" ]; then
    echo "✅  Uninstalled. The briefing will no longer run automatically."
    echo "    You can still run it manually with Run.command."
else
    echo "⚠   Could not remove $PLIST_DEST — try from Terminal."
fi

echo ""
read -p "Press Enter to close..."
