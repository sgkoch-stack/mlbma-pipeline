#!/usr/bin/env python3
"""
MLBMA STATSAPI HELPER v1.0 (2026-07-16) -- STATUS: LIVE-VALIDATED
Built by Session S from Session B's 7/16 rehearsal findings. Fixes two bugs:

BUG 1 (float mlbamid): workbook ID columns read back as floats ("665742.0"),
which break per-player URLs (/people/665742.0 -> 404-class) AND poison the
batch endpoint (personIds=665742.0,... -> HTTP 400 "Invalid Request").
Live-reproduced 2026-07-16: personIds=665742.0,592450 -> 400;
personIds=665742,592450 -> 200. The batch endpoint was never broken --
the float ids were the whole failure. FIX: norm_mlbam_id() int-casts
every id at the boundary. ALL statsapi URLs must pass ids through it.

BUG 2 (call volume): B fell back to ~2 calls per hitter. FIX: get_sides()
uses the batch endpoint as PRIMARY (chunked at 100 ids/call -> a full slate
of ~200 hitters costs 2 calls), per-person /people/{id} as fallback only.

Usage:
  python3 statsapi_helper.py selftest    offline norm checks, no network
  python3 statsapi_helper.py livetest    hits statsapi, validates known players
  from statsapi_helper import norm_mlbam_id, get_sides
      get_sides(["665742.0", 592450, 660271.0])
      -> {665742: {"name": "Juan Soto", "bat": "L", "pitch": "L"}, ...}
      bat/pitch codes: L, R, S (switch). Free API, no key, no credits.
"""
import json, sys, time
import urllib.request, urllib.error

STATSAPI = "https://statsapi.mlb.com/api/v1"
UA = {"User-Agent": "mlbma/1.0"}
BATCH_SIZE = 100


def norm_mlbam_id(v):
    """Coerce a workbook/user-supplied MLBAM id to a clean int.
    Accepts int, float, and strings like "665742", "665742.0", " 665742 ".
    Rejects bool, None, NaN, and non-integer values (raises ValueError)."""
    if isinstance(v, bool) or v is None:
        raise ValueError(f"invalid mlbam id: {v!r}")
    if isinstance(v, int):
        return v
    try:
        f = float(str(v).strip())
    except (TypeError, ValueError):
        raise ValueError(f"invalid mlbam id: {v!r}")
    if f != f:  # NaN
        raise ValueError(f"invalid mlbam id (NaN): {v!r}")
    i = int(f)
    if f != i:
        raise ValueError(f"non-integer mlbam id: {v!r}")
    return i


def _fetch(url, tries=2, timeout=20):
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}: {e.read().decode(errors='replace')[:200]}"
            if e.code == 400:
                break  # bad request will not heal on retry
        except Exception as e:
            last = repr(e)
        time.sleep(0.5)
    raise RuntimeError(f"statsapi fetch failed: {url}\n{last}")


def _row(p):
    return {"name": p.get("fullName", ""),
            "bat": (p.get("batSide") or {}).get("code", ""),
            "pitch": (p.get("pitchHand") or {}).get("code", "")}


def get_sides(ids, verbose=False):
    """{int_id: {name, bat, pitch}} for every resolvable id.
    Batch endpoint primary (chunks of 100), per-person fallback.
    Unresolvable ids are reported and OMITTED from the result -- caller
    must FLAG missing players, never guess handedness."""
    clean, bad = [], []
    for v in ids:
        try:
            clean.append(norm_mlbam_id(v))
        except ValueError:
            bad.append(v)
    if bad:
        print(f"[statsapi-helper] WARNING: unusable ids skipped: {bad}")
    clean = list(dict.fromkeys(clean))  # dedupe, keep order

    out = {}
    for i in range(0, len(clean), BATCH_SIZE):
        chunk = clean[i:i + BATCH_SIZE]
        try:
            data = _fetch(f"{STATSAPI}/people?personIds="
                          + ",".join(str(x) for x in chunk))
            for p in data.get("people", []):
                out[p["id"]] = _row(p)
            if verbose:
                print(f"[statsapi-helper] batch {len(chunk)} ids -> "
                      f"{len(data.get('people', []))} people")
        except RuntimeError as e:
            print(f"[statsapi-helper] batch failed ({e}); "
                  f"falling back per-person for {len(chunk)} ids")
            for pid in chunk:
                try:
                    d = _fetch(f"{STATSAPI}/people/{pid}")
                    for p in d.get("people", []):
                        out[p["id"]] = _row(p)
                except RuntimeError:
                    pass
    missing = [x for x in clean if x not in out]
    if missing:
        print(f"[statsapi-helper] WARNING: no statsapi record for {missing}"
              " -- FLAG these players, do not guess handedness")
    return out


def run_selftest():
    assert norm_mlbam_id(665742) == 665742
    assert norm_mlbam_id(665742.0) == 665742
    assert norm_mlbam_id("665742") == 665742
    assert norm_mlbam_id("665742.0") == 665742
    assert norm_mlbam_id(" 665742 ") == 665742
    for bad in (None, True, False, "garbage", float("nan"), 665742.5, ""):
        try:
            norm_mlbam_id(bad)
            raise AssertionError(f"norm_mlbam_id must reject {bad!r}")
        except ValueError:
            pass
    print("[selftest] all offline checks passed")


def run_livetest():
    # Known anchors: Soto bats L, Judge bats R, Ohtani bats L / throws R.
    # Feed deliberately dirty ids to prove the int-cast + batch path end to end.
    got = get_sides(["665742.0", 592450, "660271"], verbose=True)
    assert got[665742]["bat"] == "L", got.get(665742)
    assert got[592450]["bat"] == "R", got.get(592450)
    assert got[660271]["bat"] == "L", got.get(660271)
    assert all(v["name"] for v in got.values())
    for pid, v in sorted(got.items()):
        print(f"  {pid}: {v['name']}  bat={v['bat']} pitch={v['pitch']}")
    print("[livetest] batch path validated against known players")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "selftest"
    if mode == "selftest":
        run_selftest()
    elif mode == "livetest":
        run_livetest()
    else:
        raise SystemExit("modes: selftest | livetest")
