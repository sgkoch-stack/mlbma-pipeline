#!/usr/bin/env python3
"""MLBMA roster/IL module - statsapi live source. Validated 2026-07-18 (Session S).

Pulls all 30 MLB orgs: rosterType=active (true MLB active list) + rosterType=fullRoster
(whole org incl. D60/ILF players, who are NOT on the 40-man). Emits:
  - roster_il_<date>.csv          full org map (name, team, mlb_active, status, desc)
  - roster_il_<date>_MLB_IL.csv   compact D10/D15/D60 list
Crossref: crossref_flags(names) -> per-name flags for board IL checks.
Rules of use (canon): FLAG ONLY - Grant confirms before any board removal.
Name collisions are real (two Jose Ramirezes, two Curtis Meads as of 7/18):
always report ALL hits with team+status, never auto-pick.
Cost: 61 HTTP calls to statsapi.mlb.com, ~0.7s threaded. Zero Odds API credits.
"""
import csv
import json
import sys
import time
import unicodedata
import urllib.request
from concurrent.futures import ThreadPoolExecutor

BASE = "https://statsapi.mlb.com/api/v1"
IL_CODES = ("D7", "D10", "D15", "D60", "ILF")
MLB_IL_CODES = ("D10", "D15", "D60")


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "mlbma-roster/0.1"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.load(r)


def norm(s):
    """Accent-strip + lowercase for name matching (Jose == Jose\u0301)."""
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    ).lower().strip()


def _pull_team(team):
    tid, abbr = team["id"], team["abbreviation"]
    act = _get(f"{BASE}/teams/{tid}/roster?rosterType=active&season=2026")["roster"]
    full = _get(f"{BASE}/teams/{tid}/roster?rosterType=fullRoster&season=2026")["roster"]
    active_norms = {norm(p["person"]["fullName"]) for p in act}
    rows = []
    for p in full:
        nm = p["person"]["fullName"]
        rows.append({
            "name": nm,
            "norm": norm(nm),
            "team": abbr,
            "mlb_active": norm(nm) in active_norms,
            "status": p["status"]["code"],
            "desc": p["status"]["description"],
        })
    return rows


def sweep():
    """Full-league pull. Returns (rows, elapsed_seconds). Self-checks or raises."""
    t0 = time.time()
    teams = _get(f"{BASE}/teams?sportId=1&season=2026")["teams"]
    if len(teams) != 30:
        raise RuntimeError(f"selfcheck: expected 30 teams, got {len(teams)}")
    with ThreadPoolExecutor(max_workers=12) as ex:
        rows = [r for team_rows in ex.map(_pull_team, teams) for r in team_rows]
    n_active = sum(r["mlb_active"] for r in rows)
    if not (700 <= n_active <= 830):
        raise RuntimeError(f"selfcheck: MLB-active {n_active} outside sane band 700-830")
    if len(rows) < 5000:
        raise RuntimeError(f"selfcheck: only {len(rows)} org rows - partial pull?")
    return rows, time.time() - t0


def write_csvs(rows, datestr):
    fn_full = f"roster_il_{datestr}.csv"
    fn_il = f"roster_il_{datestr}_MLB_IL.csv"
    cols = ["name", "norm", "team", "mlb_active", "status", "desc"]
    with open(fn_full, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    with open(fn_il, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows([r for r in rows if r["status"] in MLB_IL_CODES])
    return fn_full, fn_il


def build_lookup(rows):
    lk = {}
    for r in rows:
        lk.setdefault(r["norm"], []).append(r)
    return lk


def crossref_flags(names, lookup):
    """Per board name -> list of (team, flag, desc). Flags:
    OK-ACTIVE / IL:<code> / NOT-ON-ACTIVE(<code>) / NOT-FOUND.
    Multiple hits = name collision: display all, Grant rules."""
    out = {}
    for probe in names:
        hits = lookup.get(norm(probe), [])
        if not hits:
            out[probe] = [("-", "NOT-FOUND", "no org match")]
            continue
        flags = []
        for h in hits:
            if h["mlb_active"]:
                flag = "OK-ACTIVE"
            elif h["status"] in IL_CODES:
                flag = "IL:" + h["status"]
            else:
                flag = f"NOT-ON-ACTIVE({h['status']})"
            flags.append((h["team"], flag, h["desc"]))
        out[probe] = flags
    return out


if __name__ == "__main__":
    datestr = time.strftime("%Y-%m-%d")
    rows, secs = sweep()
    f1, f2 = write_csvs(rows, datestr)
    il = [r for r in rows if r["status"] in MLB_IL_CODES]
    print(f"roster/IL sweep OK: {len(rows)} org rows, "
          f"{sum(r['mlb_active'] for r in rows)} MLB-active, "
          f"{len(il)} on D10/D15/D60, {secs:.1f}s -> {f1}, {f2}")
    if len(sys.argv) > 1:
        lk = build_lookup(rows)
        for name, flags in crossref_flags(sys.argv[1:], lk).items():
            for team, flag, desc in flags:
                print(f"  {name}: {team} | {flag} | {desc}")
