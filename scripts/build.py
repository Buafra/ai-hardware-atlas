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
        for s in (p.get('price') or {}).get('sources', []):
            assert urlparse(s['url']).scheme == 'https', 'Price source must be https'
        if p.get('image'):
            u = urlparse(p['image']['url'])
            assert u.scheme == 'https' and any(u.hostname == h or u.hostname.endswith('.'+h) for h in ALLOWED), 'Unofficial image'
        for s in p['sources']:
            u = urlparse(s['url'])
            assert u.scheme == 'https' and any(u.hostname == h or u.hostname.endswith('.'+h) for h in ALLOWED), 'Unofficial source'
    assert len(ids) >= 31, 'Unexpected catalog loss'

OPTIONAL = {'bandwidth_tbs': None, 'bandwidth_note': None, 'ai_compute': None, 'interconnect': None, 'form_factor': None, 'cooling': None, 'msrp_usd': None, 'use_ar': None, 'price': None, 'image': None}
AED_PEG = 3.6725  # UAE dirham is pegged to the US dollar.
INSTAGRAM = 'https://www.instagram.com/qahwa.w.ai/'
BACKEND_ONLY = ('announcements',)

def money(low, high, prefix):
    if low is None and high is None:
        return None
    low, high = low if low is not None else high, high if high is not None else low
    return f'{prefix}{low:,.0f}' if round(low) == round(high) else f'{prefix}{low:,.0f}–{high:,.0f}'

def price_view(p):
    """Display strings for the approximate price; AED falls back to the peg conversion."""
    pr = p['price']
    if not pr:
        return None
    usd = money(pr.get('usd_low'), pr.get('usd_high'), '$')
    aed, aed_kind = money(pr.get('aed_low'), pr.get('aed_high'), 'AED '), pr.get('aed_kind')
    if not aed and usd:
        near10 = lambda v: None if v is None else round(v * AED_PEG, -1)
        aed, aed_kind = money(near10(pr.get('usd_low')), near10(pr.get('usd_high')), '≈ AED '), 'Converted from USD at 3.6725'
    if not usd and not aed:
        return None
    return {'usd': usd, 'usd_kind': pr.get('usd_kind'), 'aed': aed, 'aed_kind': aed_kind, 'checked': pr.get('checked'), 'basis': pr.get('basis')}

def price_block(p):
    v = p['price_view']
    if not v:
        why = (p['price'] or {}).get('basis')
        why = f'<dd class="price-src" lang="en" dir="auto">{E(why)}</dd>' if why else ''
        return f'<div class="price-row"><dt data-i18n>Approx. price</dt><dd>{T("Not publicly priced")}</dd>{why}</div>'
    links = ' '.join(f'<a href="{E(s["url"])}" target="_blank" rel="noopener noreferrer">{E(s["label"])}</a>' for s in p['price'].get('sources', []))
    part = lambda value, kind: f'<span class="amt">{E(value)}</span><small>{T(kind) if kind else ""}</small>' if value else f'<span class="amt">{T("Not listed")}</span>'
    return f'''<div class="price-row"><dt><span data-i18n>Approx. price</span> <small><span data-i18n>checked</span> {E(v['checked'])}</small></dt><dd class="prices"><span>{part(v['usd'], v['usd_kind'])}</span><span>{part(v['aed'], v['aed_kind'])}</span></dd><dd class="price-src" lang="en" dir="auto">{E(v['basis'] or '')} {links}</dd></div>'''

def image_block(p):
    img = p['image']
    if not img or not img.get('file'):
        return ''
    return f'<figure class="shot"><img src="{E(img["file"])}" alt="{E(p["model"])}" title="{E(img.get("shows",""))}" loading="lazy" decoding="async"><figcaption><a href="{E(img["page"])}" target="_blank" rel="noopener noreferrer"><span data-i18n>Image:</span> {E(img["credit"])}</a></figcaption></figure>'

AR_MONTHS = ['يناير','فبراير','مارس','أبريل','مايو','يونيو','يوليو','أغسطس','سبتمبر','أكتوبر','نوفمبر','ديسمبر']

def news_date(iso, lang):
    d = datetime.fromisoformat(iso)
    return f'{d.day} {AR_MONTHS[d.month-1]} {d.year}' if lang == 'ar' else f'{d.day} {d.strftime("%b")} {d.year}'

def news_lists(news, sources, uae_only, limit=12):
    """Return EN and AR <ol> lists. Arabic list = native Arabic + machine-translated English items."""
    if not news or not news.get('items'):
        return f'<p class="muted">{T("Headlines appear after the first scheduled update.")}</p>'
    src = {s['id']: s for s in sources}
    items = [i for i in news['items'] if i['source'] in src and (i['uae'] if uae_only else src[i['source']]['region'] == 'global')]
    def li(i, lang):
        s = src[i['source']]
        title = i.get('title_ar') if lang == 'ar' and i['lang'] == 'en' else i['title']
        name = s['name_ar'] if lang == 'ar' else s['name']
        mt = '<span class="mt">ترجمة آلية</span>' if lang == 'ar' and i['lang'] == 'en' else ''
        text_dir = 'rtl' if (lang == 'ar') else 'ltr'
        return f'<li><a href="{E(i["url"])}" target="_blank" rel="noopener noreferrer" dir="{text_dir}">{E(title)}</a><span class="meta"><a class="src" href="{E(s["homepage"])}" target="_blank" rel="noopener noreferrer">{E(name)}</a> · {news_date(i["published"], lang)}{mt}</span></li>'
    def varied(pool):
        # Newest first, at most two headlines per source so one outlet can't fill the list.
        seen, out = {}, []
        for i in pool:
            if seen.get(i['source'], 0) < 2:
                seen[i['source']] = seen.get(i['source'], 0) + 1
                out.append(i)
        return out[:limit]
    en = varied([i for i in items if i['lang'] == 'en'])
    ar = varied([i for i in items if i['lang'] == 'ar' or i.get('title_ar')])
    out = f'<ol class="news-list" data-lang="en">{"".join(li(i, "en") for i in en)}</ol>' if en else '<p class="muted" data-lang="en">No recent English headlines.</p>'
    out += f'<ol class="news-list" data-lang="ar">{"".join(li(i, "ar") for i in ar)}</ol>' if ar else '<p class="muted" data-lang="ar">لا توجد عناوين عربية حديثة.</p>'
    return out

def news_section(news, sources):
    if not sources:
        return ''
    updated = news_date(news['updated_at'], 'en') if news else '—'
    updated_ar = news_date(news['updated_at'], 'ar') if news else '—'
    feeds = ''.join(f'<li><a href="{E(s["homepage"])}" target="_blank" rel="noopener noreferrer"><span data-lang="en">{E(s["name"])}</span><span data-lang="ar">{E(s["name_ar"])}</span></a> <small>{E(s["lang"].upper())} · {"UAE" if s["region"] == "uae" else "Global"}</small></li>' for s in sources)
    return f'''<section id="news" class="block"><div class="sec-head"><h2 data-i18n>AI news</h2><p class="muted"><span data-lang="en">Updated {updated} · twice a day (07:15 and 19:15 UAE time) from vetted official and news sources</span><span data-lang="ar">آخر تحديث {updated_ar} · مرتين يوميًا (7:15 و19:15 بتوقيت الإمارات) من مصادر رسمية وإخبارية موثوقة</span></p></div>
{news_lists(news, sources, False)}<details class="feeds"><summary data-i18n>News sources</summary><ul>{feeds}</ul><p class="muted" data-lang="en">Headlines link to the original publisher. Items marked "ترجمة آلية" were translated by AI and may be imperfect.</p><p class="muted" data-lang="ar">العناوين مرتبطة بالناشر الأصلي. العناصر الموسومة "ترجمة آلية" ترجمها الذكاء الاصطناعي وقد لا تكون دقيقة تمامًا.</p></details></section>'''

def uae_section(uae, news, sources):
    if not uae:
        return ''
    cards = ''
    for f in uae['facts']:
        hw = ''.join(f'<button type="button" class="chip" data-q="{E(h)}">{E(h)}</button>' for h in f.get('hardware', []))
        links = ' '.join(f'<a href="{E(s["url"])}" target="_blank" rel="noopener noreferrer">{E(s["label"])}</a>' for s in f['sources'])
        cards += f'''<article class="fact"><h3><span data-lang="en">{E(f['title_en'])}</span><span data-lang="ar">{E(f['title_ar'])}</span></h3><p data-lang="en">{E(f['text_en'])}</p><p data-lang="ar">{E(f['text_ar'])}</p>{f'<div class="chips">{hw}</div>' if hw else ''}<p class="fact-src"><span data-i18n>As of</span> {E(f['as_of'])} · {links}</p></article>'''
    return f'''<section id="uae" class="block"><div class="sec-head"><h2 data-i18n>UAE AI</h2><p class="muted"><span data-lang="en">Key facts checked {E(uae['checked'])} against their sources, plus AI headlines about the UAE or from UAE newsrooms, updated twice a day.</span><span data-lang="ar">حقائق رئيسية تم التحقق منها بتاريخ {E(uae['checked'])} من مصادرها، مع عناوين الذكاء الاصطناعي عن الإمارات أو من غرف الأخبار الإماراتية، تُحدَّث مرتين يوميًا.</span></p></div>
<div class="facts-grid">{cards}</div><h3 class="sub" data-i18n>UAE AI headlines</h3>{news_lists(news, sources, True, 10)}</section>'''

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
    return f'''<article class="product {p['vendor'].lower()}" data-product="{E(p['id'])}">{image_block(p)}
    <header><div class="eyebrow"><span class="vendor">{p['vendor']}</span><span>{T(p['level'])} / {T(p['type'])}</span></div><h2>{E(p['model'])}</h2><p class="architecture">{E(p['architecture'])}</p></header>
    <div class="memory"><strong>{E(p['memory'])}</strong><small>{T(p['memory_scope'])}</small><span class="fit" hidden></span></div>
    <dl class="facts"><div><dt data-i18n>Availability / target</dt><dd>{release}<small>{T(p['release_kind'])}</small></dd></div><div><dt data-i18n>Announced / launched</dt><dd>{announced}</dd></div><div><dt data-i18n>Bandwidth</dt><dd>{bandwidth}</dd></div><div><dt data-i18n>Power</dt><dd>{power}<small>{T(p['power_note'])}</small></dd></div><div><dt data-i18n>AI compute</dt><dd>{NA(p['ai_compute'])}</dd></div><div><dt data-i18n>Launch price</dt><dd>{price}</dd></div>{price_block(p)}</dl>
    <p class="use"{use_ar}>{E(p['use'])}</p><details><summary data-i18n>Notes and official sources</summary><dl class="more"><div><dt data-i18n>Form factor</dt><dd>{NA(p['form_factor'])}</dd></div><div><dt data-i18n>Cooling</dt><dd>{cooling}</dd></div><div><dt data-i18n>Interconnect</dt><dd>{NA(p['interconnect'])}</dd></div><div><dt data-i18n>Content reviewed</dt><dd>{E(p['source_reviewed'])}</dd></div></dl><p lang="en" dir="auto">{E(p['notes'])}</p><div class="sources">{sources}</div></details>
    <label class="cmp"><input type="checkbox" class="cmp-toggle" value="{E(p['id'])}"><span data-i18n>Compare</span></label></article>'''

def pdf(data):
    # Embedded fonts avoid the substitution problems seen in the first PDF.
    fontdir = ROOT / 'fonts'
    pdfmetrics.registerFont(TTFont('Atlas', str(fontdir/'DejaVuSans.ttf')))
    pdfmetrics.registerFont(TTFont('Atlas-Bold', str(fontdir/'DejaVuSans-Bold.ttf')))
    w,h = A3
    c=canvas.Canvas(str(OUT/'AI_Hardware_Atlas_2026_One_Page.pdf'),pagesize=A3)
    c.setTitle('AI Hardware Atlas - NVIDIA and AMD | Cipher AI Knowledge');c.setAuthor('Cipher AI Knowledge')
    c.setFillColor(HexColor('#f5f8ff'));c.rect(0,0,w,h,fill=1,stroke=0)
    c.setFillColor(HexColor('#4d2899'));c.roundRect(24,h-117,w-48,93,16,fill=1,stroke=0)
    c.setFillColor(HexColor('#ffffff'));c.setFont('Atlas-Bold',27);c.drawString(43,h-66,'AI HARDWARE ATLAS');c.setFont('Atlas-Bold',10);c.drawRightString(w-43,h-58,'CIPHER AI KNOWLEDGE')
    c.setFont('Atlas',12);c.drawString(44,h-95,f"NVIDIA + AMD / {len(data['products'])} products / Updated {data['updated_at'][:10]}")
    c.setFillColor(HexColor('#42516e'));c.setFont('Atlas',9)
    c.drawString(30,h-144,'A = announced / launched. R = availability or vendor target. Blank dates are not established.')
    products=data['products']
    # Two columns up to 36 products, then three so rows keep room for three text lines.
    cols=2 if len(products)<=36 else 3
    per=math.ceil(len(products)/cols);gap=18 if cols==2 else 12
    cw=(w-60-gap*(cols-1))/cols
    row_h=min(54,850/per)
    def fit(text,width,size=9,font='Atlas'):
        text=str(text)
        while pdfmetrics.stringWidth(text,font,size)>width:
            size-=.2
            if size<7:break
        c.setFont(font,size);return text
    for col in range(cols):
        part=products[col*per:(col+1)*per]
        x=30+col*(cw+gap);y=h-165
        for i,p in enumerate(part):
            top=y-i*row_h
            c.setFillColor(HexColor('#ffffff') if i%2==0 else HexColor('#eaf0ff'))
            c.rect(x,top-row_h,cw,row_h,fill=1,stroke=0)
            c.setFillColor(HexColor('#00a7aa') if p['vendor']=='NVIDIA' else HexColor('#f2803c'));c.roundRect(x+10,top-31,4,18,2,fill=1,stroke=0)
            c.setFillColor(HexColor('#182642'))
            c.drawString(x+23,top-17,fit(p['model'],cw-90,10,'Atlas-Bold'))
            c.setFont('Atlas-Bold',7.7);c.drawRightString(x+cw-12,top-17,p['vendor'])
            c.setFillColor(HexColor('#51627f'))
            line=p['memory'].replace('×','x').replace('·','/')+' / '+p['memory_scope']
            if p['bandwidth_tbs']:line+=f" / {p['bandwidth_tbs']:g} TB/s"
            c.drawString(x+23,top-32,fit(line,cw-33,8))
            dates=f"A: {p['announcement'] or '-'}  |  R: {p['release'] or '-'}"
            if p['release']:dates+=' ('+p['release_kind']+')'
            c.drawString(x+23,top-45,fit(dates,cw-33,7.5))
            c.linkURL(p['sources'][0]['url'],(x,top-row_h,x+cw,top))
    c.setFillColor(HexColor('#e9e3fc'));c.roundRect(30,49,w-60,69,11,fill=1,stroke=0)
    c.setFillColor(HexColor('#39236f'));c.setFont('Atlas-Bold',10);c.drawString(45,97,'COMPARE LIKE FOR LIKE')
    c.setFont('Atlas',8.4);c.drawString(45,80,'Dedicated GPU VRAM, shared system memory and rack totals have different meanings. Capacity is not speed.')
    c.drawString(45,65,'Each row links to an official source. The website includes power, architecture, detailed notes and all sources.')
    c.setFillColor(HexColor('#65758f'));c.setFont('Atlas',8);c.drawString(30,28,'One-page overview. Precise dates are shown only where established; availability varies by partner and region.');c.drawRightString(w-30,28,f'© {datetime.now().year} Cipher AI Knowledge')
    c.showPage();c.save()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--standalone',type=Path,help='also copy the self-contained page (and PDF beside it) to this .html path')
    args=parser.parse_args()
    data=json.loads((ROOT/'data/catalog.json').read_text(encoding='utf-8'))
    validate(data);OUT.mkdir(exist_ok=True)
    for p in data['products']:
        for k,v in OPTIONAL.items():p.setdefault(k,v)
        p['price_view']=price_view(p)
        p['price_usd']=(p['price'] or {}).get('usd_low')
    load=lambda name:json.loads((ROOT/'data'/name).read_text(encoding='utf-8')) if (ROOT/'data'/name).exists() else None
    feed,sources,uae=load('news.json'),load('news-sources.json') or [],load('uae.json')
    models=load('models.json') or {'models':[]}
    slim={'updated_at':models.get('updated_at'),'models':[{'n':m['name'],'b':m['params_b'],'o':m['open'],'s':m['params_source'],'moe':m.get('moe',False),'c':m['context'],'hf':m['hf']} for m in models['models']]}
    text=(ROOT/'web/template.html').read_text(encoding='utf-8')
    # Backend-only fields stay in data/catalog.json (review issue, AI drafts) and are not published.
    public={k:v for k,v in data.items() if k not in BACKEND_ONLY}
    replacements={'CSS':(ROOT/'web/style.css').read_text(encoding='utf-8'),'JS':(ROOT/'web/app.js').read_text(encoding='utf-8'),'PRODUCTS':''.join(product(p) for p in data['products']),'COUNT':str(len(data['products'])),'UPDATED':E(data['updated_at'][:10]),'CHECKED':E(data.get('last_check_at') or 'Not run yet'),'SCHEDULE':E(data['schedule']+' - '+data['automation_status']),'CHANGES':'<ul>'+''.join(f'<li><b>{E(x["at"][:10])}</b> - {E(x["summary"])}</li>' for x in data['changes'][:8])+'</ul>','NEWSFEED':news_section(feed,sources),'UAE':uae_section(uae,feed,sources),'INSTAGRAM':INSTAGRAM,'YEAR':str(datetime.now().year),'MODELS':json.dumps(slim,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c'),'EDITION':E(data['edition_note']),'JSON':json.dumps(public,ensure_ascii=False).replace('<','\\u003c')}
    health=data.get('check_health')
    if health:
        replacements['CHECKED'] += E(f" ({health['successful_sources']}/{health['attempted_sources']} sources reached)")
    for k,v in replacements.items():text=text.replace('__'+k+'__',v)
    (OUT/'index.html').write_text(text,encoding='utf-8',newline='\n')
    (OUT/'catalog.json').write_text(json.dumps(public,indent=2,ensure_ascii=False)+'\n',encoding='utf-8',newline='\n')
    if (ROOT/'images').exists():shutil.copytree(ROOT/'images',OUT/'images',dirs_exist_ok=True)
    pdf(data)
    if args.standalone:
        target=args.standalone.resolve()
        shutil.copyfile(OUT/'index.html',target)
        if (ROOT/'images').exists():shutil.copytree(ROOT/'images',target.parent/'images',dirs_exist_ok=True)
        shutil.copyfile(OUT/'AI_Hardware_Atlas_2026_One_Page.pdf',target.parent/'AI_Hardware_Atlas_2026_One_Page.pdf')
        print(f'Standalone copy written to {target}')
    print(f"Built {len(data['products'])} products, self-contained HTML, JSON and one-page PDF")

if __name__=='__main__':main()
