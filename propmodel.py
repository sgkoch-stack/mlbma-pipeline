"""
Prototype TB / HRR probability model (v0.2) — PA-level convolution.
P(TB>=2) and P(H+R+RBI>=line) per hitter per game, compared to market implied prob.
Inputs: statsapi season + vl/vr splits (hitters, SPs), team pitching (pen proxy),
league totals, actual lineup slot (backtest only), SP identity.
NOT yet included: park, weather, umpire, recent form, as-of-date stats (uses stats through 8/16).
"""
import pandas as pd, numpy as np

CATS = ['s1','d2','t3','hr','bb','out']   # BB includes HBP
SLOT_PA = {1:4.507,2:4.406,3:4.309,4:4.199,5:4.053,6:3.901,7:3.778,8:3.599,9:3.457}
K_HIT_SPLIT = 450   # spec's shrink for hitter platoon split
K_HIT_OVR   = 150   # shrink hitter overall toward league
K_PIT_SPLIT = 250
K_PIT_OVR   = 200
K_TEAM_PIT  = 400
TB_OF = {'s1':1,'d2':2,'t3':3,'hr':4,'bb':0,'out':0}

def rates_from(row, pa_key='plateAppearances', bf=False):
    """multinomial per-PA rates dict from a stats row (hitting or pitching)."""
    n = float(row.get('battersFaced' if bf else pa_key, 0) or 0)
    if n <= 0: return None, 0
    h  = float(row.get('hits',0) or 0); d = float(row.get('doubles',0) or 0)
    t  = float(row.get('triples',0) or 0); hr = float(row.get('homeRuns',0) or 0)
    bb = float(row.get('baseOnBalls',0) or 0) + float(row.get('hitByPitch',0) or 0)
    s1 = h - d - t - hr
    r = dict(s1=s1/n, d2=d/n, t3=t/n, hr=hr/n, bb=bb/n)
    r['out'] = max(1 - sum(r.values()), 0.01)
    return r, n

def shrink(r, n, prior, k):
    if r is None: return dict(prior)
    return {c: (n*r[c] + k*prior[c])/(n+k) for c in CATS}

def norm(r):
    s = sum(r.values()); return {c: r[c]/s for c in CATS}

def log5(b, p, lg):
    """multinomial odds-ratio combination of batter rates b, pitcher rates p vs league lg."""
    x = {c: b[c]*p[c]/lg[c] for c in CATS}
    return norm(x)

def pa_dist(mean_pa):
    lo = int(np.floor(mean_pa)); f = mean_pa - lo
    return {lo: 1-f, lo+1: f}

def conv_count(pmf_per_pa, npa, maxv):
    """pmf_per_pa: array over 0..maxv of per-PA count; returns pmf over 0..maxv*npa (truncated)."""
    dist = np.zeros(1); dist[0]=1
    for _ in range(npa):
        dist = np.convolve(dist, pmf_per_pa)
    return dist

def p_at_least(per_pa_pmf, mean_pa, thresh):
    tot=0
    for npa, w in pa_dist(mean_pa).items():
        d = conv_count(per_pa_pmf, npa, len(per_pa_pmf)-1)
        tot += w * d[thresh:].sum() if thresh < len(d) else 0
    return tot

def implied(price):
    price=float(price)
    return 100/(price+100) if price>0 else -price/(-price+100)

class PropModel:
    def __init__(self, hit_stats, pit_stats, team_pitch, league_hit):
        H=hit_stats; P=pit_stats
        # league per-PA rates
        lgrow = league_hit.sum(numeric_only=True)
        self.lg, _ = rates_from(lgrow)
        self.lg_r_pa  = lgrow['runs']/lgrow['plateAppearances']
        self.lg_rbi_pa= lgrow['rbi']/lgrow['plateAppearances']
        self.lg_obp = 1 - self.lg['out']
        # hitters
        self.hit = {}
        for pid, g in H.groupby('player_id'):
            ov = g[g.type=='season']
            if ov.empty: continue
            ov = ov.sort_values('plateAppearances', ascending=False).iloc[0]   # traded players: take the combined (largest) row
            r_ov, n_ov = rates_from(ov)
            r_ov = shrink(r_ov, n_ov, self.lg, K_HIT_OVR)
            rec = dict(name=ov['name'], bats=ov['bats'], pa=n_ov, ovr=r_ov,
                       r_pa = (ov['runs']*1.0/n_ov if n_ov else self.lg_r_pa),
                       rbi_pa=(ov['rbi']*1.0/n_ov if n_ov else self.lg_rbi_pa))
            for sc in ['vl','vr']:
                s = g[(g.type=='statSplits')&(g.split==sc)]
                if s.empty: rec[sc]=r_ov; continue
                r_s, n_s = rates_from(s.iloc[0])
                rec[sc] = shrink(r_s, n_s, r_ov, K_HIT_SPLIT)
            self.hit[int(pid)] = rec
        # pitchers (SP)
        self.pit = {}
        for pid, g in P.groupby('player_id'):
            ov = g[g.type=='season']
            if ov.empty: continue
            ov = ov.sort_values('battersFaced', ascending=False).iloc[0]   # traded players: combined row
            r_ov, n_ov = rates_from(ov, bf=True)
            r_ov = shrink(r_ov, n_ov, self.lg, K_PIT_OVR)
            gs = float(ov.get('gamesStarted',0) or 0); ip = float(ov.get('inningsPitched',0) or 0)
            outs = (int(ip)*3 + round((ip-int(ip))*10)) / gs if gs>0 else 15
            gp = float(ov.get('gamesPlayed',0) or 0)
            if gs < 10 and gp > 2*gs: outs = min(outs, 9)   # opener / swingman: relief IP inflates IP/GS (Tidwell/Bachar trap) -> cap workload
            rec = dict(name=ov['name'], throws=ov['throws'], bf=n_ov, ovr=r_ov, outs=outs)
            for sc in ['vl','vr']:
                s = g[(g.type=='statSplits')&(g.split==sc)]
                if s.empty: rec[sc]=r_ov; continue
                r_s, n_s = rates_from(s.iloc[0], bf=True)
                rec[sc] = shrink(r_s, n_s, r_ov, K_PIT_SPLIT)
            self.pit[int(pid)] = rec
        # team pitching (pen proxy)
        self.team = {}
        for _, t in team_pitch.iterrows():
            r, n = rates_from(t, bf=True)
            self.team[t['team']] = shrink(r, n, self.lg, K_TEAM_PIT)

    def per_pa(self, hitter_id, sp_id, opp_team, bats=None):
        h = self.hit.get(hitter_id)
        if h is None: return None
        sp = self.pit.get(sp_id)
        bats = bats or h['bats'] or 'R'
        pen = self.team.get(opp_team, self.lg)
        if sp is None:
            hand='R'; w_sp=0.55; sp_r=self.lg
        else:
            hand = sp['throws'] or 'R'
            w_sp = float(np.clip(0.081+0.03272*sp['outs'], 0.30, 0.80))
            sp_r = sp['vl'] if bats=='L' or (bats=='S') else sp['vr']
            if bats=='S':  # switch hitter bats opposite the pitcher
                sp_r = sp['vl'] if hand=='R' else sp['vr']
        # hitter split vs SP hand; vs pen assume hand-neutral (overall)
        b_sp = h['vl'] if hand=='L' else h['vr']
        if bats=='S':  # switch: use split vs SP hand anyway (statsapi vl/vr are vs pitcher hand)
            b_sp = h['vl'] if hand=='L' else h['vr']
        p_vs_sp  = log5(b_sp, sp_r, self.lg)
        p_vs_pen = log5(h['ovr'], pen, self.lg)
        blend = {c: w_sp*p_vs_sp[c] + (1-w_sp)*p_vs_pen[c] for c in CATS}
        # opponent run-environment factor for R/RBI (OBP allowed vs league)
        obp_allowed = 1 - (w_sp*sp_r['out'] + (1-w_sp)*pen['out'])
        env = obp_allowed / self.lg_obp
        return blend, env, w_sp

    def p_tb(self, hitter_id, sp_id, opp_team, slot, thresh=2, bats=None):
        r = self.per_pa(hitter_id, sp_id, opp_team, bats)
        if r is None: return None
        blend, env, w = r
        pmf = np.zeros(5)
        for c in CATS: pmf[TB_OF[c]] += blend[c]
        return p_at_least(pmf, SLOT_PA.get(slot,3.9), thresh)

    def p_hrr(self, hitter_id, sp_id, opp_team, slot, line, bats=None):
        """H+R+RBI as a per-PA joint outcome: HR=2+extra RBI; other hit=1+P(score)+P(RBI); BB=P(score); out=P(RBI on out)."""
        r = self.per_pa(hitter_id, sp_id, opp_team, bats)
        if r is None: return None
        blend, env, w = r
        h = self.hit[hitter_id]
        # hitter context factors relative to league (lineup spot / speed / protection baked into own R and RBI rates), shrunk
        n = h['pa']; k = 300
        run_f = ((n*h['r_pa'] + k*self.lg_r_pa)/(n+k)) / self.lg_r_pa
        rbi_f = ((n*h['rbi_pa']+ k*self.lg_rbi_pa)/(n+k)) / self.lg_rbi_pa
        p_score = min(0.30*run_f*env, 0.6)      # runner who reached (non-HR) later scores
        p_rbi_hit = min(0.32*rbi_f*env, 0.8)    # RBI on a non-HR hit
        p_rbi_out = min(0.035*rbi_f*env, 0.2)   # RBI on an out (SF, groundout)
        hr_pmf = np.array([0,0,0.55,0.30,0.15])  # HR = 2 + extra RBI
        def bern(p): return np.array([1-p,p])
        hit_pmf = np.convolve(np.array([0,1.0]), np.convolve(bern(p_score), bern(p_rbi_hit)))
        per = np.zeros(5)
        per[:len(hr_pmf)] += blend['hr']*hr_pmf
        per[:len(hit_pmf)] += (blend['s1']+blend['d2']+blend['t3'])*hit_pmf
        per[:2] += blend['bb']*bern(p_score)
        per[:2] += blend['out']*bern(p_rbi_out)
        thresh = int(np.ceil(line))
        return p_at_least(per, SLOT_PA.get(slot,3.9), thresh)
