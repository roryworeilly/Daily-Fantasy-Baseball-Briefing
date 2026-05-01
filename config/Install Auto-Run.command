#!/bin/bash
# ══════════════════════════════════════════════════════════════════
#  Fantasy Baseball Daily Briefing — Auto-Run Installer
#  Double-click this file to install the daily 7 AM auto-run.
#  Run it again at any time to update the schedule.
# ══════════════════════════════════════════════════════════════════

PLIST_NAME="com.rory.fantasybriefing"
PLIST_SRC="$(dirname "$0")/${PLIST_NAME}.plist"
PLIST_DEST="$HOME/Library/LaunchAgents/${PLIST_NAME}.plist"
FB_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_PYTHON="$FB_DIR/.venv/bin/python"

echo ""
echo "══════════════════════════════════════════════"
echo "  Fantasy Baseball — Auto-Run Installer"
echo "══════════════════════════════════════════════"
echo ""

# ── Preflight checks ──────────────────────────────────────────────
if [ ! -f "$PLIST_SRC" ]; then
    echo "❌  ERROR: plist not found at:"
    echo "    $PLIST_SRC"
    read -p "Press Enter to close..."
    exit 1
fi

if [ ! -f "$VENV_PYTHON" ]; then
    echo "❌  ERROR: Virtual environment not found."
    echo "    Expected: $VENV_PYTHON"
    echo ""
    echo "    Set up the venv first:"
    echo "      python3 -m venv .venv"
    echo "      .venv/bin/pip install espn-api pybaseball requests-cache"
    read -p "Press Enter to close..."
    exit 1
fi

# ── Unload any existing version ───────────────────────────────────
if launchctl list | grep -q "$PLIST_NAME" 2>/dev/null; then
    echo "→  Unloading existing agent..."
    launchctl unload "$PLIST_DEST" 2>/dev/null
fi

# ── Copy plist to LaunchAgents ────────────────────────────────────
mkdir -p "$HOME/Library/LaunchAgents"
cp "$PLIST_SRC" "$PLIST_DEST"
sed -i '' "s|__FB_DIR__|${FB_DIR}|g" "$PLIST_DEST"
chmod 644 "$PLIST_DEST"
echo "→  Installed plist to:"
echo "   $PLIST_DEST"

# ── Load the agent ────────────────────────────────────────────────
launchctl load "$PLIST_DEST"
if [ $? -eq 0 ]; then
    echo ""
    echo "✅  Auto-run installed successfully!"
    echo ""
    echo "   The briefing will now run automatically every morning at 7:00 AM."
    echo "   Logs are saved to:"
    echo "     $FB_DIR/output/briefing_run.log"
    echo "     $FB_DIR/output/briefing_error.log"
    echo ""
    echo "   To change the time: edit com.rory.fantasybriefing.plist"
    echo "   (Hour/Minute keys) then re-run this installer."
    echo ""
    echo "   To uninstall: run Uninstall Auto-Run.command"
else
    echo ""
    echo "⚠   launchctl load returned an error."
    echo "    Try running this script from Terminal instead of Finder."
fi

read -p "Press Enter to close..."
