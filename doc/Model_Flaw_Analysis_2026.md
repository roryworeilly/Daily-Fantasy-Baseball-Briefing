# Fantasy Baseball Model — Flaw Analysis & Optimization Roadmap
*Generated: April 7, 2026 — Based on full model audit + live 2026 early season data*

---

## Executive Summary

After a full audit of `model.py`, `settings.py`, and cross-referencing against real April 2026 early-season data, **18 distinct model flaws** were identified spanning four severity tiers. The most critical flaw is that the model is running almost entirely on 2025 data while players like Jordan Walker (19% barrel rate, .420 xwOBA) and Garrett Mitchell (98.4 mph EV, 15.4% barrel) are posting dramatically different 2026 profiles that the model is blind to. The second most critical: the model identifies regression risks (e.g. BABIP outliers like Joey Wiemer at .727) but never actually corrects projected points downward — it just flags and hopes.

---

## TIER 1 — CRITICAL FLAWS (Direct scoring impact, fix immediately)

---

### FLAW 1: The Model Is Running Entirely on 2025 Data One Week Into 2026

**Where:** `load_reference_db()` — hardcoded `season = YEAR - 1` (2025). `load_statcast_db()` — built from 2025 Baseball Savant. `load_projection_db()` — preseason Steamer/ZiPS from March 2026.

**The problem:** We are now 1+ full weeks into the 2026 season. Real performance is available and dramatically diverges from preseason projections for several key players:

| Player | 2025 Profile (what model sees) | 2026 Reality (what model misses) |
|--------|-------------------------------|----------------------------------|
| Jordan Walker | Disappointment, low EV | 97.1 mph EV, 19% barrel, .420 xwOBA, improved chase rate |
| Garrett Mitchell | Injury-shortened, discounted | 98.4 mph EV, 15.4% barrel, .444 wOBA, leading MLB in exit velocity |
| Parker Messick | Limited track record | 1.53 FIP, 0.00 ERA, emerging profile |
| Joey Wiemer | Moderate hitter | .727 BABIP hot start — regression incoming |
| Andy Pages | Unproven | .500 BABIP, .549 OBP — all smoke, xwOBP only .345 |

**Fix:** Build a live 2026 data layer. Once a hitter reaches 30 PA or a pitcher reaches 10 IP in 2026, begin blending current-season stats. A reasonable blend formula early in the season:
- Weeks 1-2: 15% current season + 85% preseason projection
- Weeks 3-4: 30% + 70%
- Month 2+: 50% + 50%
- All-Star break+: 70% + 30%

This prevents early-sample noise while incorporating genuine breakouts and busts faster.

---

### FLAW 2: BABIP & xwOBA Signals Are Flagged But Never Act on Projected Points

**Where:** `get_statcast_metrics()` returns signal data. `_velocity_alert()` renders a visual alert. But `get_projected_pts()` never reads the signal field and never adjusts the output.

**The problem:** The model correctly identifies Joey Wiemer as a regression risk (.727 BABIP) and Andy Pages as inflated (.500 BABIP). It puts a red badge on their card. But when deciding whether to start, trade, or add these players, the model's actual projected points number is unchanged — it still uses ESPN's inflated projection that reflects the hot start. The alert is cosmetic. It has zero effect on rankings, waiver recommendations, or trade analysis.

**Impact quantified:** If ESPN inflates Wiemer from 350 projected pts (preseason) to 420 pts based on his hot start, the model ranks him 70 pts higher than warranted. The regression alert says "sell" but every ranking says "start him." These two signals contradict each other with rankings winning in practice.

**Fix:** Apply a BABIP regression multiplier directly inside `get_projected_pts()`:
- BABIP > .360 (no elite sprint speed): apply 0.88× multiplier to projected hitting stats
- BABIP > .400: apply 0.78× multiplier
- xwOBA gap > .050 negative (overperforming): apply 0.90× to projected pts
- xwOBA gap > .050 positive (underperforming): apply 1.08× to projected pts (buy-low bonus)

Salvador Perez is currently the biggest xwOBA underperformer in MLB — leading in xwOBA underperformance with an xBA of .331 but suppressed ISO. The model should be surfacing him as the single best buy-low in the league right now.

---

### FLAW 3: No Park Factor Adjustments in Matchup Grading

**Where:** `grade_pitcher_matchup()` — grades opposing pitcher quality 1-5. `_hitter_matchups_section()` — renders matchup cards.

**The problem:** The matchup grading grades the pitcher's quality (FIP, xFIP, SwStr%) but completely ignores where the game is being played. This creates massive errors:

- **Coors Field** (Colorado): historically +15-20% run environment. A Grade 3 matchup at Coors is actually a Grade 4-5 for hitters.
- **Globe Life Field** (Texas): emerged as one of baseball's toughest parks for hitters in 2025-2026.
- **Kauffman Stadium**: moved walls in for 2026 — now a significantly better HR environment.
- **Dodger Stadium**: became one of the best HR parks in baseball.
- **Camden Yards** (Baltimore): consistently top-5 hitter-friendly, tied for 2nd in HR park factor.

A Grade 4 pitcher matchup at Coors (great matchup + great park) is fundamentally different from a Grade 4 at Globe Life (great matchup + suppressed environment). The model treats them identically.

**Fix:** Add a park factor multiplier to the matchup score. FanGraphs publishes park factor tables (already in the pybaseball ecosystem). A simple park factor of 1.0 = neutral, >1.0 = hitter-friendly, <1.0 = pitcher-friendly. Multiply the matchup attractiveness score by this factor.

---

### FLAW 4: Projection Hierarchy Is Fully Waterfall — No Weighted Blending

**Where:** `get_projected_pts()` — priority order: ESPN live > Steamer/ZiPS > prior season > avg×26.

**The problem:** If ESPN has any projection (>5 pts), it wins outright. ESPN's in-season projections are reactive — they update heavily based on recent 1-2 week samples. In Week 2 of April, ESPN's projection for Garrett Mitchell incorporates his 6-RBI game and leads to a major spike. For a player who was previously a non-factor (Parker Messick), ESPN may have zero projection, so the model falls all the way to prior-season FanGraphs which also has minimal data on him.

Additionally, there is zero communication between the projection system and the Statcast signal system. A player with a `BREAKOUT_CANDIDATE` signal should have his projection adjusted upward. Currently these two systems never talk to each other.

**Fix:** Build a composite projection that weighs all three sources:
```
composite_pts = (
    espn_weight   * espn_proj   +
    steamer_weight * steamer_pts +
    statcast_adj   * statcast_signal_factor
) / total_weight
```
Where `statcast_adj` is derived from the xwOBA gap — breakout candidates get +5-8% on projections, regression risks get -8-12%.

---

## TIER 2 — SIGNIFICANT FLAWS (Material impact, fix this week)

---

### FLAW 5: 2025 Statcast Signals Applied to Players Who Have Already Broken Out or Busted

**Where:** `build_statcast_cache.py` + `STATCAST_DB`

**The problem:** The Phase 2 Statcast cache classifies BREAKOUT_CANDIDATE / REGRESSION_RISK based on 2025 xwOBA vs wOBA gaps. But it's now April 2026. Jordan Walker was almost certainly a BREAKOUT_CANDIDATE in 2025 (his tools were evident even in his underperforming seasons). Now he IS breaking out — so the signal is stale. The model may still show him as "Breakout Candidate 🟢" based on 2025 data, when the proper 2026 signal is simply "this guy is for real — hold."

Similarly, a player who was flagged as REGRESSION_RISK in 2025 may have already regressed fully. The 2025 signal is now noise.

**Fix:** The Statcast cache needs to pull 2026 data once minimum sample thresholds are met. Until then, add a "SIGNAL STALE — 2025 DATA" disclaimer on all Statcast badges when the current date is April+.

---

### FLAW 6: Two-Start Season Value Is Never Surfaced — Only Weekly

**Where:** `get_two_start_multiplier()` — applies 0.30 / 1.0 / 1.75 weekly. No season-level equivalent.

**The problem:** The 1.75× two-start multiplier is the single highest-leverage daily edge in this model. It's correctly applied for the current week. But the model never answers the crucial season-long question: "Which SPs project for the most two-start weeks this season?"

A SP with 8 two-start weeks is worth dramatically more season-long than a SP with only 4 two-start weeks — even if they have identical per-start ERA and FIP. This is invisible in the current model when making trade or waiver decisions.

For Week 2 (April 6-12, 2026), confirmed two-starters include Tarik Skubal, Max Scherzer (Blue Jays, vs LAD + vs MIN), Andrew Painter (PHI, @SFG + vs ARI), and Michael Wacha (KC, vs CLE + vs CWS). The model correctly weights them for this week. But it has no record of "Painter has already had 2 two-start weeks in the first 12 days — he's in a great spot in the rotation."

**Fix:** Build a season two-start week tracker. At each run, record how many two-start weeks each SP has had YTD and project forward based on remaining schedule. Surface this in the player card and in trade analysis.

---

### FLAW 7: Closer/Bullpen Role Data Is Static and Already Stale

**Where:** `bullpen_hierarchy.md` + `is_reliever_role()` + scarcity model.

**The problem:** The bullpen hierarchy was built at a fixed point. Real 2026 closer situations have already evolved:
- **ARI**: Listed as "Sewald/Ginkel co-closers" — but Paul Sewald is clearly the closer now per current waiver wire analysis. If a manager in the league owns Ginkel expecting close competition, the model's mixed signal hurts real-time decision making.
- **HOU**: Josh Hader on IL → Bryan Abreu closing. The model knows this (noted in CLAUDE.md) but it's not dynamically tracked.
- The waiver wire data shows Gregory Soto generating early add activity — suggesting a new or changed closer role somewhere.

The `is_reliever_role()` function uses prior-season GS data. A player who converted from starter to closer this offseason (or vice versa) is misclassified.

**Fix:** Cross-reference ESPN's recent activity feed (already captured in `get_recent_activity()`) against the closer list. A closer who gets dropped in multiple leagues in the same week has likely lost the role. Surface this as an alert.

---

### FLAW 8: No Confirmed Lineup Awareness — Matchup Intelligence Is Unreliable

**Where:** `build_hitter_matchups_today()` — identifies active hitters vs. today's probable starters.

**The problem:** The matchup tab correctly identifies a hitter has a Grade 5 (great) matchup today. But it has no way of knowing whether that hitter is actually confirmed in the lineup. A player can be rested against a tough lefty, given a day off after a doubleheader, or scratched due to a minor injury — none of this is reflected.

In today's game (April 7, 2026), managers who wake up and see a Grade 5 matchup highlighted for a player who is actually sitting will make a wrong decision if they're checking the briefing before lineups post (~3-4 hours before first pitch).

**Fix:** Integrate confirmed lineup data from the MLB Stats API's `/schedule` endpoint, which includes lineup data once posted. Add a "LINEUP PENDING" vs "LINEUP CONFIRMED" status to each matchup card. If the lineup is confirmed and the player is in it, show a ✅. If lineups aren't posted yet, show a ⏳. If the player is confirmed OUT, flag it immediately.

---

### FLAW 9: GWRBI Estimation Is Uniformly Wrong

**Where:** `_hitter_pts_from_stats()` — `BATTING_SCORING["GWRBI"] * (rbi * 0.02)`

**The problem:** The model estimates game-winning RBI as 2% of total RBI uniformly across all hitters. But GWRBI rate is heavily dependent on batting order position and lineup context:
- A cleanup hitter (4th/5th in the order) generates 3-4× more GWRBI opportunities than a 7th-9th hitter, because they bat with runners on in close games more often.
- The model gives Freddie Freeman and a #8 hitter the same GWRBI rate per RBI.

Similarly, `BATTING_SCORING["GSHR"] * (pa * 0.003)` estimates grand slams at 0.3% of PA regardless of whether the player bats in the middle of a lineup that puts runners on base constantly or bats at the bottom of an anemic lineup.

**Fix:** Add batting order position as a modifier. If lineup order data is unavailable, use a crude positional proxy: C/1B/3B typically bat 4-6 (higher GWRBI), SS/2B tend to bat 1-2 or 7-9 (lower GWRBI). This would modestly improve projection accuracy for cleanup vs. leadoff hitters.

---

## TIER 3 — MODERATE FLAWS (Meaningful improvements, address this month)

---

### FLAW 10: Catcher Scarcity Is Massively Undervalued by the Uniform Scarcity Formula

**Where:** `get_scarcity_multiplier()` — `1.0 + (1.0 / math.sqrt(depth + 1))`

**The problem:** The scarcity formula applies the same math to every position. But catcher is uniquely scarce: only 1 roster slot for 14 teams, the talent pool drops off a cliff after the top 8-10 catchers, and many C-eligible players have declining tools by their mid-30s. Every fantasy analyst knows "find a catcher early" but the model doesn't price this appropriately because the sqrt formula treats a shallow catcher pool the same way it treats a shallow 3B pool.

In a 14-team league, the replacement-level catcher is genuinely terrible. The gap between a top-5 C and a replacement C is enormous relative to other positions. The current formula underprices this gap.

**Fix:** Add position-specific scarcity multiplier floors. Catchers and SS get a minimum scarcity multiplier of 1.25 regardless of pool depth calculation, reflecting the structural scarcity that exists independent of the current pool.

---

### FLAW 11: IL Injury Factor Doesn't Distinguish Severity

**Where:** `calculate_base_score_raw()` — `injury_factor = 0.80` for IL slot, `0.60` for day-to-day.

**The problem:** An elite player on the 10-day IL with a hamstring strain (back in 2 weeks) and a player with Tommy John surgery (out 12-18 months) both receive the exact same 0.80 injury factor. This means the model drastically overvalues TJS patients and barely discounts short-term IL stints for stars.

**Fix:** Incorporate injury type if available from ESPN's injury description field. If the word "surgery," "Tommy John," "UCL," or "labrum" appears in the injury note, apply a 0.15 factor (effectively treating them as out for the season). Knee surgeries: 0.35. Standard strains/sprains on 10-day IL: 0.82. This requires parsing the ESPN injury string, which is available but currently ignored.

---

### FLAW 12: LOB% and HR/FB% Regression Signals Don't Adjust Pitcher Projected Points

**Where:** `get_reference_metrics()` returns these values. `_pitcher_pts_from_stats()` never reads them.

**The problem:** The model tracks LOB% (strand rate, mean-reverts to ~72%) and HR/FB% (mean-reverts to ~10%) as regression signals visually, but like the BABIP issue for hitters, these signals never feed into actual pitcher projected points.

A pitcher with an 82% LOB% (extreme — regression incoming, ERA will rise) and a 7% HR/FB% (below normal, HRs will increase) should have their projected ERA adjusted upward, which cascades to lower projected points. Currently they don't.

**Fix:** Apply ERA adjustment factors based on LOB%/HR/FB% deviation from mean:
- LOB% > 78%: multiply projected ERA by 1.10 (10% ERA increase incoming)
- LOB% < 66%: multiply projected ERA by 0.92 (improvement pending)
- HR/FB% < 8%: multiply projected ERA by 1.08 (HR rate will normalize upward)
- HR/FB% > 15%: multiply projected ERA by 0.94 (HR rate will normalize downward)

---

### FLAW 13: GS-Based Role Classification Uses Prior Season — Creates Converter Blindspot

**Where:** `is_starter_role()` / `is_reliever_role()` — reads GS from `REFERENCE_DB` (2025 data).

**The problem:** A reliever converting to a starter in 2026 (e.g., a top bullpen arm given a rotation spot) will be classified as a reliever all season based on their 2025 GS count. Their replacement level, scarcity multiplier, and two-start multiplier eligibility will all be wrong. Conversely, an injured starter demoted to the bullpen mid-2025 will be classified as a starter in 2026, inflating their value.

This affects every aspect of their valuation: replacement level pool, scarcity calculation, and the two-start multiplier logic.

**Fix:** Override prior-season GS classification with 2026 lineup slot data from ESPN. If ESPN has already slotted a player as "SP" or "RP" in their league, that real-time classification should take precedence over the prior-season proxy.

---

### FLAW 14: Free Agent Scan Capped at 350 — Misses Breakouts on Thin Rosters

**Where:** `build_market_context()` and waiver intelligence — `league.free_agents(size=350)`.

**The problem:** In a 14-team league where each team carries ~30 players (active roster + IL + bench), that's ~420 rostered players. With 350 additional free agents scanned, the model sees roughly 770 total players. But active MLB rosters plus the full 40-man carry ~1,400 players. Early-season callups, players who were just DFA'd, and streaming options showing up in September callups are invisible to the model.

Specifically, Parker Messick — one of the top waiver adds of Week 2, with a 1.53 FIP — may not appear in a 350-player FA scan depending on how ESPN sorts free agent lists. The model might entirely miss recommending him.

**Fix:** Increase the FA scan to 500 in-season, and specifically add a targeted search for players with >0 ESPN ownership percentage who are not on any team roster.

---

## TIER 4 — DATA CURRENCY ISSUES (Fix the pipeline)

---

### FLAW 15: Statcast Cache 7-Day TTL Refreshes Timestamps But Not the Data Source Season

The TTL correctly prevents fetching the same 2025 data repeatedly, but `build_statcast_cache.py` hardcodes the prior season as its data source. After running the build tool, you'll have fresh 2025 data — just timestamped today. The TTL is working correctly but on the wrong season. Once Baseball Savant has sufficient 2026 sample size (~April 20-25), the cache builder needs to switch to the 2026 leaderboard endpoints.

---

### FLAW 16: Projection Cache Built in March Is Now Losing Accuracy Quickly

The Steamer/ZiPS preseason projections were excellent in March. By April 7, after one full week of games, some projections are already significantly wrong. Cam Smith (2 HR, 3 SB in week 1 at a pace nobody projected) will have an ESPN-boosted projection but a stale Steamer projection. The 7-day cache TTL re-fetches Steamer/ZiPS data but those systems update their projections in-season — fetching fresh Steamer data now will get their updated in-season rest-of-season projections, which is better than the March preseason numbers.

**Fix:** Reduce projection cache TTL from 7 days to 3 days during April, when projections are updating rapidly. After June 1, can relax back to 7 days.

---

### FLAW 17: Reference DB Season Is Fixed at YEAR-1 With No In-Season Blend Path

As discussed in Flaw 1, the reference DB always uses `YEAR - 1`. There is currently no code path to incorporate any 2026 data. The entire analytics pipeline — wRC+, wOBA, ISO, FIP, SIERA, K-BB% — is 2025 vintage for every player. This makes the model fundamentally backward-looking with no mechanism to update during the season it's actually being used in.

---

### FLAW 18: Batting Order Position Is Completely Absent From the Model

This is the one dimension that affects nearly every hitter metric yet is entirely missing:

- **R/RBI context**: Leadoff hitters generate more runs, fewer RBI. Cleanup hitters generate the opposite.
- **GWRBI**: Almost exclusively a 3rd-5th hitter stat.
- **BB opportunities**: Patient leadoff hitters accumulate far more BBs than those batting 7th.
- **K penalty impact**: A 30% K-rate leadoff hitter (600+ PA) is penalized far more than a 30% K-rate #8 hitter (350 PA).

The MLB Stats API's `/schedule` endpoint includes lineup order once lineups are posted. This data is free, already partially integrated (for schedule purposes), and would meaningfully improve projection accuracy.

---

## Real 2026 Players the Model Is Currently Getting Wrong

### Overvalued (Model Too High)
- **Joey Wiemer**: .727 BABIP, career norm is .258. EPA expects ~420 pts, true value is closer to 320. Model should flag and discount by ~20%.
- **Andy Pages**: .500 BABIP, .345 xwOBP vs .549 OBP. Enormous regression incoming. Model is likely riding ESPN's inflated projection.

### Undervalued (Model Too Low)
- **Jordan Walker**: 2025 data shows disappointment. 2026 shows .420 xwOBA, 19% barrel, improved mechanics. Model likely has him below 400 pts projected. He should be above 450.
- **Garrett Mitchell**: Leading MLB in exit velocity (98.4 mph). 2025 injury-shortened profile severely discounts him in the model. True 2026 value is significantly higher.
- **Salvador Perez**: Leading MLB in xwOBA underperformance. His xBA is .331 but his HR/FB rate is suppressed at 4.5%. When the HR/FB normalizes, his counting stats will surge. The model should be surfacing him as the top buy-low hitter in the league.
- **Parker Messick** (CLE): 1.53 FIP, 0.00 ERA, 15 K over 11.7 IP in Week 1-2. Model has minimal 2025 data on him and may not even include him in the FA scan.

### Stale Signals
- **ARI Closer situation**: Model shows committee. Reality: Paul Sewald is the clear closer and a legitimate SV accumulator.

---

## Prioritized Fix Order

| Priority | Flaw | Estimated Impact |
|----------|------|-----------------|
| 1 | Flaw 2: BABIP/xwOBA regression must adjust projected pts | Very High |
| 2 | Flaw 1: Live 2026 data blend layer | Very High |
| 3 | Flaw 3: Park factor adjustments to matchup grades | High |
| 4 | Flaw 4: Weighted projection blend (not waterfall) | High |
| 5 | Flaw 8: Confirmed lineup awareness | High |
| 6 | Flaw 6: Season-level two-start week tracker | High |
| 7 | Flaw 7: Dynamic closer role tracking via ESPN activity | Medium-High |
| 8 | Flaw 5: Statcast signal staleness disclaimer | Medium |
| 9 | Flaw 9: GWRBI estimation by batting order | Medium |
| 10 | Flaw 10: Catcher scarcity floor multiplier | Medium |
| 11 | Flaw 12: LOB%/HR/FB% pitcher ERA adjustment | Medium |
| 12 | Flaw 11: IL severity distinction | Medium |
| 13 | Flaw 14: Expand FA scan to 500 | Low-Medium |
| 14 | Flaws 15-18: Data pipeline currency | Ongoing |

---

*Sources used: [ESPN MLB Stats](https://www.espn.com/mlb/stats) · [MLB.com Stats](https://www.mlb.com/stats) · [FantasyPros 2026](https://www.fantasypros.com/mlb/rankings/overall.php) · [CBS Sports Waiver Wire](https://www.cbssports.com/fantasy/baseball/news/fantasy-baseball-waiver-wire-jordan-walker-cam-smith-finally-delivering-on-their-promise/) · [Yahoo Sports Regression Candidates](https://sports.yahoo.com/fantasy/article/2026-fantasy-baseball-positive-and-negative-regression-candidates-141844888.html) · [ESPN Week 2 Forecaster](https://www.espn.com/fantasy/baseball/story/_/id/48370338/fantasy-baseball-forecaster-espn-2026-mlb-starting-pitcher-hitter-ranks-week-2-april-6-12) · [Yahoo Park Factors](https://sports.yahoo.com/fantasy/article/2026-fantasy-baseball-park-factors-ranking-the-best-and-worst-mlb-stadiums-for-hitting-141855255.html)*
