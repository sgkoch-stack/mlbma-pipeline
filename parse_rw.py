import re,json,html
h=open('rw_lineups.html').read()
blocks=re.split(r'<div class="lineup is-mlb', h)[1:]
out=[]
for b in blocks:
    b=b[:b.find('<div class="lineup is-mlb')] if '<div class="lineup is-mlb' in b else b
    tm=re.search(r'lineup__time">([^<]+)<',b)
    teams=re.findall(r'lineup__abbr">([A-Z]{2,3})<',b)
    if not tm or len(teams)<2: continue
    # lineup lists
    lists=re.findall(r'<ul class="lineup__list is-(visit|home)([^"]*)">(.*?)</ul>',b,re.S)
    d=dict(time=tm.group(1).replace(' ET','').strip(), teams=teams[:2])
    ok=True
    for side_key,(sd,cls,body) in zip(('away','home'),lists[:2]):
        status='is-confirmed' if 'is-confirmed' in cls else ('is-confirmed' if 'lineup__status is-confirmed' in body else 'expected')
        st2=re.search(r'lineup__status[^"]*"',body)
        players=[]
        for li in re.findall(r'<li class="lineup__player[^"]*">(.*?)</li>',body,re.S):
            nm=re.search(r'title="([^"]+)"',li); pos=re.search(r'lineup__pos">([^<]*)<',li); bats=re.search(r'lineup__bats[^>]*>([LRS])<',li)
            if nm: players.append(dict(name=html.unescape(nm.group(1)).strip(),pos=pos.group(1).strip() if pos else '',bats=bats.group(1) if bats else ''))
        conf = 'is-confirmed' in (st2.group(0) if st2 else '')
        d[side_key]=dict(status='is-confirmed' if conf else 'expected', players=players[:9])
    if 'away' not in d or 'home' not in d: continue
    # SPs
    sps=re.findall(r'lineup__player-highlight-name[^>]*>\s*<a[^>]*>([^<]+)</a>\s*<span[^>]*>([LRS])</span>',b)
    d['sps']=[(html.unescape(a).strip(),t) for a,t in sps[:2]]
    out.append(d)
json.dump(out,open('rw_lineups.json','w'),indent=1)
for d in out:
    print(f"{d['time']:9} {d['teams'][0]:>3}@{d['teams'][1]:<3} away {d['away']['status']:12} n={len(d['away']['players'])}  home {d['home']['status']:12} n={len(d['home']['players'])}  SP {d.get('sps')}")
