"""Search basics for the built site (scripts/build.py calls write() last, once every page is in dist/):

- robots.txt: everything may be crawled except the Android app's data (app/) and the APK folder (download/); it names
  the sitemap.
- sitemap.xml: built from the pages actually in dist/ (no list kept by hand): every .html page except 404.html and pages
  marked noindex, at its canonical address, with the hreflang alternates it declares. So the Arabic pages, /apk/ and any
  later page (weekly pages, for example) are listed as soon as the build writes them.
- favicon.ico at the root (16, 32 and 48 px, from the brand's icon-512.png) for browsers and tools that ask for it.
- site.webmanifest from the brand icons, with "display": "browser": a manifest without an app display mode is not
  installable, so Chrome on Android never offers to install the website (the Android app is the APK). The iPhone Home
  Screen keeps its own tags (apple-touch-icon, apple-mobile-web-app-*), which the pages keep.
- 404.html: GitHub Pages serves it for any missing address, at any depth, so its links start at the site root (/) and
  everything else is inline. English and Arabic, with links to both home pages; noindex.

JSON-LD (organization(), website()) uses only facts the site already shows: the name, the address, the logo, the tagline
and the page's own description. No contact address (the site keeps it out of its page source).
"""
import json
import re
from pathlib import Path
from xml.sax.saxutils import escape

import lang_pages

SITE_URL = lang_pages.SITE_URL
ORG_ID = SITE_URL + '#organization'
SITE_ID = SITE_URL + '#website'
NAME = 'Cipher Lacuna'
TAGLINE = {'en': 'Decoding the gaps in AI knowledge', 'ar': 'كشف المجهول في عالم الذكاء الاصطناعي'}
LOGO = 'brand/icon-512.png'
MANIFEST = 'site.webmanifest'
THEME = '#6537d7'      # the pages' theme-color
BACKGROUND = '#f5f8ff'  # the light background of the brand palette
DISALLOW = ('/app/', '/download/')

def organization(lang='en'):
    return {'@type': 'Organization', '@id': ORG_ID, 'name': NAME, 'url': SITE_URL, 'logo': SITE_URL + LOGO, 'slogan': TAGLINE[lang]}

def website(lang, description):
    """WebSite + Organization for the overview in `lang`."""
    return {'@context': 'https://schema.org', '@graph': [
        {'@type': 'WebSite', '@id': SITE_ID, 'url': SITE_URL, 'name': NAME, 'description': description,
         'inLanguage': ['en', 'ar'], 'publisher': {'@id': ORG_ID}},
        organization(lang)]}

# ---------- files ----------

def png_size(path):
    """(width, height) from a PNG's header; None for anything else."""
    head = Path(path).read_bytes()[:24]
    if head[1:4] != b'PNG' or head[12:16] != b'IHDR':
        return None
    return int.from_bytes(head[16:20], 'big'), int.from_bytes(head[20:24], 'big')

def manifest(brand_dir, description):
    """The web app manifest (not installable on purpose: "display": "browser"). Icons: the brand PNGs at their real sizes."""
    icons = []
    for name in ('icon-32.png', 'apple-touch-icon.png', 'icon-512.png'):
        f = Path(brand_dir) / name
        size = png_size(f) if f.exists() else None
        if size:
            icons.append({'src': f'brand/{name}', 'sizes': f'{size[0]}x{size[1]}', 'type': 'image/png'})
    return {'name': NAME, 'short_name': NAME, 'description': description, 'lang': 'en', 'dir': 'ltr',
            'start_url': './', 'scope': './', 'display': 'browser', 'theme_color': THEME, 'background_color': BACKGROUND,
            'icons': icons}

def favicon(brand_dir, target):
    """favicon.ico (16, 32 and 48 px) from the brand's icon-512.png. Pillow is in requirements.txt; without it, or
    without the icon, no file (the pages' own icon links still work). Returns the path written or None."""
    src = Path(brand_dir) / 'icon-512.png'
    try:
        from PIL import Image
    except ImportError:
        return None
    if not src.exists():
        return None
    with Image.open(src) as im:
        im.convert('RGBA').save(target, format='ICO', sizes=[(16, 16), (32, 32), (48, 48)])
    return Path(target)

def robots():
    lines = ['User-agent: *'] + [f'Disallow: {p}' for p in DISALLOW] + ['', f'Sitemap: {SITE_URL}sitemap.xml', '']
    return '\n'.join(lines)

CANONICAL = re.compile(r'<link rel="canonical" href="([^"]+)"')
ALTERNATE = re.compile(r'<link rel="alternate" hreflang="([^"]+)" href="([^"]+)"')
NOINDEX = re.compile(r'<meta name="robots" content="[^"]*noindex', re.I)

def head_of(text):
    end = text.find('</head>')
    return text[:end] if end >= 0 else text[:20000]

def sitemap_pages(out_dir):
    """[(address, [(hreflang, address)])] for the pages in out_dir: canonical address (else the file's own), noindex
    pages and 404.html left out, each address once (with the alternates of every file that names it), home first."""
    out_dir, pages = Path(out_dir), {}
    for f in sorted(out_dir.rglob('*.html'), key=lambda f: f.relative_to(out_dir).as_posix()):
        rel = f.relative_to(out_dir).as_posix()
        if rel == '404.html':
            continue
        head = head_of(f.read_text(encoding='utf-8', errors='replace'))
        if NOINDEX.search(head):
            continue
        m = CANONICAL.search(head)
        loc = m.group(1) if m else lang_pages.url(rel)
        if not loc.startswith(SITE_URL):
            continue
        alts = pages.setdefault(loc, [])
        alts.extend(a for a in ALTERNATE.findall(head) if a[1].startswith(SITE_URL) and a not in alts)
    return sorted(pages.items(), key=lambda p: (p[0] != SITE_URL, p[0]))

def sitemap(out_dir):
    rows = []
    for loc, alts in sitemap_pages(out_dir):
        links = ''.join(f'<xhtml:link rel="alternate" hreflang="{escape(h)}" href="{escape(u)}"/>' for h, u in alts)
        rows.append(f'<url><loc>{escape(loc)}</loc>{links}</url>')
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">\n'
            + '\n'.join(rows) + '\n</urlset>\n')

NOT_FOUND = {
    'en': ('Page not found', "This page isn't here. The link may be mistyped, or the page has moved.", 'Go to the home page'),
    'ar': ('الصفحة غير موجودة', 'هذه الصفحة غير موجودة هنا. ربما في الرابط خطأ، أو نُقلت الصفحة.', 'اذهب إلى الصفحة الرئيسية'),
}

def page_404(logo_uri='', icon_uri=''):
    """The branded 404 page: both languages, links to / and /ar/, no outside request (logo and icon as data: images)."""
    en, ar = NOT_FOUND['en'], NOT_FOUND['ar']
    logo = f'<img class="logo" src="{logo_uri}" alt="" width="44" height="44">' if logo_uri else ''
    icon = f'<link rel="icon" type="image/svg+xml" href="{icon_uri}">' if icon_uri else ''
    return f'''<!doctype html>
<html lang="en" dir="ltr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex"><meta name="color-scheme" content="light dark"><meta name="theme-color" content="{THEME}">
<title>{en[0]} · {NAME} | {ar[0]}</title>
<link rel="icon" type="image/png" sizes="32x32" href="/brand/icon-32.png">{icon}<link rel="apple-touch-icon" href="/brand/apple-touch-icon.png">
<style>
:root{{--bg:#F5F8FF;--card:#fff;--ink:#0E1222;--muted:#5A6380;--line:#E4E0F5;--accent:#6537d7;--deep:#42208D}}
@media (prefers-color-scheme:dark){{:root{{--bg:#0E1222;--card:#161b30;--ink:#EEF0FA;--muted:#A6AEC8;--line:#2A3150;--accent:#8A63F0;--deep:#B9A2FF}}}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 "Segoe UI",system-ui,-apple-system,Roboto,Arial,sans-serif}}
[lang="ar"]{{font-family:"Segoe UI",Tahoma,"Geeza Pro","Noto Sans Arabic","Noto Naskh Arabic",Arial,sans-serif;line-height:1.75}}
.rule{{height:6px;background:linear-gradient(90deg,#42208D,#753ACA 38%,#D52F89 72%,#22D4D6)}}
main{{max-width:560px;margin:0 auto;padding:32px 16px 48px}}
.brand{{display:flex;align-items:center;gap:12px;text-decoration:none;color:inherit;font-weight:700;font-size:22px;margin-bottom:22px}}
.brand b{{color:var(--deep)}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:22px 20px;margin:0 0 14px}}
.code{{font-weight:800;color:var(--accent);letter-spacing:.08em;margin:0 0 6px;font-size:14px}}
h1,h2{{margin:0 0 8px;font-size:24px;line-height:1.3}}
p{{margin:0 0 16px;color:var(--muted)}}
a.btn{{display:inline-flex;align-items:center;min-height:44px;padding:10px 18px;border-radius:12px;background:var(--accent);color:#fff;font-weight:700;text-decoration:none}}
a.btn:focus-visible,.brand:focus-visible{{outline:3px solid var(--accent);outline-offset:3px}}
</style></head>
<body><div class="rule"></div>
<main>
<a class="brand" href="/" lang="en" dir="ltr">{logo}<span>Cipher <b>Lacuna</b></span></a>
<section class="card"><p class="code">404</p><h1>{en[0]}</h1><p>{en[1]}</p><a class="btn" href="/">{en[2]}</a></section>
<section class="card" lang="ar" dir="rtl"><h2>{ar[0]}</h2><p>{ar[1]}</p><a class="btn" href="/ar/">{ar[2]}</a></section>
</main>
</body></html>
'''

def assets(out_dir, brand_dir, description):
    """site.webmanifest and favicon.ico (also beside a --standalone copy, whose pages link the manifest). Returns the names."""
    out_dir = Path(out_dir)
    (out_dir / MANIFEST).write_text(json.dumps(manifest(brand_dir, description), indent=2, ensure_ascii=False) + '\n',
                                    encoding='utf-8', newline='\n')
    return [MANIFEST] + (['favicon.ico'] if favicon(brand_dir, out_dir / 'favicon.ico') else [])

def write(out_dir, brand_dir, description, logo_uri='', icon_uri=''):
    """Write robots.txt, site.webmanifest, favicon.ico and 404.html, then sitemap.xml from the pages now in out_dir.
    Returns the names written."""
    out_dir = Path(out_dir)
    written = assets(out_dir, brand_dir, description)
    for name, text in (('robots.txt', robots()), ('404.html', page_404(logo_uri, icon_uri))):
        (out_dir / name).write_text(text, encoding='utf-8', newline='\n')
        written.append(name)
    (out_dir / 'sitemap.xml').write_text(sitemap(out_dir), encoding='utf-8', newline='\n')
    return written + ['sitemap.xml']
