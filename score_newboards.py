"""Score propboards/DATE.csv (TB / HRR) and ttboards/DATE.csv from statsapi boxscores.
Writes propboards/DATE_scored.csv and ttboards/DATE_scored.csv. Serial fetch + backoff."""
import csv,json,sys,time,unicodedata,urllib.request,os,base64
date=sys.argv[1]
def get(url,tries=6):
    for i in range(tries):
        try:
            with urllib.request.urlopen(url,timeout=30) as r: return json.load(r)
        except Exception as e:
            time.sleep(2+3*i)
    raise SystemExit("fetch failed "+url)
def norm(s):
    s=unicodedata.normalize('NFKD',s).encode('ascii','ignore').decode().lower()
    for suf in [' jr.',' jr',' sr.',' ii',' iii']:
        if s.endswith(suf): s=s[:-len(suf)]
    return s.replace('.','').strip()
sched=get(f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={date}&hydrate=linescore,team")
games=[g for d in sched['dates'] for g in d['games']]
team_runs={}; team_final={}; box={}
for g in games:
    pk=g['gamePk']; st=g['status']['abstractGameState']; det=g['status'].get('detailedState','')
    a=g['teams']['away']['team']['abbreviation']; h=g['teams']['home']['team']['abbreviation']
    ls=g.get('linescore',{}).get('teams',{})
    for side,ab in (('away',a),('home',h)):
        team_runs[ab]=ls.get(side,{}).get('runs'); team_final[ab]=(st=='Final')
    b=get(f"https://statsapi.mlb.com/api/v1/game/{pk}/boxscore")
    for side in ('away','home'):
        ab=b['teams'][side]['team']['abbreviation']
        for pid,p in b['teams'][side]['players'].items():
            bs=p.get('stats',{}).get('batting',{})
            if not bs: continue
            box.setdefault(ab,{})[norm(p['person']['fullName'])]=dict(pid=p['person']['id'],
                tb=bs.get('totalBases', bs.get('hits',0)+bs.get('doubles',0)+2*bs.get('triples',0)+3*bs.get('homeRuns',0)),
                h=bs.get('hits',0),r=bs.get('runs',0),rbi=bs.get('rbi',0),pa=bs.get('plateAppearances',0),final=(st=='Final'))
    time.sleep(0.4)
# alias statsapi abbrevs to board abbrevs
alias={'ARI':'AZ','CHW':'CWS','WSN':'WSH','KCR':'KC','SDP':'SD','SFG':'SF','TBR':'TB'}
def units(res,price):
    price=float(price)
    if res=='W': return round(price/100,4) if price>0 else round(100/-price,4)
    if res=='L': return -1.0
    return 0.0
# ---- propboard
pp=f"propboards/{date}.csv"
if os.path.exists(pp):
    rows=list(csv.DictReader(open(pp))); out=[]
    for r in rows:
        tm=alias.get(r['team'],r['team']); pl=box.get(tm,{}).get(norm(r['name']))
        line=float(r['line'])
        if pl is None or pl['pa']==0: act='';res='V'
        else:
            act=pl['tb'] if r['market']=='TB' else pl['h']+pl['r']+pl['rbi']
            res='W' if act>line else 'L'
        r.update(actual=act,settle=res,units=units(res,r['best_price'])); out.append(r)
    w=csv.DictWriter(open(f"propboards/{date}_scored.csv",'w',newline=''),fieldnames=list(out[0].keys())); w.writeheader(); w.writerows(out)
    for r in out: print('PROP',r['market'],r['name'],r['line'],r['best_price'],'->',r['actual'],r['settle'],r['units'])
# ---- ttboard
tp=f"ttboards/{date}.csv"
if os.path.exists(tp):
    rows=list(csv.DictReader(open(tp))); out=[]
    for r in rows:
        tm=r['team']; runs=team_runs.get(tm); fin=team_final.get(tm)
        line=float(r['line'])
        if runs is None or not fin: act='';res='V'
        else:
            act=runs
            if r['side']=='Over': res='W' if runs>line else ('P' if runs==line else 'L')
            else: res='W' if runs<line else ('P' if runs==line else 'L')
        r.update(actual=act,settle=res,units=units(res,r['price'])); out.append(r)
    w=csv.DictWriter(open(f"ttboards/{date}_scored.csv",'w',newline=''),fieldnames=list(out[0].keys())); w.writeheader(); w.writerows(out)
    print("TT scored",len(out))
