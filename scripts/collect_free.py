"""Collect RSS candidates without paid AI. Never modifies published articles."""
import json, re, hashlib, os, sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse
import feedparser, requests

ROOT=Path(__file__).resolve().parents[1]
SOURCES=json.loads((ROOT/'sources.json').read_text(encoding='utf-8'))
OUT=ROOT/'data/news_candidates.json'
LIMIT=int(os.getenv('MAX_ITEMS','10'))
CUTOFF=datetime.now(timezone.utc)-timedelta(days=14)

def https(url):
    p=urlparse(url)
    return p.scheme=='https' and bool(p.hostname) and not p.username and not p.password

def main():
    previous=json.loads(OUT.read_text(encoding='utf-8')) if OUT.exists() else {'candidates':[]}
    by_url={x['source_url']:x for x in previous.get('candidates',[]) if isinstance(x,dict) and x.get('source_url')}
    new=0
    for src in SOURCES:
        try:
            url=src['feed_url']
            if not https(url): raise ValueError('Invalid HTTPS feed')
            resp=requests.get(url,timeout=20,headers={'User-Agent':'SDAH-NewsCollector/1.0 (+https://www.swissdigitalassethub.ch/)'})
            resp.raise_for_status()
            feed=feedparser.parse(resp.content)
            if not feed.entries: print('NO RSS ENTRIES:',src['name'],file=sys.stderr)
            for entry in feed.entries[:30]:
                link=entry.get('link','').strip()
                if not https(link) or link in by_url: continue
                date_tuple=entry.get('published_parsed') or entry.get('updated_parsed')
                date=datetime(*date_tuple[:6],tzinfo=timezone.utc) if date_tuple else None
                if date and date<CUTOFF: continue
                summary=re.sub(r'<[^>]*>',' ',entry.get('summary',''))
                summary=re.sub(r'\s+',' ',summary).strip()[:900]
                by_url[link]={'id':hashlib.sha256(link.encode()).hexdigest()[:16], 'source_name':src['name'], 'source_url':link, 'original_title':entry.get('title','').strip()[:250], 'published_at':date.date().isoformat() if date else '', 'source_excerpt':summary, 'review_status':'unreviewed'}
                new+=1
        except Exception as e:
            print('SOURCE ERROR:',src.get('name','unknown'),str(e),file=sys.stderr)
    candidates=sorted(by_url.values(),key=lambda x:x.get('published_at',''),reverse=True)[:max(LIMIT,1)]
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({'candidates':candidates},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'New: {new}; saved candidates: {len(candidates)}; no AI API; no public publishing')

if __name__=='__main__':main()
