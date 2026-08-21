import json,os,time,urllib.request
DATE='2026-08-21'
KEY=os.environ['ODDS_API_KEY']
def team_abbr_import():
    import sys; sys.path.insert(0,'.')
    from pull_odds import team_abbr; return team_abbr
ta=team_abbr_import()
events=json.load(open(f'odds_out/events_{DATE}.json'))
out={}
rem=None
for ev in events:
    u=(f"https://api.the-odds-api.com/v4/sports/baseball_mlb/events/{ev['id']}/odds"
       f"?apiKey={KEY}&regions=us,us2,eu&markets=totals,alternate_totals&oddsFormat=american")
    for i in range(4):
        try:
            with urllib.request.urlopen(u,timeout=40) as r:
                rem=r.headers.get('x-requests-remaining'); d=json.load(r); break
        except Exception as e: err=e; time.sleep(2+2*i)
    else:
        print("FAIL",ev['id'],err); continue
    key=f"{ta(ev['away_team'])}@{ta(ev['home_team'])}"
    out[key]=d
    n=sum(len(m['outcomes']) for b in d.get('bookmakers',[]) for m in b['markets'])
    print(f"{key:9} books={len(d.get('bookmakers',[])):2} outcomes={n}")
    time.sleep(0.2)
json.dump(out,open('odds_out/alt_totals.json','w'))
print("quota remaining",rem,"matchups",len(out))
