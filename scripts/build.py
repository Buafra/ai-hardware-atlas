"""Build the self-contained website and one-page PDF from a single data file."""
import argparse
import html
import json
import math
import shutil
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A3
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'dist'
E = lambda value: html.escape(str(value if value is not None else 'Not established'))
ALLOWED = ('nvidia.com', 'amd.com')

def validate(data):
    ids = set()
    for p in data['products']:
        assert p['id'] not in ids, 'Duplicate product'
        ids.add(p['id'])
        assert 0 < p['memory_gb'] <= 2000000
        assert p['vendor'] in ('NVIDIA','AMD')
        assert p['sources'], 'Missing evidence'
        for k in ('bandwidth_tbs', 'msrp_usd'):
            assert p.get(k) is None or (isinstance(p[k], (int, float)) and p[k] > 0), f'Invalid {k}'
        assert p.get('cooling') in (None, 'Air', 'Liquid', 'Air or liquid'), 'Unknown cooling'
        for s in p['sources']:
            u = urlparse(s['url'])
            assert u.scheme == 'https' and any(u.hostname == h or u.hostname.endswith('.'+h) for h in ALLOWED), 'Unofficial source'
    assert len(ids) >= 31, 'Unexpected catalog loss'

OPTIONAL = {'bandwidth_tbs': None, 'bandwidth_note': None, 'ai_compute': None, 'interconnect': None, 'form_factor': None, 'cooling': None, 'msrp_usd': None, 'use_ar': None}

def T(value):
    # English text the page can translate client-side; unknown strings fall back to English.
    return f'<span data-i18n>{html.escape(str(value))}</span>'

def NA(value, fmt=lambda v: E(v)):
    return T('Not listed') if value is None or value == '' else fmt(value)

def product(p):
    sources = ' '.join(f'<a href="{E(s["url"])}" target="_blank" rel="noopener noreferrer">{E(s["label"])}</a>' for s in p['sources'])
    power = NA(p['power_w'], lambda v: f'{v:g} W')
    bandwidth = NA(p['bandwidth_tbs'], lambda v: f'{v:g} TB/s') + (f'<small>{E(p["bandwidth_note"])}</small>' if p['bandwidth_note'] else '')
    price = NA(p['msrp_usd'], lambda v: f'${v:,.0f}')
    release = E(p['release']) if p['release'] else T('Not established')
    announced = E(p['announcement']) if p['announcement'] else T('Not established')
    cooling = NA(p['cooling'], T)
    use_ar = f' data-ar="{E(p["use_ar"])}"' if p['use_ar'] else ''
    return f'''<article class="product {p['vendor'].lower()}" data-product="{E(p['id'])}">
    <header><div class="eyebrow"><span class="vendor">{p['vendor']}</span><span>{T(p['level'])} / {T(p['type'])}</span></div><h2>{E(p['model'])}</h2><p class="architecture">{E(p['architecture'])}</p></header>
    <div class="memory"><strong>{E(p['memory'])}</strong><small>{T(p['memory_scope'])}</small><span class="fit" hidden></span></div>
    <dl class="facts"><div><dt data-i18n>Availability / target</dt><dd>{release}<small>{T(p['release_kind'])}</small></dd></div><div><dt data-i18n>Announced / launched</dt><dd>{announced}</dd></div><div><dt data-i18n>Bandwidth</dt><dd>{bandwidth}</dd></div><div><dt data-i18n>Power</dt><dd>{power}<small>{T(p['power_note'])}</small></dd></div><div><dt data-i18n>AI compute</dt><dd>{NA(p['ai_compute'])}</dd></div><div><dt data-i18n>Launch price</dt><dd>{price}</dd></div></dl>
    <p class="use"{use_ar}>{E(p['use'])}</p><details><summary data-i18n>Notes and official sources</summary><dl class="more"><div><dt data-i18n>Form factor</dt><dd>{NA(p['form_factor'])}</dd></div><div><dt data-i18n>Cooling</dt><dd>{cooling}</dd></div><div><dt data-i18n>Interconnect</dt><dd>{NA(p['interconnect'])}</dd></div><div><dt data-i18n>Content reviewed</dt><dd>{E(p['source_reviewed'])}</dd></div></dl><p lang="en" dir="auto">{E(p['notes'])}</p><div class="sources">{sources}</div></details>
    <label class="cmp"><input type="checkbox" class="cmp-toggle" value="{E(p['id'])}"><span data-i18n>Compare</span></label></article>'''

def pdf(data):
    # Embedded fonts avoid the substitution problems seen in the first PDF.
    fontdir = ROOT / 'fonts'
    pdfmetrics.registerFont(TTFont('Atlas', str(fontdir/'DejaVuSans.ttf')))
    pdfmetrics.registerFont(TTFont('Atlas-Bold', str(fontdir/'DejaVuSans-Bold.ttf')))
    w,h = A3
    c=canvas.Canvas(str(OUT/'AI_Hardware_Atlas_2026_One_Page.pdf'),pagesize=A3)
    c.setTitle('AI Hardware Atlas - NVIDIA and AMD')
    c.setFillColor(HexColor('#f5f8ff'));c.rect(0,0,w,h,fill=1,stroke=0)
    c.setFillColor(HexColor('#4d2899'));c.roundRect(24,h-117,w-48,93,16,fill=1,stroke=0)
    c.setFillColor(HexColor('#ffffff'));c.setFont('Atlas-Bold',27);c.drawString(43,h-66,'AI HARDWARE ATLAS')
    c.setFont('Atlas',12);c.drawString(44,h-95,f"NVIDIA + AMD / {len(data['products'])} products / Updated {data['updated_at'][:10]}")
    c.setFillColor(HexColor('#42516e'));c.setFont('Atlas',9)
    c.drawString(30,h-144,'A = announced / launched. R = availability or vendor target. Blank dates are not established.')
    products=data['products'];split=math.ceil(len(products)/2)
    row_h=min(54,850/split)
    def fit(text,width,size=9,font='Atlas'):
        text=str(text)
        while pdfmetrics.stringWidth(text,font,size)>width:
            size-=.2
            if size<7:break
        c.setFont(font,size);return text
    for col,part in enumerate([products[:split],products[split:]]):
        x=30+col*400;y=h-165
        for i,p in enumerate(part):
            top=y-i*row_h
            c.setFillColor(HexColor('#ffffff') if i%2==0 else HexColor('#eaf0ff'))
            c.rect(x,top-row_h,382,row_h,fill=1,stroke=0)
            c.setFillColor(HexColor('#00a7aa') if p['vendor']=='NVIDIA' else HexColor('#f2803c'));c.roundRect(x+10,top-31,4,18,2,fill=1,stroke=0)
            c.setFillColor(HexColor('#182642'))
            c.drawString(x+23,top-17,fit(p['model'],292,10,'Atlas-Bold'))
            c.setFont('Atlas-Bold',7.7);c.drawRightString(x+370,top-17,p['vendor'])
            c.setFillColor(HexColor('#51627f'))
            line=p['memory'].replace('×','x').replace('·','/')+' / '+p['memory_scope']
            if p['bandwidth_tbs']:line+=f" / {p['bandwidth_tbs']:g} TB/s"
            c.drawString(x+23,top-32,fit(line,350,8))
            dates=f"A: {p['announcement'] or '-'}  |  R: {p['release'] or '-'}"
            if p['release']:dates+=' ('+p['release_kind']+')'
            c.drawString(x+23,top-45,fit(dates,350,7.5))
            c.linkURL(p['sources'][0]['url'],(x,top-row_h,x+382,top))
    c.setFillColor(HexColor('#e9e3fc'));c.roundRect(30,49,w-60,69,11,fill=1,stroke=0)
    c.setFillColor(HexColor('#39236f'));c.setFont('Atlas-Bold',10);c.drawString(45,97,'COMPARE LIKE FOR LIKE')
    c.setFont('Atlas',8.4);c.drawString(45,80,'Dedicated GPU VRAM, shared system memory and rack totals have different meanings. Capacity is not speed.')
    c.drawString(45,65,'Each row links to an official source. The website includes power, architecture, detailed notes and all sources.')
    c.setFillColor(HexColor('#65758f'));c.setFont('Atlas',8);c.drawString(30,28,'One-page overview. Precise dates are shown only where established; availability varies by partner and region.')
    c.showPage();c.save()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--standalone',type=Path,help='also copy the self-contained page (and PDF beside it) to this .html path')
    args=parser.parse_args()
    data=json.loads((ROOT/'data/catalog.json').read_text(encoding='utf-8'))
    validate(data);OUT.mkdir(exist_ok=True)
    for p in data['products']:
        for k,v in OPTIONAL.items():p.setdefault(k,v)
    text=(ROOT/'web/template.html').read_text(encoding='utf-8')
    news='<p>No announcement check has run yet.</p>'
    if data.get('announcements'):
        news='<ul>'+''.join(f'<li><a href="{E(n["url"])}" target="_blank" rel="noopener noreferrer">{E(n["title"])}</a> - discovered {E(n["discovered_at"][:10])}</li>' for n in data['announcements'][:12])+'</ul><p>These are official source headlines. Discovery dates are not release dates.</p>'
    replacements={'CSS':(ROOT/'web/style.css').read_text(encoding='utf-8'),'JS':(ROOT/'web/app.js').read_text(encoding='utf-8'),'PRODUCTS':''.join(product(p) for p in data['products']),'COUNT':str(len(data['products'])),'UPDATED':E(data['updated_at'][:10]),'CHECKED':E(data.get('last_check_at') or 'Not run yet'),'SCHEDULE':E(data['schedule']+' - '+data['automation_status']),'CHANGES':'<ul>'+''.join(f'<li><b>{E(x["at"][:10])}</b> - {E(x["summary"])}</li>' for x in data['changes'][:8])+'</ul>','NEWS':news,'EDITION':E(data['edition_note']),'JSON':json.dumps(data,ensure_ascii=False).replace('<','\\u003c')}
    health=data.get('check_health')
    if health:
        replacements['CHECKED'] += E(f" ({health['successful_sources']}/{health['attempted_sources']} sources reached)")
    for k,v in replacements.items():text=text.replace('__'+k+'__',v)
    (OUT/'index.html').write_text(text,encoding='utf-8',newline='\n')
    (OUT/'catalog.json').write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n',encoding='utf-8',newline='\n')
    pdf(data)
    if args.standalone:
        target=args.standalone.resolve()
        shutil.copyfile(OUT/'index.html',target)
        shutil.copyfile(OUT/'AI_Hardware_Atlas_2026_One_Page.pdf',target.parent/'AI_Hardware_Atlas_2026_One_Page.pdf')
        print(f'Standalone copy written to {target}')
    print(f"Built {len(data['products'])} products, self-contained HTML, JSON and one-page PDF")

if __name__=='__main__':main()
