"""Build the self-contained website and one-page PDF from the data files."""
import argparse
import html
import json
import math
import re
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, urlparse
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

def https(url):
    return urlparse(str(url or '')).scheme == 'https'

def validate_links(sources, uae):
    """Hand-edited link lists: an http:, javascript: or empty URL fails the build (news items are filtered in news_items)."""
    for s in sources:
        assert https(s.get('homepage')), f"News source {s.get('id')} homepage must be https"
    for f in (uae or {}).get('facts', []):
        for s in f.get('sources', []):
            assert https(s.get('url')), f"UAE fact {f.get('id')} source must be https"

OPTIONAL = {'bandwidth_tbs': None, 'bandwidth_note': None, 'ai_compute': None, 'interconnect': None, 'form_factor': None, 'cooling': None, 'msrp_usd': None, 'use_ar': None, 'price': None, 'image': None}
AED_PEG = 3.6725  # UAE dirham is pegged to the US dollar.
INSTAGRAM = 'https://www.instagram.com/qahwa.w.ai/'
# Run bookkeeping (schedule, automation status, fetch statistics) is not published either; the page never uses it.
BACKEND_ONLY = ('announcements', 'check_health', 'automation_status', 'schedule', 'last_attempt_at')
SITE_NAME = 'Cipher Lacuna'
UAE_TZ = timezone(timedelta(hours=4))
LEVELS = ['Personal', 'Workstation', 'Enterprise', 'Data center', 'Rack scale']
BRAND_DIR = ROOT / 'web' / 'brand'
# Neutral, text-free placeholder until the owner's own favicon is dropped into web/brand/.
PLACEHOLDER_FAVICON = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
                       '<stop offset="0" stop-color="#42208d"/><stop offset=".6" stop-color="#753aca"/><stop offset="1" stop-color="#d52f89"/>'
                       '</linearGradient></defs><rect width="32" height="32" rx="8" fill="url(#g)"/></svg>')

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
        return f'<div class="price-row"><dt data-i18n>Approx. price</dt><dd class="price-none">{T("Not publicly priced")}</dd>{why}</div>'
    links = ' '.join(f'<a href="{E(s["url"])}" target="_blank" rel="noopener noreferrer">{E(s["label"])}</a>' for s in p['price'].get('sources', []))
    part = lambda value, kind: f'<span class="amt"><bdi>{E(value)}</bdi></span><small>{T(kind) if kind else ""}</small>' if value else f'<span class="amt">{T("Not listed")}</span>'
    return f'''<div class="price-row"><dt><span data-i18n>Approx. price</span> <small><span data-i18n>checked</span> {L(ymd(v['checked'], 'en'), ymd(v['checked'], 'ar'))}</small></dt><dd class="prices"><span>{part(v['usd'], v['usd_kind'])}</span><span>{part(v['aed'], v['aed_kind'])}</span></dd><dd class="price-src" lang="en" dir="auto">{E(v['basis'] or '')} {links}</dd></div>'''

def image_block(p, badge=''):
    img = p['image']
    if not img or not img.get('file'):
        return ''
    return f'<figure class="shot"><img src="{E(img["file"])}" alt="{E(p["model"])}" title="{E(img.get("shows",""))}" lang="en" loading="lazy" decoding="async"><figcaption><a class="credit" href="{E(img["page"])}" target="_blank" rel="noopener noreferrer"><span data-i18n>Image:</span> {E(img["credit"])}</a></figcaption>{badge}</figure>'

AR_MONTHS = ['يناير','فبراير','مارس','أبريل','مايو','يونيو','يوليو','أغسطس','سبتمبر','أكتوبر','نوفمبر','ديسمبر']
EN_MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
EN_DAYS = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
AR_DAYS = ['الاثنين','الثلاثاء','الأربعاء','الخميس','الجمعة','السبت','الأحد']

def news_date(iso, lang):
    d = datetime.fromisoformat(iso)
    return f'{d.day} {AR_MONTHS[d.month-1]} {d.year}' if lang == 'ar' else f'{d.day} {d.strftime("%b")} {d.year}'

def to_uae(iso):
    d = datetime.fromisoformat(str(iso).replace('Z', '+00:00'))
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(UAE_TZ)

def ymd(value, lang):
    """'2025-05-22' -> '22 May 2025' / '22 مايو 2025'; month-only values keep their precision; timestamps use UAE time."""
    s = str(value or '')
    m = re.match(r'^(\d{4})-(\d{2})(?:-(\d{2}))?(T.*)?$', s)
    if not m:
        return E(s)
    if m.group(4):
        d = to_uae(s)
        y, mo, day = d.year, d.month, d.day
    else:
        y, mo, day = int(m.group(1)), int(m.group(2)), int(m.group(3)) if m.group(3) else None
    mon = (AR_MONTHS if lang == 'ar' else EN_MONTHS)[mo - 1]
    return f'{day} {mon} {y}' if day else f'{mon} {y}'

WINDOW_NAMES = {
    'en': {'Q1': 'Q1', 'Q2': 'Q2', 'Q3': 'Q3', 'Q4': 'Q4', 'H1': 'H1', 'H2': 'H2', 'Summer': 'Summer', 'end': 'End of'},
    'ar': {'Q1': 'الربع الأول', 'Q2': 'الربع الثاني', 'Q3': 'الربع الثالث', 'Q4': 'الربع الرابع', 'H1': 'النصف الأول', 'H2': 'النصف الثاني', 'Summer': 'صيف', 'end': 'نهاية'},
}

def when(value, lang):
    """Release and announcement values for people (same output as when() in app.js): '2025-Q3' -> 'Q3 2025' /
    'الربع الثالث 2025', '2025-03-18' -> '18 Mar 2025' / '18 مارس 2025'. Sorting keeps using the raw value."""
    m = re.match(r'^(\d{4})-(Q[1-4]|H[12]|Summer|end)$', str(value or ''))
    if m:
        return f"{WINDOW_NAMES['ar' if lang == 'ar' else 'en'][m.group(2)]} {m.group(1)}"
    return ymd(value, lang)

def dated(value):
    return L(when(value, 'en'), when(value, 'ar')) if value else T('Not established')

def release_kind(kind):
    """The kind under an availability date; left out when it would only repeat "Not established" (same rule as releaseKind in app.js)."""
    return '' if kind in (None, '', 'Not established') else f'<small>{T(kind)}</small>'

def day_label(d, lang):
    return f'{AR_DAYS[d.weekday()]} {d.day} {AR_MONTHS[d.month-1]} {d.year}' if lang == 'ar' else f'{EN_DAYS[d.weekday()]} {d.day} {EN_MONTHS[d.month-1]} {d.year}'

NOUNS = {
    'product': (('product', 'products'), ('منتج واحد', 'منتجان', 'منتجات', 'منتجاً', 'منتج')),
    'headline': (('headline', 'headlines'), ('عنوان واحد', 'عنوانان', 'عناوين', 'عنواناً', 'عنوان')),
    'fact': (('key fact', 'key facts'), ('معلومة رئيسية واحدة', 'معلومتان رئيسيتان', 'معلومات رئيسية', 'معلومة رئيسية', 'معلومة رئيسية')),
    'source': (('source', 'sources'), ('مصدر واحد', 'مصدران', 'مصادر', 'مصدراً', 'مصدر')),
    'vetted': (('vetted source', 'vetted sources'), ('مصدر موثوق واحد', 'مصدران موثوقان', 'مصادر موثوقة', 'مصدراً موثوقاً', 'مصدر موثوق')),
}

def cnt(n, kind, lang):
    """Number + noun with English plurals and Arabic number agreement (same rules as countLabel in app.js)."""
    en, ar = NOUNS[kind]
    if lang != 'ar':
        return f'{n} {en[0] if n == 1 else en[1]}'
    if n == 1:
        return ar[0]
    if n == 2:
        return ar[1]
    r = n % 100
    return f'{n} {ar[2]}' if 3 <= r <= 10 else f'{n} {ar[3]}' if 11 <= r <= 99 else f'{n} {ar[4]}'

def T(value):
    # English text the page can translate client-side; unknown strings fall back to English.
    return f'<span data-i18n>{html.escape(str(value))}</span>'

def L(en, ar):
    """Both language versions of generated text (already escaped); CSS shows the one matching <html lang>."""
    return f'<span data-lang="en">{en}</span><span data-lang="ar">{ar}</span>'

def NA(value, fmt=lambda v: E(v)):
    return T('Not listed') if value is None or value == '' else fmt(value)

def EN(value):
    """English-only data inside Arabic pages: marked so screen readers use English pronunciation."""
    return f'<span lang="en">{E(value)}</span>'

# Field names used by scripts/refresh.py in its automatic change notes, in words and with units.
FIELD_WORDS = {'power_w': ('power', '{} W'), 'memory_gb': ('memory', '{} GB'), 'bandwidth_tbs': ('memory bandwidth', '{} TB/s'), 'msrp_usd': ('launch price', '${}')}

def change_text(summary):
    """'GeForce RTX 5070: power_w changed from None to 250' -> 'GeForce RTX 5070: power changed from not listed to 250 W'."""
    m = re.match(r'^(.+): (\w+) changed from (.+) to (.+)$', str(summary))
    if not m or m.group(2) not in FIELD_WORDS:
        return str(summary)
    word, unit = FIELD_WORDS[m.group(2)]
    show = lambda v: 'not listed' if v in ('None', '') else unit.format(v)
    return f'{m.group(1)}: {word} changed from {show(m.group(3))} to {show(m.group(4))}'

def product(p):
    sources = ' '.join(f'<a href="{E(s["url"])}" target="_blank" rel="noopener noreferrer">{E(s["label"])}</a>' for s in p['sources'])
    power = NA(p['power_w'], lambda v: f'{v:g} W')
    bandwidth = NA(p['bandwidth_tbs'], lambda v: f'{v:g} TB/s') + (f'<small lang="en">{E(p["bandwidth_note"])}</small>' if p['bandwidth_note'] else '')
    price = NA(p['msrp_usd'], lambda v: f'${v:,.0f}')
    release = dated(p['release'])
    announced = dated(p['announcement'])
    cooling = NA(p['cooling'], T)
    use_ar = f' data-ar="{E(p["use_ar"])}"' if p['use_ar'] else ''
    shot = image_block(p, f'<span class="vbadge">{p["vendor"]}</span>')
    vendor = '' if shot else f'<span class="vendor">{p["vendor"]}</span> · '
    return f'''<article class="product {p['vendor'].lower()}" id="p-{E(p['id'])}" data-product="{E(p['id'])}">{shot}
    <div class="c-body"><p class="c-eye">{vendor}{T(p['level'])} · {T(p['type'])}</p><h3><bdi lang="en">{E(p['model'])}</bdi></h3><p class="architecture"><bdi lang="en">{E(p['architecture'])}</bdi></p><p class="use"{use_ar}>{E(p['use'])}</p>
    <p class="memory"><strong><bdi lang="en">{E(p['memory'])}</bdi></strong><small>{T(p['memory_scope'])}</small><span class="fit" hidden></span></p>
    <dl class="facts"><div><dt data-i18n>Availability / target</dt><dd>{release}{release_kind(p['release_kind'])}</dd></div><div><dt data-i18n>Announced / launched</dt><dd>{announced}</dd></div><div><dt data-i18n>Bandwidth</dt><dd>{bandwidth}</dd></div><div><dt data-i18n>Power</dt><dd>{power}<small>{T(p['power_note'])}</small></dd></div><div><dt data-i18n>AI compute</dt><dd>{NA(p['ai_compute'], EN)}</dd></div><div><dt data-i18n>Launch price</dt><dd>{price}</dd></div>{price_block(p)}</dl></div>
    <details><summary data-i18n>Notes and official sources</summary><dl class="more"><div><dt data-i18n>Form factor</dt><dd>{NA(p['form_factor'], EN)}</dd></div><div><dt data-i18n>Cooling</dt><dd>{cooling}</dd></div><div><dt data-i18n>Interconnect</dt><dd>{NA(p['interconnect'], EN)}</dd></div><div><dt data-i18n>Content reviewed</dt><dd>{dated(p['source_reviewed'])}</dd></div></dl><p lang="en" dir="auto">{E(p['notes'])}</p><div class="sources" lang="en">{sources}</div></details>
    <label class="cmp"><input type="checkbox" class="cmp-toggle" value="{E(p['id'])}"><span data-i18n>Compare</span></label></article>'''

# ---------- brand slot ----------

def sanitize_svg(text, prefix='logo-'):
    """Inline-safe copy of an owner-supplied SVG: no scripts, event handlers, foreign HTML or external references.
    Ids are prefixed so the mark cannot collide with ids on the page."""
    s = re.sub(r'<\?xml.*?\?>|<!DOCTYPE[^>]*>|<!--.*?-->', '', text, flags=re.S | re.I)
    s = re.sub(r'<(script|foreignObject|iframe|object|embed|metadata)\b.*?</\1\s*>', '', s, flags=re.S | re.I)
    s = re.sub(r'<(script|foreignObject|iframe|object|embed|metadata)\b[^>]*/?>', '', s, flags=re.I)
    s = re.sub(r'</?a\b[^>]*>', '', s, flags=re.I)  # the mark already sits inside the home link
    s = re.sub(r'\s+on[a-z0-9_-]*\s*=\s*("[^"]*"|\'[^\']*\'|[^\s>]+)', '', s, flags=re.I)
    # Only same-document references and embedded raster data survive; anything else would be a remote request or a script URL.
    s = re.sub(r'\s+(?:xlink:)?href\s*=\s*("(?!#|data:image/(?:png|jpeg|gif|webp);)[^"]*"|\'(?!#|data:image/(?:png|jpeg|gif|webp);)[^\']*\')', '', s, flags=re.I)
    s = re.sub(r'url\(\s*(["\']?)(?!#)[^)]*\)', 'none', s, flags=re.I)
    s = re.sub(r'@import[^;]*;?', '', s, flags=re.I)
    start, end = s.lower().find('<svg'), s.lower().rfind('</svg>')
    if start < 0 or end < start:
        return ''
    s = s[start:end + 6]
    if prefix:
        for i in sorted(set(re.findall(r'\bid\s*=\s*["\']([^"\']+)["\']', s)), key=len, reverse=True):
            q = re.escape(i)
            s = re.sub(r'(\bid\s*=\s*["\'])' + q + r'(["\'])', r'\g<1>' + prefix + i + r'\2', s)
            s = re.sub(r'(url\(\s*["\']?#)' + q + r'(["\']?\s*\))', r'\g<1>' + prefix + i + r'\2', s)
            s = re.sub(r'(href\s*=\s*["\']#)' + q + r'(["\'])', r'\g<1>' + prefix + i + r'\2', s)
    return s.strip()

def svg_uri(svg):
    """data: URI for an SVG shown as an image. Image decoding is strict XML, so the root gets the SVG (and xlink)
    namespace if the file left it out. Quotes and angle brackets are percent-encoded: the URI can't end its attribute."""
    def ns(m):
        attrs = m.group(1)
        if not re.search(r'\sxmlns\s*=', attrs):
            attrs += ' xmlns="http://www.w3.org/2000/svg"'
        if 'xlink:' in svg and not re.search(r'\sxmlns:xlink\s*=', attrs):
            attrs += ' xmlns:xlink="http://www.w3.org/1999/xlink"'
        return '<svg' + attrs + '>'
    svg = re.sub(r'^<svg\b([^>]*?)\s*(?<!/)>', ns, svg, count=1)
    return 'data:image/svg+xml,' + quote(svg, safe=" :/=;,()-.")

def brand_assets(brand_dir=BRAND_DIR):
    """(logo <img> markup or '', favicon data URI). The logo is shown before the wordmark; nothing is invented when absent.
    Both are loaded as images (never inlined), and an SVG image cannot run script or load anything else, whatever
    slips past sanitize_svg; the sanitiser only keeps the file tidy."""
    logo, icon = '', PLACEHOLDER_FAVICON
    lp, fp = brand_dir / 'logo.svg', brand_dir / 'favicon.svg'
    if lp.exists():
        svg = sanitize_svg(lp.read_text(encoding='utf-8'), prefix='')
        if svg:
            logo = f'<img class="brand-logo" src="{svg_uri(svg)}" alt="">'
    if fp.exists():
        icon = sanitize_svg(fp.read_text(encoding='utf-8'), prefix='') or PLACEHOLDER_FAVICON
    return logo, svg_uri(icon)

def copy_brand_images(dest, brand_dir=BRAND_DIR):
    """Raster brand files (apple-touch-icon.png, icon-32.png, icon-512.png, og.png) are served as files next to the page:
    the home-screen icon, the PNG tab icon and the share preview are fetched by URL, so they can't be data URIs."""
    pngs = sorted(brand_dir.glob('*.png'))
    if pngs:
        dest.mkdir(parents=True, exist_ok=True)
        for f in pngs:
            shutil.copyfile(f, dest / f.name)
    return [f.name for f in pngs]

# ---------- owner choices (data/site.json) ----------

def load_site(products, facts, path=None):
    """Featured products and UAE highlights from data/site.json. Unknown ids are skipped and gaps filled, so a bad edit never breaks the build."""
    path = path or ROOT / 'data' / 'site.json'
    try:
        site = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        site = {}
    if not isinstance(site, dict):
        site = {}
    pick = lambda ids, known, n: list(dict.fromkeys(i for i in (ids if isinstance(ids, list) else []) if isinstance(i, str) and i in known))[:n]
    by_id = {p['id']: p for p in products}
    featured = pick(site.get('featured_products'), by_id, 3)
    for level in ('Personal', 'Data center', 'Rack scale', 'Workstation', 'Enterprise'):
        if len(featured) >= 3:
            break
        extra = next((p['id'] for p in products if p['level'] == level and p['id'] not in featured and p.get('image') and p.get('price_view')), None)
        if extra:
            featured.append(extra)
    fact_ids = {f['id']: f for f in facts}
    highlights = pick(site.get('uae_highlights'), fact_ids, 2)
    for f in sorted(facts, key=lambda f: str(f.get('as_of') or ''), reverse=True):
        if len(highlights) >= 2:
            break
        if f['id'] not in highlights:
            highlights.append(f['id'])
    return [by_id[i] for i in featured], [fact_ids[i] for i in highlights]

# ---------- news helpers ----------

def news_items(news, sources):
    src = {s['id'] for s in sources}
    # news.py only keeps https links from allowed hosts; this guards against a hand edit of news.json.
    items = [i for i in (news or {}).get('items', []) if i.get('source') in src and https(i.get('url'))]
    return sorted(items, key=lambda i: i['published'], reverse=True)

def in_lang(i, lang):
    # Arabic list = native Arabic headlines + English ones that carry an AI translation.
    return i['lang'] == 'ar' or bool(i.get('title_ar')) if lang == 'ar' else i['lang'] == 'en'

def regions(i, src):
    r = []
    if src[i['source']]['region'] == 'global':
        r.append('global')
    if i.get('uae'):
        r.append('uae')
    return r or ['global']

def varied(pool, per, limit):
    """Newest first, at most `per` headlines per source so one outlet can't fill the list."""
    seen, out = {}, []
    for i in pool:
        seen[i['source']] = seen.get(i['source'], 0) + 1
        if seen[i['source']] <= per:
            out.append(i)
        if len(out) >= limit:
            break
    return out

def headline_text(i, lang):
    title = i['title_ar'] if lang == 'ar' and i['lang'] == 'en' and i.get('title_ar') else i['title']
    mt = '<span class="mt">ترجمة آلية</span>' if lang == 'ar' and i['lang'] == 'en' else ''
    return title, mt

SUMMARY_LABEL = {'ai': {'en': 'AI summary', 'ar': 'ملخص بالذكاء الاصطناعي'}, 'publisher': {'en': 'From the publisher', 'ar': 'من الناشر'}}

def summary_of(i, lang):
    """(text, kind) shown under a headline in one language: the AI summary in that language, else the publisher's own
    excerpt when the item is in that language (an English excerpt never stands in for Arabic), else (None, None)."""
    text = i.get(f'summary_{lang}')
    if i.get('summary_source') == 'ai' and text:
        return text, 'ai'
    if i.get('excerpt') and i['lang'] == lang:
        return i['excerpt'], 'publisher'
    return None, None

def news_card(i, lang, src, tags=''):
    """One headline: the title as plain text, a short summary with who wrote it, then a small link to the original
    article with the publisher's name, and the date (UAE time)."""
    s, d = src[i['source']], to_uae(i['published'])
    title, mt = headline_text(i, lang)
    ar = lang == 'ar'
    text_dir = f'lang="{lang}" dir="{"rtl" if ar else "ltr"}"'
    text, kind = summary_of(i, lang)
    summary = f'<p class="n-sum" {text_dir}>{E(text)}</p><p class="n-by">{SUMMARY_LABEL[kind][lang]}</p>' if text else ''
    name = s['name_ar'] if ar else s['name']
    when = f'{d.day} {AR_MONTHS[d.month-1]}، <bdi>{d:%H:%M}</bdi>' if ar else f'{d.day} {EN_MONTHS[d.month-1]}, <bdi>{d:%H:%M}</bdi>'
    link = f'<a class="n-src" href="{E(i["url"])}" target="_blank" rel="noopener noreferrer">{"المصدر" if ar else "Source"}: {E(name)} <span class="n-ext" aria-hidden="true">↗</span></a>'
    return (f'<h4 class="n-title" {text_dir}>{E(title)}</h4>{summary}'
            f'<p class="n-meta">{link}<time datetime="{E(i["published"])}">{when}</time>{tags}{mt}</p>')

def heads(items, src, per, limit):
    """Compact headline cards for the home pillars, one list per language."""
    out = ''
    for lang in ('en', 'ar'):
        pool = varied([i for i in items if in_lang(i, lang)], per, limit)
        out += f'<ol class="heads" data-lang="{lang}">{"".join(f"<li>{news_card(i, lang, src)}</li>" for i in pool)}</ol>' if pool else f'<p class="muted" data-lang="{lang}">{"لا توجد عناوين حديثة." if lang == "ar" else "No recent headlines."}</p>'
    return out

REGION_TAG = {'en': {'global': 'Global', 'uae': 'UAE'}, 'ar': {'global': 'عالمي', 'uae': 'الإمارات'}}

def news_li(i, lang, src):
    reg = regions(i, src)
    tags = ''.join(f'<span class="tag {"uae" if r == "uae" else "glob"}">{REGION_TAG[lang][r]}</span>' for r in reg)
    return f'<li class="nitem" data-region="{" ".join(reg)}">{news_card(i, lang, src, tags)}</li>'

NEWS_NOTE = L('Summaries marked "AI summary" are machine-written from the article or the publisher\'s description and may contain mistakes. Follow the source link to read the full story.',
              'الملخصات الموسومة «ملخص بالذكاء الاصطناعي» مكتوبة آلياً من نص المقال أو من وصف الناشر، والعناوين الموسومة «ترجمة آلية» مترجمة آلياً، وقد تحتوي على أخطاء. اتبع رابط المصدر لقراءة الخبر كاملاً.')

def day_lists(items, src, empty_en, empty_ar):
    """Full headline lists, one per language, grouped by day in UAE time."""
    out = ''
    for lang in ('en', 'ar'):
        pool = [i for i in items if in_lang(i, lang)]
        if not pool:
            out += f'<p class="muted" data-lang="{lang}">{empty_ar if lang == "ar" else empty_en}</p>'
            continue
        body, cur = '', None
        for i in pool:
            day = to_uae(i['published']).date()
            if day != cur:
                body += ('</ol></section>' if cur else '') + f'<section class="nday"><h3>{day_label(day, lang)}</h3><ol>'
                cur = day
            body += news_li(i, lang, src)
        out += f'<div class="nlist" data-lang="{lang}">{body}</ol></section></div>'
    return out

# ---------- shared markup ----------

# The UAE flag marks the UAE AI area: red band at the hoist (a quarter of the width), then green, white and black
# stripes, in the official 1:2 proportion. It is shown at sizes where the band and the stripes fall on whole pixels
# (24x12, 36x18) and drawn with crisp edges; the thin frame that keeps the white stripe visible on light backgrounds
# and the black one on dark backgrounds is a CSS box-shadow outside the flag, not a stroke over the colours.
# Flags are not mirrored, so it has no "flip" class: the red band stays on the left in Arabic too.
UAE_FLAG = ('<svg class="flag" viewBox="0 0 24 12" width="24" height="12" shape-rendering="crispEdges" aria-hidden="true" focusable="false">'
            '<rect width="24" height="12" fill="#FFFFFF"/><rect x="6" width="18" height="4" fill="#009739"/>'
            '<rect x="6" y="8" width="18" height="4" fill="#000000"/><rect width="6" height="12" fill="#EF3340"/></svg>')

ICON = {
    'hw': '<svg viewBox="0 0 24 24" width="21" height="21" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="6" y="6" width="12" height="12" rx="2"/><rect x="9.5" y="9.5" width="5" height="5" rx="1"/><path d="M9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4"/></svg>',
    'news': '<svg viewBox="0 0 24 24" width="21" height="21" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 5h13v14H6a2 2 0 0 1-2-2z"/><path d="M17 9h3v8a2 2 0 0 1-2 2"/><path d="M8 9h5M8 13h5M8 16h3"/></svg>',
    'uae': UAE_FLAG,
    'flag': UAE_FLAG,
    'contact': '<svg viewBox="0 0 24 24" width="21" height="21" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3.5 6.5 8.5 6.5 8.5-6.5"/></svg>',
    'mail': '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3.5 6.5 8.5 6.5 8.5-6.5"/></svg>',
    'home': '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 11.5 12 4l9 7.5"/><path d="M5.5 10v10h13V10"/></svg>',
    'arrow': '<svg class="flip" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6"/></svg>',
    'back': '<svg class="flip" viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M19 12H5M11 6l-6 6 6 6"/></svg>',
    'ig': '<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="5" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="12" cy="12" r="4" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="17.5" cy="6.5" r="1.3" fill="currentColor"/></svg>',
    'theme': '<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><circle cx="12" cy="12" r="8.5" fill="none" stroke="currentColor" stroke-width="2"/><path d="M12 3.5a8.5 8.5 0 0 1 0 17z" fill="currentColor"/></svg>',
    'compare': '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><rect x="3" y="4" width="7" height="16" rx="1.5"/><rect x="14" y="4" width="7" height="16" rx="1.5"/></svg>',
    'run': '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/></svg>',
    'timeline': '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M3 12h18"/><circle cx="7" cy="12" r="2"/><circle cx="14" cy="12" r="2"/><circle cx="20" cy="12" r="1"/></svg>',
    'shield': '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3l7 3v5c0 5-3.5 8.5-7 10-3.5-1.5-7-5-7-10V6z"/><path d="M9 12l2 2 4-4"/></svg>',
    'calendar': '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/></svg>',
    'check': '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 6L9 17l-5-5"/></svg>',
    'clock': '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>',
}
NAV = {'hardware': 'Hardware', 'news': 'AI news', 'uae': 'UAE AI', 'contact': 'Contact'}
CONTACT_LEAD = 'Questions, corrections or partnership ideas? Email us.'

def follow_btn():
    """The Qahwa & AI follow button: the same markup in the hero, every view header, the contact card and the footer."""
    return (f'<a class="ig follow-btn" href="{INSTAGRAM}" target="_blank" rel="noopener noreferrer">{ICON["ig"]}'
            '<span data-i18n>Follow Qahwa &amp; AI</span> <bdi class="handle" lang="en">@qahwa.w.ai</bdi></a>')

def ihead(view, title, lead, extra='', follow=True):
    """Inner view header: breadcrumb, title (the UAE flag before "UAE AI"), lead, Back to overview and the follow button.
    The contact view leaves the follow button to its card."""
    heading = f'<span class="ih-flag">{UAE_FLAG}</span><span data-i18n>{title}</span>' if view == 'uae' else f'<span data-i18n>{title}</span>'
    acts = f'<a class="back" href="#home">{ICON["back"]}<span data-i18n>Back to overview</span></a>' + (follow_btn() if follow else '')
    return (f'<div class="ihead ih-{view}"><nav class="crumbs" aria-label="Breadcrumb" data-i18n-aria="Breadcrumb"><a href="#home" data-i18n>Overview</a><span aria-hidden="true">/</span><span aria-current="page" data-i18n>{NAV[view]}</span></nav>'
            f'<div class="ihead-row"><div><h1 id="{view}-title" tabindex="-1">{heading}</h1><p class="lead">{lead}</p></div>'
            f'<div class="ihead-acts">{acts}</div></div>{extra}</div>')

def schedule_times(data):
    """'07:15 and 19:15 Asia/Dubai' -> ['07:15', '19:15'] (the publish workflow's cron, in UAE time; checked by a test)."""
    return re.findall(r'\b\d{1,2}:\d{2}\b', str((data or {}).get('schedule') or ''))

def schedule_phrase(data, lang):
    """How often the site refreshes, in words: 'twice a day' / 'مرتين يومياً' (the times themselves are not shown)."""
    n = len(schedule_times(data))
    if not n:
        return ''
    if lang == 'ar':
        return {1: 'مرة يومياً', 2: 'مرتين يومياً'}.get(n, f'{n} مرات يومياً')
    return {1: 'once a day', 2: 'twice a day'}.get(n, f'{n} times a day')

def fresh_line(feed, data=None):
    """'Updated 26 Sep 2026 · twice a day': when the headlines last changed and how often they do. No fetch statistics."""
    if not feed or not feed.get('updated_at'):
        return T('Headlines appear after the first scheduled update.')
    en, ar = schedule_phrase(data, 'en'), schedule_phrase(data, 'ar')
    return L(f'Updated {ymd(feed["updated_at"], "en")}' + (f' · {en}' if en else ''), f'آخر تحديث {ymd(feed["updated_at"], "ar")}' + (f' · {ar}' if ar else ''))

def xnav(c, views):
    cards = {
        'hardware': ('', ICON['hw'], L(E(f'Compare {cnt(c["n_products"], "product", "en")} from NVIDIA and AMD'), f'قارن {cnt(c["n_products"], "product", "ar")} من NVIDIA وAMD')),
        'news': (' x-news', ICON['news'], L(E(f'{cnt(c["n_headlines"], "headline", "en")} from {cnt(c["n_active_sources"], "source", "en")}'), f'{cnt(c["n_headlines"], "headline", "ar")} من {cnt(c["n_active_sources"], "source", "ar")}')),
        'uae': (' x-uae', ICON['uae'], L(E(f'{cnt(c["n_facts"], "fact", "en")} and UAE headlines'), f'{cnt(c["n_facts"], "fact", "ar")} وعناوين إماراتية')),
        'contact': (' x-contact', ICON['contact'], T(CONTACT_LEAD)),
    }
    out = ''.join(f'<a class="xcard{cls}" href="#{v}"><span class="p-icon{" p-flag" if v == "uae" else ""}" aria-hidden="true">{icon}</span><span><b data-i18n>{NAV[v]}</b><span class="x-sub">{sub}</span></span><span class="x-arr">{ICON["arrow"]}</span></a>' for v in views for cls, icon, sub in [cards[v]])
    return f'<nav class="xnav" aria-label="Other areas" data-i18n-aria="Other areas">{out}</nav>'

def stat(value, label):
    return f'<div class="stat"><dt data-i18n>{label}</dt><dd><bdi>{value}</bdi></dd></div>'

# ---------- views ----------

def home_view(c):
    src, items = c['src'], c['items']
    ps = c['products']
    nv, amd = c['vendors'].get('NVIDIA', 0), c['vendors'].get('AMD', 0)
    total = max(len(ps), 1)
    minis = ''
    for p in c['featured']:
        v = p['price_view']
        img = f'<img src="{E(p["image"]["file"])}" alt="" loading="lazy" decoding="async">' if p.get('image') and p['image'].get('file') else ''
        if v:
            amount, kind = (v['usd'], v['usd_kind']) if v['usd'] else (v['aed'], v['aed_kind'])
            price = f'<span class="m-price"><span data-i18n>Approx.</span> <bdi>{E(amount)}</bdi><span class="m-kind">{T(kind) + " · " if kind else ""}<span data-i18n>checked</span> {L(ymd(v["checked"], "en"), ymd(v["checked"], "ar"))}</span></span>'
        else:
            price = f'<span class="m-price">{T("Not publicly priced")}</span>'
        minis += (f'<li class="mini"><a href="#p-{E(p["id"])}" data-route="hardware/p/{E(p["id"])}"><span class="thumb">{img}</span><span class="m-text">'
                  f'<span class="m-name"><i class="vdot{" amd" if p["vendor"] == "AMD" else ""}" aria-hidden="true"></i><bdi>{E(p["model"])}</bdi></span>'
                  f'<span class="m-meta"><bdi>{E(p["memory"])}</bdi> · {T(p["level"])}</span>{price}</span></a></li>')
    levels = ''.join(f'<a class="chip" href="#hardware" data-route="hardware/level/{E(quote(l))}">{T(l)} <span class="n">{c["levels"][l]}</span></a>' for l in LEVELS if c['levels'].get(l))
    en_items = [i for i in items if in_lang(i, 'en')]
    ar_items = [i for i in items if in_lang(i, 'ar')]
    reg_n = lambda pool, r: sum(r in regions(i, src) for i in pool)
    browse = ''.join(f'<a class="chip" href="#news" data-route="news/{r}"><span data-i18n>{label}</span> <span class="n">{L(reg_n(en_items, r), reg_n(ar_items, r))}</span></a>' for r, label in (('global', 'Global'), ('uae', 'UAE')))
    uae_items = [i for i in items if i.get('uae')]
    u_en, u_ar = sum(in_lang(i, 'en') for i in uae_items), sum(in_lang(i, 'ar') for i in uae_items)
    uae_en_ar = L(f'{u_en} · {u_ar}', f'{u_ar} · {u_en}')
    facts = ''.join(f'<a class="fmini" href="#fact-{E(f["id"])}" data-route="uae/f/{E(f["id"])}"><span class="f-date">{L("As of " + ymd(f["as_of"], "en"), "بتاريخ " + ymd(f["as_of"], "ar"))}</span><h4>{L(E(f["title_en"]), E(f["title_ar"]))}</h4><p>{L(E(f["text_en"]), E(f["text_ar"]))}</p></a>' for f in c['highlights'])
    health = c['check_health']
    checked_en, checked_ar = ymd(c['last_check'], 'en') if c['last_check'] else '—', ymd(c['last_check'], 'ar') if c['last_check'] else '—'
    trust3 = (L(E(f'{cnt(health["attempted_sources"], "source", "en")} checked'), f'فحص {cnt(health["attempted_sources"], "source", "ar")}'),
              L(f'Hardware sources last checked {checked_en}.', f'آخر فحص لمصادر العتاد في {checked_ar}.')) if health else (
              T('Official sources checked'), T('Hardware sources are checked twice a day.'))
    trust4 = T('Each summary says whether AI or the publisher wrote it, and every headline has a source link to the original article.')
    cta = lambda href, label: f'<div class="p-foot"><a class="cta" href="#{href}"><span data-i18n>{label}</span><span class="arr">{ICON["arrow"]}</span></a></div>'
    en_ar = L(f'{len(en_items)} · {len(ar_items)}', f'{len(ar_items)} · {len(en_items)}')
    return f'''<div id="home" class="view" data-view="home">
<section class="hero" aria-labelledby="home-title"><div class="hero-main"><p class="eyebrow"><bdi>NVIDIA + AMD</bdi> · <span data-i18n>AI news</span> · <span data-i18n>UAE</span></p><h1 id="home-title" tabindex="-1"><bdi lang="en">{SITE_NAME}</bdi></h1><p class="hero-tag" data-i18n>Decoding the gaps in AI knowledge</p><p class="promise" data-i18n>Compare NVIDIA and AMD AI hardware, catch up on the latest AI news, and follow what the UAE is building — with sources and dates shown throughout.</p></div>
<div class="hero-side"><p class="fresh"><span class="pulse" aria-hidden="true"></span><span>{fresh_line(c['feed'], c['data'])}</span></p>{follow_btn()}</div>
<nav class="jump" aria-label="The three areas" data-i18n-aria="The three areas"><a href="#hardware"><i class="j-hw" aria-hidden="true"></i><b data-i18n>Hardware</b><span>{L(cnt(len(ps), "product", "en"), cnt(len(ps), "product", "ar"))}</span></a><a href="#news"><i class="j-news" aria-hidden="true"></i><b data-i18n>News</b><span>{L(cnt(c["n_headlines"], "headline", "en"), cnt(c["n_headlines"], "headline", "ar"))}</span></a><a href="#uae"><i class="j-flag" aria-hidden="true">{UAE_FLAG}</i><b data-i18n>UAE</b><span>{L(cnt(c["n_facts"], "fact", "en"), cnt(c["n_facts"], "fact", "ar"))}</span></a></nav></section>
<section class="pillars" aria-label="The three areas of the site" data-i18n-aria="The three areas of the site">
<article class="pillar p-hw" aria-labelledby="p1-title"><div class="p-head"><div class="kick"><span class="p-icon" aria-hidden="true">{ICON['hw']}</span><span>01</span></div><h2 id="p1-title"><a href="#hardware" data-i18n>Hardware</a></h2><p class="p-lead" data-i18n>NVIDIA and AMD GPUs, desktop systems, servers and racks, side by side.</p></div>
<div class="p-body"><dl class="stats">{stat(len(ps), 'products')}{stat(len(c['levels']), 'levels')}{stat(c['n_priced'], 'with approx. price')}</dl>
<div class="split-wrap"><div class="split" role="img" aria-label="NVIDIA {nv}, AMD {amd}"><i class="s-nv" style="width:{nv / total * 100:.2f}%"></i><i class="s-amd" style="width:{amd / total * 100:.2f}%"></i></div><div class="split-legend"><a class="lg" href="#hardware" data-route="hardware/vendor/NVIDIA"><bdi>NVIDIA <b>{nv}</b></bdi></a><a class="lg amd" href="#hardware" data-route="hardware/vendor/AMD"><bdi>AMD <b>{amd}</b></bdi></a></div></div>
<div><h3 class="p-sub"><span data-i18n>Featured</span><small data-i18n>Prices approximate</small></h3><ul class="minis">{minis}</ul></div>
<div><h3 class="p-sub"><span data-i18n>Browse by level</span></h3><div class="lvl">{levels}</div></div>
<div class="quick"><a href="#hardware" data-route="hardware/compare">{ICON['compare']}<span data-i18n>Compare</span></a><a href="#estimator" data-route="hardware/run">{ICON['run']}<span data-i18n>What can it run?</span></a><a href="#hardware" data-route="hardware/timeline">{ICON['timeline']}<span data-i18n>Timeline</span></a></div></div>
{cta('hardware', 'Open hardware')}</article>
<article class="pillar p-news" aria-labelledby="p2-title"><div class="p-head"><div class="kick"><span class="p-icon" aria-hidden="true">{ICON['news']}</span><span>02</span></div><h2 id="p2-title"><a href="#news" data-i18n>AI news</a></h2><p class="p-lead">{L(E(f"The latest AI headlines in English and Arabic, from the {cnt(c['n_sources'], 'vetted', 'en')} we follow."), f"أحدث عناوين الذكاء الاصطناعي بالعربية والإنجليزية، من {cnt(c['n_sources'], 'vetted', 'ar')} نتابعها.")}</p></div>
<div class="p-body"><dl class="stats">{stat(c['n_headlines'], 'headlines')}{stat(en_ar, 'English · Arabic')}{stat(c['n_sources'], 'sources')}</dl>
<p class="live"><span class="pulse" aria-hidden="true"></span><span>{fresh_line(c['feed'], c['data'])}</span></p>
<div><h3 class="p-sub"><span data-i18n>Latest headlines</span><small data-i18n>Times in UAE time</small></h3>{heads([i for i in items if 'global' in regions(i, src)], src, 1, 4)}</div>
<div><h3 class="p-sub"><span data-i18n>Browse</span></h3><div class="lvl">{browse}</div></div></div>
{cta('news', 'Open AI news')}</article>
<article class="pillar p-uae" aria-labelledby="p3-title"><div class="p-head"><div class="kick"><span class="p-icon p-flag" aria-hidden="true">{ICON['uae']}</span><span>03</span></div><h2 id="p3-title"><a href="#uae" data-i18n>UAE AI</a></h2><p class="p-lead" data-i18n>What the UAE is building in AI: strategy, compute and models, each fact with its source.</p></div>
<div class="p-body"><dl class="stats">{stat(c['n_facts'], 'key facts')}{stat(len(uae_items), 'UAE headlines')}{stat(uae_en_ar, 'English · Arabic')}</dl>
<div><h3 class="p-sub"><span data-i18n>Highlights</span><small>{L('Checked ' + ymd(c['uae_checked'], 'en'), 'تم التحقق في ' + ymd(c['uae_checked'], 'ar'))}</small></h3><div class="fminis">{facts}</div></div>
<div><h3 class="p-sub"><span data-i18n>Latest UAE headlines</span><small data-i18n>Twice a day</small></h3>{heads(uae_items, src, 2, 3)}</div></div>
{cta('uae', 'Open UAE AI')}</article></section>
<section class="trust" aria-labelledby="trust-title"><h2 id="trust-title" class="sr-only" data-i18n>Why trust this</h2>
<div><span class="t-ic" aria-hidden="true">{ICON['shield']}</span><div><h3 data-i18n>Official sources</h3><p>{L(f"All {len(ps)} products link to official NVIDIA or AMD pages.", f"كل المنتجات الـ{len(ps)} مرتبطة بصفحات رسمية من NVIDIA أو AMD.")}</p></div></div>
<div><span class="t-ic" aria-hidden="true">{ICON['calendar']}</span><div><h3 data-i18n>Dated prices</h3><p data-i18n>Prices are approximate, labelled by kind, with the date they were checked.</p></div></div>
<div><span class="t-ic" aria-hidden="true">{ICON['check']}</span><div><h3>{trust3[0]}</h3><p>{trust3[1]}</p></div></div>
<div><span class="t-ic" aria-hidden="true">{ICON['clock']}</span><div><h3 data-i18n>News twice a day</h3><p>{trust4}</p></div></div></section>
</div>'''

def hardware_head(c, data):
    n = len(c['products'])
    lead = L(E(f'{cnt(n, "product", "en")} from NVIDIA and AMD, from desktop GPUs to rack-scale systems. Prices are approximate, dated snapshots, not offers.'),
             f'{cnt(n, "product", "ar")} من NVIDIA وAMD، من بطاقات الرسوميات المكتبية إلى الأنظمة على مستوى الرف. الأسعار لقطات تقريبية مؤرّخة وليست عروض بيع.')
    pc = c['prices_checked']
    span = lambda lang: ymd(pc[0], lang) if len(pc) == 1 else f'{ymd(pc[0], lang)} – {ymd(pc[-1], lang)}'
    prices = L(span('en'), span('ar')) if pc else '—'
    # When the content and the prices were last updated; how and when the checks run is backend detail.
    status = (f'<p class="statusbar"><span><b data-i18n>Content updated:</b> {L(ymd(data["updated_at"], "en"), ymd(data["updated_at"], "ar"))}</span>'
              f'<span><b data-i18n>Prices checked:</b> {prices}</span></p>')
    downloads = ('<div class="downloads" role="group" aria-label="Download and share" data-i18n-aria="Download and share"><a href="AI_Hardware_Atlas_2026_One_Page.pdf" download data-i18n>One-page PDF</a>'
                 '<button type="button" id="csv" class="js-only" data-i18n>Export CSV</button><button type="button" id="share" class="js-only" data-i18n>Copy link</button><button type="button" id="print" class="js-only" data-i18n>Print table</button></div>')
    return ihead('hardware', 'AI Hardware Atlas', lead, status + downloads)

def news_view(c):
    src, items, feed = c['src'], c['items'], c['feed']
    if not c['sources']:
        return ''
    en_items = [i for i in items if in_lang(i, 'en')]
    ar_items = [i for i in items if in_lang(i, 'ar')]
    reg_n = lambda pool, r: sum(r in regions(i, src) for i in pool) if r else len(pool)
    chips = ''.join(f'<button type="button" class="chip" data-region-chip="{r}" aria-pressed="{str(r == "").lower()}"><span data-i18n>{label}</span> <span class="n">{L(reg_n(en_items, r), reg_n(ar_items, r))}</span></button>' for r, label in (('', 'All'), ('global', 'Global'), ('uae', 'UAE')))
    side = stat(c['n_headlines'], 'headlines') + stat(len(en_items), 'English') + stat(len(ar_items), 'Arabic')
    lead = L(E(f'Headlines from the {cnt(c["n_sources"], "vetted", "en")} we follow, official and news, in English and Arabic, each with a short summary where one is available and a link to the original article.'),
             f'عناوين من {cnt(c["n_sources"], "vetted", "ar")} نتابعها، بين رسمي وإخباري، بالعربية والإنجليزية، مع ملخص قصير حين يتوفر ورابط إلى المقال الأصلي.')
    return f'''<section id="news" class="view v-news" data-view="news" aria-labelledby="news-title">
{ihead('news', 'AI news', lead, f'<p class="ifresh"><span class="pulse" aria-hidden="true"></span><span>{fresh_line(feed, c["data"])}</span></p>')}
<div class="split-layout"><aside class="side" aria-labelledby="n-side-h"><div class="panel"><h2 class="side-h" id="n-side-h" data-i18n>Headlines at a glance</h2>
<div class="js-only"><span class="fl" id="fl-nreg" data-i18n>Region</span><div class="chips" role="group" aria-labelledby="fl-nreg">{chips}</div></div>
<dl class="side-stats">{side}</dl></div></aside>
<div class="main-col"><h2 class="sr-only" data-i18n>Headlines</h2><div class="bar"><p class="count" id="news-count" aria-live="polite">{L(cnt(len(en_items), "headline", "en"), cnt(len(ar_items), "headline", "ar"))}</p><p class="muted" data-i18n>Times in UAE time</p></div>
{day_lists(items, src, 'No recent English headlines.', 'لا توجد عناوين عربية حديثة.')}
<div class="more-row js-only"><button type="button" class="btn" id="news-more" hidden data-i18n>Show more</button></div>
<p class="muted n-note">{NEWS_NOTE}</p>
</div></div>
{xnav(c, ('hardware', 'uae'))}
</section>'''

def uae_view(c):
    uae, src, items = c['uae'], c['src'], c['items']
    if not uae:
        return ''
    cards = ''
    for f in sorted(uae['facts'], key=lambda f: str(f.get('as_of') or ''), reverse=True):
        hw = ''.join(f'<a class="chip" href="#hardware" data-q="{E(h)}"><bdi>{E(h)}</bdi></a>' for h in f.get('hardware', []))
        links = ''.join(f'<a href="{E(s["url"])}" target="_blank" rel="noopener noreferrer" lang="en" dir="ltr">{E(s["label"])}</a>' for s in f['sources'])
        chips = f'<div class="chips">{hw}</div>' if hw else ''
        cards += (f'<article class="fact" id="fact-{E(f["id"])}" data-fact="{E(f["id"])}"><span class="f-date">{L("As of " + ymd(f["as_of"], "en"), "بتاريخ " + ymd(f["as_of"], "ar"))}</span>'
                  f'<h3>{L(E(f["title_en"]), E(f["title_ar"]))}</h3><p>{L(E(f["text_en"]), E(f["text_ar"]))}</p>'
                  f'{chips}<p class="f-src"><span data-i18n>Sources</span>{links}</p></article>')
    uae_items = [i for i in items if i.get('uae')]
    n_en, n_ar = sum(in_lang(i, 'en') for i in uae_items), sum(in_lang(i, 'ar') for i in uae_items)
    # Each headline names its publisher and links to the article, so there is no separate list of newsrooms.
    side = stat(len(uae_items), 'headlines') + stat(n_en, 'English') + stat(n_ar, 'Arabic')
    lead = L(f'Key facts checked {ymd(uae["checked"], "en")} against their sources, plus AI headlines about the UAE or from UAE newsrooms, updated twice a day.',
             f'حقائق رئيسية تم التحقق منها بتاريخ {ymd(uae["checked"], "ar")} من مصادرها، مع عناوين الذكاء الاصطناعي عن الإمارات أو من غرف الأخبار الإماراتية، تُحدَّث مرتين يومياً.')
    return f'''<section id="uae" class="view v-uae" data-view="uae" aria-labelledby="uae-title">
{ihead('uae', 'UAE AI', lead, f'<p class="ifresh"><span class="pulse" aria-hidden="true"></span><span>{fresh_line(c["feed"], c["data"])}</span></p>')}
<div class="sec-h"><h2 data-i18n>Key facts</h2><p data-i18n>Newest first. Hardware tags open the matching products.</p></div>
<div class="fgrid">{cards}</div>
<div class="split-layout uae-heads"><aside class="side" aria-labelledby="u-side-h"><div class="panel"><h2 class="side-h" id="u-side-h" data-i18n>Headlines at a glance</h2><dl class="side-stats">{side}</dl></div></aside>
<div class="main-col"><div class="sec-h"><h2 data-i18n>UAE AI headlines</h2><p>{L(cnt(n_en, "headline", "en") + " · times in UAE time", cnt(n_ar, "headline", "ar") + " · الأوقات بتوقيت الإمارات")}</p></div>
{day_lists(uae_items, src, 'No recent English UAE headlines.', 'لا توجد عناوين إماراتية حديثة.')}
<p class="muted n-note">{NEWS_NOTE}</p></div></div>
{xnav(c, ('hardware', 'news'))}
</section>'''

def contact_head():
    return ihead('contact', 'Contact', T(CONTACT_LEAD), follow=False)

# ---------- page ----------

def context(data, feed, sources, uae):
    ps = data['products']
    items = news_items(feed, sources)
    facts = (uae or {}).get('facts', [])
    featured, highlights = load_site(ps, facts)
    vendors, levels = {}, {}
    for p in ps:
        vendors[p['vendor']] = vendors.get(p['vendor'], 0) + 1
        levels[p['level']] = levels.get(p['level'], 0) + 1
    return {
        'data': data, 'products': ps, 'feed': feed, 'sources': sources, 'uae': uae, 'items': items,
        'src': {s['id']: s for s in sources}, 'featured': featured, 'highlights': highlights,
        'vendors': vendors, 'levels': levels, 'n_products': len(ps), 'n_priced': sum(1 for p in ps if p.get('price_view')),
        'n_headlines': len(items), 'n_sources': len(sources), 'n_facts': len(facts),
        'n_active_sources': len({i['source'] for i in items}),
        'check_health': data.get('check_health'),
        'last_check': data.get('last_check_at'), 'uae_checked': (uae or {}).get('checked'),
        # Oldest and newest price check: one date while they agree, a range once they differ.
        'prices_checked': sorted({p['price_view']['checked'] for p in ps if p.get('price_view') and p['price_view'].get('checked')}),
    }

def prepare(data):
    for p in data['products']:
        for k, v in OPTIONAL.items():
            p.setdefault(k, v)
        p['price_view'] = price_view(p)
        p['price_usd'] = (p['price'] or {}).get('usd_low')
    return data

def load_all():
    data = json.loads((ROOT/'data/catalog.json').read_text(encoding='utf-8'))
    validate(data)
    prepare(data)
    load = lambda name: json.loads((ROOT/'data'/name).read_text(encoding='utf-8')) if (ROOT/'data'/name).exists() else None
    sources, uae = load('news-sources.json') or [], load('uae.json')
    validate_links(sources, uae)
    return data, load('news.json'), sources, uae, load('models.json') or {'models': []}

def render_page(data, feed, sources, uae, models, brand_dir=BRAND_DIR):
    """Return (index.html text, public catalog dict). Pure: writes nothing."""
    c = context(data, feed, sources, uae)
    slim = {'updated_at': models.get('updated_at'), 'models': [{'n': m['name'], 'b': m['params_b'], 'o': m['open'], 's': m['params_source'], 'moe': m.get('moe', False), 'c': m['context'], 'hf': m['hf']} for m in models['models']]}
    # Backend-only fields stay in data/catalog.json (review issue, AI drafts) and are not published.
    public = {k: v for k, v in data.items() if k not in BACKEND_ONLY}
    logo, favicon = brand_assets(brand_dir)
    text = (ROOT/'web/template.html').read_text(encoding='utf-8')
    replacements = {
        'CSS': (ROOT/'web/style.css').read_text(encoding='utf-8'), 'JS': (ROOT/'web/app.js').read_text(encoding='utf-8'),
        'FAVICON': favicon, 'LOGO': logo, 'HOME': home_view(c), 'HW_HEAD': hardware_head(c, data),
        'PRODUCTS': ''.join(product(p) for p in data['products']), 'COUNT': E(cnt(len(data['products']), 'product', 'en')),
        'CHANGES': '<ul>' + ''.join(f'<li><b>{ymd(x["at"], "en")}</b> - {E(change_text(x["summary"]))}</li>' for x in data['changes'][:8]) + '</ul>',
        'EDITION': E(data['edition_note']), 'XNAV_HW': xnav(c, ('news', 'uae')), 'NEWS': news_view(c), 'UAE': uae_view(c),
        'CONTACT_HEAD': contact_head(), 'XNAV_CONTACT': xnav(c, ('hardware', 'news', 'uae')),
        'INSTAGRAM': INSTAGRAM, 'FOLLOW': follow_btn(), 'YEAR': str(data['updated_at'])[:4],
        'MODELS': json.dumps(slim, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c'),
        'JSON': json.dumps(public, ensure_ascii=False).replace('<', '\\u003c'),
    }
    replacements.update({'ICON_' + k.upper(): v for k, v in ICON.items()})
    missing = set(re.findall(r'__([A-Z][A-Z0-9_]*)__', text)) - set(replacements)
    assert not missing, f'Unfilled template placeholders: {sorted(missing)}'
    # One pass, so inserted data (headlines, JSON) is never scanned for placeholders.
    text = re.sub(r'__([A-Z][A-Z0-9_]*)__', lambda m: replacements[m.group(1)], text)
    return text, public

def pdf(data):
    # Embedded fonts avoid the substitution problems seen in the first PDF.
    fontdir = ROOT / 'fonts'
    pdfmetrics.registerFont(TTFont('Atlas', str(fontdir/'DejaVuSans.ttf')))
    pdfmetrics.registerFont(TTFont('Atlas-Bold', str(fontdir/'DejaVuSans-Bold.ttf')))
    w,h = A3
    c=canvas.Canvas(str(OUT/'AI_Hardware_Atlas_2026_One_Page.pdf'),pagesize=A3,invariant=1)
    c.setTitle(f'AI Hardware Atlas - NVIDIA and AMD | {SITE_NAME}');c.setAuthor(SITE_NAME)
    c.setFillColor(HexColor('#f5f8ff'));c.rect(0,0,w,h,fill=1,stroke=0)
    c.setFillColor(HexColor('#4d2899'));c.roundRect(24,h-117,w-48,93,16,fill=1,stroke=0)
    c.setFillColor(HexColor('#ffffff'));c.setFont('Atlas-Bold',27);c.drawString(43,h-66,'AI HARDWARE ATLAS');c.setFont('Atlas-Bold',10);c.drawRightString(w-43,h-58,SITE_NAME.upper())
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
            # The kind also explains a missing date (for example "Not on NVIDIA's current roadmap").
            if p['release'] or p['release_kind'] not in (None,'','Not established'):dates+=' ('+p['release_kind']+')'
            c.drawString(x+23,top-45,fit(dates,cw-33,7.5))
            c.linkURL(p['sources'][0]['url'],(x,top-row_h,x+cw,top))
    c.setFillColor(HexColor('#e9e3fc'));c.roundRect(30,49,w-60,69,11,fill=1,stroke=0)
    c.setFillColor(HexColor('#39236f'));c.setFont('Atlas-Bold',10);c.drawString(45,97,'COMPARE LIKE FOR LIKE')
    c.setFont('Atlas',8.4);c.drawString(45,80,'Dedicated GPU VRAM, shared system memory and rack totals have different meanings. Capacity is not speed.')
    c.drawString(45,65,'Each row links to an official source. The website includes power, architecture, detailed notes and all sources.')
    c.setFillColor(HexColor('#65758f'));c.setFont('Atlas',8);c.drawString(30,28,'One-page overview. Precise dates are shown only where established; availability varies by partner and region.');c.drawRightString(w-30,28,f"© {str(data['updated_at'])[:4]} {SITE_NAME}")
    c.showPage();c.save()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--standalone',type=Path,help='also copy the self-contained page (and PDF beside it) to this .html path')
    args=parser.parse_args()
    data,feed,sources,uae,models=load_all()
    OUT.mkdir(exist_ok=True)
    text,public=render_page(data,feed,sources,uae,models)
    (OUT/'index.html').write_text(text,encoding='utf-8',newline='\n')
    (OUT/'catalog.json').write_text(json.dumps(public,indent=2,ensure_ascii=False)+'\n',encoding='utf-8',newline='\n')
    if (ROOT/'images').exists():shutil.copytree(ROOT/'images',OUT/'images',dirs_exist_ok=True)
    copy_brand_images(OUT/'brand')
    pdf(data)
    if args.standalone:
        target=args.standalone.resolve()
        shutil.copyfile(OUT/'index.html',target)
        if (ROOT/'images').exists():shutil.copytree(ROOT/'images',target.parent/'images',dirs_exist_ok=True)
        copy_brand_images(target.parent/'brand')
        shutil.copyfile(OUT/'AI_Hardware_Atlas_2026_One_Page.pdf',target.parent/'AI_Hardware_Atlas_2026_One_Page.pdf')
        print(f'Standalone copy written to {target}')
    print(f"Built {len(data['products'])} products, self-contained HTML, JSON and one-page PDF")

if __name__=='__main__':main()
