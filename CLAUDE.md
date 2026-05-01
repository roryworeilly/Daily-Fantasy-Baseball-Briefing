# Fantasy Baseball Daily Briefing — Claude Session File

## ⚠️ READ THIS FIRST — EVERY SESSION

Before writing a single line of code or making any change, read the context document:

```
/Users/roryoreilly/Desktop/FB/CONTEXT.md
```

It contains: full repo layout, all public APIs, build_payload return keys, stream_plan dict shape, tab structure with pane IDs, JS switcher functions, settings variables, test setup rules, known gotchas, and a changelog of recent changes. Reading it takes 2 minutes and prevents 30 minutes of codebase archaeology.

---

## Project in One Line

Python app that generates a self-contained HTML morning briefing for a 14-team ESPN H2H points fantasy baseball league. Rory's team = "The Undisputed".

---

## Current Codebase State (as of 2026-05-01)

- **10 tabs → 4 tabs**: Today / My Team / Tools / ⋯ More (restructured May 2026)
- **Weekly Pitcher Streaming Plan** feature live in model.py + html.py
- **80 tests passing**, all offline (no ESPN credentials needed)
- Repo is clean and ready for GitHub push
- One-click launcher: `Run.command` in repo root

Full architecture detail → **CONTEXT.md**

---

## Domain Knowledge — Scoring Insights

These are strategic facts about Rory's specific scoring system that inform every recommendation. Keep them in mind when reasoning about player value.

### Scoring system (H2H points)
```
BATTING:  R+1  HR+1  TB+1  RBI+1  BB+1  SB+1  K-1   E-1   GWRBI+2  GSHR+4  CYC+15
PITCHING: IP+3 H-1  ER-2  HR-1  BB-1  K+1  QS+2  CG+5  SO+9  NH+10  PG+35
          W+2  L-2  SV+6  BS-3  HD+5  SVHD+2
```

### Key strategic insights

**1. Holds are massively undervalued.** HD+5 + SVHD+2 = 7 pts/hold. A 30-hold setup man projects ~456 pts vs an elite closer at ~490 pts — only a 34-point gap. Strategy: 1 elite closer + 2 high-hold setup men beats 2 closers.

**2. K-rate is the biggest hidden hitter drag.** A 30% K-rate in 600 PA = 180 Ks = -180 pts. A 15% K-rate costs only -90 pts — a 90-pt difference equal to ~15 HR or ~30 SB. K% is the biggest market inefficiency ESPN rankings don't price.

**3. Two-start multiplier = highest in-season edge.** A 2-start SP is worth ~1.75× a 1-start SP that week. Already implemented in `get_weekly_projected_pts()`.

**4. Breakeven ERA threshold.** At 6 IP/start: any SP with ERA < 6.15 is net-positive. Short starts (4 IP) require ERA < 3.94. High-floor SPs are worth more than raw season totals suggest.

**5. Contact hitters > pure sluggers.** TB+1 partially helps power, but K-1 punishes strikeout-heavy hitters hard. A .290/.15HR/12%K often outscores a .240/.35HR/30%K hitter.

**6. IP+3 is huge.** 200-inning workhorse SPs gain +600 pts from IP alone. Don't undervalue durability.

---

## Metric Quick Reference

### Hitters
| Metric | Elite | Above Avg | Average | Concern |
|---|---|---|---|---|
| wRC+ | >140 | 115–140 | 100–115 | <85 |
| Exit Velo | >91 mph | 89–91 | 87–89 | <87 |
| Barrel% | >10% | 6–10% | 4–6% | <4% |
| K% | <15% | 15–20% | 20–25% | >28% |
| xwOBA | >.370 | .340–.370 | .310–.340 | <.310 |

### Pitchers
| Metric | Elite | Above Avg | Average | Concern |
|---|---|---|---|---|
| SIERA | <3.30 | 3.30–3.80 | 3.80–4.30 | >4.50 |
| SwStr% | >13% | 10–13% | 9–10% | <9% |
| K-BB% | >20% | 15–20% | 10–15% | <10% |
| xERA gap | xERA > ERA = sell/regression | | | xERA < ERA = buy/breakout |

### Statcast regression signals
- `xwOBA − wOBA > .030` → Breakout Candidate 🟢
- `wOBA − xwOBA > .030` → Regression Risk 🔴
- `xERA − ERA > 1.00` → SP Sell-High 🔴 *(positive gap = regression risk)*
- `ERA − xERA > 1.00` → SP Buy-Low 🟢

---

## Critical Rules (mistakes to never repeat)

1. **New settings variable added?** → Also add it to `test/conftest.py` `_settings` stub or all 80 tests fail with ImportError.
2. **f-strings with dict keys** (`f"{d['key']}"`) → SyntaxError pre-Python 3.12. Extract to a local var first.
3. **xERA gap direction**: positive gap (xERA > ERA) = pitcher is getting lucky = sell. Negative = buy. Not the other way around.
4. **Tie scoring**: wins += 0.5 only. Losses are NOT incremented on a tie (ESPN convention). `test_simulate.py::test_tie_gives_half_win_no_loss` is the regression guard.
5. **Always use `esc(v)`** when embedding user-facing strings in HTML.
6. **CSS colors**: never hardcode hex — always use CSS variables (`var(--accent)`, `var(--red)`, etc.).

---

*For full architecture, APIs, and tab/UI details → read CONTEXT.md*
