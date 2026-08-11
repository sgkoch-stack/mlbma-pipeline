#!/usr/bin/env python3
"""MLBMA scoring script — model-vs-actuals, all 8 markets.

THE FEEDBACK LOOP (Great Simplification, S 8/7): measures THE MODEL, not the
card. Every projection row on the board gets scored against finals. Dollar P&L
is Grant's alone and never appears here.

PROJECTIONS SCHEMA — projections/YYYY-MM-DD.csv, one row per board entry:
  date,game_pk,away,home,market,entity,player_id,line,side,proj,price,ts
    market : ML | TOTAL | TT | TB | HRR | K | BB | ER
    entity : team abbrev (ML/TT), "GAME" (TOTAL), or player name w/ team tag
             e.g. "Riley Greene (DET)" (TB/HRR/K/BB/ER)
    player_id : statsapi person id when known (preferred join; blank = name match)
    line   : the number AS BET (half-run rule already applied upstream); blank for ML
    side   : O | U  (props/totals)  or team abbrev picked (ML)
    proj   : model's projected value (runs / total / TBs / HRs / Ks / BBs / ERs;
             ML = projected margin for the picked team, sign +)
    price  : American odds at board time
    ts     : board-build pull timestamp (ISO)

SETTLE RULES (canon):
  - O/U mechanical vs actual; equal on whole line = PUSH.
  - ML: picked team wins = W.
  - Game not Final (postponed/suspended) = VOID for all its rows.
  - Player with markets pulled who never appeared = VOID (scratch rule).
  - TB computed H + 2B + 2*3B + 3*HR unless boxscore carries totalBases.

OUTPUT:
  scoring/YYYY-MM-DD_scored.csv  — per-row: actual, err (actual-proj), settle, units
  scoring/summary.csv            — per-market running aggregates recomputed from
                                   ALL scored files (self-healing, no state carried)
  Both committed to the repo via contents API (GITHUB_PAT env).

USAGE:
  python3 score_day.py --date 2026-08-08              # score + commit
  python3 score_day.py --date 2026-08-08 --no-commit  # score locally only
  python3 score_day.py --selftest [--date YYYY-MM-DD] # fabricate rows from a real
                                                      # Final boxscore, score them,
                                                      # assert; commits nothing

statsapi etiquette: serial fetch + backoff, never ThreadPoolExecutor (canon).
"""

import argparse, base64, csv, io, json, os, re, sys, time, unicodedata
import urllib.request, urllib.error, urllib.parse
from datetime import datetime, timezone

REPO = "sgkoch-stack/mlbma-pipeline"
API_GH = "https://api.github.com"
API_MLB = "https://statsapi.mlb.com/api/v1"
MARKETS = ["ML", "TOTAL", "TT", "TB", "HRR", "K", "BB", "ER"]
SCORED_FIELDS = ["date","game_pk","away","home","market","entity","player_id",
                 "line","side","proj","price","ts","actual","err","settle","units"]

# ---------------------------------------------------------------- http helpers
def _get(url, headers=None, tries=4, backoff=2.0):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=headers or {})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode())
        except Exception as e:
            if i == tries - 1:
                raise
            time.sleep(backoff * (i + 1))

def _gh_headers():
    tok = os.environ.get("GITHUB_PAT", "")
    if not tok:
        raise SystemExit("GITHUB_PAT not in env")
    return {"Authorization": f"Bearer {tok}",
            "Accept": "application/vnd.github+json"}

def gh_get_file(path):
    """Return (text, sha) or (None, None) if absent."""
    url = f"{API_GH}/repos/{REPO}/contents/{urllib.parse.quote(path)}"
    try:
        d = _get(url, headers=_gh_headers(), tries=2)
        return base64.b64decode(d["content"]).decode(), d["sha"]
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None, None
        raise

def gh_put_file(path, text, msg):
    url = f"{API_GH}/repos/{REPO}/contents/{urllib.parse.quote(path)}"
    _, sha = gh_get_file(path)
    body = {"message": msg,
            "content": base64.b64encode(text.encode()).decode()}
    if sha:
        body["sha"] = sha
    req = urllib.request.Request(url, method="PUT", headers=_gh_headers(),
                                 data=json.dumps(body).encode())
    with urllib.request.urlopen(req, timeout=30) as r:
        out = json.loads(r.read().decode())
    return out["commit"]["sha"][:8]

# ---------------------------------------------------------------- mlb actuals
def fetch_day(date_iso):
    """schedule + boxscores for the date -> games dict keyed by game_pk."""
    mmdd = datetime.strptime(date_iso, "%Y-%m-%d").strftime("%m/%d/%Y")
    sched = _get(f"{API_MLB}/schedule?sportId=1&date={mmdd}")
    games = {}
    for d in sched.get("dates", []):
        for g in d.get("games", []):
            pk = g["gamePk"]
            st = g["status"]["detailedState"]
            games[pk] = {
                "final": st.startswith("Final") or st == "Game Over",
                "state": st,
                "away": g["teams"]["away"]["team"].get("abbreviation")
                        or g["teams"]["away"]["team"]["name"],
                "home": g["teams"]["home"]["team"].get("abbreviation")
                        or g["teams"]["home"]["team"]["name"],
                "away_runs": g["teams"]["away"].get("score"),
                "home_runs": g["teams"]["home"].get("score"),
                "players": {},        # norm name -> stats
                "players_by_id": {},  # person id -> stats
            }
    for pk, g in games.items():
        if not g["final"]:
            continue
        box = _get(f"{API_MLB}/game/{pk}/boxscore")
        time.sleep(0.6)  # serial + polite
        for side in ("away", "home"):
            team_abbr = box["teams"][side]["team"].get("abbreviation", g[side])
            g[side] = team_abbr or g[side]
            for pid_key, pl in box["teams"][side]["players"].items():
                pid = pl["person"]["id"]
                name = pl["person"]["fullName"]
                bat = pl.get("stats", {}).get("batting", {}) or {}
                pit = pl.get("stats", {}).get("pitching", {}) or {}
                appeared = bool(bat) or bool(pit)
                if bat:
                    tb = bat.get("totalBases")
                    if tb is None:
                        tb = (bat.get("hits", 0) + bat.get("doubles", 0)
                              + 2 * bat.get("triples", 0)
                              + 3 * bat.get("homeRuns", 0))
                else:
                    tb = None
                rec = {"name": name, "team": g[side], "appeared": appeared,
                       "tb": tb, "hrr": (bat.get("hits",0) + bat.get("runs",0) + bat.get("rbi",0)) if bat else None,
                       "k": pit.get("strikeOuts") if pit else None,
                       "bb": pit.get("baseOnBalls") if pit else None,
                       "er": pit.get("earnedRuns") if pit else None}
                g["players_by_id"][pid] = rec
                g["players"][norm_name(name)] = rec
    return games

SUFFIXES = re.compile(r"\s+(jr\.?|sr\.?|ii|iii|iv|v)$", re.I)
def norm_name(s):
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-zA-Z\s]", "", s).strip().lower()
    return SUFFIXES.sub("", s).strip()

def split_entity(entity):
    """'Riley Greene (DET)' -> ('riley greene', 'DET'); no tag -> (name, None)."""
    m = re.match(r"^(.*?)\s*\(([A-Z]{2,3})\)\s*$", entity.strip())
    if m:
        return norm_name(m.group(1)), m.group(2)
    return norm_name(entity), None

# ---------------------------------------------------------------- settle math
def american_units(price, won):
    """Flat 1u: profit units on win, -1 on loss."""
    p = float(price)
    if won:
        return round(p / 100.0, 4) if p > 0 else round(100.0 / -p, 4)
    return -1.0

def settle_ou(actual, line, side):
    if actual > line:
        w = "O"
    elif actual < line:
        w = "U"
    else:
        return "P"
    return "W" if side.upper().startswith(w) else "L"

def score_row(row, games):
    pk = int(row["game_pk"]) if row.get("game_pk") else None
    g = games.get(pk)
    out = dict(row)
    def fin(actual, settle):
        out["actual"] = "" if actual is None else actual
        out["err"] = ("" if actual is None or not row.get("proj")
                      else round(float(actual) - float(row["proj"]), 3))
        out["settle"] = settle
        out["units"] = (0.0 if settle in ("P", "V") or row.get("price") in ("", None)
                        else american_units(row["price"], settle == "W"))
        return out
    if g is None or not g["final"]:
        return fin(None, "V")
    mkt = row["market"].upper()
    if mkt == "ML":
        pick = row["side"].strip().upper()
        margin = ((g["away_runs"] - g["home_runs"])
                  if pick == g["away"].upper()
                  else (g["home_runs"] - g["away_runs"]))
        return fin(margin, "W" if margin > 0 else "L")
    if mkt == "TOTAL":
        tot = g["away_runs"] + g["home_runs"]
        return fin(tot, settle_ou(tot, float(row["line"]), row["side"]))
    if mkt == "TT":
        team = row["entity"].strip().upper()
        runs = g["away_runs"] if team == g["away"].upper() else g["home_runs"]
        return fin(runs, settle_ou(runs, float(row["line"]), row["side"]))
    # player props
    rec = None
    if row.get("player_id"):
        rec = g["players_by_id"].get(int(row["player_id"]))
    if rec is None:
        nm, _tag = split_entity(row["entity"])
        rec = g["players"].get(nm)
    if rec is None or not rec["appeared"]:
        return fin(None, "V")   # scratch with markets pulled = VOID
    key = {"TB": "tb", "HRR": "hrr", "K": "k", "BB": "bb", "ER": "er"}[mkt]
    actual = rec[key]
    if actual is None:          # e.g. K market on a guy who only hit
        return fin(None, "V")
    return fin(actual, settle_ou(actual, float(row["line"]), row["side"]))

# ---------------------------------------------------------------- summary
def rebuild_summary(scored_texts):
    agg = {m: {"n":0,"W":0,"L":0,"P":0,"V":0,"units":0.0,"abs_err":0.0,
               "err":0.0,"err_n":0} for m in MARKETS}
    for text in scored_texts:
        for r in csv.DictReader(io.StringIO(text)):
            m = r["market"].upper()
            if m not in agg:
                continue
            a = agg[m]
            a["n"] += 1
            a[r["settle"]] += 1
            a["units"] += float(r["units"] or 0)
            if r["err"] not in ("", None):
                a["err_n"] += 1
                a["err"] += float(r["err"])
                a["abs_err"] += abs(float(r["err"]))
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["market","n","W","L","P","V","win_pct","units_flat",
                "MAE","bias"])
    for m in MARKETS:
        a = agg[m]
        wl = a["W"] + a["L"]
        w.writerow([m, a["n"], a["W"], a["L"], a["P"], a["V"],
                    round(a["W"]/wl, 4) if wl else "",
                    round(a["units"], 2),
                    round(a["abs_err"]/a["err_n"], 3) if a["err_n"] else "",
                    round(a["err"]/a["err_n"], 3) if a["err_n"] else ""])
    return out.getvalue()

# ---------------------------------------------------------------- selftest
def selftest(date_iso):
    games = fetch_day(date_iso)
    finals = {pk: g for pk, g in games.items() if g["final"]}
    if not finals:
        print(f"SELFTEST: no Final games on {date_iso}"); return 1
    pk, g = sorted(finals.items())[0]
    tot = g["away_runs"] + g["home_runs"]
    batter = next((r for r in g["players_by_id"].values()
                   if r["tb"] is not None and r["appeared"]), None)
    pitcher = next((r for r in g["players_by_id"].values()
                    if r["k"] is not None and r["appeared"]), None)
    winner = g["away"] if g["away_runs"] > g["home_runs"] else g["home"]
    rows = [
        {"date":date_iso,"game_pk":pk,"away":g["away"],"home":g["home"],
         "market":"ML","entity":winner,"player_id":"","line":"",
         "side":winner,"proj":"2.0","price":"-120","ts":""},
        {"date":date_iso,"game_pk":pk,"away":g["away"],"home":g["home"],
         "market":"TOTAL","entity":"GAME","player_id":"","line":str(tot-0.5),
         "side":"O","proj":str(tot),"price":"-110","ts":""},
        {"date":date_iso,"game_pk":pk,"away":g["away"],"home":g["home"],
         "market":"TB","entity":f'{batter["name"]} ({batter["team"]})',
         "player_id":"","line":str(batter["tb"]+0.5),"side":"U",
         "proj":str(batter["tb"]),"price":"+100","ts":""},
        {"date":date_iso,"game_pk":pk,"away":g["away"],"home":g["home"],
         "market":"K","entity":f'{pitcher["name"]} ({pitcher["team"]})',
         "player_id":"","line":str(pitcher["k"]),"side":"O",
         "proj":str(pitcher["k"]),"price":"-115","ts":""},
        {"date":date_iso,"game_pk":pk,"away":g["away"],"home":g["home"],
         "market":"HRR","entity":f'{batter["name"]} ({batter["team"]})',
         "player_id":"","line":str(batter["hrr"]-0.5),"side":"O",
         "proj":str(batter["hrr"]),"price":"-110","ts":""},
        {"date":date_iso,"game_pk":pk,"away":g["away"],"home":g["home"],
         "market":"HRR","entity":"Nobody Realman (ZZZ)","player_id":"",
         "line":"0.5","side":"O","proj":"0.4","price":"+300","ts":""},
    ]
    scored = [score_row(r, games) for r in rows]
    # ML on the actual winner = W; TOTAL O at (tot-0.5) = W;
    # TB U at (tb+0.5) = W; K O at exactly k = P;
    # HRR O at (h+r+rbi - 0.5) = W (real H+R+RBI, the 8/11 fix); unknown = V
    exp = ["W", "W", "W", "P", "W", "V"]
    got = [s["settle"] for s in scored]
    ok = got == exp
    for s, e in zip(scored, exp):
        print(f'  {s["market"]:5s} {s["entity"][:28]:28s} line={s["line"] or "-":>5} '
              f'side={s["side"]:>3} actual={s["actual"]} settle={s["settle"]} '
              f'(exp {e}) units={s["units"]}')
    print("SELFTEST", "PASS" if ok else f"FAIL got={got} exp={exp}")
    return 0 if ok else 1

# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None)
    ap.add_argument("--no-commit", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--local-proj", default=None,
                    help="score a local projections csv instead of repo copy")
    args = ap.parse_args()
    date_iso = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if args.selftest:
        sys.exit(selftest(date_iso))
    if args.local_proj:
        proj_text = open(args.local_proj).read()
    else:
        proj_text, _ = gh_get_file(f"projections/{date_iso}.csv")
        if proj_text is None:
            raise SystemExit(f"no projections/{date_iso}.csv in repo")
    rows = list(csv.DictReader(io.StringIO(proj_text)))
    games = fetch_day(date_iso)
    scored = [score_row(r, games) for r in rows]
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=SCORED_FIELDS, extrasaction="ignore")
    w.writeheader()
    for s in scored:
        w.writerow(s)
    scored_text = out.getvalue()
    print(scored_text)
    if args.no_commit:
        open(f"{date_iso}_scored.csv", "w").write(scored_text)
        print(f"wrote {date_iso}_scored.csv locally (no commit)")
        return
    c1 = gh_put_file(f"scoring/{date_iso}_scored.csv", scored_text,
                     f"scoring: {date_iso}")
    # rebuild summary from every scored file in the repo
    url = f"{API_GH}/repos/{REPO}/git/trees/main?recursive=1"
    tree = _get(url, headers=_gh_headers())
    texts = []
    for t in tree["tree"]:
        if t["path"].startswith("scoring/") and t["path"].endswith("_scored.csv"):
            txt, _ = gh_get_file(t["path"])
            texts.append(txt)
    c2 = gh_put_file("scoring/summary.csv", rebuild_summary(texts),
                     f"summary rebuild through {date_iso}")
    print(f"committed {c1} (scored) + {c2} (summary)")

if __name__ == "__main__":
    main()
