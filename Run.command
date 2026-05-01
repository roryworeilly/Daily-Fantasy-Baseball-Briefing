#!/bin/bash
# ══════════════════════════════════════════════════════════════
#  Fantasy Baseball Daily Briefing — One-Click Launcher
#
#  Double-click this file in Finder to generate your briefing.
#  First time only: right-click → Open to approve in Gatekeeper.
# ══════════════════════════════════════════════════════════════

# Always run from the folder this script lives in
cd "$(dirname "$0")"

PYTHON=".venv/bin/python"
SCRIPT="run_briefing.py"

# ── Pretty header ──────────────────────────────────────────────
clear
echo ""
echo "  ⚾  Fantasy Baseball Daily Briefing"
echo "  $(date '+%A, %B %-d %Y — %-I:%M %p')"
echo "  ─────────────────────────────────────"
echo ""

# ── Pre-flight: virtual environment ────────────────────────────
if [ ! -f "$PYTHON" ]; then
    echo "  ✗  Virtual environment not found (.venv/)"
    echo ""
    echo "  Set it up once with:"
    echo "    python3 -m venv .venv"
    echo "    .venv/bin/pip install -r dep/requirements.txt"
    echo ""
    read -p "  Press Enter to close..."
    exit 1
fi

# ── Pre-flight: .env credentials ───────────────────────────────
if [ ! -f ".env" ]; then
    echo "  ✗  Missing .env file (ESPN credentials)"
    echo ""
    echo "  Copy the template and fill in your credentials:"
    echo "    cp .env.example .env"
    echo ""
    read -p "  Press Enter to close..."
    exit 1
fi

# ── Run ────────────────────────────────────────────────────────
echo "  Running briefing..."
echo ""
"$PYTHON" "$SCRIPT"
EXIT=$?
echo ""

if [ $EXIT -eq 0 ]; then
    echo "  ✓  Done! Briefing written to output/"
else
    echo "  ✗  Exited with error code $EXIT"
    echo "  Check the output above for details."
    read -p "  Press Enter to close..."
fi
