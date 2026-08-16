"""
TEAM TOTAL model v0.1 — team run distribution from the propmodel per-PA engine.
For each game: nine carded hitters per side -> per-PA multinomial vs SP hand (blended w/ opp
pen by w_sp) -> vectorized base-out Markov simulation of BOTH teams jointly (9 innings, home
team skips bottom 9 when leading, extras w/ ghost runner) -> run distributions.
Outputs P(team runs >= k) for TT, plus P(total >= k) and P(home wins) as by-products.
NOT included in v0.1: park, weather, umpire, as-of-date stats, defense.
Calibration: league-average lineup vs league-average SP -> 4.40 R (away) / 4.33 (home) vs league 4.48;
  baserunning params fixed at league-typical values (P_ADV tuned to close the gap).
Backtest 8/11-8/15 (68 games, actual lineups + SP used, season stats through 8/16, closing no-vig
  TT market = median across DK/FD/WH/MGM/BetRivers/Fanatics): team-run corr .30 (pooled 136);
  primary lines n=136: model corr .18 vs market .12, logloss .677 vs .687; model side W .559
  (BE .521), |edge|>=.03 n=95 W .621 +19u; all lines n=371 W .571 / edge>=.03 n=245 W .629.
  Five slates, ~1-1.5 sigma — suggestive, not proven. Day variance high (8/12 -8.7u).
Board rule v0.1: best half-line per team, edge>=.03, >=3 actionable books, price -180..+150, cap 8.
Companion: propmodel.py (per-PA engine, v0.2 = traded-player combined row + opener workload cap).
"""
import numpy as np, pandas as pd, sys
sys.path.insert(0, "/home/claude/repo")
from propmodel import PropModel, CATS, log5

# baserunning parameters (league-typical, fixed)
P_R2_SCORE_ON_1B = 0.60
P_R1_TO_3_ON_1B  = 0.28
P_R1_SCORE_ON_2B = 0.45
P_SF_ON_OUT      = 0.27   # R3 scores on an out with <2 outs (already net of K share)
P_GIDP           = 0.08   # out with R1 & <2 outs becomes a DP
P_ADV            = 0.055  # misc one-base advance per PA with runners on (SB/WP/PB/errors)
HFA_ONBASE       = 1.03   # home-team scale on non-out events (renormalized)
LG_RUNS_TARGET   = None   # set from data for a sanity check only

def per_pa_matrix(model, lineup, sp_id, opp_team):
    """lineup: list of (player_id, bats). returns 9x6 per-PA prob matrix in CATS order + w_sp."""
    M = np.zeros((9, len(CATS))); ws=[]
    for i,(pid,bats) in enumerate(lineup):
        r = model.per_pa(int(pid), sp_id, opp_team, bats)
        if r is None:   # unknown hitter -> league
            M[i] = [model.lg[c] for c in CATS]; ws.append(np.nan); continue
        blend, env, w = r
        M[i] = [blend[c] for c in CATS]; ws.append(w)
    return M, np.nanmean(ws) if any(np.isfinite(ws)) else 0.55

def sim_half(rng, M, batter, runs, nsim):
    """simulate one half inning for all sims. batter: array of next batter idx (0-8). returns runs scored array, new batter idx."""
    outs = np.zeros(nsim, dtype=np.int8)
    b1 = np.zeros(nsim, bool); b2 = np.zeros(nsim, bool); b3 = np.zeros(nsim, bool)
    scored = np.zeros(nsim, dtype=np.int16)
    active = np.ones(nsim, bool)
    cum = np.cumsum(M, axis=1)   # 9 x 6
    for _ in range(40):
        idx = np.where(active)[0]
        if idx.size == 0: break
        u = rng.random(idx.size)
        ev = (u[:,None] > cum[batter[idx]]).sum(axis=1)   # 0..5 index in CATS: s1,d2,t3,hr,bb,out
        # per event
        # extra random draws
        u2 = rng.random(idx.size); u3 = rng.random(idx.size)
        B1=b1[idx]; B2=b2[idx]; B3=b3[idx]; O=outs[idx]; sc=np.zeros(idx.size, dtype=np.int16)
        # OUT
        m = ev==5
        sf = m & B3 & (O<2) & (u2 < P_SF_ON_OUT)
        sc += sf; B3 = np.where(sf, False, B3)
        dp = m & B1 & (O<2) & (u3 < P_GIDP)
        O = O + m.astype(np.int8) + dp.astype(np.int8); B1 = np.where(dp, False, B1)
        # BB / HBP (force)
        m = ev==4
        force = m & B1 & B2 & B3; sc += force
        nB3 = np.where(m & B1 & B2, True, B3); nB2 = np.where(m & B1, True, B2); nB1 = np.where(m, True, B1)
        B1,B2,B3 = np.where(m,nB1,B1), np.where(m,nB2,B2), np.where(m,nB3,B3)
        # HR
        m = ev==3
        sc += m*(1 + B1.astype(int)+B2.astype(int)+B3.astype(int))
        B1 = np.where(m, False, B1); B2 = np.where(m, False, B2); B3 = np.where(m, False, B3)
        # 3B
        m = ev==2
        sc += m*(B1.astype(int)+B2.astype(int)+B3.astype(int))
        B1 = np.where(m, False, B1); B2 = np.where(m, False, B2); B3 = np.where(m, True, B3)
        # 2B
        m = ev==1
        sc += m*(B2.astype(int)+B3.astype(int))
        r1s = m & B1 & (u2 < P_R1_SCORE_ON_2B); sc += r1s
        nB3 = m & B1 & ~r1s
        B3 = np.where(m, nB3, B3); B2 = np.where(m, True, B2); B1 = np.where(m, False, B1)
        # 1B
        m = ev==0
        sc += m*B3.astype(int)
        r2s = m & B2 & (u2 < P_R2_SCORE_ON_1B); sc += r2s
        r2to3 = m & B2 & ~r2s
        r1to3 = m & B1 & (u3 < P_R1_TO_3_ON_1B) & ~r2to3
        nB3 = r2to3 | r1to3
        nB2 = m & B1 & ~r1to3
        B3 = np.where(m, nB3, B3); B2 = np.where(m, nB2, B2); B1 = np.where(m, True, B1)
        # misc advance: lead runner moves up one base
        adv = (rng.random(idx.size) < P_ADV) & (B1|B2|B3)
        a3 = adv & B3; sc += a3; B3 = np.where(a3, False, B3)
        a2 = adv & ~a3 & B2; B3 = np.where(a2, True, B3); B2 = np.where(a2, False, B2)
        a1 = adv & ~a3 & ~a2 & B1; B2 = np.where(a1, True, B2); B1 = np.where(a1, False, B1)
        # write back
        b1[idx]=B1; b2[idx]=B2; b3[idx]=B3; outs[idx]=O; scored[idx]+=sc
        batter[idx] = (batter[idx]+1) % 9
        active[idx] = O < 3
    return scored, batter

def hfa(M):
    M = M.copy(); M[:, :5] *= HFA_ONBASE; return M / M.sum(axis=1, keepdims=True)

def sim_game(Ma, Mh, nsim=20000, seed=7):
    """Ma/Mh: 9x6 per-PA matrices for away/home. returns arrays away_runs, home_runs."""
    Mh = hfa(Mh)
    rng = np.random.default_rng(seed)
    ar = np.zeros(nsim, dtype=np.int16); hr = np.zeros(nsim, dtype=np.int16)
    ba = np.zeros(nsim, dtype=np.int64); bh = np.zeros(nsim, dtype=np.int64)
    for inn in range(1, 10):
        s, ba = sim_half(rng, Ma, ba, ar, nsim); ar += s
        if inn < 9:
            s, bh = sim_half(rng, Mh, bh, hr, nsim); hr += s
        else:
            need = ~(hr > ar)         # home bats bottom 9 only if not leading
            s, bh2 = sim_half(rng, Mh, bh.copy(), hr, nsim)
            s = np.minimum(s, ar - hr + 1)   # walk-off truncation (approx)
            hr += np.where(need, s, 0); bh = np.where(need, bh2, bh)
    # extras (ghost runner approx: add ~+0.55 runs expectancy — approximate by playing halves w/ runner on 2nd)
    tied = ar == hr
    for _ in range(6):
        if not tied.any(): break
        idx = np.where(tied)[0]
        # simplistic: each half from a runner-on-2nd start ~ scoring prob ~.62 mean ~1.0 run; sample from a Poisson-ish
        sa = rng.poisson(1.05, idx.size); sh = rng.poisson(1.05, idx.size)
        ar[idx] += sa
        # home stops when it takes the lead: cap home runs at away lead+1
        sh = np.where(sh > sa, sa + 1, sh)
        hr[idx] += sh
        tied = ar == hr
    return ar, hr

def p_ge(arr, k): return float((arr >= k).mean())
