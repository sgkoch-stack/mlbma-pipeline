#!/usr/bin/env python3
"""
MLBMA ODDS PIPELINE v0.7 (2026-07-17) -- STATUS: BUILT, PENDING LIVE-VALIDATION
v0.6: corrupt-quote filter -- American odds in (-100,+100) are impossible;
such feed garbage is dropped before all median/no-vig math with a
[corrupt-quote] re-pull flag. Fully-corrupt sides: consensus row skipped,
closers row gets clv_note, game row skipped. Input hygiene only.
v0.1 live-validated 2026-07-06 (7 games, 709 prop rows, 22 credits).
v0.2 fix: medians of American odds are now computed in probability space
(am_to_prob -> median -> prob_to_am). v0.1 medianed raw American prices,
which is invalid when a book set straddles +/-100 (produced e.g. -2).
Applies to props consensus, game lines, and closers. FROZEN -- never
reimplement this logic from memory.
v0.3 (2026-07-07): pitcher_earned_runs added to PROP_MARKETS (ER model CLV).
v0.4 (2026-07-07): team_totals added to the per-event fetch (EVENT_EXTRA_MARKETS);
TT consensus flows through props_consensus AND a dedicated team_totals_DATE.csv;
closers grades spreads and team_totals bets. CLV is vs the CLOSING point only --
a fill at a nonstandard point (e.g. RL -1 vs -1.5 close) reports "no closing quote"
with points seen. Team totals in bets CSV: market=team_totals, player=team abbrev,
side=Over/Under, point=line. Spreads: market=spreads, side=team abbrev, point=spread.
v0.7 (2026-07-17): CLV blind-spot fix (ADD, not swap). batter_total_bases_alternate
added to the morning per-event pull as a SEPARATE ladder feed (ALT_MARKETS); its rows
do NOT enter the modal consensus (that would collapse the mode) -- they are written to
props_ladder_alt_DATE.csv as a per-(player,point) rung table incl every 0.5..N.5 line.
Closers: for batter_total_bases bets the closing snapshot pulls the alternate ladder so
CLV grades at the exact bet point (e.g. O1.5) even when the book's standard main line is
0.5 -- this closes the ~20% ungradeable TB CLV hole. Standard batter_total_bases and the
props_consensus output are UNCHANGED. Cost: +1 credit/event morning; +1/TB-bet-event close.

Modes:
  python3 pull_odds.py selftest
      Offline unit checks (math + team map). No network, no credits.
  python3 pull_odds.py check
      Validates API key + prints credit quota. ~0-1 credits.
  python3 pull_odds.py morning
      Pulls today's slate: TB/K/BB props per event + h2h/totals game
      lines. Writes CSVs + raw JSON archive to /home/claude/odds_out/.
      Cost: ~1 + (7 x n_events) + 2 credits.  # v0.7: 7 = 5 props + team_totals + TB alt ladder
  python3 pull_odds.py closers --bets /path/bets.csv
      Pulls closing snapshots (first pitch minus 5 min) for each bet,
      computes CLV. Cost: ~10 x markets x events actually bet.

bets.csv contract (written at fill-logging time; event_id comes from the
morning events archive):
  date,event_id,commence_time,market,player,side,point,my_odds,stake
  market: batter_total_bases | pitcher_strikeouts | pitcher_walks |
          h2h | totals
  side:   Over/Under for props+totals; team abbrev for h2h
  player: blank for game bets
  point:  blank for h2h
"""
import sys, os, json, csv, argparse, statistics
import urllib.request, urllib.error
from datetime import datetime, timedelta, timezone

API_KEY = "c3ea2318774ddd484acbd6455e09e6b6"
BASE = "https://api.the-odds-api.com/v4"
SPORT = "baseball_mlb"
PROP_MARKETS = ["batter_total_bases", "pitcher_strikeouts", "pitcher_walks", "pitcher_earned_runs", "batter_hits_runs_rbis"]
EVENT_EXTRA_MARKETS = ["team_totals"]  # per-event only; not supported on bulk /odds
ALT_MARKETS = ["batter_total_bases_alternate"]  # v0.7: TB ladder, separate CLV feed (not in consensus)
REGION = "us"
OUT_DIR = "/home/claude/odds_out"
ET_OFFSET = -4  # EDT in July

LAST_HEADERS = {}

NICK_TO_ABBR = {
    "Diamondbacks": "AZ", "Braves": "ATL", "Orioles": "BAL", "Red Sox": "BOS",
    "Cubs": "CHC", "White Sox": "CHW", "Reds": "CIN", "Guardians": "CLE",
    "Rockies": "COL", "Tigers": "DET", "Astros": "HOU", "Royals": "KC",
    "Angels": "LAA", "Dodgers": "LAD", "Marlins": "MIA", "Brewers": "MIL",
    "Twins": "MIN", "Mets": "NYM", "Yankees": "NYY", "Athletics": "ATH",
    "Phillies": "PHI", "Pirates": "PIT", "Padres": "SD", "Mariners": "SEA",
    "Giants": "SF", "Cardinals": "STL", "Rays": "TB", "Rangers": "TEX",
    "Blue Jays": "TOR", "Nationals": "WSH",
}

def team_abbr(full_name):
    """'Milwaukee Brewers' -> 'MIL'. Matches on nickname (last words),
    robust to city renames. Athletics normalizes to ATH per house rule."""
    for nick, ab in NICK_TO_ABBR.items():
        if full_name.endswith(nick):
            return ab
    return full_name  # unmatched: pass through, caller flags it

def am_to_prob(odds):
    o = float(odds)
    return (-o) / ((-o) + 100.0) if o < 0 else 100.0 / (o + 100.0)

def prob_to_am(p):
    if p <= 0 or p >= 1:
        raise ValueError("prob out of range")
    return round(-100.0 * p / (1.0 - p)) if p >= 0.5 else round(100.0 * (1.0 - p) / p)

def novig_two_way(p_a, p_b):
    """De-vig by proportional normalization. Returns fair prob of side A."""
    return p_a / (p_a + p_b)

def is_corrupt_am(x):
    """American odds cannot exist in (-100, +100). None/garbage counts too."""
    try:
        return abs(float(x)) < 100.0
    except (TypeError, ValueError):
        return True

def clean_prices(prices, context=""):
    """v0.6: drop corrupt (|am|<100) quotes before any median/no-vig math.
    Prints a re-pull flag for every drop. Returns surviving quotes."""
    good, bad = [], []
    for x in prices or []:
        (bad if is_corrupt_am(x) else good).append(x)
    if bad:
        where = f" in {context}" if context else ""
        print(f"[corrupt-quote] dropped {bad}{where} -- re-pull this market before trusting")
    return good

def med_am(prices):
    """Median of American odds via probability space (valid across +/-100).
    v0.6: corrupt quotes dropped first; raises ValueError if none survive."""
    import statistics as _st
    good = clean_prices(prices)
    if not good:
        raise ValueError("all quotes corrupt (|am|<100)")
    p = _st.median(am_to_prob(x) for x in good)
    if p >= 1.0: p = 0.9999
    if p <= 0.0: p = 0.0001
    return prob_to_am(p)

def parse_iso(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))

def iso_z(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def fetch(url, tries=2):
    global LAST_HEADERS
    last_err = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "mlbma/0.1"})
            with urllib.request.urlopen(req, timeout=30) as r:
                LAST_HEADERS = {k.lower(): v for k, v in r.headers.items()}
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")[:400]
            if e.code == 401:
                raise SystemExit("FATAL: API key rejected (401). Body: " + body)
            if e.code == 422:
                raise SystemExit("FATAL: bad request (422) -- likely a wrong "
                                 "market key or param. Body: " + body)
            if e.code == 429:
                raise SystemExit("FATAL: rate/quota limit (429). Body: " + body)
            last_err = f"HTTP {e.code}: {body}"
        except Exception as e:
            last_err = repr(e)
    raise SystemExit(f"FATAL: fetch failed after {tries} tries: {url}\n{last_err}")

def print_quota():
    used = LAST_HEADERS.get("x-requests-used", "?")
    rem = LAST_HEADERS.get("x-requests-remaining", "?")
    print(f"[quota] used={used} remaining={rem}")
    try:
        if float(rem) < 2000:
            print("[quota] WARNING: under 2,000 credits remaining -- tell Grant.")
    except (TypeError, ValueError):
        pass

# ---------------------------------------------------------------- slate window
def slate_window(now_utc=None):
    """Window covering today's ET slate: from now until 08:00 ET tomorrow."""
    now = now_utc or datetime.now(timezone.utc)
    et_now = now + timedelta(hours=ET_OFFSET)
    et_tomorrow_8am = (et_now + timedelta(days=1)).replace(hour=8, minute=0,
                                                           second=0, microsecond=0)
    end_utc = et_tomorrow_8am - timedelta(hours=ET_OFFSET)
    return now - timedelta(hours=1), end_utc.replace(tzinfo=timezone.utc)

# ---------------------------------------------------------------- morning mode
def pair_outcomes(outcomes):
    """Group a market's outcomes into {(player, point): {'Over': p, 'Under': p}}.
    For h2h, key is (team_name, None) with side name as the outcome name."""
    d = {}
    for o in outcomes or []:
        player = o.get("description")  # None for game markets
        point = o.get("point")
        key = (player, point)
        d.setdefault(key, {})[o.get("name")] = o.get("price")
    return d

def ladder_rows_from(alt_rows, today):
    """v0.7: build a per-(player, point) rung table from the alternate TB ladder.
    No modal collapse -- every rung is its own row, so O1.5 is always present when
    any book posts it. Used to backfill the CLV close and archive the full ladder."""
    by = {}
    for r in alt_rows:
        if r["player"] is None or r["point"] is None:
            continue
        by.setdefault((r["event_id"], r["player"], r["point"]), []).append(r)
    out = []
    for (eid, player, point), rows in sorted(
            by.items(), key=lambda kv: (kv[0][0], str(kv[0][1]), float(kv[0][2]))):
        overs = clean_prices([r["over"] for r in rows if r["over"] is not None],
                             f"alt/{player}/{point} over")
        unders = clean_prices([r["under"] for r in rows if r["under"] is not None],
                              f"alt/{player}/{point} under")
        if not overs:
            continue  # a TB over ladder needs at least the over side
        mo = med_am(overs)
        if unders:
            mu = med_am(unders)
            fair_over = novig_two_way(am_to_prob(mo), am_to_prob(mu))
            novig, fair_am = round(fair_over, 4), prob_to_am(fair_over)
        else:
            mu, novig, fair_am = "", "", ""   # over-only rung (typical for alt ladders)
        best = max(rows, key=lambda r: (r["over"] if (r["over"] is not None
                                        and not is_corrupt_am(r["over"]))
                                        else -10**9))
        out.append({
            "date": today, "event_id": eid, "matchup": rows[0]["matchup"],
            "commence_time": rows[0]["commence_time"],
            "market": "batter_total_bases_alternate", "player": player, "point": point,
            "n_books": len(rows), "med_over": mo, "med_under": mu,
            "novig_over_prob": novig, "fair_over_am": fair_am,
            "best_over": best["over"], "best_over_book": best["book"],
        })
    return out

def run_morning(date_str=None):
    os.makedirs(OUT_DIR, exist_ok=True)
    today = date_str or (datetime.now(timezone.utc)
                         + timedelta(hours=ET_OFFSET)).strftime("%Y-%m-%d")
    lo, hi = slate_window()

    events = fetch(f"{BASE}/sports/{SPORT}/events?apiKey={API_KEY}&dateFormat=iso")
    print_quota()
    slate = []
    for ev in events:
        try:
            ct = parse_iso(ev["commence_time"])
        except Exception:
            continue
        if lo <= ct <= hi:
            slate.append(ev)
    if not slate:
        raise SystemExit("FATAL: no events found in today's window. "
                         "Check date/window logic before running boards.")
    print(f"[events] {len(slate)} games in window {today}")

    with open(f"{OUT_DIR}/events_{today}.json", "w") as f:
        json.dump(slate, f, indent=1)

    # ---- props, per event
    long_rows, alt_rows, raw_props = [], [], {}
    market_hits = {m: 0 for m in PROP_MARKETS + EVENT_EXTRA_MARKETS + ALT_MARKETS}
    mkts = ",".join(PROP_MARKETS + EVENT_EXTRA_MARKETS + ALT_MARKETS)
    for ev in slate:
        eid = ev["id"]
        url = (f"{BASE}/sports/{SPORT}/events/{eid}/odds?apiKey={API_KEY}"
               f"&regions={REGION}&markets={mkts}&oddsFormat=american")
        data = fetch(url)
        raw_props[eid] = data
        matchup = f'{team_abbr(ev["away_team"])}@{team_abbr(ev["home_team"])}'
        for bk in data.get("bookmakers", []):
            for mk in bk.get("markets", []):
                mkey = mk.get("key")
                if mkey not in PROP_MARKETS + EVENT_EXTRA_MARKETS + ALT_MARKETS:
                    continue
                market_hits[mkey] += 1
                dest = alt_rows if mkey in ALT_MARKETS else long_rows  # v0.7: alt ladder kept out of consensus
                for (player, point), sides in pair_outcomes(mk.get("outcomes")).items():
                    dest.append({
                        "date": today, "event_id": eid, "matchup": matchup,
                        "commence_time": ev["commence_time"], "market": mkey,
                        "book": bk.get("key"), "player": player, "point": point,
                        "over": sides.get("Over"), "under": sides.get("Under"),
                    })
    print_quota()
    with open(f"{OUT_DIR}/raw_props_{today}.json", "w") as f:
        json.dump(raw_props, f)

    for m, n in market_hits.items():
        if n == 0:
            print(f"[props] WARNING: zero books returned market '{m}'. "
                  f"Verify market key / posting time before trusting boards.")
        else:
            print(f"[props] {m}: {n} book-market blocks")

    long_path = f"{OUT_DIR}/props_long_{today}.csv"
    write_csv(long_path, long_rows,
              ["date", "event_id", "matchup", "commence_time", "market",
               "book", "player", "point", "over", "under"])

    # v0.7: alternate TB ladder -> separate per-rung file (NOT through modal consensus)
    alt_ladder = ladder_rows_from(alt_rows, today)
    alt_path = f"{OUT_DIR}/props_ladder_alt_{today}.csv"
    write_csv(alt_path, alt_ladder,
              ["date", "event_id", "matchup", "commence_time", "market", "player",
               "point", "n_books", "med_over", "med_under", "novig_over_prob",
               "fair_over_am", "best_over", "best_over_book"])
    print(f"[ladder] {len(alt_rows)} alt rows -> {len(alt_ladder)} rungs -> {alt_path}")

    # ---- consensus per (market, player) at modal point
    cons_rows = []
    by_mp = {}
    for r in long_rows:
        if r["player"] is None:
            continue
        by_mp.setdefault((r["market"], r["player"]), []).append(r)
    for (mkey, player), rows in sorted(by_mp.items()):
        pts = [r["point"] for r in rows if r["point"] is not None]
        if not pts:
            continue
        modal = statistics.mode(pts) if len(set(pts)) > 1 else pts[0]
        at = [r for r in rows if r["point"] == modal]
        overs = clean_prices([r["over"] for r in at if r["over"] is not None],
                             f"{mkey}/{player} over")
        unders = clean_prices([r["under"] for r in at if r["under"] is not None],
                              f"{mkey}/{player} under")
        if not overs or not unders:
            if [r for r in at if r["over"] is not None or r["under"] is not None]:
                print(f"[corrupt-quote] {mkey}/{player}: no clean two-way quotes"
                      f" -- consensus row skipped, re-pull")
            continue
        mo, mu = med_am(overs), med_am(unders)
        fair_over = novig_two_way(am_to_prob(mo), am_to_prob(mu))
        best_o = max(at, key=lambda r: (r["over"] if (r["over"] is not None
                                        and not is_corrupt_am(r["over"]))
                                        else -10**9))
        cons_rows.append({
            "date": today, "market": mkey, "player": player,
            "matchup": at[0]["matchup"], "event_id": at[0]["event_id"],
            "commence_time": at[0]["commence_time"],
            "point": modal, "n_books": len(at),
            "med_over": mo, "med_under": mu,
            "novig_over_prob": round(fair_over, 4),
            "fair_over_am": prob_to_am(fair_over),
            "best_over": best_o["over"], "best_over_book": best_o["book"],
            "alt_points": ";".join(str(p) for p in sorted(set(pts))
                                   if p != modal) or "",
        })
    cons_path = f"{OUT_DIR}/props_consensus_{today}.csv"
    write_csv(cons_path, cons_rows,
              ["date", "market", "player", "matchup", "event_id",
               "commence_time", "point", "n_books", "med_over", "med_under",
               "novig_over_prob", "fair_over_am", "best_over",
               "best_over_book", "alt_points"])
    tt_rows = [dict(r, team=team_abbr(r["player"])) for r in cons_rows
               if r["market"] == "team_totals"]
    tt_path = f"{OUT_DIR}/team_totals_{today}.csv"
    write_csv(tt_path, tt_rows,
              ["date", "event_id", "matchup", "team", "player", "point",
               "n_books", "med_over", "med_under", "novig_over_prob",
               "best_over", "best_over_book", "alt_points"])
    print(f"[team_totals] {len(tt_rows)} team-total consensus rows -> {tt_path}")

    # ---- game lines (whole slate, 2 credits)
    g = fetch(f"{BASE}/sports/{SPORT}/odds?apiKey={API_KEY}"
              f"&regions={REGION}&markets=h2h,totals&oddsFormat=american")
    print_quota()
    with open(f"{OUT_DIR}/raw_gamelines_{today}.json", "w") as f:
        json.dump(g, f)
    game_rows = []
    for ev in g:
        if not (lo <= parse_iso(ev["commence_time"]) <= hi):
            continue
        home, away = team_abbr(ev["home_team"]), team_abbr(ev["away_team"])
        h2h_home, h2h_away, tot_pts, tot_over, tot_under = [], [], [], [], []
        for bk in ev.get("bookmakers", []):
            for mk in bk.get("markets", []):
                if mk["key"] == "h2h":
                    for o in mk["outcomes"]:
                        (h2h_home if o["name"] == ev["home_team"]
                         else h2h_away).append(o["price"])
                elif mk["key"] == "totals":
                    for o in mk["outcomes"]:
                        if o.get("point") is not None:
                            if o["name"] == "Over":
                                tot_pts.append(o["point"]); tot_over.append(o["price"])
                            else:
                                tot_under.append(o["price"])
        if not h2h_home:
            continue
        try:
            (med_am(h2h_home), med_am(h2h_away),
             med_am(tot_over) if tot_over else None,
             med_am(tot_under) if tot_under else None)
        except ValueError:
            print(f"[corrupt-quote] {away}@{home}: game-line side fully corrupt"
                  f" -- game skipped, re-pull")
            continue
        row = {"date": today, "event_id": ev["id"],
               "commence_time": ev["commence_time"],
               "matchup": f"{away}@{home}", "home": home, "away": away,
               "med_ml_home": med_am(h2h_home),
               "med_ml_away": med_am(h2h_away),
               "n_books_ml": len(h2h_home)}
        if tot_pts:
            modal_t = statistics.mode(tot_pts) if len(set(tot_pts)) > 1 else tot_pts[0]
            row.update({"market_total": modal_t,
                        "med_total_over": med_am(tot_over) if tot_over else "",
                        "med_total_under": med_am(tot_under) if tot_under else ""})
        else:
            row.update({"market_total": "", "med_total_over": "",
                        "med_total_under": ""})
        game_rows.append(row)
    glpath = f"{OUT_DIR}/game_lines_{today}.csv"
    write_csv(glpath, game_rows,
              ["date", "event_id", "commence_time", "matchup", "home", "away",
               "med_ml_home", "med_ml_away", "n_books_ml", "market_total",
               "med_total_over", "med_total_under"])

    print(f"\n[done] {len(long_rows)} prop rows | {len(cons_rows)} consensus "
          f"rows | {len(game_rows)} games")
    print(f"[files] {long_path}\n        {cons_path}\n        {glpath}")
    print_quota()

# ---------------------------------------------------------------- closers mode
def close_markets_for(mkey):
    """v0.7: grade batter_total_bases CLV against the alternate ladder so the exact
    bet point (e.g. O1.5) is present at close even when the book main line is 0.5.
    Alt is a superset and close matching is exact-point, so no modal risk here."""
    if mkey == "batter_total_bases":
        return "batter_total_bases_alternate"
    return mkey

def run_closers(bets_path, snapshot_lead_min=5):
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(bets_path) as f:
        bets = list(csv.DictReader(f))
    if not bets:
        raise SystemExit("FATAL: bets file empty.")
    need = {"event_id", "commence_time", "market", "side", "my_odds"}
    missing = need - set(bets[0].keys())
    if missing:
        raise SystemExit(f"FATAL: bets.csv missing columns: {missing}")

    cache, out = {}, []
    for b in bets:
        eid, mkey = b["event_id"], b["market"]
        snap = iso_z(parse_iso(b["commence_time"])
                     - timedelta(minutes=snapshot_lead_min))
        ck = (eid, mkey, snap)
        if ck not in cache:
            url = (f"{BASE}/historical/sports/{SPORT}/events/{eid}/odds"
                   f"?apiKey={API_KEY}&regions={REGION}&markets={close_markets_for(mkey)}"
                   f"&oddsFormat=american&date={snap}")
            resp = fetch(url)
            cache[ck] = resp.get("data", resp)  # historical wraps in 'data'
        data = cache[ck]
        row = dict(b)
        row.update(close_for_bet(data, b))
        out.append(row)
    print_quota()

    date_tag = bets[0].get("date", "unknown")
    path = f"{OUT_DIR}/closers_{date_tag}.csv"
    cols = list(bets[0].keys()) + ["close_point", "close_med_side",
                                   "close_med_opp", "close_novig_myside",
                                   "my_implied", "clv_prob_pts",
                                   "fair_close_am", "close_n_books", "clv_note"]
    write_csv(path, out, cols)
    print(f"[done] CLV written: {path}")

def close_for_bet(event_data, bet):
    """Extract closing consensus for this bet's exact market/selection."""
    mkey = bet["market"]; side = bet["side"]
    player = (bet.get("player") or "").strip() or None
    point = bet.get("point")
    point = float(point) if point not in (None, "",) else None
    my_prices, opp_prices, pts_seen = [], [], []

    accept = {mkey}
    if mkey == "batter_total_bases":
        accept.add("batter_total_bases_alternate")  # v0.7: alt ladder carries the O1.5 close
    for bk in event_data.get("bookmakers", []):
        for mk in bk.get("markets", []):
            if mk.get("key") not in accept:
                continue
            pairs = pair_outcomes(mk.get("outcomes"))
            if mkey == "h2h":
                # h2h outcomes carry team names in 'name'; match on abbrev
                for o in mk.get("outcomes", []):
                    ab = team_abbr(o.get("name", ""))
                    (my_prices if ab == side else opp_prices).append(o.get("price"))
            elif mkey == "spreads":
                # bet: side=team abbrev, point=my spread; opponent carries -point
                for o in mk.get("outcomes", []):
                    ab = team_abbr(o.get("name", ""))
                    pt = o.get("point")
                    if pt is None or point is None:
                        continue
                    if ab == side and abs(float(pt) - point) <= 1e-9:
                        my_prices.append(o.get("price"))
                    elif ab != side and abs(float(pt) + point) <= 1e-9:
                        opp_prices.append(o.get("price"))
                    elif ab == side:
                        pts_seen.append(pt)
            elif mkey == "team_totals":
                # outcomes: name=Over/Under, description=team full name
                # bet: player=team abbrev, side=Over/Under, point=line
                for (pl, pt), sides in pairs.items():
                    if team_abbr(pl or "") != (player or ""):
                        continue
                    if point is not None and pt is not None and \
                       abs(float(pt) - point) > 1e-9:
                        pts_seen.append(pt)
                        continue
                    mine = sides.get(side)
                    opp = sides.get("Under" if side == "Over" else "Over")
                    if mine is not None:
                        my_prices.append(mine)
                    if opp is not None:
                        opp_prices.append(opp)
            else:
                for (pl, pt), sides in pairs.items():
                    if mkey in ("batter_total_bases", "pitcher_strikeouts",
                                "pitcher_walks", "pitcher_earned_runs",
                                "batter_hits_runs_rbis"):
                        if pl != player:
                            continue
                    if point is not None and pt is not None and \
                       abs(float(pt) - point) > 1e-9:
                        pts_seen.append(pt)
                        continue
                    mine = sides.get(side)
                    opp = sides.get("Under" if side == "Over" else "Over")
                    if mine is not None:
                        my_prices.append(mine)
                    if opp is not None:
                        opp_prices.append(opp)

    if not my_prices:
        note = "no closing quote at bet point"
        if pts_seen:
            note += f" (points seen at close: {sorted(set(pts_seen))})"
        return {"close_point": point, "close_med_side": "", "close_med_opp": "",
                "close_novig_myside": "", "my_implied": "",
                "clv_prob_pts": "", "fair_close_am": "",
                "close_n_books": 0, "clv_note": note}

    try:
        ms = med_am(my_prices)
    except ValueError:
        return {"close_point": point, "close_med_side": "", "close_med_opp": "",
                "close_novig_myside": "", "my_implied": "",
                "clv_prob_pts": "", "fair_close_am": "",
                "close_n_books": 0,
                "clv_note": "corrupt closing quotes (|am|<100) -- re-pull before grading"}
    mine_imp = am_to_prob(float(bet["my_odds"]))

    mo = None
    if opp_prices:
        try:
            mo = med_am(opp_prices)
        except ValueError:
            mo = None

    if mo is not None:
        fair = novig_two_way(am_to_prob(ms), am_to_prob(mo))
        return {"close_point": point, "close_med_side": ms, "close_med_opp": mo,
                "close_novig_myside": round(fair, 4),
                "my_implied": round(mine_imp, 4),
                "clv_prob_pts": round((fair - mine_imp) * 100, 2),
                "fair_close_am": prob_to_am(fair),
                "close_n_books": len(my_prices), "clv_note": ""}
    # v0.7: one-sided (over-only) close -- raw-price CLV, no de-vig possible
    close_imp = am_to_prob(ms)
    return {"close_point": point, "close_med_side": ms, "close_med_opp": "",
            "close_novig_myside": "", "my_implied": round(mine_imp, 4),
            "clv_prob_pts": round((close_imp - mine_imp) * 100, 2),
            "fair_close_am": ms,
            "close_n_books": len(my_prices),
            "clv_note": "raw-price CLV (one-sided close, no de-vig)"}

# ---------------------------------------------------------------- utils/modes
def write_csv(path, rows, cols):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)

def run_check():
    data = fetch(f"{BASE}/sports/?apiKey={API_KEY}")
    ok = any(s.get("key") == SPORT for s in data)
    print(f"[check] key valid; {len(data)} sports listed; MLB present: {ok}")
    print_quota()

def run_selftest():
    assert abs(am_to_prob(-110) - 0.5238) < 0.001
    assert abs(am_to_prob(+120) - 0.4545) < 0.001
    assert prob_to_am(0.60) == -150
    assert prob_to_am(0.40) == 150
    f = novig_two_way(am_to_prob(-115), am_to_prob(-105))
    assert 0.51 < f < 0.53
    assert team_abbr("Milwaukee Brewers") == "MIL"
    assert team_abbr("Athletics") == "ATH"
    assert team_abbr("Chicago White Sox") == "CHW"
    assert team_abbr("Chicago Cubs") == "CHC"
    assert team_abbr("Arizona Diamondbacks") == "AZ"
    lo, hi = slate_window(datetime(2026, 7, 6, 15, 0, tzinfo=timezone.utc))
    assert lo < hi
    p = pair_outcomes([
        {"name": "Over", "description": "Shohei Ohtani", "price": -125, "point": 1.5},
        {"name": "Under", "description": "Shohei Ohtani", "price": 105, "point": 1.5},
    ])
    assert p[("Shohei Ohtani", 1.5)]["Over"] == -125
    # med_am must survive sign-straddling sets (the v0.1 bug)
    assert med_am([103, 102, -105, -105, -105, 105]) in (-101, 100, -100)
    assert med_am([-110, -110, -110]) == -110
    assert med_am([120, 130, 140]) == 130
    # v0.6: corrupt-quote filter
    assert is_corrupt_am(-1.5) and is_corrupt_am(-3.0) and is_corrupt_am(99)
    assert is_corrupt_am(None) and is_corrupt_am("garbage")
    assert not is_corrupt_am(-110) and not is_corrupt_am(100) and not is_corrupt_am(-100)
    assert med_am([-110, -3.0, -110]) == -110  # corrupt dropped, median survives
    try:
        med_am([-1.5, 5, -99])
        raise AssertionError("med_am must raise when all quotes corrupt")
    except ValueError:
        pass
    # v0.7: alt ladder builds per-rung rows without modal collapse
    _alt = [
        {"event_id": "E1", "matchup": "AAA@BBB", "commence_time": "t",
         "market": "batter_total_bases_alternate", "book": "bk1",
         "player": "Test Hitter", "point": 1.5, "over": 120, "under": -140},
        {"event_id": "E1", "matchup": "AAA@BBB", "commence_time": "t",
         "market": "batter_total_bases_alternate", "book": "bk2",
         "player": "Test Hitter", "point": 1.5, "over": 115, "under": -135},
        {"event_id": "E1", "matchup": "AAA@BBB", "commence_time": "t",
         "market": "batter_total_bases_alternate", "book": "bk1",
         "player": "Test Hitter", "point": 0.5, "over": -260, "under": 210},
        {"event_id": "E1", "matchup": "AAA@BBB", "commence_time": "t",
         "market": "batter_total_bases_alternate", "book": "bk1",
         "player": "Test Hitter", "point": 2.5, "over": 300, "under": None},
    ]
    lad = ladder_rows_from(_alt, "2026-07-17")
    assert sorted(r["point"] for r in lad) == [0.5, 1.5, 2.5]
    r15 = [r for r in lad if r["point"] == 1.5][0]
    assert r15["n_books"] == 2 and r15["best_over"] == 120
    r25 = [r for r in lad if r["point"] == 2.5][0]  # over-only rung kept, no de-vig
    assert r25["novig_over_prob"] == "" and r25["med_under"] == "" and r25["best_over"] == 300
    assert close_markets_for("batter_total_bases") == "batter_total_bases_alternate"
    assert close_markets_for("pitcher_strikeouts") == "pitcher_strikeouts"
    print("[selftest] all offline checks passed")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["selftest", "check", "morning", "closers"])
    ap.add_argument("--bets")
    ap.add_argument("--date")
    a = ap.parse_args()
    if a.mode == "selftest":
        run_selftest()
    elif a.mode == "check":
        run_check()
    elif a.mode == "morning":
        run_morning(a.date)
    else:
        if not a.bets:
            raise SystemExit("closers mode needs --bets path")
        run_closers(a.bets)
