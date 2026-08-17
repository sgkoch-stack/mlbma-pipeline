import json,sys,os,time,urllib.request,csv,statistics
import pandas as pd, numpy as np
sys.path.insert(0,'.')
from propmodel import PropModel, CATS
import ttmodel
from pricing import am_to_prob
DATE=os.environ.get('MLBMA_DATE')
def get(u,tries=6):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'mlbma/1.0'}),timeout=40) as r: return json.load(r)
        except Exception as e: time.sleep(2+3*i)
    raise SystemExit(u)
splits=json.load(open('splits.json')); pit=json.load(open('sp_stats.json')); games=json.load(open('games.json')); lineups=json.load(open('lineups.json'))
HK=['plateAppearances','hits','doubles','triples','homeRuns','baseOnBalls','hitByPitch','runs','rbi']
PK=['battersFaced','hits','doubles','triples','homeRuns','baseOnBalls','hitByPitch','gamesStarted','gamesPlayed','inningsPitched']
hrows=[]
for pid,r in splits.items():
    for typ,key in (('season','season'),('statSplits','vl'),('statSplits','vr')):
        if key in r:
            d={k:r[key].get(k,0) or 0 for k in HK}; d.update(player_id=int(pid),name=r['name'],bats=r['bats'],type=typ,split=key if typ=='statSplits' else '')
            hrows.append(d)
prows=[]
for pid,r in pit.items():
    for typ,key in (('season','season'),('statSplits','vl'),('statSplits','vr')):
        if key in r:
            d={k:(float(r[key].get(k)) if r[key].get(k) not in (None,'') else 0) for k in PK}; d.update(player_id=int(pid),name=r['name'],throws=r['throws'],type=typ,split=key if typ=='statSplits' else '')
            prows.append(d)
H=pd.DataFrame(hrows); P=pd.DataFrame(prows)
# team pitching + league hitting
tp=get("https://statsapi.mlb.com/api/v1/teams/stats?sportId=1&stats=season&group=pitching&season=2026")['stats'][0]['splits']
tprows=[]
for s in tp:
    st=s['stat']; d={k:float(st.get(k,0) or 0) for k in ['battersFaced','hits','doubles','triples','homeRuns','baseOnBalls','hitByPitch']}; d['team']=s['team']['abbreviation'] if 'abbreviation' in s['team'] else None; d['team_id']=s['team']['id']; tprows.append(d)
tm=get("https://statsapi.mlb.com/api/v1/teams?sportId=1")['teams']; ab={t['id']:t['abbreviation'] for t in tm}
for d in tprows: d['team']=ab[d['team_id']]
TP=pd.DataFrame(tprows)
th=get("https://statsapi.mlb.com/api/v1/teams/stats?sportId=1&stats=season&group=hitting&season=2026")['stats'][0]['splits']
LH=pd.DataFrame([{k:float(s['stat'].get(k,0) or 0) for k in HK} for s in th])
model=PropModel(H,P,TP,LH)
print('model built: hitters',len(model.hit),'pitchers',len(model.pit),'teams',len(model.team),'lg r/pa',round(model.lg_r_pa,4))
# ---- odds quotes
raw=json.load(open(f'odds_out/raw_props_{DATE}.json')); events=json.load(open(f'odds_out/events_{DATE}.json'))
from pull_odds import team_abbr
ACT={'draftkings','fanduel','williamhill_us','betmgm','betrivers','fanatics'}
import unicodedata,re
def norm(s):
    s=unicodedata.normalize('NFKD',s).encode('ascii','ignore').decode().lower()
    s=re.sub(r'\b(jr|sr|ii|iii|iv)\.?$','',s.strip()).replace('.','').replace("'",'').strip(); return re.sub(r'\s+',' ',s)
def eid_for(g):
    a=('CHW' if g['away']=='CWS' else g['away']); h=('CHW' if g['home']=='CWS' else g['home'])
    c=sorted([e for e in events if team_abbr(e['away_team'])==a and team_abbr(e['home_team'])==h],key=lambda e:e['commence_time'])
    return c[g['gn']-1]['id'] if g.get('dh') in ('S','Y') else c[0]['id']
def quotes(eid,mkt):
    out={}
    for bk in raw[eid]['bookmakers']:
        for m in bk['markets']:
            if m['key']!=mkt: continue
            for o in m['outcomes']:
                if o['name']=='Over': out.setdefault((norm(o.get('description','')),o.get('point')),[]).append((bk['key'],o['price']))
    return out
def mkt_prob(rows):
    act=[am_to_prob(p) for b,p in rows if b in ACT]
    if len(act)<1: return None,0,None,None
    best=max([(p,b) for b,p in rows if b in ACT],key=lambda t:-am_to_prob(t[0]))
    return statistics.median(act)-0.02,len(act),best[0],best[1]
prop=[]; ttrows=[]
for g in games:
    gp=str(g['game_pk']); eid=eid_for(g)
    qtb=quotes(eid,'batter_total_bases'); qtba=quotes(eid,'batter_total_bases_alternate'); qh=quotes(eid,'batter_hits_runs_rbis'); qtt=quotes(eid,'team_totals')
    for side in ('away','home'):
        team=g[side]; opp=g['home' if side=='away' else 'away']; sp_id=g[('home' if side=='away' else 'away')+'_sp_id']
        lu=lineups[gp][side]
        for p in lu['players']:
            pid=p['id']; nm=norm(p['name']); bats=(splits.get(str(pid)) or {}).get('bats')
            # TB 1.5
            rows=qtb.get((nm,1.5),[])+qtba.get((nm,1.5),[])
            if rows:
                pm=model.p_tb(pid,sp_id,opp,p['slot'],2,bats)
                mk,nb,bp,bk=mkt_prob(rows)
                if pm is not None and mk is not None: prop.append(dict(market='TB',name=p['name'],team=team,opp=opp,slot=p['slot'],src=lu['src'],line=1.5,p_model=round(pm,4),p_mkt=mk,edge=pm-mk,best_price=bp,book=bk,nbooks=nb,date=DATE,player_id=pid,game_pk=gp))
            # HRR: modal line
            hl=[(pt,rows) for (n2,pt),rows in qh.items() if n2==nm]
            if hl:
                pt,rows=max(hl,key=lambda t:len(t[1]))
                pm=model.p_hrr(pid,sp_id,opp,p['slot'],pt,bats); mk,nb,bp,bk=mkt_prob(rows)
                if pm is not None and mk is not None: prop.append(dict(market='HRR',name=p['name'],team=team,opp=opp,slot=p['slot'],src=lu['src'],line=pt,p_model=round(pm,4),p_mkt=mk,edge=pm-mk,best_price=bp,book=bk,nbooks=nb,date=DATE,player_id=pid,game_pk=gp))
    # TT sim
    ev=[e for e in events if e['id']==eid][0]
    def lu_list(side):
        return [(p['id'],(splits.get(str(p['id'])) or {}).get('bats')) for p in lineups[gp][side]['players']]
    Ma,wa=ttmodel.per_pa_matrix(model,lu_list('away'),g['home_sp_id'],g['home'])
    Mh,wh=ttmodel.per_pa_matrix(model,lu_list('home'),g['away_sp_id'],g['away'])
    ar,hr=ttmodel.sim_game(Ma,Mh,nsim=20000)
    for side,arr,team in (('away',ar,g['away']),('home',hr,g['home'])):
        tname=ev['away_team'] if side=='away' else ev['home_team']
        # gather both O/U per point across books
        pts={}
        for bk in raw[eid]['bookmakers']:
            for m in bk['markets']:
                if m['key']!='team_totals': continue
                for o in m['outcomes']:
                    if o.get('description')==tname: pts.setdefault(o['point'],{}).setdefault(o['name'],[]).append((bk['key'],o['price']))
        for pt,d in sorted(pts.items()):
            ov=[am_to_prob(p) for b,p in d.get('Over',[]) if b in ACT]; un=[am_to_prob(p) for b,p in d.get('Under',[]) if b in ACT]
            if not ov or not un: continue
            po,pu=statistics.median(ov),statistics.median(un); nv=po/(po+pu)
            pmo=ttmodel.p_ge(arr,int(np.ceil(pt)))
            for sd,pm,pmk,rows in (('Over',pmo,nv,d.get('Over',[])),('Under',1-pmo,1-nv,d.get('Under',[]))):
                act=[(p,b) for b,p in rows if b in ACT]; best=max(act,key=lambda t:-am_to_prob(t[0])) if act else (None,None)
                ttrows.append(dict(date=DATE,game=f"{g['away']}@{g['home']}"+(f" G{g['gn']}" if g.get('dh') in ('S','Y') else ''),team=team,line=pt,side=sd,p_model=round(pm,3),p_mkt=round(pmk,3),edge=round(pm-pmk,3),price=best[0],book=best[1],nb=len(act),mean=round(float(arr.mean()),2),lineup=('CONF (statsapi)' if lineups[gp][side]['src']=='statsapi' else lineups[gp][side]['src']),game_pk=gp))
    print(g['away'],'@',g['home'],'sim mean',round(float(ar.mean()),2),round(float(hr.mean()),2),'total',round(float((ar+hr).mean()),2),'P(home)',round(float((hr>ar).mean()),3))
pdf=pd.DataFrame(prop); tdf=pd.DataFrame(ttrows)
# board rules (S 8/16 v0.1, Claude-set, unratified)
pdf['on_board']=False
for mk,th in (('TB',.04),('HRR',.10)):
    sel=pdf[(pdf.market==mk)&(pdf.edge>=th)&(pdf.nbooks>=2)].sort_values('edge',ascending=False).head(8)
    pdf.loc[sel.index,'on_board']=True
tdf['on_board']=False
best=tdf[(tdf.edge>=.03)&(tdf.nb>=3)&(tdf.price.notna())&(tdf.price>=-180)&(tdf.price<=150)].sort_values('edge',ascending=False).drop_duplicates('team').head(8)
tdf.loc[best.index,'on_board']=True
os.makedirs('propboards',exist_ok=True); os.makedirs('ttboards',exist_ok=True)
pdf.to_csv(f'propboards/{DATE}.csv',index=False); tdf.to_csv(f'ttboards/{DATE}.csv',index=False)
print('prop rows',len(pdf),'TB',(pdf.market=='TB').sum(),'HRR',(pdf.market=='HRR').sum(),'| tt rows',len(tdf))
