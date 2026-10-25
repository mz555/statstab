#!/usr/bin/env python3
from __future__ import annotations

import difflib, hashlib, html, json, os, re, time, unicodedata
import urllib.parse, urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

BSKY = os.getenv('BSKY_HANDLE', 'mzloteanu.bsky.social')
MASTO = os.getenv('MASTODON_ACTOR', 'https://mastodon.social/users/mzloteanu')
START = datetime.fromisoformat(os.getenv('STATSTAB_START_DATE', '2024-01-01')).replace(tzinfo=timezone.utc)
XFILE = Path(os.getenv('X_STATSTABS_FILE', 'data/x_statstabs.json'))
OUT = Path(os.getenv('STATSTAB_OUTPUT', 'data/statstabs.json'))
UA = 'statstab-archive/3.0 (+https://github.com/mz555/statstab)'
TAG = re.compile(r'(?<!\w)#([\w-]+)', re.U)
STAT = re.compile(r'(?i)(?<!\w)#statstab\b')
NUM = re.compile(r'(?is)#statstab\b.{0,60}?#(\d{1,4})\b')
URL = re.compile(r'https?://[^\s<>()]+')
SOCIAL = {'x.com','twitter.com','bsky.app','mastodon.social'}

def dt(s): return datetime.fromisoformat(s.replace('Z','+00:00'))
def iso(d): return d.astimezone(timezone.utc).isoformat().replace('+00:00','Z')

def get(url, accept='application/json'):
    req = urllib.request.Request(url, headers={'User-Agent':UA,'Accept':accept})
    with urllib.request.urlopen(req, timeout=35) as r: return json.load(r)

def uniq(xs, key=lambda x:x):
    out=[]; seen=set()
    for x in xs:
        k=key(x)
        if x and k not in seen: seen.add(k); out.append(x)
    return out

def clean_url(u):
    u=html.unescape((u or '').strip()).rstrip('.,;:!?)]}')
    if not u: return ''
    try:
        p=urllib.parse.urlsplit(u); host=p.netloc.lower().removeprefix('www.')
        qs=[(k,v) for k,v in urllib.parse.parse_qsl(p.query,keep_blank_values=True)
            if not k.lower().startswith('utm_') and k.lower() not in {'ref','source'}]
        return urllib.parse.urlunsplit((p.scheme.lower() or 'https',host,p.path.rstrip('/') or '/',urllib.parse.urlencode(qs),''))
    except Exception: return u

def social(u):
    try: return urllib.parse.urlsplit(u).netloc.lower().removeprefix('www.') in SOCIAL
    except Exception: return False

def number(text):
    m=NUM.search(text or ''); return int(m.group(1)) if m else None

def tags(text):
    return uniq([t for t in TAG.findall(text or '') if t.casefold()!='statstab' and not t.isdigit()], key=str.casefold)

def norm(text):
    text=unicodedata.normalize('NFKC',text or '').lower(); text=STAT.sub(' ',text)
    text=URL.sub(' ',text); text=TAG.sub(' ',text); text=re.sub(r'[^a-z0-9\s]',' ',text)
    return re.sub(r'\s+',' ',text).strip()

def title_body(text):
    s=STAT.sub('',text or '',count=1).strip(); m=re.search(r'#\d{1,4}\b',s[:80])
    if m: s=s[m.end():].strip()
    p=re.split(r'(?i)\bThoughts\s*:\s*',s,maxsplit=1)
    title=re.sub(r'\s+',' ',p[0]).strip(); body=p[1].strip() if len(p)==2 else ''
    body=URL.sub('',body); body=TAG.sub('',body); body=re.sub(r'\s+',' ',body).strip(' -–—')
    return title,body

def record(source,sid,url,created,text,links=(),extra_tags=()):
    ti,bo=title_body(text)
    return {'source':source,'source_id':str(sid),'url':url,'created_at':created,'number':number(text),
            'title':ti,'body':bo,'text':text,'tags':uniq(list(extra_tags)+tags(text),key=str.casefold),
            'external_links':uniq([clean_url(u) for u in links if u and not social(u)],key=str.casefold)}

class HTML(HTMLParser):
    def __init__(self): super().__init__(convert_charrefs=True); self.parts=[]; self.links=[]
    def handle_starttag(self,tag,attrs):
        if tag in {'p','br','div'}: self.parts.append('\n')
        if tag=='a':
            u=dict(attrs).get('href')
            if u: self.links.append(u)
    def handle_data(self,data): self.parts.append(data)
    def result(self): return re.sub(r'\n{3,}','\n\n',''.join(self.parts)).strip(),self.links

def load_x():
    if not XFILE.exists(): return []
    rows=json.loads(XFILE.read_text(encoding='utf-8')).get('posts',[]); out=[]
    for r in rows:
        if STAT.search(r.get('text','')):
            out.append(record('x',r.get('source_id') or r.get('id'),r.get('url',''),r['created_at'],r['text'],r.get('external_links',()),r.get('tags',())))
    return out

def bluesky():
    api='https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed'; cursor=None; out=[]
    while True:
        q={'actor':BSKY,'limit':100,'filter':'posts_no_replies','includePins':'false'}
        if cursor: q['cursor']=cursor
        data=get(api+'?'+urllib.parse.urlencode(q)); feed=data.get('feed',[])
        if not feed: break
        oldest=None
        for e in feed:
            if e.get('reason'): continue
            p=e.get('post',{}); a=p.get('author',{}); r=p.get('record',{}); text=r.get('text','')
            created=r.get('createdAt') or p.get('indexedAt')
            if created: oldest=min(oldest,dt(created)) if oldest else dt(created)
            if not created or a.get('handle','').casefold()!=BSKY.casefold() or not STAT.search(text): continue
            links=[]
            for f in r.get('facets',[]) or []:
                for x in f.get('features',[]) or []:
                    if x.get('$type')=='app.bsky.richtext.facet#link' and x.get('uri'): links.append(x['uri'])
            emb=p.get('embed') or {}; ext=emb.get('external') or {}
            if ext.get('uri'): links.append(ext['uri'])
            links += URL.findall(text)
            uri=p.get('uri',''); key=uri.rsplit('/',1)[-1]
            out.append(record('bluesky',uri or key,f'https://bsky.app/profile/{BSKY}/post/{key}',created,text,links))
        cursor=data.get('cursor')
        if not cursor or (oldest and oldest<START): break
        time.sleep(.1)
    return out

def mastodon():
    accept='application/activity+json, application/ld+json; profile="https://www.w3.org/ns/activitystreams"'
    actor=get(MASTO,accept); first=get(actor['outbox'],accept).get('first'); out=[]
    page=first if isinstance(first,dict) and first.get('orderedItems') else None
    nxt=None if page else (first.get('id') if isinstance(first,dict) else first)
    while page is not None or nxt:
        if page is None: page=get(nxt,accept)
        oldest=None
        for a in page.get('orderedItems',[]) or []:
            if a.get('type')!='Create' or not isinstance(a.get('object'),dict): continue
            o=a['object']; created=o.get('published') or a.get('published')
            if created: oldest=min(oldest,dt(created)) if oldest else dt(created)
            h=HTML(); h.feed(o.get('content','')); text,links=h.result()
            if not created or not STAT.search(text): continue
            xt=[(t.get('name') or '').lstrip('#') for t in o.get('tag',[]) or [] if isinstance(t,dict) and t.get('type')=='Hashtag']
            u=o.get('url') or o.get('id','')
            if isinstance(u,list): u=next((x.get('href') for x in u if isinstance(x,dict) and x.get('href')),o.get('id',''))
            out.append(record('mastodon',o.get('id') or u,u,created,text,links+URL.findall(text),xt))
        n=page.get('next'); nxt=n.get('id') if isinstance(n,dict) else n; page=None
        if not nxt or (oldest and oldest<START): break
        time.sleep(.1)
    return out

def sim(a,b): return difflib.SequenceMatcher(None,norm(a),norm(b)).ratio()
def overlap(a,b): return bool({clean_url(x) for x in a['external_links']} & {clean_url(x) for x in b['external_links']})
def match(a,b):
    if a['source']==b['source']: return False
    days=abs((dt(a['created_at'])-dt(b['created_at'])).total_seconds())/86400
    if days>30: return False
    ts=sim(a['title'],b['title']); same=a['number'] is not None and a['number']==b['number']
    if overlap(a,b) and (days<=21 or ts>=.58): return True
    if days<=14 and (ts>=.84 or sim(a['text'],b['text'])>=.80): return True
    if same and days<=7 and ts>=.52: return True
    ta={x.casefold() for x in a['tags']}; tb={x.casefold() for x in b['tags']}; j=len(ta&tb)/len(ta|tb) if ta|tb else 0
    return same and days<=3 and j>=.35

def clusters(rows):
    cs=[]
    for r in sorted(rows,key=lambda x:dt(x['created_at'])):
        hits=[i for i,c in enumerate(cs) if any(match(r,o) for o in c)]
        if not hits: cs.append([r]); continue
        cs[hits[0]].append(r)
        for i in reversed(hits[1:]): cs[hits[0]].extend(cs.pop(i))
    return cs

def canon(c):
    c=sorted(c,key=lambda x:dt(x['created_at'])); first=c[0]; n=first['number']; issues=[]
    if n is None: n=next((x['number'] for x in c if x['number'] is not None),None); issues.append('earliest_number_missing')
    if len({x['number'] for x in c if x['number'] is not None})>1: issues.append('number_disagreement')
    rich=max(c,key=lambda x:len(norm((x['body'] or '')+' '+(x['title'] or ''))))
    src={}
    for x in c: src.setdefault(x['source'],[]).append({'source_id':x['source_id'],'url':x['url'],'created_at':x['created_at'],'number':x['number'],'text':x['text']})
    return {'canonical_id':hashlib.sha1('|'.join(sorted(x['source']+':'+x['source_id'] for x in c)).encode()).hexdigest()[:14],
            'display_number':n,'number_issue':bool(issues),'number_issues':issues,'first_published':first['created_at'],'year':dt(first['created_at']).year,
            'title':rich['title'] or first['title'] or '#statstab','body':rich['body'] or '','display_source':rich['source'],
            'tags':uniq(sorted([t for x in c for t in x['tags']],key=str.casefold),key=str.casefold),
            'external_links':uniq([u for x in c for u in x['external_links']],key=str.casefold),'sources':src}

def main():
    parts={'x':load_x()}
    for name,fn in [('bluesky',bluesky),('mastodon',mastodon)]:
        try: parts[name]=fn()
        except Exception as e: print(f'WARNING {name}: {e}'); parts[name]=[]
    posts=[canon(c) for c in clusters(sum(parts.values(),[]))]
    by={}
    for p in posts:
        if p['display_number'] is not None: by.setdefault(p['display_number'],[]).append(p)
    for group in by.values():
        if len(group)>1:
            for p in group: p['number_issue']=True; p['number_issues'].append('number_reused')
    posts.sort(key=lambda p:(dt(p['first_published']),p['display_number'] or -1),reverse=True)
    payload={'generated_at':iso(datetime.now(timezone.utc)),'hashtag':'#statstab','source_counts':{k:len(v) for k,v in parts.items()},'canonical_count':len(posts),'posts':posts}
    OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'source_counts':payload['source_counts'],'canonical_count':len(posts)}))

if __name__=='__main__': main()
