#!/usr/bin/env python3
"""
MLBMA SHARED PRICING MODULE v1.0 (2026-07-23)
=============================================
THE single canonical implementation of all price math for MLBMA.
Extracted verbatim from pull_odds.py v0.7 at Session S 2026-07-23,
per the Grant ruling that consensus pricing must be ONE SHARED
FUNCTION that every session imports.

RULE (S27, ledger rev31): NEVER re-implement any of this math by hand
in a session, a notebook, or a tracker build. The 7/12 HRR-paper build
computed medians in-session in American-odds space and silently
mispriced 220 rows across three days (misdiagnosed as a corrupt feed).
The math here is FROZEN. Import it:

    from pricing import med_am, am_to_prob, prob_to_am, novig_two_way

Zero dependencies beyond the standard library. No API key. No network.
Safe to import from any script, any session, any container.

WHY PROBABILITY SPACE (S27): American odds are discontinuous across
+/-100 with nothing between. A median (or any average) taken directly
on American prices is invalid whenever a book set straddles the gap:
[-103, -101, +100, +105] "averages" its middle values to -0.5, which
is not a price. Convert each price to implied probability, take the
median THERE, convert back.

CORRUPT-QUOTE FILTER (v0.6 rule): |American| < 100 is impossible and
means feed garbage. Such quotes are dropped BEFORE any median/no-vig
math, loudly. If every quote in a set is corrupt, med_am raises --
it never fabricates a price.
"""

import statistics as _st

__version__ = "1.0"
__all__ = [
    "am_to_prob", "prob_to_am", "novig_two_way",
    "is_corrupt_am", "clean_prices", "med_am", "consensus_price",
    "run_selftest",
]


def am_to_prob(odds):
    """American odds -> implied probability (vig included)."""
    o = float(odds)
    return (-o) / ((-o) + 100.0) if o < 0 else 100.0 / (o + 100.0)


def prob_to_am(p):
    """Implied probability -> American odds (rounded to whole number)."""
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
    """Drop corrupt (|am|<100) quotes before any median/no-vig math.
    Prints a re-pull flag for every drop. Returns surviving quotes."""
    good, bad = [], []
    for x in prices or []:
        (bad if is_corrupt_am(x) else good).append(x)
    if bad:
        where = f" in {context}" if context else ""
        print(f"[corrupt-quote] dropped {bad}{where} -- re-pull this market before trusting")
    return good


def med_am(prices, context=""):
    """Median of American odds via probability space (valid across +/-100).
    Corrupt quotes dropped first; raises ValueError if none survive.
    This IS 'med_over' / 'med_under' / every consensus price in MLBMA."""
    good = clean_prices(prices, context)
    if not good:
        raise ValueError("all quotes corrupt (|am|<100)")
    p = _st.median(am_to_prob(x) for x in good)
    if p >= 1.0:
        p = 0.9999
    if p <= 0.0:
        p = 0.0001
    return prob_to_am(p)


# Discoverability alias: sessions searching for "consensus" find the
# canonical function. Same object, not a copy.
consensus_price = med_am


def run_selftest():
    """Every invariant that has ever bitten us, frozen as assertions."""
    # conversions
    assert abs(am_to_prob(-110) - 0.5238) < 0.001
    assert abs(am_to_prob(+120) - 0.4545) < 0.001
    assert prob_to_am(0.60) == -150
    assert prob_to_am(0.40) == 150
    # round-trips at the boundary
    assert prob_to_am(am_to_prob(-100)) in (-100, 100)
    assert prob_to_am(am_to_prob(100)) in (-100, 100)
    # no-vig
    f = novig_two_way(am_to_prob(-115), am_to_prob(-105))
    assert 0.51 < f < 0.53
    # med_am must survive sign-straddling sets (the v0.1 bug)
    assert med_am([103, 102, -105, -105, -105, 105]) in (-101, 100, -100)
    assert med_am([-110, -110, -110]) == -110
    assert med_am([120, 130, 140]) == 130
    # THE S27 CASE: the exact 7/12 book-set shape that produced "-3" when
    # medianed in American space must come back as a real price near even.
    assert med_am([-103, -101, 100, 105]) in (-101, -100, 100, 101)
    # corrupt-quote filter
    assert is_corrupt_am(-1.5) and is_corrupt_am(-3.0) and is_corrupt_am(99)
    assert is_corrupt_am(None) and is_corrupt_am("garbage")
    assert not is_corrupt_am(-110) and not is_corrupt_am(100) and not is_corrupt_am(-100)
    assert med_am([-110, -3.0, -110]) == -110  # corrupt dropped, median survives
    try:
        med_am([-1.5, 5, -99])
        raise AssertionError("med_am must raise when all quotes corrupt")
    except ValueError:
        pass
    # alias is the same object
    assert consensus_price is med_am
    print("[pricing selftest] ALL PASS")


if __name__ == "__main__":
    run_selftest()
