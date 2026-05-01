#!/bin/bash
# ─────────────────────────────────────────────────────────────
#  Fantasy Baseball Daily Briefing — Double-click launcher
#  Place this file in your FB folder. Right-click → Open the
#  first time to approve it (macOS Gatekeeper), then it will
#  double-click normally from then on.
# ─────────────────────────────────────────────────────────────

# Move to the folder this script lives in, regardless of where
# Finder launched it from.
cd "$(dirname "$0")"

VENV="$PWD/.venv/bin/python"

if [ ! -f "$VENV" ]; then
    echo "ERROR: Virtual environment not found at .venv/"
    echo "Expected: $VENV"
    echo ""
    echo "Set up the venv first:"
    echo "  python3 -m venv .venv"
    echo "  .venv/bin/pip install espn-api pybaseball requests-cache"
    read -p "Press Enter to close..."
    exit 1
fi

echo "=========================================="
echo "  Fantasy Baseball Daily Briefing"
echo "  $(date '+%A, %B %-d %Y — %-I:%M %p')"
echo "=========================================="
echo ""

"$VENV" run_briefing.py

EXIT_CODE=$?
if [ $EXIT_CODE -ne 0 ]; then
    echo ""
    echo "Script exited with error code $EXIT_CODE"
    read -p "Press Enter to close..."
fi
