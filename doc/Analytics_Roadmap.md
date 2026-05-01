# Fantasy Baseball Analytics Roadmap
### Advanced Metrics Research & Implementation Plan
*Generated: March 25, 2026*

---

## Executive Summary

The current model is a solid foundation — it pulls ESPN fantasy data, cross-references FanGraphs/Baseball Reference prior-season stats, calculates replacement levels, and applies positional scarcity multipliers. However, it operates almost entirely on **traditional counting stats and rate stats** (HR, RBI, SB, ERA, WHIP, etc.). Modern baseball analytics has moved well beyond these, and integrating the right advanced metrics can dramatically improve player valuation accuracy — catching breakout candidates earlier, flagging regression risks, and finding undervalued players the market is mispricing.

This document maps out every meaningful metric tier, what it measures, why it matters, where to get the data, and a phased implementation plan.

---

## Current Model: What We Have

### Hitter Metrics Tracked
`PA, H, 2B, 3B, HR, R, RBI, SB, BB, SO, TB, OPS, WAR`

### Pitcher Metrics Tracked
`IP, H, ER, HR, BB, SO, W, L, SV, HD, BS, QS, GS, ERA, WHIP, WAR`

### System Features
- ESPN fantasy league API integration (live roster, matchup, free agents)
- FanGraphs prior-season data via pybaseball (primary source)
- Baseball Reference as fallback
- Positional replacement level calculation with role-split SP/RP pools
- Positional scarcity multipliers using pool depth
- Two-start multiplier for starting pitchers
- Market context (waiver wire pool depth)

### Key Gaps Identified
The model currently has **zero** Statcast data, **zero** expected stats, **zero** platoon splits, **zero** pitch-level metrics, and **zero** projection system integration. These are the highest-leverage additions.

---

## Tier 1 — Statcast Core Metrics (HIGHEST PRIORITY)

These metrics come directly from MLB's radar/camera tracking system and are available via Baseball Savant. They measure *quality of contact* and *true skill*, not results — which makes them the best leading indicators of future performance.

### For Hitters

**Exit Velocity (EV) & Average Exit Velocity**
What it is: Speed of the ball off the bat in mph immediately after contact. Higher EV strongly correlates with positive outcomes. The league average is typically around 88–89 mph.
Why it matters: A hitter posting a low batting average but elite exit velocity is likely to regress upward. A hitter posting a high average with weak contact is a regression candidate.
Fantasy signal: EV above 91 mph = elite contact quality.

**Barrel Rate (Brls%)**
What it is: A "barrel" requires ≥98 mph exit velocity at a launch angle of 26–30°. As EV increases past 98 mph, the acceptable launch angle range widens. Barrels produce essentially a 1.000 batting average and 2.000+ slugging.
Why it matters: Barrel rate is the single best predictor of HR and extra-base hit production. It outperforms HR from prior seasons as a future HR predictor.
Fantasy signal: 10%+ barrel rate = elite power; 6–10% = above average; <4% = limited power ceiling.

**Hard Hit Rate (HardHit%)**
What it is: Percentage of batted balls hit at ≥95 mph exit velocity. Slightly broader than barrel rate — catches hard contact that isn't perfectly launched.
Why it matters: Complements barrel rate. A player with elite hard hit rate but lower barrel rate may have a launch angle issue, not a bat speed issue — a more fixable problem.
Fantasy signal: 45%+ = elite; 38–45% = above average; <35% = concern.

**EV50 (Best Speed / 90th Percentile EV)**
What it is: A player's average exit velocity on their hardest 50% of contact events. More stable than max EV and better than average EV for measuring true bat-to-ball power.
Why it matters: Recent research suggests EV50 is more predictive than HardHit% for isolating a player's true ability to hit the ball hard. It filters out weak grounders.
Fantasy signal: Use in conjunction with barrel rate to build a complete contact quality profile.

**Launch Angle (LA) & Launch Angle Swing (LA Sweet Spot%)**
What it is: Vertical angle of the ball off the bat. Sweet Spot% measures the percentage of batted balls in the optimal 8–32° range.
Why it matters: A hitter improving launch angle toward the sweet spot range while maintaining exit velocity is a breakout candidate. A hitter with declining launch angle is a concern.
Fantasy signal: Sweet Spot% above 35% is above average; pairing with barrel rate tells the full power story.

**Sprint Speed**
What it is: A player's maximum running speed in feet per second, measured on competitive runs (not all runs). MLB average is approximately 27 ft/s.
Why it matters: Directly tied to stolen base ability, leg infield hits, and extra bases taken. A player's sprint speed is also used in xwOBA calculations for certain batted balls.
Fantasy signal: 28+ ft/s = elite speed; 27–28 = above average; <26 = limited base-stealing profile. Track sprint speed year over year — decline signals aging.

**xBA (Expected Batting Average)**
What it is: Expected batting average based purely on exit velocity and launch angle of each batted ball, compared to historical outcomes from similar batted balls since 2015.
Why it matters: A large gap between BA and xBA in either direction signals regression. Hitters outperforming xBA by more than 20 points are likely to decline; those underperforming are likely to rise.
Fantasy signal: xBA−BA gap of >+0.030 = overperformer (regression risk); <−0.030 = underperformer (breakout candidate).

**xSLG (Expected Slugging Percentage)**
What it is: Expected slugging based on exit velocity and launch angle. Analogous to xBA but for power.
Why it matters: Identifies hitters whose SLG is being distorted by park factors, defense, or luck on balls in play.

**xwOBA (Expected Weighted On-Base Average)**
What it is: The most comprehensive expected hitting metric. Incorporates EV, launch angle, and sprint speed. Assigns each batted ball a probability of single/double/triple/HR based on comparable historical balls in play.
Why it matters: xwOBA is the best single-number summary of a hitter's underlying skill. The gap between actual wOBA and xwOBA isolates luck from skill.
Fantasy signal: Players with xwOBA significantly above wOBA are undervalued; those with xwOBA below wOBA are overvalued.

---

### For Pitchers

**xERA (Expected ERA)**
What it is: Pitcher's xwOBA allowed converted to an ERA scale. Accounts for the quality of contact allowed, not just outcomes.
Why it matters: ERA is heavily influenced by defense, park, and sequencing luck. xERA strips those out and shows what the pitcher "earned" based on contact quality. A large ERA−xERA gap signals either regression or continuation risk.
Fantasy signal: Gap of >1.00 ERA points above xERA = pitcher is due for ERA improvement; >1.00 below = regression risk.

**Whiff Rate / SwStr% (Swinging Strike Rate)**
What it is: Swings and misses divided by total pitches. The most direct measure of swing-and-miss stuff.
Why it matters: SwStr% has the highest correlation with future K rate of any pitching metric. It's also predictive of ERA and FIP because strikeouts eliminate balls in play entirely.
Fantasy signal: SwStr% >13% = elite strikeout potential; 10–13% = above average; <9% = limited K upside.

**CSW% (Called Strikes + Whiffs)**
What it is: (Called strikes + swinging strikes) / total pitches. Expands SwStr% to include pitches that freeze batters.
Why it matters: A pitcher can generate value both by inducing swings and misses AND by painting the corner for called strikes. CSW% captures both and is one of the best overall pitch effectiveness metrics.
Fantasy signal: CSW% >30% = elite; 27–30% = above average; <25% = concern.

**GB% (Ground Ball Rate)**
What it is: Ground balls allowed as a percentage of all balls in play.
Why it matters: Ground balls rarely become home runs. Elite GB pitchers maintain lower HR/9 even in hitter-friendly parks. However, GB pitchers are more reliant on defense and infield positioning, so they can be streaky on BABIP.
Fantasy signal: GB% >50% = strong ground ball profile (HR resistant); <40% = fly ball pitcher (HR vulnerable, better K upside).

---

## Tier 2 — FanGraphs Advanced Rate Stats (HIGH PRIORITY)

These are available via pybaseball's `batting_stats()` and `pitching_stats()` functions — they're already within the existing data pipeline and just need to be extracted and stored.

### For Hitters

**wRC+ (Weighted Runs Created Plus)**
What it is: Runs created per plate appearance, adjusted for park and league. Scaled so 100 = league average. A wRC+ of 130 means the hitter is 30% better than league average at creating runs.
Why it matters: The single best context-neutral offensive rate stat. Better than OPS because it adjusts for park and weights outcomes by their actual run value.
Fantasy signal: >140 = MVP-tier; 115–140 = fantasy star; 100–115 = solid starter; <85 = droppable.

**wOBA (Weighted On-Base Average)**
What it is: Combines all offensive events (BB, HBP, singles, doubles, triples, HR) weighted by their actual run value. The unadjusted version of wRC+.
Why it matters: More accurate than OBP or SLG individually. The gap between actual wOBA and xwOBA (from Statcast) is the core regression/breakout signal.
Fantasy signal: >.370 = elite; .340–.370 = above average; .310–.340 = average; <.310 = below average.

**ISO (Isolated Power)**
What it is: SLG − AVG. Measures raw extra-base hit power by stripping out singles.
Why it matters: More stable year-over-year than HR total. A hitter with high ISO but lower HR may be in a bad park or hitting behind weak lineups — true power is still there.
Fantasy signal: >.220 = elite power; .180–.220 = above average; .150–.180 = average; <.120 = light contact hitter.

**BB% (Walk Rate) and K% (Strikeout Rate)**
What it is: Walks and strikeouts as a percentage of plate appearances.
Why it matters: BB% is highly stable year-over-year (skill-based). K% is also relatively stable but can shift with mechanical changes. The combination defines a hitter's plate discipline profile.
Fantasy signal: BB% >10% + K% <20% = elite plate discipline (high floor); BB% <6% + K% >28% = high-risk boom/bust profile.

**BABIP (Batting Average on Balls In Play)**
What it is: BA excluding HRs and strikeouts: (H − HR) / (AB − K − HR + SF).
Why it matters: League average BABIP is approximately .300. Significant deviations are usually partly luck-driven and tend to revert. Fast players and those with strong line-drive rates can sustain slightly above-average BABIP.
Fantasy signal: BABIP >.340 with no speed skills = likely regression; BABIP <.260 with good contact metrics = likely breakout.

**LD% (Line Drive Rate)**
What it is: Line drives as a percentage of balls in play.
Why it matters: Line drives produce the highest BABIP of any batted ball type (~.690). High LD% hitters sustain above-average BABIP legitimately. Strong LD% with poor results = BABIP-unlucky.
Fantasy signal: LD% >24% = elite contact; 20–24% = above average; <18% = pull-heavy or pop-up prone.

---

### For Pitchers

**FIP (Fielding Independent Pitching)**
What it is: An ERA estimator based only on outcomes the pitcher controls: K, BB, HBP, and HR. Formula: (13×HR + 3×(BB+HBP) − 2×K) / IP + constant. Scaled to ERA.
Why it matters: Eliminates the noise of fielding quality and BABIP luck. A pitcher with ERA much higher than FIP is probably being hurt by their defense or bad BABIP luck — a buy-low candidate.
Fantasy signal: FIP−ERA gap of +0.75 or more = strong buy candidate; −0.75 or more = likely regression target.

**xFIP (Expected FIP)**
What it is: FIP but with HR replaced by an expected HR calculated from fly ball rate × league average HR/FB ratio.
Why it matters: Home run rates on fly balls vary year to year even for the same pitcher. xFIP normalizes this, making it even more stable than FIP and a better predictor of next-year ERA than ERA itself.
Fantasy signal: Dramatically different from ERA? The truth is usually between them, weighted toward xFIP.

**SIERA (Skill-Interactive ERA)**
What it is: The most sophisticated ERA estimator. Like FIP but adds adjustments for GB%, FB%, and how those batted ball types interact with K rate. Accounts for the fact that high-K pitchers can sustain lower BABIP.
Why it matters: Outperforms both FIP and xFIP at predicting next-year ERA. A pitcher with elite SIERA despite a bloated ERA is one of the best buy-low targets in fantasy.
Fantasy signal: SIERA <3.30 = elite; 3.30–3.80 = above average; 3.80–4.30 = average; >4.50 = concern.

**K/9, BB/9, K-BB% (K minus BB Rate)**
What it is: Strikeouts and walks per 9 innings, and their combined differential.
Why it matters: K-BB% (K% minus BB%) is considered the best single-metric predictor of ERA among component stats. High K-BB% = low variance, consistent performance. It's more stable than either rate alone.
Fantasy signal: K-BB% >20% = elite (Gerrit Cole/Corbin Burnes tier); 15–20% = above average; <10% = high risk.

**HR/FB% (Home Run per Fly Ball Rate)**
What it is: Home runs allowed as a percentage of fly balls allowed.
Why it matters: Sustainable HR/FB% is approximately 10–12% at the MLB level. Pitchers allowing HR/FB% well above this are due for regression; those below are at risk of rising.
Fantasy signal: HR/FB% >14% = regression candidate (ERA likely to improve); <8% = regression risk (ERA likely to worsen).

**LOB% (Left On Base Rate / Strand Rate)**
What it is: Percentage of baserunners a pitcher strands.
Why it matters: League average is roughly 72–74%. Pitchers significantly above this are likely to regress (ERA will rise); those significantly below have been unlucky (ERA will fall).
Fantasy signal: LOB% >78% = ERA inflation, expect regression downward; LOB% <68% = ERA deflation, expect improvement.

---

## Tier 3 — Pitch-Level & Stuff Metrics (MEDIUM PRIORITY)

These require pitch-by-pitch Statcast data and represent the frontier of pitcher evaluation.

**Stuff+ (from Baseball Savant / third-party models)**
What it is: A model-based rating of a pitcher's raw stuff (velocity, movement, spin) independent of command or outcomes. Scaled to 100 = average. A starter with Stuff+ 120 has stuff 20% better than average.
Why it matters: Stuff+ can identify pitchers whose raw arsenal deserves better results than they're getting — especially useful for identifying breakout candidates mid-season.
Data source: Fangraphs (staff.plus column in pitching leaderboards), or third-party APIs.

**Location+ (Command Score)**
What it is: Complements Stuff+ by measuring how well a pitcher locates their pitches, independent of the quality of stuff. A pitcher with average Stuff+ but elite Location+ can still be highly effective.
Why it matters: Pitchers who succeed primarily on command (rather than stuff) are more fragile — a slight mechanical change can destroy their value. Pitchers with elite Stuff+ and mediocre Location+ have upside if they improve command.

**Pitch Movement Profiles (Horizontal & Vertical Break)**
What it is: How much a pitch moves horizontally and vertically compared to a theoretical "spinless" pitch. Measured in inches.
Why it matters: Pitchers with elite movement on their secondary pitches (especially vertical break on a curveball, horizontal sweep on a slider) generate more swings and misses regardless of velocity.
Data source: Baseball Savant pitch-level data via pybaseball's `statcast()` function.

**Velocity Trends**
What it is: Tracking a pitcher's average fastball velocity game-by-game or week-by-week across a season.
Why it matters: Velocity decline of 1+ mph is an early injury indicator. Velocity gains (often in spring training or after a delivery adjustment) can signal a breakout. This is the #1 daily monitoring metric for SP health.
Implementation: Track via Baseball Savant's game-by-game data or pybaseball pitch data.

---

## Tier 4 — Projection System Integration (MEDIUM PRIORITY)

Projection systems combine historical performance, aging curves, and regression to the mean to forecast future stats. Integrating these replaces our crude "prior season × multiplier" approach.

**Steamer Projections**
What it is: One of the most accurate publicly available projection systems. Available via FanGraphs. Projects PA, HR, RBI, SB, AVG, OBP, SLG for hitters and IP, ERA, WHIP, K, W, SV for pitchers.
Why it matters: Steamer has been consistently one of the top-performing projection systems in accuracy studies. It incorporates aging, regression to the mean, and weighted multi-year averaging.
Data source: Available directly from FanGraphs leaderboard downloads via pybaseball's `batting_stats()` with the `split_seasons=False` parameter, or via direct FanGraphs CSV download.

**ZiPS Projections**
What it is: Dan Szymborski's projection system at FanGraphs. Uses comparable player databases and similarity scores to weight projections. Strong at identifying breakout candidates via aging curve analysis.
Why it matters: ZiPS and Steamer tend to agree on most players — disagreements are worth investigating. ZiPS has a slight edge on identifying outlier performances.

**Consensus Projection (Average of Systems)**
Best practice is to average Steamer + ZiPS projections for each player. Research consistently shows that averaging projection systems outperforms any single system.

**PECOTA Percentile Bands**
What it is: Baseball Prospectus's system provides 10th/50th/90th percentile projections — giving a player's floor, median, and ceiling.
Why it matters: Knowing a player's range of outcomes is more valuable than a point estimate alone. A player with a tight range (low variance) is safer than one with a wide range.
Data source: Baseball Prospectus subscription required for full data.

---

## Tier 5 — Contextual & Situational Metrics (MEDIUM PRIORITY)

**Platoon Splits (vs LHP / vs RHP)**
What it is: A player's wOBA, OPS, or wRC+ split by whether they faced left-handed or right-handed pitchers.
Why it matters: Most hitters are significantly better against opposite-handed pitching. Knowing your hitters' platoon profiles lets you predict performance against that week's pitching matchups.
Implementation: FanGraphs splits data; build a matchup-aware projection overlay in the briefing.

**Ballpark Factors**
What it is: Indexed adjustments for how each MLB stadium affects offense. Coors Field has a park factor of ~115 (15% more offense); Oracle Park ~91 (9% less offense).
Why it matters: A hitter on Colorado plays 81 games in the best hitter's park in baseball. A pitcher moving from Coors to a pitcher's park is a buy-low. Always context-adjust ERA and production.
Data source: FanGraphs park factors are available in pybaseball.

**Schedule Strength (Upcoming Opponent Analysis)**
What it is: Analyzing a player's upcoming week of matchups based on opposing pitcher quality, ballpark, and weather.
Why it matters: In head-to-head weekly leagues, scheduling can swing outcomes by 10–15%. Knowing you have four hitters facing a cellar-dweller rotation gives you a real edge.
Implementation: Cross-reference ESPN schedule data with FanGraphs pitcher quality metrics.

**Lineup Position & Protection**
What it is: Tracking where a hitter bats in the lineup (1-9) and who surrounds them.
Why it matters: Lineup position dramatically affects counting stat accumulation. A hitter moving from 6th to 3rd in a strong lineup gets significantly more R and RBI opportunities. Protection matters too — a star hitter surrounded by weak hitters gets fewer fastballs.

---

## Tier 6 — Defensive & Catching Metrics (LOWER PRIORITY)

Less directly relevant to fantasy (most leagues don't score defense) but useful for WAR-based valuations and injury/role risk assessment.

**OAA (Outs Above Average)**
What it is: A fielding metric from Baseball Savant that measures range, reaction, and route efficiency. Accounts for difficulty of each play.
Why it matters: Helps assess whether a player's defensive value keeps them in the lineup even during offensive slumps. A star defender won't get benched despite a cold streak.
Data source: Baseball Savant leaderboard via their CSV download API.

**Catcher Framing Runs**
What it is: Runs saved by a catcher through pitch framing — convincing umpires to call borderline pitches strikes. Measured on a ~0.125 runs/extra strike basis.
Why it matters: Elite framers stay in the lineup regardless of offense. Poor framers get replaced quickly when they hit poorly.

**Catcher Pop Time**
What it is: Time (in seconds) from pitch hitting the mitt to ball reaching 2B. MLB average ≈ 2.0 seconds.
Why it matters: Elite pop time (under 1.95s) extends a catcher's career and role stability. In daily leagues, pop time affects stolen base suppression for opposing baserunners.

---

## Tier 7 — Aging Curves & Injury Risk (STRATEGIC PRIORITY)

**Aging Curves**
Research (from FanGraphs and Baseball Prospectus) shows:
- Hitters typically peak at age 27 and decline roughly 0.5–1 WAR/year after 30
- Sprint speed begins meaningful decline at 29–30
- Power (ISO) peaks at 26–28, declines sharply after 32
- Contact quality (barrel rate) is more durable, often stable into mid-30s
- Pitchers peak velocity-wise at 24–26; velocity typically declines 0.3 mph/year after 28

Implementation: Flag players over 32 with speed-dependent value; flag 24–27 year olds entering prime years as upside candidates.

**Injury Risk Signals**
Key indicators to monitor daily in the briefing:
- Sprint speed decline year-over-year (soft tissue / lower body indicator)
- Velocity decline for pitchers (arm/shoulder indicator)
- BABIP collapse for hitters (leg injury / speed loss indicator)
- Spike in BB% for pitchers (command/control issue, often mechanical or injury-related)
- Sharp drop in SwStr% for pitchers (often precedes DL trip)

---

## Implementation Roadmap: Phased Plan

### Phase 1 — Expand the FanGraphs Pull (2–3 days of work)
The data is already available in the existing pybaseball pipeline. We just need to extract and store more columns.

Hitter fields to add from `batting_stats()`:
`wRC+, wOBA, ISO, BB%, K%, BABIP, LD%, GB%, FB%, Hard%, Barrel%`

Pitcher fields to add from `pitching_stats()`:
`FIP, xFIP, SIERA, SwStr%, GB%, LD%, FB%, K/9, BB/9, K-BB%, HR/FB%, LOB%`

This is the highest-ROI improvement: zero new data sources, just more columns from a feed we already query. These should be stored in the reference DB and surfaced in the morning briefing with color-coded thresholds.

**Output in briefing:** Add a "Skills Profile" card per player showing key advanced metrics with simple traffic-light coloring (green = elite, yellow = average, red = concern).

---

### Phase 2 — Statcast Layer via Baseball Savant (1–2 weeks of work)
Add a new data module that queries Baseball Savant's CSV export endpoints for:
- Hitter Statcast: `exit_velocity_avg, launch_angle_avg, barrel_rate, hard_hit_rate, sprint_speed, xwOBA, xBA, xSLG`
- Pitcher Statcast: `xERA, xwOBA_against, whiff_rate, csw_rate, gb_rate, barrel_rate_against`

The Baseball Savant custom leaderboard endpoint: `https://baseballsavant.mlb.com/leaderboard/custom` accepts parameters for year, type (batter/pitcher), and stat columns, returning CSV. This can be queried via `requests` and parsed into pandas DataFrames.

**New briefing feature:** "Statcast Percentile Card" — show each player's Baseball Savant percentile (0–100) for their most relevant metrics, color-coded red/yellow/green matching Savant's own color scheme. This is the single most visually impactful addition.

**Regression/Breakout Alerts:** Automatically flag players where:
- `xwOBA − wOBA > .030` → "Breakout Candidate"
- `wOBA − xwOBA > .030` → "Regression Risk"
- `xERA − ERA > 1.00` → "SP Buy-Low"
- `ERA − xERA > 1.00` → "SP Sell-High"

---

### Phase 3 — Projection System Integration (1–2 weeks of work)
Replace the current "prior season stats × multiplier" projection fallback with actual Steamer/ZiPS projections from FanGraphs.

FanGraphs projections are available as downloadable CSVs from their leaderboard. The current pybaseball integration can be extended to fetch the current season's projections using the `proj_season` parameter in `batting_stats()` and `pitching_stats()`.

**Key improvement:** Instead of projecting from prior-season counting stats, project from the consensus of Steamer + ZiPS, which already account for aging, regression, and injury history. This is particularly important for breakout candidates and declining veterans.

**Output in briefing:** "Projection vs. Current Pace" comparison — show if a player is on pace to beat or miss their Steamer/ZiPS projection, and what the gap implies for the rest of the season.

---

### Phase 4 — Matchup & Context Intelligence (2–3 weeks of work)
Build a matchup overlay that assesses each day/week's schedule quality:

For hitters: Pull the opposing starter's FIP, xFIP, SwStr%, and GB% to rate each matchup as favorable/neutral/unfavorable.
For pitchers: Pull the opposing lineup's wRC+, barrel rate, and K% to rate the offense they'll face.
Add ballpark factor adjustments from FanGraphs park factor tables.
Flag two-start pitchers with both favorable matchups as elite weekly plays.

**Output in briefing:** "Today's Best Matchups" section — ranked list of your players with the best matchup-adjusted projections for the day/week.

---

### Phase 5 — Velocity & Trend Monitoring (3–4 weeks of work)
Build a daily velocity tracker for all starting pitchers on your roster:
- Pull game-by-game pitch data from Baseball Savant
- Track 4-seam fastball average velocity with a 10-game rolling average
- Alert when velocity drops >0.5 mph from season average (early injury signal)
- Alert when velocity jumps >1.0 mph (mechanical improvement / breakout signal)

Also track sprint speed for key speed-dependent hitters (SB thieves, OF candidates) across the season.

**Output in briefing:** "Velocity Watch" section showing SP velocity trends with red flags for declines.

---

### Phase 6 — Aging & Roster Strategy Intelligence (4–6 weeks of work)
Build an aging curve overlay that:
- Flags players entering their peak age window (24–28) as upside assets
- Flags players over 32 with speed-dependent value as regression risks
- Integrates with the power rankings to project which teams have the youngest/most durable rosters

**Output in briefing:** "Roster Health Index" — a composite score combining age profile, injury history, and current Statcast trends.

---

## Data Sources & APIs

**Primary Data Sources:**

FanGraphs (via pybaseball): `batting_stats()`, `pitching_stats()` — already integrated. Expand columns pulled. All Tier 2 metrics available here.
Baseball Savant CSV API: `baseballsavant.mlb.com/leaderboard/custom` — free, no auth required, returns CSV. All Tier 1 Statcast metrics available here.
pybaseball `statcast()`: Pitch-level Statcast data for velocity/movement tracking. Requires date range queries; cache aggressively.
ESPN Fantasy API: Already integrated. Continue using for roster, schedule, and projections.

**Secondary Sources:**

Baseball Reference (via pybaseball): Already as fallback. Keep.
FanGraphs Splits: `fg_batting_leaders()` with split parameters for platoon data.
Baseball Prospectus: PECOTA data requires a subscription but adds percentile projection bands.

**Recommended Python Libraries:**

```
pybaseball    # already in use — expand columns extracted
requests      # for Baseball Savant CSV downloads
pandas        # already in use for data processing
scipy         # for regression/correlation analysis
numpy         # for aging curve calculations
```

---

## Metric Priority Matrix

| Metric | Impact | Difficulty | Phase |
|---|---|---|---|
| wRC+, wOBA, ISO, FIP, xFIP, SIERA | Very High | Very Low | 1 |
| BB%, K%, K-BB%, SwStr%, GB%, LOB% | High | Very Low | 1 |
| BABIP, Hard%, LD% | High | Very Low | 1 |
| xwOBA, xBA, xERA, barrel%, sprint speed | Very High | Low | 2 |
| Regression/breakout alerts | Very High | Low | 2 |
| Steamer/ZiPS projections | High | Medium | 3 |
| Matchup overlays | High | Medium | 4 |
| Velocity trend monitoring | High | Medium | 5 |
| Platoon splits | Medium | Medium | 4 |
| Aging curve flags | Medium | High | 6 |
| Pitch-level stuff metrics | Medium | High | 5–6 |
| OAA/defensive metrics | Low | Medium | 6 |

---

## Key Research Sources

The following sources were used to inform this roadmap and are valuable ongoing references:

- [FanGraphs Sabermetrics Library](https://library.fangraphs.com) — definitive reference for all advanced metrics
- [Baseball Savant Statcast Leaderboard](https://baseballsavant.mlb.com/statcast_leaderboard) — live Statcast data
- [Baseball Savant Percentile Rankings](https://baseballsavant.mlb.com/leaderboard/percentile-rankings) — player percentile cards
- [Baseball Savant Expected Statistics](https://baseballsavant.mlb.com/leaderboard/expected_statistics) — xwOBA, xBA, xSLG, xERA
- [pybaseball GitHub](https://github.com/jldbc/pybaseball) — Python library for FanGraphs/BRef/Savant data
- [FanGraphs 2026 Projections](https://blogs.fangraphs.com/all-the-2026-projections-are-in/) — Steamer + ZiPS consensus
- [RotoBaller Sabermetrics Glossary 2026](https://www.rotoballer.com/sabermetrics-glossary-explaining-key-stats-for-fantasy-baseball-2026/1801752) — fantasy-specific metric definitions
- [Pitcher List Advanced Metrics](https://pitcherlist.com/leaderboard/) — pitcher-focused analysis
- [The Dynasty Dugout: Statcast 101](https://www.thedynastydugout.com/p/statcast-101-expected-stats) — expected stats explainer
- [Fantasy Six Pack Sabermetrics Guide](https://fantasysixpack.net/fantasy-baseball-sabermetric-statistics/) — fantasy application of advanced stats

---

## Summary: The 3 Highest-Impact Additions

If only three improvements can be made in the near term, these are the ones with the greatest expected return on player valuation accuracy:

**1. Expand the FanGraphs pull to include wRC+, FIP, xFIP, SIERA, SwStr%, and K-BB%**
This is already within the existing pipeline. Zero new data sources. Dramatically better player evaluation with a day or two of work.

**2. Add Baseball Savant Statcast data: xwOBA, barrel rate, exit velocity, xERA**
The regression/breakout alert system built on xwOBA vs. actual wOBA gaps is the single most valuable addition for identifying buy-low and sell-high situations before the rest of your league catches on.

**3. Replace the projection fallback with Steamer/ZiPS consensus projections**
The current fallback (prior season stats × multiplier) is crude. Steamer projections already account for aging, regression, and injury — switching to them improves all downstream calculations including replacement level and positional scarcity scoring.

---

*This roadmap is designed to be implemented iteratively. Each phase builds on the last and delivers standalone value — there is no need to complete later phases before earlier ones provide meaningful improvement to the morning briefing.*
