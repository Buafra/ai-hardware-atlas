"""Check official sources and refresh narrowly parsed specs and announcement links.

Never infer availability from the calendar or let a failed request erase data.
New product specifications and changes without a configured parser go to review.
"""
import concurrent.futures
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse, urljoin, urldefrag
from urllib.request import Request, build_opener, HTTPRedirectHandler

ROOT=Path(__file__).resolve().parents[1]
VENDORS=('nvidia.com','amd.com')
DISCOVERY=['https://nvidianews.nvidia.com/news/latest','https://newsroom.amd.com/category/data-center/','https://newsroom.amd.com/category/client-computing/','https://newsroom.amd.com/category/ai/']
KEYWORDS=re.compile(r'\b(DGX|RTX|Instinct|MI\d{3}|Radeon|Helios|Rubin|Blackwell|Ryzen AI)\b',re.I)

def official(url):
    u=urlparse(url)
    return u.scheme=='https' and not u.username and not u.password and u.port in (None,443) and any(u.hostname==v or (u.hostname or '').endswith('.'+v) for v in VENDORS)

class Redirects(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        if not official(newurl):raise ValueError('Redirect left official source domain')
        return super().redirect_request(req,fp,code,msg,headers,newurl)

class Page(HTMLParser):
    def __init__(self):
        super().__init__();self.parts=[];self.links=[];self.h1=[];self.h1depth=0;self.skip=0;self.anchor=None
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag in ('script','style','noscript'):self.skip+=1
        if tag=='h1':self.h1depth+=1
        if tag=='a':self.anchor={'href':a.get('href',''),'text':[]}
        if tag in ('p','div','td','th','dd','dt','li','h1','h2','h3'):self.parts.append(' ')
    def handle_endtag(self,tag):
        if tag in ('script','style','noscript') and self.skip:self.skip-=1
        if tag=='h1':self.h1depth=max(0,self.h1depth-1)
        if tag=='a' and self.anchor:self.links.append(self.anchor);self.anchor=None
    def handle_data(self,value):
        if not self.skip:
            self.parts.append(value+' ')
            if self.h1depth:self.h1.append(value)
            if self.anchor:self.anchor['text'].append(value)
    @property
    def text(self):return re.sub(r'\s+',' ',' '.join(self.parts)).strip()

def fetch(url):
    if not official(url):raise ValueError('Unofficial source')
    req=Request(url,headers={'User-Agent':'AI-Hardware-Atlas/1.0 (public official-specification monitor)','Accept':'text/html'})
    with build_opener(Redirects).open(req,timeout=25) as r:
        if not official(r.url) or 'text/html' not in r.headers.get('Content-Type',''):raise ValueError('Unsupported source response')
        raw=r.read(2_000_001)
        if len(raw)>2_000_000:raise ValueError('Source exceeded size limit')
        page=Page();page.feed(raw.decode('utf-8',errors='replace'))
    if len(page.text)<500 or not page.h1:raise ValueError('Source incomplete or blocked')
    return page

def parse_spec(page,rule):
    if rule['title'].casefold() not in re.sub(r'\s+',' ',' '.join(page.h1)).casefold():raise ValueError('Product title mismatch')
    values={}
    for key,pattern in rule['fields'].items():
        found=re.findall(pattern,page.text,re.I)
        nums={float(v.replace(',','')) for v in found}
        if len(nums)!=1:raise ValueError('Missing or conflicting specification: '+key)
        n=nums.pop()
        if not 1<=n<=2000:raise ValueError('Specification outside accepted bounds')
        values[key]=n
    return values

def apply_values(p,values):
    changed=[]
    for field,value in values.items():
        # Only individual GPU fields use these parsers; never rewrite aggregate memory.
        if field=='memory_gb' and p['memory_scope']!='Per GPU':raise ValueError('Memory scope mismatch')
        if p.get(field)!=value:
            old=p.get(field);p[field]=value
            if field=='memory_gb':p['memory']=re.sub(r'^\d+(?:\.\d+)?\s*GB',f'{value:g} GB',p['memory'])
            if field=='power_w' and p.get('power_note') in (None,'Not documented in this edition'):p['power_note']='Official specification, checked automatically'
            changed.append(f"{p['model']}: {field} changed from {old} to {value:g}")
    return changed

def main():
    catalog_path=ROOT/'data/catalog.json';state_path=ROOT/'data/source-state.json'
    data=json.loads(catalog_path.read_text(encoding='utf-8'));state=json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else {}
    now=datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    rules=json.loads((ROOT/'data/refresh-rules.json').read_text(encoding='utf-8'))
    urls=set(DISCOVERY)|{r['url'] for r in rules.values()}
    for p in data['products']:
        # Partner devices also cite their maker's site; only NVIDIA / AMD pages are monitored.
        urls.update(s['url'] for s in p['sources'] if official(s['url']) and not urlparse(s['url']).path.lower().endswith('.pdf'))
    pages={};errors={}
    def load(url):
        try:return url,fetch(url),None
        except Exception as exc:return url,None,type(exc).__name__
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for url,page,error in pool.map(load,sorted(urls)):
            if error:errors[url]=error
            else:pages[url]=page
    review=[];changes=[]
    for url,page in pages.items():
        digest=hashlib.sha256(page.text.encode()).hexdigest()
        previous=state.get(url,{})
        if previous.get('digest') and previous['digest']!=digest:
            review.append({'url':url,'reason':'Official page changed; inspect timeline and unparsed specifications','at':now})
        state[url]={'digest':digest,'checked_at':now}
    for p in data['products']:
        rule=rules.get(p['id'])
        if not rule or rule['url'] not in pages:continue
        try:
            values=parse_spec(pages[rule['url']],rule)
            changes.extend(apply_values(p,values))
            p['spec_checked_at']=now
        except ValueError as exc:
            review.append({'product_id':p['id'],'url':rule['url'],'reason':str(exc),'at':now})
    known={a['url']:a for a in data.get('announcements',[])}
    for url in DISCOVERY:
        page=pages.get(url)
        if not page:continue
        for link in page.links:
            title=re.sub(r'\s+',' ',' '.join(link['text'])).strip()
            target=urldefrag(urljoin(url,link['href']))[0]
            if official(target) and len(title)>25 and KEYWORDS.search(title) and '/news/' in urlparse(target).path and target not in known:
                known[target]={'title':title[:220],'url':target,'discovered_at':now}
    data['announcements']=sorted(known.values(),key=lambda a:a['discovered_at'],reverse=True)[:40]
    data['last_check_at']=now if pages else data.get('last_check_at')
    data['last_attempt_at']=now
    data['check_health']={'successful_sources':len(pages),'failed_sources':len(errors),'attempted_sources':len(urls)}
    # A run does not prove future schedule activation. The deploy workflow records that separately.
    if changes:
        data['updated_at']=now
        data['changes']=([{'at':now,'summary':s} for s in changes]+data['changes'])[:80]
    report={'at':now,'health':data['check_health'],'changes':changes,'review':review,'errors':errors}
    (ROOT/'data/refresh-report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
    for path,obj in [(catalog_path,data),(state_path,state)]:
        temp=path.with_suffix('.tmp');temp.write_text(json.dumps(obj,indent=2,ensure_ascii=False)+'\n',encoding='utf-8',newline='\n');temp.replace(path)
    print(f'Checked {len(pages)}/{len(urls)} official sources; {len(changes)} verified field changes; {len(review)} items for review')
    if not pages:print('No sources reachable. Existing catalog retained.',file=sys.stderr)
    return 0

if __name__=='__main__':sys.exit(main())
