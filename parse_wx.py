import re,json,html
w=open('rw_weather.html').read()
RW={'Tigers':'DET','Pirates':'PIT','Padres':'SD','Mets':'NYM','Braves':'ATL','Twins':'MIN','White Sox':'CWS','Cubs':'CHC',
'Diamondbacks':'AZ','Red Sox':'BOS','Marlins':'MIA','Phillies':'PHI','Yankees':'NYY','Orioles':'BAL','Giants':'SF','Guardians':'CLE',
'Cardinals':'STL','Reds':'CIN','Blue Jays':'TOR','Rays':'TB','Athletics':'ATH',"A's":'ATH','Royals':'KC','Mariners':'SEA','Brewers':'MIL',
'Nationals':'WSH','Rangers':'TEX','Angels':'LAA','Astros':'HOU','Dodgers':'LAD','Rockies':'COL'}
boxes=re.split(r'<div class="weather-box"',w)[1:]
out=[]
for b in boxes:
    b=b[:20000]
    tms=re.findall(r'weather-box__team is-(?:visit|home)".*?<div>([^<]+)</div>',b,re.S)
    when=re.search(r'weather-box__date">([^<]+)<',b)
    txt=re.search(r'weather-box__weather.*?text-80">(.*?)</div>',b,re.S)
    head=re.search(r'heading size-2 mb-5">([^<]+)<',b)
    if not tms or len(tms)<2 or not when: continue
    t=html.unescape(re.sub('<[^>]+>','',txt.group(1))) if txt else ''
    temp=re.search(r'(\d+)&deg;|(\d+)°',txt.group(1)) if txt else None
    temp=int(temp.group(1) or temp.group(2)) if temp else None
    mph=re.search(r'(\d+)\s*MPH',t); mph=int(mph.group(1)) if mph else 0
    d=None
    tl=t.lower()
    if 'blowing out' in tl or 'out to' in tl: d='out'
    elif 'blowing in' in tl or 'in from' in tl: d='in'
    elif 'left to right' in tl or 'right to left' in tl: d='left to right'
    dome = ('roof' in tl and 'closed' in tl) or (head and 'Dome' in head.group(1)) or 'retractable' in tl
    pr=re.search(r'(\d+)% chance',t); pr=int(pr.group(1)) if pr else 0
    wh=re.search(r'at (\d+:\d+ [AP]M)',when.group(1))
    out.append(dict(away=RW.get(tms[0].strip(),tms[0].strip()),home=RW.get(tms[1].strip(),tms[1].strip()),
        when=wh.group(1) if wh else '', temp=temp,mph=mph,dir=d,precip=pr,dome=bool(dome),text=t.strip()[:200],head=head.group(1) if head else ''))
json.dump(out,open('rw_weather.json','w'),indent=1)
for o in out: print(f"{o['away']:>3}@{o['home']:<3} {o['when']:9} {str(o['temp']):>3}F {o['mph']:>2}mph dir={str(o['dir']):13} pr={o['precip']:>2}% dome={o['dome']}  {o['head']}")
