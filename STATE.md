# MLBMA STATE — head file
Post-simplification (Great Simplification, ruled by Grant 8/7-8/9/2026). Distilled
from ledger rev37 (Drive, superseded). This file + this repo are the ENTIRE system
of record. Git history is the archive. There is no rev chain, no mirror, no cut
ceremony, no session pens. Edit this file in place; commit messages are the log.

## 0. MISSION & DIVISION OF LABOR
- The mission is a model that is accurate, data-driven and successful. Everything
  else is secondary.
- **Claude NEVER logs or grades Grant's card. Grant self-grades. Dollar P&L is
  Grant's alone and appears nowhere in this repo.** The scoring loop (sec 7)
  measures THE MODEL — every board row — not the card.
- Grant delegates analytical heavy lifting, keeps final ruling authority. Hold
  positions under challenge, be honest about uncertainty. Settlement-rule
  questions defer to his book; factual stat questions verify vs statsapi and
  hold (Harper precedent). Plain English on all stats talk ("I'm a lawyer. I
  barely passed stats."). Night owl — never suggest sleep. One question at a
  time. Proactively warn when a session nears context limits. Any Drive file
  Grant needs → direct clickable link.

## 1. BOOT (any session)
1. Fetch this file + code from the repo (raw.githubusercontent.com/sgkoch-stack/
   mlbma-pipeline/main/...; tarball fallback via codeload on raw 404).
2. Vault: MLBMA_vault_v2_2026-08-07.txt, Drive id 1O90VQdxo6mccYYZbxQlBcvCwYTUX_NCh
   (282 B) — Drive's sole surviving role. Labeled two-key format (ODDS_API_KEY=,
   GITHUB_PAT=), aes-256-cbc pbkdf2 iter=200000, base64. Passphrase from Grant
   in-session, NEVER stored; case-sensitive; "bad decrypt" + intact Salted__
   header = wrong passphrase — probe variants in-container before asking a re-key.
   Ciphertext never goes in this public repo (brute-force exposure).
3. Selftests (pull_odds.py selftest; score_day.py --selftest) run when something
   looks off or code changed — not as daily ceremony. Git integrity replaces the
   old md5 boot gates.

## 2. SESSION TYPES
- **Unnamed daily session** (the norm): boot → ingest Grant's files → build the
  board (sec 5) → commit projections/YYYY-MM-DD.csv → run score_day.py for the
  PREVIOUS day in the same pass → emit the board. No close ceremony, no
  cross-session debts.
- **Intraday refresh**: same chat or a new one; delta re-pull of lineups /
  weather / odds and a re-emit of affected rows. Design supports multiple light
  touches per day. A live odds pull AGES OUT (started games drop from the
  window) — a second pull is NOT a superset of the first.
- **Session S**: system/rework work. **Session Q**: read-only queries; no
  canonical writes; flag-never-fix; provenance + sample size on every number.
- The A/B/C/D alphabet and the sec-2D model roster are DEAD. No model/effort
  callout owed.

## 3. DAILY INPUTS (from Grant, unchanged)
Four files: workbook (contains the algo-card tab), Model A, Model B, pitcher
props page. Model A and Model B are EXTERNAL morning models Grant posts — not
any 2.0 model. Plus his fills/notes if he chooses to share them (informational
only — nothing is logged from them). Expected-data rule: lineups statsapi-CONF
if posted else projected (exp); weather best-available (exp); a build NEVER
stalls waiting on confirmations. Credits never gate a pull.

## 4. THE MODELS (all 8 markets stay: ML, TOTAL, TT, TB, HRR, K, BB, ER)
Simplification applies to how the system is RUN, not model coverage. Future
cuts happen on scoring evidence (sec 7), never by fiat.
- **Spec sources (the reconstruction set, proven at B 8/4 + B 8/5):** SPEC v1.1
  (Drive 12p22zfCkb7D96E-C2ybTypJnp-STEdCw) + SPEC v1.0 (1XSfKSy2aY51x5ccg2ddNsoWBhNUx8Mjz
  — sole carrier of the full TB/HRR/TT component weights; never delete) +
  PARAMS SNAPSHOT (1JQRLOlT4jHDb37-iN4aPkeCMsASWlZx-) + TT park-runs addendum
  (1EJa_xgpnjTdCzbuJqamNUXDHFAhFjJjS; COL 1.28 → SEA 0.92; keys are workbook
  abbrevs, ARI=AZ, CHW=CWS). **MIGRATE ALL FOUR INTO THIS REPO at demolition —
  until then they live on Drive and this pointer is load-bearing.**
- Recovered structure (S-docket verify vs workbook still owed): slot_pp pure by
  slot s1..s9 = 4.76 / 3.77 / 2.81 / 1.73 / 0.30 / -1.20 / -2.41 / -4.17 /
  -5.57; pa_mult = 1.12031 / 1.09520 / 1.07109 / 1.04375 / 1.00746 / 0.96967 /
  0.93910 / 0.89461 / 0.85931; hrr_score = (0.4*hits_z + 0.3*runs_z +
  0.3*rbi_z) * pa_mult (least-squares exact to 8e-4).
- K 2.0 option C: 0.20 z[own proj_K - line]; proj_K = shrink(K/GS, GS) *
  (outgs_adj / shrink(OUT/GS, GS)) * opp_adj_K; opp_adj_K = lineup-weighted opp
  K% vs hand / league avg, clamp [0.80, 1.20]. BB 2.0 same architecture on
  BB/GS; weights 0.60 internal + 0.20 proj-gap + 0.15 opp + 0.05 L30. ER:
  proj_ER = shrunk_skill/27 * outgs_adj * opp_adj * recency_adj; opp term =
  lineup-weighted SEASON xwOBA. K/BB/ER opp terms = PA-weighted aggregate of
  the NINE CARDED HITTERS, never team-agg. TB does not move with lineups.
  TT park term .1075 live at every build. TT opp_offense = z[PA-weighted
  carded-lineup OPS vs SP hand] — nine carded hitters per shared machinery
  (statsapi vl/vr splits, EB-shrunk k=450 toward overall + league gap); no
  lineup → team OPS YTD fallback, flagged team-agg. RATIFIED by Grant S 8/10,
  closing B 8/4 reconstruction interpretation (2). Leakage terms RETIRED (7/22).
- **Model freeze: bug fixes only; no single-stretch reweights.** PA >= 100 for
  TB/HRR board display; projections stay full-population.
- Triple Locks: ML+totals only, all three legs same side — Model A >= 65%;
  Model B top-5-in-market (RANKINGS ONLY — its percentages are identical to
  Model A's, independence is weak); qualifying algo play. Max 10/day. The only
  bet-shaped output; the board prints NO algo plays. Six straight no-fire
  slates through 8/5; two ML locks fired 8/11 (TEX, MIL); architecture review
  whenever Grant calls one.
- **ALGO SCOPE (Grant ruling 8/12, restating and enforcing the line above):
  the ONLY reason to run the algo qual test is to check for Triple Locks.
  Claude does NOT emit an algo card, a qual list, or any ML/TOTAL play
  recommendation — Grant plays and tracks his card himself. Nor does algo
  eligibility filter what gets committed: projections/ carries ONE ML row per
  game (the model's projected winner) and ONE TOTAL row per game (the model's
  side), whole slate, so the scoring loop measures the model and not a card.**
- Algo qual rules: plus-money dog qualifies ONLY if projected winner; negative-
  ML favorite must be projected winner, margin WITH sign, sliding margin
  (|ML|-100)/100. **THE -160 CEILING IS AN ELIGIBILITY BAR, NOT A CAP ON THE
  REQUIRED MARGIN (Grant ruling 8/12): a favorite priced worse than -160 is NOT
  an algo play at all, however large its projected margin.** The prior reading
  (slide capped at 0.60, heavy favorites still eligible) is WRONG and retired --
  it wrongly qualified TB -194 on 8/12 and would have fired a Triple Lock.
  Totals |diff| >= 0.75 tested vs the nearest half-line the market ACTUALLY
  OFFERS (resolution rule governs the QUAL TEST). **WHOLE-NUMBER TOTALS (Grant
  ruling 8/16): the qual test uses the HALF-RUN RUNG — the half-line the
  half-run ruling would have you bet (Under 9.0 -> test vs 9.5; Over 9.0 ->
  test vs 8.5), NOT the harder rung. Fired AZ@ATL U9.5 8/16 (model 8.40 vs 9.0:
  -1.10 vs 9.5).**

## 5. BOARD STANDARDS (v2.1 emission — unchanged by the rework)
Icon key FIRST (not optional). Split OVER/UNDER boards per model, every row
numbered, enriched icons (fried-egg cold, sun/tornado/arrow wind, boom power,
warning, rain, check/cross model-vs-grade agreement, crossed-swords conflict).
Brief narrative after EVERY category (especially TTs). Full pitcher name lists,
never a 6-name cut. TB + HRR top-20, max 6 per game each. K/BB/ER boards side
by SIGN OF (proj - line) — composite score is strength within a side, never the
side; always carry the props-page grade column. TB ranking = EV-per-$100 at
best ACTIONABLE price (edge displayed; EV-vs-edge basis is an open item, sec 9).
**SECOND TB BOARD (ruled by Grant 8/10, built S 8/10): top 20 by z (composite
model score), PURE ranking — NO per-game cap; printed directly after the EV
board, which stays exactly as-is (its max-6-per-game cap unchanged); same
PA >= 100 display gate; carry price + edge columns on both boards; brief
overlap/divergence note vs the EV board each day — evidence for the EV-vs-edge
open item (sec 9), which this supplements but does not settle.**
Beautiful tables with icons and narratives.

## 6. STANDING RULINGS (board + data canon that survives)
- **THE HALF-RUN RULING** (Grant: "I buy the half run 99 percent of the time"):
  whole-number total → buy the half-run. Strong default, not absolute — surface
  the whole-number leg when the half-run price is materially bad.
- Bare hitter name = TB O1.5 always. TEAM TAG whenever a surname is duplicated
  slate-wide; GAME tag on doubleheader names (G1/G2 by commence order, verify
  vs opposing starter).
- Fade-vs-play is a property of the PRICE, never the name (Langford 8/5).
- Rowdy Tellez never appears on any board.
- TT standing context: Grant loves betting TTs — never propose benching them;
  all recs work WITH continued TT betting.
- Actionable books: DraftKings, FanDuel, Hard Rock, bet365, Caesars, Pinnacle,
  BetMGM, BetRivers, theScore, LowVig; Bovada NEVER. Computable API subset = 9
  keys (pinnacle EU REGION ONLY — include eu in every pull); theScore + bet365
  + **Novig (Grant's primary book, no-vig exchange)** unquotable on the feed.
  The board's price universe understates his real prices; never mistake that
  measurement gap for an argument against exchange betting.
- Opener games: K/BB/ER boards flag the OPENER; bulk-arm rows info-only
  NOT-BETTABLE; opener micro-props unmodeled. Opener is NOT an ITT mismatch;
  game scores + handedness key off the bulk arm; opener tell = GS/apps ratio +
  rest gap, never name recognition.
- SP identity disputes: statsapi + the prop market beat rotowire (LAA 8/4,
  DET@SEA 8/5); the prop market is the tiebreaker — a book with posted lines
  has taken a position.
- Weather: algo-page icons are DISPLAY-ONLY; models use pulled forecasts.
  Sports-site wind icons encode direction blowing TOWARD. rotowire weather.php
  = every park's game-time temp/wind/precip on one page (good method, reuse).
- Lineups: statsapi CONF + rotowire expected (daily-lineups.php,
  li.lineup__player title attr, ARI/AZ alias, suffix-strip both sides); ALL
  names board-eligible incl. EXP-only; join on MLBAM id where carried; hitter
  vl/vr from statsapi statSplits (hydrated people call, ~40 ids/chunk, serial).
- Roster traps: NEVER resolve team/in-out from memory — confirmed lineup or
  boxscore only; deadline movers are a recurring tax and the workbook lists old
  teams; fuzzy-match before flagging a scratch; name collisions resolve by
  role/GS.
- Workbook: column maps DRIFT — re-verify every build (whole sheet shifted -1
  between 8/4 and 8/5); tabs are DATED ("MATCHUP 85"); Hitters tab abbrevs are
  fangraphs-style (KCR/SDP/SFG/TBR/WSN — alias them); read the SP Ranks+Ks tab
  every build; ITT-vs-probables check at boot (TBD is not a mismatch).
- Grading-adjacent definitions the SCORER inherits (sec 7): called-but-official
  = played at the final; PPD = void; scratched with all markets pulled = VOID;
  rostered player who just didn't play = PUSH (S36; never coalesce null to 0).

## 7. THE SCORING LOOP (score_day.py — the feedback mechanism)
- **Scope ruled by Grant 8/9: THE WHOLE BOARD.** Every projection row is scored,
  not a card-qualified subset.
- candidates/YYYY-MM-DD.csv committed at each build (Grant ruling 8/11): the FULL
  modeled pools for TB (all bats priced at 1.5 actionable) and HRR (all lined
  bats) — proj, z, price, rank, PA, on_board tag. OUTSIDE projections/ so
  summary.csv (the board's record) is never polluted; graded ad hoc for
  discrimination studies (board vs field, deciles). K/BB/ER/TT/ML/TOTAL have no
  discarded population — the board already covers every modeled entity.
- projections/YYYY-MM-DD.csv committed at each build (schema in score_day.py
  docstring: date,game_pk,away,home,market,entity,player_id,line,side,proj,
  price,ts,board,ev; line stored AS BET — half-run applied upstream).
  **board + ev added 8/12 (Grant ruling): TB rows carry board=EV|Z|BOTH and
  ev=modelled EV per $100 at the stored price, because proj holds z for BOTH
  TB boards and the EV board's own ranking basis was otherwise absent from the
  record. Blank on all non-TB markets. score_day.py passes both through to
  scoring/. This makes open item 3 (EV-vs-edge basis) measurable from the
  record. NOTE: 8/10 and 8/11 predate the columns — those days committed the
  two boards as an untagged union, and the 7 overlap names cannot be
  identified after the fact, so those two days are NOT backfillable.** score_day.py pulls
  statsapi finals + boxscores (serial + backoff, zero Odds credits), writes
  scoring/DATE_scored.csv + rebuilds scoring/summary.csv (per-market n, W-L-P-V,
  win%, MAE, bias, flat-1u units) from ALL scored files — self-healing, no
  carried state. Units are a MODEL metric at board price, never P&L.
- Known simplification: a boarded player who never appeared scores V uniformly
  (the boxscore alone can't distinguish scratch-with-markets-pulled from
  didn't-play; both are 0 units either way).
- Per-market evidence from this loop is the ONLY basis for future market cuts.

## 8. EXECUTION KNOWLEDGE
- statsapi: flaky under threading → SERIAL fetch + backoff (6 attempts, 2+3n s),
  never ThreadPoolExecutor.
- Odds API: historical path /v4/historical/.../events?date=ISO then
  /events/<id>/odds?date=<commence-3h>; markets batter_total_bases,
  batter_hits_runs_rbis, pitcher_strikeouts, pitcher_walks, pitcher_earned_runs;
  UTC BOUNDARY TRAP — filter by SLATE, never date-prefix; ISO dates always;
  strip CRLF; live pulls run cheaper than nominal — never gate on credits.
- GitHub: commits via contents API (PUT /repos/.../contents/<path>, base64 +
  sha-if-update) are BYTE-FAITHFUL — none of the old Drive emission risk. Repo
  is PUBLIC by Grant's ruling (do not re-raise); projections/scoring/STATE are
  world-readable; only ciphertext is excluded.
- openpyxl (for on-demand exports): insert_rows does not adjust formulas; never
  mix ws.append() with manual indexing; reconcile finished workbooks to source;
  READ formula ranges, never infer.

## 9. OPEN ITEMS (everything that survives, in one place)
1. Verify recovered model structure (slot_pp / pa_mult / .4-.3-.3 HRR blend)
   against the workbook — retires reconstruction interpretation (3) if it holds.
2. Dog sliding-margin question: projected-winner dogs that fail the margin test
   (CWS/STL/PIT 8/5) — uniform reading vs carve-out. Affects algo quals.
3. TB board ranking basis: EV-per-$100 vs raw edge at a no-vig book (the Novig
   question). Needs a ruling before any change.
4. Intraday-refresh design: does the workbook ride along so mid-slate NO-DATA
   entrants can be modeled (42 of them on 8/5)?
5. Rescore method: additive-pp interpretation for TB slot moves — ratify or
   restate.
6. TTproj: recast as a candidate second TT model — commit its projections
   alongside TT 2.0 and let the scoring loop decide (design doc Drive
   1nzDj7CcruZIvzB1qXQs3UbRxIqPDrkSM).
7. Triple Lock architecture review (six straight no-fire slates; A/B legs not
   independent) — whenever Grant calls it.
8. Demolition (trails the proven build): migrate the four spec sources into the
   repo; Drive teardown + Grant's delete list; memory primer rewrite; fold the
   live pens.

## 10. DEAD — DO NOT RESURRECT
Card logging and grading by Claude; allbets CSVs; results tracker; HRR-paper /
ghost / unplayed trackers and all paper days; CLV closer ceremony and the TB
streak bookkeeping; chain / dog-record dollar figures; the Drive ledger rev
chain, mirrors, size gates, cuts, pens, folds; session close ceremonies,
C-CLOSE, bet-count reconciliation; the A/B/C/D taxonomy and the 2D model
roster; daily md5 boot-gate ceremony; per-game exposure policing (card
construction is Grant's domain). Historical records live in the superseded
Drive ledger (rev37 = STATE 1-gEVeBSX7pZhA5TMQStepkPgEiUsy3vA + DOCKETS
18iLSq1rQq3_DNqgnV80rzSiTTgMGU8tT) — read-only archaeology, never operational.
