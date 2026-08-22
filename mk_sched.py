import json,time,urllib.request,collections
DATE='2026-08-22'
def get(u,tries=6):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'mlbma/1.0'}),timeout=40) as r: return json.load(r)
        except Exception as e: err=e; time.sleep(2+3*i)
    raise SystemExit(f"fail {u} {err}")
sch=get(f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={DATE}&hydrate=probablePitcher,lineups,team,venue")
out=[]
for d in sch['dates']:
    for g in d['games']:
        a=g['teams']['away']['team']['abbreviation']; h=g['teams']['home']['team']['abbreviation']
        pa=g['teams']['away'].get('probablePitcher') or {}; ph=g['teams']['home'].get('probablePitcher') or {}
        lu=g.get('lineups',{}) or {}
        def blk(k):
            return [(p['id'],p['fullName']) for p in lu.get(k,[])] if lu.get(k) else []
        out.append(dict(game_pk=g['gamePk'],time=g['gameDate'],away=a,home=h,venue=g['venue']['name'],
            away_sp=pa.get('fullName'),away_sp_id=pa.get('id'),home_sp=ph.get('fullName'),home_sp_id=ph.get('id'),
            dh=bool(g.get('doubleHeader','N')!='N'),gn=g.get('gameNumber',1),
            away_lu=blk('awayPlayers'),home_lu=blk('homePlayers'),status=g['status']['detailedState']))
cnt=collections.Counter((o['away'],o['home']) for o in out)
json.dump(out,open('sched_raw.json','w'),indent=1)
print(len(out),"games")
for o in out:
    print(f"{o['time'][11:16]}Z {o['away']:>3}@{o['home']:<3} {o['venue'][:22]:22} SP {str(o['away_sp'])[:20]:20}({o['away_sp_id']}) / {str(o['home_sp'])[:20]:20}({o['home_sp_id']}) lu {len(o['away_lu'])}/{len(o['home_lu'])} {o['status']} DH={o['dh']}#{o['gn']}")
