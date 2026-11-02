"""Human-only local publisher: validates a draft and adds it to approved JSON."""
import argparse,json,re
from pathlib import Path
from urllib.parse import urlparse
ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('draft',help='drafts/<id>.json')
args=parser.parse_args()
p=(ROOT/args.draft).resolve()
if not p.is_relative_to((ROOT/'drafts').resolve()) or p.suffix!='.json':raise SystemExit('Must choose a drafts/*.json file')
a=json.loads(p.read_text())
required=['id','title_en','title_ko','summary_en','summary_ko','facts_en','facts_ko','korea_impact_en','korea_impact_ko','opportunities_en','opportunities_ko','caveats_en','caveats_ko','source_url','source_name','published_at']
if any(not isinstance(a.get(k),str) or not a[k].strip() for k in required):raise SystemExit('Draft has missing required fields')
if not re.fullmatch('[a-f0-9]{16}',a['id']):raise SystemExit('Invalid id')
u=urlparse(a['source_url'])
if u.scheme!='https' or not u.hostname:raise SystemExit('Source URL must be HTTPS')
allowed={k:a[k] for k in required}
allowed['category']=a.get('category','Swiss Finance')
path=ROOT/'data/articles.json';obj=json.loads(path.read_text())
items=[x for x in obj.get('articles',[]) if x.get('id')!=a['id']]
items.insert(0,allowed)
items.sort(key=lambda x:x['published_at'],reverse=True)
path.write_text(json.dumps({'articles':items},ensure_ascii=False,indent=2)+'\n')
print('Added approved article:',a['id'])
