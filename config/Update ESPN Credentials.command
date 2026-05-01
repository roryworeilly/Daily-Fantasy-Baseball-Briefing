#!/bin/bash
# Opens the ESPN credentials file in TextEdit so you can update SWID / ESPN_S2.
# Run this whenever you get a 401 error or the briefing shows no data.
#
# How to get fresh values:
#   1. Go to fantasy.espn.com (make sure you're logged in)
#   2. Open DevTools: Cmd+Option+I → Application tab → Cookies → fantasy.espn.com
#   3. Copy SWID (includes the curly braces  { } )
#   4. Copy espn_s2 (long encoded string)
#   5. Paste both into this file and save

DIR="$(cd "$(dirname "$0")" && pwd)"
open -a TextEdit "$DIR/.env"
