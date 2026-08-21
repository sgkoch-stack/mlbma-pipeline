import json,re,unicodedata,time,urllib.request,urllib.parse,sys
DATE='2026-08-21'
def get(u,tries=6):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'mlbma/1.0'}),timeout=40) as r: return json.load(r)
        except Exception as e: err=e; time.sleep(2+3*i)
    raise SystemExit(f"fail {u} {err}")
def norm(s):
    s=unicodedata.normalize('NFKD',s).encode('ascii','ignore').decode().lower()
    s=re.sub(r'\b(jr|sr|ii|iii|iv)\.?$','',s.strip()).replace('.','').replace("'",'').strip()
    return re.sub(r'\s+',' ',s)
RW2SA={'ARI':'AZ','CHW':'CWS','WAS':'WSH','OAK':'ATH'}
sched=json.load(open('sched_raw.json')); rw=json.load(open('rw_lineups.json')); wx=json.load(open('rw_weather.json'))
teams=sorted({g['away'] for g in sched}|{g['home'] for g in sched})
# team ids
tm=get("https://statsapi.mlb.com/api/v1/teams?sportId=1")['teams']
tid={t['abbreviation']:t['id'] for t in tm}
roster={}
for t in teams:
    r=get(f"https://statsapi.mlb.com/api/v1/teams/{tid[t]}/roster?rosterType=40Man")
    roster[t]={norm(p['person']['fullName']):p['person']['id'] for p in r['roster']}
    time.sleep(0.3)
# override BOS SP + workbook opener rule
SP_OVERRIDE_BY_MATCH={  # 'AWAY@HOME' -> list of (side, name, mlbam_id)
 'TOR@NYY':[('away','Spencer Arrighetti',681293)],  # OPENER: Mason Fluharty opens (props page line 0 K / proj 1.2, "Short start"); workbook PROBABLES + rotowire agree Arrighetti is the bulk arm
 'STL@PHI':[('away','Hunter Dobbins',690928)],      # statsapi posted NO probable; workbook PROBABLES + rotowire agree Dobbins (R); Model A says TBD (R) - hand matches
 'MIN@SD':[('home','Randy Vasquez',681190)],        # statsapi silent; workbook + rotowire say Musgrove but the PROP MARKET has Vasquez K/BB/ER lines and Model A + props page name Vasquez - market tiebreaker wins
}
SP_OVERRIDE={}
games=[];lineups={};sp_ids=set()
def rw_block(g):
    # match by teams + time (DH)
    hh=int(g['time'][11:13]); 
    for b in rw:
        a=RW2SA.get(b['teams'][0],b['teams'][0]); h=RW2SA.get(b['teams'][1],b['teams'][1])
        if a==g['away'] and h==g['home']:
            t=b['time']; m=re.match(r'(\d+):(\d+) (AM|PM)',t); hr=int(m.group(1))%12+(12 if m.group(3)=='PM' else 0)
            if (hr+4)%24==hh: return b
    return None
def wx_block(g):
    hh=int(g['time'][11:13])
    for b in wx:
        a=RW2SA.get(b['away'],b['away']); h=RW2SA.get(b['home'],b['home'])
        if a==g['away'] and h==g['home']:
            m=re.search(r'(\d+):(\d+) (AM|PM)',b['when']); hr=int(m.group(1))%12+(12 if m.group(3)=='PM' else 0)
            if (hr+4)%24==hh: return b
    return None
weather={}
for g in sched:
    gp=str(g['game_pk']); b=rw_block(g); w=wx_block(g)
    assert b and w, (g['away'],g['home'],g['time'])
    mk=f"{g['away']}@{g['home']}"
    if mk in SP_OVERRIDE_BY_MATCH:
        for side,nm,pid in SP_OVERRIDE_BY_MATCH[mk]: g[side+'_sp']=nm; g[side+'_sp_id']=pid
    games.append(dict(game_pk=g['game_pk'],time=g['time'],away=g['away'],home=g['home'],venue=g['venue'],away_sp=g['away_sp'],away_sp_id=g['away_sp_id'],home_sp=g['home_sp'],home_sp_id=g['home_sp_id'],dh=g['dh'],gn=g['gn']))
    sp_ids.update([g['away_sp_id'],g['home_sp_id']])
    lineups[gp]={}
    for side in ('away','home'):
        team=g[side]; sa=g[side+'_lu']
        if len(sa)==9:
            pl=[dict(id=i,name=n,slot=k+1) for k,(i,n) in enumerate(sa)]; src='statsapi'
        else:
            pl=[]
            for k,p in enumerate(b[side]['players']):
                pid=roster[team].get(norm(p['name']))
                if pid is None:
                    # fuzzy: last name + first initial
                    ln=norm(p['name']).split()[-1]; fi=norm(p['name'])[0]
                    c=[v for kk,v in roster[team].items() if kk.split()[-1]==ln and kk[0]==fi]
                    if len(c)==1: pid=c[0]
                    else:
                        s=get("https://statsapi.mlb.com/api/v1/people/search?names="+urllib.parse.quote(p['name'])+"&sportIds=1&hydrate=currentTeam")
                        cand=[x for x in s['people'] if x.get('currentTeam',{}).get('id')==tid[team]] or s['people']
                        pid=cand[0]['id'] if cand else None
                        print('SEARCH',team,p['name'],'->',pid,[x['fullName'] for x in cand[:3]])
                pl.append(dict(id=pid,name=p['name'],slot=k+1,bats_rw=p['bats'],pos=p['pos']))
            src='Confirmed Lineup' if b[side]['status']=='is-confirmed' else 'Expected Lineup'
        lineups[gp][side]=dict(src=src,players=pl)
        miss=[p['name'] for p in pl if p['id'] is None]
        if miss: print('UNRESOLVED',team,miss)
    d=w['dir'] or ''
    wdir='OUT' if d.startswith('out') else ('IN' if d.startswith('in') else ('X' if ('left' in d or 'right' in d) else None))
    weather[gp]=dict(temp=w['temp'] if w['temp'] is not None else 72,mph=w['mph'] or 0,dir=wdir,precip=w['precip'],dome=w['dome'],text=w['text'])
json.dump(games,open('games.json','w'),indent=1); json.dump(lineups,open('lineups.json','w'),indent=1); json.dump(weather,open('weather.json','w'),indent=1)
# hitter ids
hids=sorted({p['id'] for g in lineups.values() for s in g.values() for p in s['players'] if p['id']})
print('hitters',len(hids),'sps',sp_ids)
# splits: hydrate stats season + statSplits vl/vr hitting
splits={}
for i in range(0,len(hids),40):
    chunk=hids[i:i+40]
    d=get("https://statsapi.mlb.com/api/v1/people?personIds="+','.join(map(str,chunk))+"&hydrate=stats(group=[hitting],type=[season,statSplits],sitCodes=[vl,vr],season=2026)")
    for p in d['people']:
        rec=dict(name=p['fullName'],bats=p.get('batSide',{}).get('code'))
        for st in p.get('stats',[]):
            typ=st['type']['displayName']
            for sp in st.get('splits',[]):
                s=sp['stat']
                row=dict(PA=s.get('plateAppearances',0),OPS=float(s.get('ops',0) or 0),AB=s.get('atBats'),H=s.get('hits'),
                         **{k:s.get(k) for k in ('doubles','triples','homeRuns','baseOnBalls','hitByPitch','runs','rbi','plateAppearances','hits')})
                if typ=='season':
                    if sp.get('team') is None or 'season' not in rec or row['PA']>rec['season']['PA']: rec['season']=row  # combined/largest
                elif typ=='statSplits':
                    code=sp['split']['code']
                    if code in ('vl','vr'):
                        if sp.get('team') is None or code not in rec or row['PA']>rec[code]['PA']: rec[code]=row
        splits[str(p['id'])]=rec
    time.sleep(0.5)
json.dump(splits,open('splits.json','w'),indent=1)
# sp hands + pitching stats
sph={}
d=get("https://statsapi.mlb.com/api/v1/people?personIds="+','.join(map(str,sorted(sp_ids)))+"&hydrate=stats(group=[pitching],type=[season,statSplits],sitCodes=[vl,vr],season=2026)")
pit={}
for p in d['people']:
    sph[str(p['id'])]=[p['fullName'],p.get('pitchHand',{}).get('code','R')]
    rec=dict(name=p['fullName'],throws=p.get('pitchHand',{}).get('code','R'))
    for st in p.get('stats',[]):
        typ=st['type']['displayName']
        for sp in st.get('splits',[]):
            s=sp['stat']; row={k:s.get(k) for k in ('battersFaced','hits','doubles','triples','homeRuns','baseOnBalls','hitByPitch','gamesStarted','gamesPlayed','inningsPitched')}
            if typ=='season':
                if sp.get('team') is None or 'season' not in rec or (row['battersFaced'] or 0)>(rec['season']['battersFaced'] or 0): rec['season']=row
            elif typ=='statSplits' and sp['split']['code'] in ('vl','vr'):
                code=sp['split']['code']
                if sp.get('team') is None or code not in rec: rec[code]=row
    pit[str(p['id'])]=rec
json.dump(sph,open('sp_hands.json','w'),indent=1); json.dump(pit,open('sp_stats.json','w'),indent=1)
print({v[0]:v[1] for v in sph.values()})
print('missing splits',[h for h in hids if str(h) not in splits or 'season' not in splits[str(h)]])
