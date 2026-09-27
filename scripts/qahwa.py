"""Qahwa & AI library: validate data/qahwa.json and render the separate static page qahwa.html.

    python scripts/qahwa.py                 # writes dist/qahwa.html (plus its covers, fonts and brand images)
    python scripts/qahwa.py --out DIR       # another folder

build_safe(out_dir, home='index.html') is the entry point for scripts/build.py: it never stops the site build. When
data/qahwa.json has a problem it logs it and leaves out only the posts at fault (or, if the file itself is broken, builds
the early-state page). build() is the strict version (used by the tests). page_doc() is the data exactly as build_safe()
puts it on the page, and lesson_url(n, doc) gives Learn AI the page's deep link for a lesson in it (None for a lesson
that is not published, so Learn AI never names a future lesson).

    python scripts/qahwa.py --check [--data F --images D]   # only check the data (exit 1 on a problem); the exporter
                                                           # in C:/Projects/AI Lessons runs this before every push

The page lists only posts already published on Instagram (@qahwa.w.ai): data/qahwa.json holds nothing else, and validate() rejects a post flagged as unpublished. A missing
data/qahwa.json builds a valid page in its early state ("New lessons arrive here as they are published on Instagram").

The page is self-contained like learn.html: web/qahwa.css and web/qahwa.js are inlined, and the data is inlined as JSON
(with <, > and & escaped, so it can never close its <script> block). Covers (images/qahwa/<id>.webp), the Qahwa & AI
brand images (web/brand/qahwa/) and the fonts (web/fonts/qahwa/: Outfit, IBM Plex Sans Arabic and Caveat, SIL OFL 1.1)
are copied next to it, so the page makes no request to another host. It has no "last updated" line: the site shows its
freshness line only in the AI news view.

Data contract (data/qahwa.json), shared with the lane that writes it:
  {"schema": 1, "generated_at": ISO, "profile": "https://www.instagram.com/qahwa.w.ai/",
   "posts": [{"id": url-safe "<content file id>|<post id>" (e.g. week-01-day-01--1-learn-lesson-01),
              "kind": lesson|reel|challenge|recap|welcome|story|news|other, "lesson": int|null, "code": "L01"|null,
              "week": int|null, "topic": pillar|null, "title": {"en","ar"}, "summary": {"en","ar"},
              "slides": [{"type", "en": {...}, "ar": {...}, ...}], "prompt": {"en","ar","code"}|null,
              "permalink": https URL on instagram.com, "published_at": ISO, "cover": "images/qahwa/<id>.webp"|null,
              "related_concepts": [Learn AI concept ids]}]}
"""
import argparse
import base64
import html
import json
import re
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data' / 'qahwa.json'
IMAGES = ROOT / 'images' / 'qahwa'
CONCEPTS = ROOT / 'data' / 'learn' / 'concepts.json'
WEB = ROOT / 'web'
FONTS = WEB / 'fonts' / 'qahwa'
BRAND = WEB / 'brand' / 'qahwa'
LOGO = WEB / 'brand' / 'logo.svg'
OUT = ROOT / 'dist'
PAGE = 'qahwa.html'
LEARN_PAGE = 'learn.html'
SITE_URL = 'https://cipherlacuna.ae/'
PROFILE = 'https://www.instagram.com/qahwa.w.ai/'
SCHEMA = 1
KINDS = ('lesson', 'reel', 'challenge', 'recap', 'welcome', 'story', 'news', 'other')
PUBLISHED = ('posted', 'posted-manually')
POST_FIELDS = ('id', 'kind', 'lesson', 'code', 'week', 'topic', 'title', 'summary', 'slides', 'prompt', 'permalink',
               'published_at', 'cover', 'related_concepts')
UAE_TZ = timezone(timedelta(hours=4))  # the bot posts on Dubai time; a time without an offset is read as Dubai time
ID = re.compile(r'^[a-z0-9][a-z0-9-]*$')
IG_HOSTS = ('instagram.com', 'www.instagram.com')
# Keys that hold image or video paths. The same list as the exporter's PATH_KEYS (tools/export_cipher.py).
IMAGE_KEYS = {'image', 'images', 'hero', 'bg', 'background', 'src', 'path', 'file', 'photo', 'thumb', 'cover',
              'shot', 'inset', 'logo', 'img', 'video'}
IMAGE_PATH = re.compile(r'(?:^|[/\\])[\w.-]+\.(?:png|jpe?g|webp|gif|svg|avif|mp4|mov)$', re.I)
AR_LETTER = re.compile(r'[؀-ۿ]')

class QahwaDataError(ValueError):
    """data/qahwa.json breaks a rule; the message lists every problem found."""

# ---------- data ----------

def empty_doc():
    return {'schema': SCHEMA, 'generated_at': None, 'profile': PROFILE, 'posts': []}

def load(path=DATA):
    """data/qahwa.json, or an empty document (the page's early state) when the file does not exist yet."""
    try:
        text = Path(path).read_text(encoding='utf-8')
    except FileNotFoundError:
        return empty_doc()
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise QahwaDataError(f'{Path(path).name} is not valid JSON: {e}') from None

def load_concepts(path=CONCEPTS):
    """{concept id: {'en': title, 'ar': title}} from Learn AI's concepts (empty when the file is missing)."""
    try:
        doc = json.loads(Path(path).read_text(encoding='utf-8'))
    except FileNotFoundError:
        return {}
    return {c['id']: {'en': c.get('title_en', c['id']), 'ar': c.get('title_ar') or c.get('title_en', c['id'])}
            for c in doc.get('concepts', []) if isinstance(c, dict) and c.get('id')}

def parse_time(value):
    """An aware datetime for an ISO time (Dubai time when it has no offset), or None when it is not ISO."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        d = datetime.fromisoformat(value.strip().replace('Z', '+00:00'))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=UAE_TZ)

def _text(v):
    return isinstance(v, str) and bool(v.strip())

def _both(o, where, errs, required=True):
    """o is {'en': str, 'ar': str}; with `required`, both non-empty."""
    if not isinstance(o, dict):
        errs.append(f'{where} must be an object with "en" and "ar"')
        return
    for lang in ('en', 'ar'):
        v = o.get(lang)
        if not isinstance(v, str):
            errs.append(f'{where}.{lang} is missing')
        elif required and not v.strip():
            errs.append(f'{where}.{lang} is empty')

def _image_paths(o, where, errs):
    """Slides carry text only: no image keys and no strings that are image or video paths."""
    if isinstance(o, dict):
        for k, v in o.items():
            if k in IMAGE_KEYS:
                errs.append(f'{where}.{k}: slides must not carry image paths')
            else:
                _image_paths(v, f'{where}.{k}', errs)
    elif isinstance(o, list):
        for i, v in enumerate(o):
            _image_paths(v, f'{where}[{i}]', errs)
    elif isinstance(o, str) and IMAGE_PATH.search(o.strip()):
        errs.append(f'{where}: slides must not carry image paths ({o!r})')

def instagram_url(url):
    u = urlparse(str(url or ''))
    return u.scheme == 'https' and (u.hostname or '').lower() in IG_HOSTS

def unpublished_flag(p):
    """Why a post is marked as not published ('' when it is not)."""
    status = p.get('status')
    if status is not None and status not in PUBLISHED:
        return f'status {status!r}'
    for key in ('unpublished', 'preview', 'draft', 'scheduled'):
        if p.get(key):
            return f'{key} is set'
    if p.get('published') is False:
        return 'published is false'
    return ''

def _policy(post, where):
    """The site's UAE/GCC content-policy guard (the same check as the Learn AI and fixed pages)."""
    if str(ROOT / 'scripts') not in sys.path:
        sys.path.insert(0, str(ROOT / 'scripts'))
    import learn
    text = {k: post.get(k) for k in ('title', 'summary', 'slides', 'prompt')}
    return learn.policy_problems(text, where)

def validate(doc, images_dir=IMAGES, concept_ids=None, check_policy=True, warnings=None):
    """Raise QahwaDataError listing every problem; return the document unchanged when it is fine.
    concept_ids: the Learn AI concept ids that related_concepts may name (None skips that check).
    warnings: a list that gets notes which do not stop the build (for example an Arabic title made only of Latin
    product names, such as "CPU + GPU + NPU + 128 GB", which the owner's rules allow)."""
    errs = []
    notes = warnings if warnings is not None else []
    if not isinstance(doc, dict):
        raise QahwaDataError('data/qahwa.json must be a JSON object')
    if doc.get('schema') != SCHEMA:
        errs.append(f'schema must be {SCHEMA}, not {doc.get("schema")!r}')
    if doc.get('profile') not in (None, PROFILE):
        errs.append(f'profile must be {PROFILE}')
    if doc.get('generated_at') is not None and not parse_time(doc.get('generated_at')):
        errs.append(f'generated_at is not an ISO time: {doc.get("generated_at")!r}')
    posts = doc.get('posts')
    if not isinstance(posts, list):
        raise QahwaDataError('1 problem(s) in data/qahwa.json:\n  posts must be a list' + ''.join(f'\n  {e}' for e in errs))
    seen, lessons = set(), {}
    images_dir = Path(images_dir)
    for i, p in enumerate(posts):
        where = f'posts[{i}]'
        if not isinstance(p, dict):
            errs.append(f'{where} must be an object')
            continue
        pid = p.get('id')
        if not isinstance(pid, str) or not ID.match(pid):
            errs.append(f'{where} has an invalid id {pid!r} (lowercase letters, digits and hyphens only)')
        elif pid in seen:
            errs.append(f'duplicate post id {pid!r}')
        else:
            seen.add(pid)
            where = f'post {pid}'
        flag = unpublished_flag(p)
        if flag:
            errs.append(f'{where} is not published ({flag}); the page lists published posts only')
        kind = p.get('kind')
        if kind not in KINDS:
            errs.append(f'{where}: unknown kind {kind!r} (one of {", ".join(KINDS)})')
        lesson = p.get('lesson')
        if lesson is not None and (not isinstance(lesson, int) or isinstance(lesson, bool) or not 1 <= lesson <= 999):
            errs.append(f'{where}: lesson must be a whole number from 1 to 999 or null, not {lesson!r}')
        elif kind == 'lesson':
            if lesson is None:
                errs.append(f'{where}: a lesson needs its lesson number')
            elif lesson in lessons:
                errs.append(f'{where}: lesson {lesson} is also {lessons[lesson]}')
            else:
                lessons[lesson] = pid
        for key in ('code', 'topic'):
            if p.get(key) is not None and not _text(p.get(key)):
                errs.append(f'{where}: {key} must be text or null')
        week = p.get('week')
        if week is not None and (not isinstance(week, int) or isinstance(week, bool) or week < 0):
            errs.append(f'{where}: week must be a whole number or null, not {week!r}')
        _both(p.get('title'), f'{where}.title', errs)
        if isinstance(p.get('title'), dict) and _text(p['title'].get('ar')) and not AR_LETTER.search(p['title']['ar']):
            notes.append(f'{where}.title.ar has no Arabic letters (fine for Latin product names; check it is not English by mistake)')
        _both(p.get('summary'), f'{where}.summary', errs, required=False)
        slides = p.get('slides')
        if not isinstance(slides, list):
            errs.append(f'{where}.slides must be a list')
        else:
            for j, s in enumerate(slides):
                at = f'{where}.slides[{j}]'
                if not isinstance(s, dict) or not _text(s.get('type')):
                    errs.append(f'{at} must be an object with a type')
                    continue
                if not isinstance(s.get('en'), dict) or not isinstance(s.get('ar'), dict):
                    errs.append(f'{at} needs its text in both languages ("en" and "ar")')
                _image_paths({k: v for k, v in s.items() if k != 'type'}, at, errs)
        prompt = p.get('prompt')
        if prompt is not None:
            _both(prompt, f'{where}.prompt', errs)
            if isinstance(prompt, dict) and prompt.get('code') is not None and not _text(prompt.get('code')):
                errs.append(f'{where}.prompt.code must be text or null')
        if not instagram_url(p.get('permalink')):
            errs.append(f'{where}: permalink must be an https link on instagram.com, not {p.get("permalink")!r}')
        if not parse_time(p.get('published_at')):
            errs.append(f'{where}: published_at must be an ISO time, not {p.get("published_at")!r}')
        cover = p.get('cover')
        if cover is not None:
            if isinstance(pid, str) and cover != f'images/qahwa/{pid}.webp':
                errs.append(f'{where}: cover must be images/qahwa/{pid}.webp or null, not {cover!r}')
            elif isinstance(pid, str) and not (images_dir / f'{pid}.webp').is_file():
                errs.append(f'{where}: cover file {pid}.webp is missing from {images_dir}')
        rel = p.get('related_concepts', [])
        if not isinstance(rel, list) or not all(isinstance(r, str) for r in rel):
            errs.append(f'{where}: related_concepts must be a list of concept ids')
        elif concept_ids is not None:
            for r in rel:
                if r not in concept_ids:
                    errs.append(f'{where}: related concept {r!r} is not in data/learn/concepts.json')
        if check_policy:
            errs += _policy(p, where)
    if errs:
        raise QahwaDataError(f'{len(errs)} problem(s) in data/qahwa.json:\n  ' + '\n  '.join(errs))
    return doc

# ---------- links for the rest of the site ----------

def slug(post):
    """The page's deep link for a post (without #): lesson-NN for a lesson, post-<id> otherwise."""
    if post.get('kind') == 'lesson' and isinstance(post.get('lesson'), int):
        return f'lesson-{post["lesson"]:02d}'
    return f'post-{post["id"]}'

def lesson_url(n, doc=None):
    """'qahwa.html#lesson-NN' when lesson n is published (listed in the data), else None. For Learn AI's lesson chips.
    doc: the page's document (default: page_doc(), the posts qahwa.html really shows)."""
    if doc is None:
        doc = page_doc()[0]
    try:
        n = int(n)
    except (TypeError, ValueError):
        return None
    for p in (doc or {}).get('posts') or []:
        if isinstance(p, dict) and p.get('kind') == 'lesson' and p.get('lesson') == n and not unpublished_flag(p):
            return f'{PAGE}#lesson-{n:02d}'
    return None

# ---------- page ----------

def esc(v):
    return html.escape(str(v if v is not None else ''), quote=True)

def plain(s):
    return ' '.join(str(s or '').replace('==', '').split())

def json_block(data):
    """JSON for an inline <script type="application/json">: <, > and & escaped, so no </script> or <!-- can appear."""
    text = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
    return text.replace('&', '\\u0026').replace('<', '\\u003c').replace('>', '\\u003e').replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')

def _asset(name):
    text = (WEB / name).read_text(encoding='utf-8')
    closing = '</script' if name.endswith('.js') else '</style'
    if closing in text.lower():
        raise QahwaDataError(f'web/{name} contains {closing}, which would end the inline block early')
    return text

def logo_uri(path=LOGO):
    """The Cipher Lacuna logo, as the owner made it, as a data: image (shown with <img>, so it cannot run script)."""
    try:
        data = Path(path).read_bytes()
    except FileNotFoundError:
        return ''
    return 'data:image/svg+xml;base64,' + base64.b64encode(data).decode('ascii')

TEASER_LESSON = re.compile(r'^(?:Lesson|الدرس)\s*0*(\d{1,3})\s*[:：]')
TEASER_PREFIX = re.compile(r'^[^:：]{1,30}[:：]\s*')

def teaser_target(nxt, posts):
    """The post a "Coming next" teaser names, when that post is on the page; None otherwise.
    A teaser for a post that is not published yet must never reach the page."""
    if not isinstance(nxt, dict):
        return None
    for lang in ('en', 'ar'):
        m = TEASER_LESSON.match(plain(nxt.get(lang)))
        if m:
            n = int(m.group(1))
            return next((p for p in posts if p.get('kind') == 'lesson' and p.get('lesson') == n), None)
    en = plain(nxt.get('en'))
    for p in posts:
        t = plain((p.get('title') or {}).get('en'))
        if t and t in (en, TEASER_PREFIX.sub('', en)):
            return p
    return None

def page_posts(doc):
    """The posts as the page gets them: contract fields only, times with an offset, newest first, and no
    "Coming next" teaser that names a post missing from the page."""
    out = []
    listed = [p for p in doc.get('posts') or [] if isinstance(p, dict)]
    for p in listed:
        q = {k: p.get(k) for k in POST_FIELDS}
        q['related_concepts'] = list(p.get('related_concepts') or [])
        q['slides'] = [s if 'next' not in s or teaser_target(s['next'], listed) else {k: v for k, v in s.items() if k != 'next'}
                       for s in p.get('slides') or [] if isinstance(s, dict)]
        q['published_at'] = parse_time(p.get('published_at')).isoformat()
        out.append(q)
    out.sort(key=lambda q: (q['published_at'], q.get('lesson') or 0), reverse=True)
    return out

HEAD_SCRIPT = ("(function(d){d.classList.add('js');var t=null,l=null,q=null;try{t=localStorage.getItem('atlas-theme');l=localStorage.getItem('atlas-lang')}catch(e){}"
               "if(t==='light'||t==='dark')d.dataset.theme=t;try{q=new URLSearchParams(location.search).get('lang')}catch(e){}if(q==='ar'||q==='en')l=q;"
               "if(l!=='ar'&&l!=='en')l=/^ar\\b/i.test(navigator.language||'')?'ar':'en';"
               "if(l==='ar'){d.lang='ar';d.dir='rtl'}})(document.documentElement)")
DESCRIPTION = ('Every published Qahwa & AI lesson from @qahwa.w.ai, in Arabic and English, with the prompt to copy. '
               'Part of Cipher Lacuna.')
TITLE = 'Qahwa & AI Lessons · Cipher Lacuna'
IG_SVG = ('<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="5.2"/><circle cx="12" cy="12" r="4.1"/>'
          '<circle cx="17.3" cy="6.7" r="1.1" class="fill"/></svg>')

def _noscript(posts):
    if not posts:
        return ''
    items = ''.join(
        f'<li><a href="{esc(PROFILE if p["kind"] == "story" else p["permalink"])}" rel="noopener">{esc(plain(p["title"]["en"]))}</a>'
        f'<span class="ar" lang="ar" dir="rtl">{esc(plain(p["title"]["ar"]))}</span></li>' for p in posts)
    return f'<noscript><ul class="nojs">{items}</ul></noscript>'

def render(doc, concepts=None, home='index.html'):
    """Return the qahwa.html text for a validated document. Pure: writes nothing.
    concepts: {id: {'en','ar'}} titles for the related Learn AI guides; `home` is the overview page beside it."""
    concepts = concepts or {}
    posts = page_posts(doc)
    used = sorted({c for p in posts for c in p['related_concepts'] if c in concepts})
    data = {'home': home, 'learn': LEARN_PAGE, 'concepts': {c: concepts[c] for c in used}, 'posts': posts}
    h = esc(home)
    logo = logo_uri()
    cl_img = f'<img src="{logo}" alt="" width="22" height="22">' if logo else ''
    cl_img20 = f'<img src="{logo}" alt="" width="20" height="20">' if logo else ''
    early_hidden = ' hidden' if posts else ''
    head = (f'<!doctype html>\n<html lang="en" dir="ltr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<meta name="color-scheme" content="light dark"><title>{esc(TITLE)}</title><meta name="description" content="{esc(DESCRIPTION)}">'
            f'<meta name="author" content="Cipher Lacuna">'
            f'<meta name="theme-color" content="#FEFBF7" media="(prefers-color-scheme: light)"><meta name="theme-color" content="#1C1413" media="(prefers-color-scheme: dark)">'
            f'<link rel="icon" type="image/webp" href="brand/qahwa/bot-badge.webp"><link rel="canonical" href="{SITE_URL}{PAGE}">\n'
            f'<meta property="og:type" content="website"><meta property="og:site_name" content="Cipher Lacuna"><meta property="og:title" content="{esc(TITLE)}">'
            f'<meta property="og:description" content="{esc(DESCRIPTION)}"><meta property="og:url" content="{SITE_URL}{PAGE}">'
            f'<meta property="og:image" content="{SITE_URL}brand/og.png"><meta property="og:locale" content="en_US"><meta property="og:locale:alternate" content="ar_AE">'
            f'<meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="{esc(TITLE)}"><meta name="twitter:description" content="{esc(DESCRIPTION)}">\n'
            f'<script>{HEAD_SCRIPT}</script>\n<style>{_asset("qahwa.css")}</style></head>\n')
    body = f'''<body>
<a class="skip" href="#library" data-i18n="skip">Skip to the lessons</a>
<div class="sitebar">
  <div class="wrap sitebar-in">
    <a class="cl" data-home href="{h}">{cl_img}<span data-i18n-html="partOf">Part of <b>Cipher Lacuna</b></span></a>
    <div class="bar-tools js-only">
      <button class="icon-btn lang-btn" id="langBtn" type="button" lang="ar">العربية</button>
      <button class="icon-btn" id="themeBtn" type="button" aria-pressed="false">
        <svg class="i-moon" viewBox="0 0 24 24" aria-hidden="true"><path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5Z"/></svg>
        <svg class="i-sun" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4.2"/><path d="M12 2.5v2.2M12 19.3v2.2M4.6 4.6l1.6 1.6M17.8 17.8l1.6 1.6M2.5 12h2.2M19.3 12h2.2M4.6 19.4l1.6-1.6M17.8 6.2l1.6-1.6"/></svg>
        <span class="vh" data-i18n="theme">Dark mode</span>
      </button>
    </div>
  </div>
</div>
<header class="hub">
  <div class="wrap hub-in">
    <div class="hub-copy">
      <span class="plate"><img class="lockup" src="brand/qahwa/logo-lockup.webp" width="560" height="132" alt="Qahwa &amp; AI · قهوة و AI"></span>
      <h1 class="tagline" data-i18n-html="tagline">A free AI lesson <span class="hl">with your morning coffee</span></h1>
      <p class="sub"><span data-i18n="steps">Learn · Try · Check</span> <span class="dot" aria-hidden="true"></span> <span data-i18n="langs">Arabic &amp; English</span></p>
      <nav class="links" aria-label="Links" data-i18n-aria="linksLabel">
        <a class="btn btn-primary" id="followBtn" href="{PROFILE}" rel="noopener">{IG_SVG}<span><span data-i18n="follow">Follow on Instagram</span> <small dir="ltr">@qahwa.w.ai</small></span></a>
        <a class="btn" data-home href="{h}">{cl_img20}<span data-i18n="website">Cipher Lacuna website</span></a>
        <a class="btn js-only" href="#library" id="promptsLink"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 5h14v10H9l-4 4z"/><path d="M9 9h6M9 12h4"/></svg><span data-i18n="allPrompts">All prompts</span></a>
      </nav>
    </div>
    <img class="hub-scene" src="brand/qahwa/scene-companion.webp" width="520" height="370" alt="">
  </div>
</header>
<main id="library" class="wrap" tabindex="-1">
  <section class="early" id="early"{early_hidden} aria-labelledby="earlyH">
    <img src="brand/qahwa/bot-badge.webp" width="96" height="96" alt="">
    <h2 id="earlyH" data-i18n="earlyH">The first lessons are on their way</h2>
    <p data-i18n="earlyP">New lessons arrive here as they are published on Instagram. Follow @qahwa.w.ai to see each one first.</p>
    <a class="btn btn-primary" href="{PROFILE}" rel="noopener">{IG_SVG}<span data-i18n="follow">Follow on Instagram</span></a>
  </section>
  <div id="libTools" class="js-only">
    <div class="tabs" id="tabs" role="group" aria-label="Show" data-i18n-aria="showLabel"></div>
    <div class="controls">
      <div class="search">
        <label class="vh" for="q" data-i18n="searchLabel">Search lessons</label>
        <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="6.5"/><path d="m16 16 4.5 4.5"/></svg>
        <input id="q" type="search" autocomplete="off" spellcheck="false" data-i18n-ph="searchPh" placeholder="Search lessons, prompts and topics">
        <button class="clear" id="clearQ" type="button" hidden><span class="vh" data-i18n="clear">Clear search</span><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m7 7 10 10M17 7 7 17"/></svg></button>
      </div>
      <div class="filters" id="filters">
        <div class="chips" id="weekRow" role="group" aria-labelledby="weekLbl"><span class="chips-lbl" id="weekLbl" data-i18n="week">Week</span><div id="weekChips" class="chip-row"></div></div>
        <div class="chips" id="topicRow" role="group" aria-labelledby="topicLbl"><span class="chips-lbl" id="topicLbl" data-i18n="topic">Topic</span><div id="topicChips" class="chip-row"></div></div>
      </div>
      <p class="count" id="count" aria-live="polite"></p>
    </div>
  </div>
  <section class="block js-only" id="listBlock" aria-labelledby="listH">
    <h2 class="vh" id="listH">Lessons</h2>
    <div class="grid" id="grid"></div>
    <div class="more-wrap" id="moreWrap" hidden><button class="act" id="moreBtn" type="button">Show more</button></div>
    <p class="soon" id="soon" hidden><img src="brand/qahwa/bot-badge.webp" width="36" height="36" alt=""><span><span data-i18n="soon">New lessons arrive here as they are published on Instagram.</span> <a href="{PROFILE}" rel="noopener" data-i18n="soonFollow">Follow @qahwa.w.ai</a></span></p>
  </section>
  <p class="empty js-only" id="empty" hidden></p>
  {_noscript(posts)}
</main>
<footer class="foot">
  <div class="wrap foot-in">
    <img src="brand/qahwa/bot-badge.webp" width="48" height="48" alt="">
    <p data-i18n-html="footer">Qahwa &amp; AI is a free bilingual AI series on Instagram, and part of <a data-home href="{h}">Cipher Lacuna</a>.</p>
    <ul class="foot-links">
      <li><a data-home href="{h}" data-i18n="home">Cipher Lacuna</a></li>
      <li><a data-learn href="{LEARN_PAGE}" data-i18n="learnAI">Learn AI</a></li>
      <li><a href="{PROFILE}" rel="noopener" lang="en" dir="ltr">Instagram @qahwa.w.ai</a></li>
    </ul>
  </div>
</footer>
<dialog id="detail" class="js-only" aria-labelledby="dTitle">
  <div class="d-bar">
    <span class="d-crumb" id="dCrumb"></span>
    <button class="icon-btn" id="dClose" type="button"><span class="vh" data-i18n="close">Close</span><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m7 7 10 10M17 7 7 17"/></svg></button>
  </div>
  <div class="d-body" id="dBody"></div>
</dialog>
<div class="toast" id="toast" role="status" aria-live="polite"></div>
<script type="application/json" id="qahwa-data">{json_block(data)}</script>
<script>{_asset("qahwa.js")}</script>
</body></html>
'''
    return head + body

# ---------- build ----------

def _copy_tree(src, dest, patterns):
    """Copy the files matching `patterns` under src to dest (same layout); returns the relative paths copied."""
    copied = []
    for pattern in patterns:
        for f in sorted(Path(src).rglob(pattern)):
            if f.is_file():
                rel = f.relative_to(src)
                (dest / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(f, dest / rel)
                copied.append(rel.as_posix())
    return copied

def build(out_dir=OUT, home='index.html', data_path=DATA, images_dir=IMAGES, concepts_path=CONCEPTS, doc=None, warnings=None):
    """Validate the data and write <out_dir>/qahwa.html, the covers it shows (images/qahwa/), the Qahwa & AI brand
    images (brand/qahwa/) and the fonts (fonts/qahwa/). Nothing is written when the data is wrong. Returns the page path.
    doc: an already loaded document (instead of data_path). warnings: a list that gets the notes that do not stop it."""
    doc = load(data_path) if doc is None else doc
    concepts = load_concepts(concepts_path)
    validate(doc, images_dir, set(concepts) if concepts else None, warnings=warnings)
    page = render(doc, concepts, home=home)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    covers = out_dir / 'images' / 'qahwa'
    covers.mkdir(parents=True, exist_ok=True)
    wanted = {f'{p["id"]}.webp' for p in doc.get('posts') or [] if p.get('cover')}
    for old in covers.glob('*.webp'):
        if old.name not in wanted:  # a cover whose post is no longer listed is not served
            old.unlink()
    for name in sorted(wanted):
        shutil.copyfile(Path(images_dir) / name, covers / name)
    _copy_tree(BRAND, out_dir / 'brand' / 'qahwa', ('*.webp',))
    _copy_tree(FONTS, out_dir / 'fonts' / 'qahwa', ('*.woff2', 'OFL.txt'))
    target = out_dir / PAGE
    target.write_text(page, encoding='utf-8', newline='\n')
    return target

def page_doc(data_path=DATA, images_dir=IMAGES, concepts_path=CONCEPTS, warnings=None):
    """(document, problems): the data exactly as build_safe() puts it on the page. A post that breaks a rule, or repeats
    an id or a lesson number, is left out; a file that is broken as a whole gives the empty (early-state) document.
    Never raises on bad data, so Learn AI can ask it which lessons are published without risking the site build."""
    problems = []
    try:
        doc = load(data_path)
    except QahwaDataError as e:
        return empty_doc(), [str(e)]
    concepts = load_concepts(concepts_path)
    ids = set(concepts) if concepts else None
    try:
        return validate(doc, images_dir, ids, warnings=warnings), []
    except QahwaDataError as e:
        problems.append(str(e))
    if not isinstance(doc, dict):
        return empty_doc(), problems
    top = {k: doc.get(k) for k in ('schema', 'generated_at', 'profile')}
    keep, seen, lessons = [], set(), set()
    for p in doc.get('posts') if isinstance(doc.get('posts'), list) else []:
        try:
            validate({**top, 'posts': [p]}, images_dir, ids)
        except QahwaDataError:
            continue
        if p['id'] in seen or (p.get('kind') == 'lesson' and p.get('lesson') in lessons):
            continue
        seen.add(p['id'])
        if p.get('kind') == 'lesson':
            lessons.add(p.get('lesson'))
        keep.append(p)
    kept = {**top, 'posts': keep}
    try:
        validate(kept, images_dir, ids)
    except QahwaDataError as e:  # the top of the file itself is wrong (for example its schema)
        problems.append(str(e))
        kept = empty_doc()
    return kept, problems

def build_safe(out_dir=OUT, home='index.html', data_path=DATA, images_dir=IMAGES, concepts_path=CONCEPTS, log=None):
    """build() that never stops the site build: news and hardware pages still deploy when the Qahwa data is wrong.
    On a data problem it logs it, leaves out only the posts at fault (page_doc()) and builds the page with the rest; if
    the file itself is broken it builds the early-state page. Returns (page path, list of problems logged)."""
    log = log or (lambda msg: print(msg, file=sys.stderr))
    notes = []
    try:
        doc, problems = page_doc(data_path, images_dir, concepts_path, warnings=notes)
    except Exception as e:  # anything unexpected in the data still leaves the rest of the site deployable
        doc, problems = empty_doc(), [f'{type(e).__name__}: {e}']
    path = build(out_dir, home, data_path, images_dir, concepts_path, doc=doc)
    if problems:
        try:
            listed = load(data_path).get('posts')
            total = len(listed) if isinstance(listed, list) else 0
        except Exception:
            total = 0
        log(f'qahwa: data/qahwa.json has problems; built {PAGE} with {len(doc["posts"])} of {total} post(s).')
        for msg in problems:
            log('qahwa: ' + msg)
    for msg in notes:
        log('qahwa: note: ' + msg)
    return path, problems

def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--out', type=Path, default=OUT, help='folder to write qahwa.html into (default: dist/)')
    parser.add_argument('--home', default='index.html', help='file name of the overview page beside it (default: index.html)')
    parser.add_argument('--data', type=Path, default=DATA, help='the data file (default: data/qahwa.json)')
    parser.add_argument('--images', type=Path, default=IMAGES, help='folder with the <id>.webp covers (default: images/qahwa/)')
    parser.add_argument('--concepts', type=Path, default=CONCEPTS, help='Learn AI concepts (default: data/learn/concepts.json)')
    parser.add_argument('--check', action='store_true', help='only check the data; exit 1 when the page would refuse it')
    args = parser.parse_args()
    if args.check:
        notes = []
        try:
            doc = load(args.data)
            concepts = load_concepts(args.concepts)
            validate(doc, args.images, set(concepts) if concepts else None, warnings=notes)
        except QahwaDataError as e:
            print(e)
            sys.exit(1)
        print(f'ok: {len(doc.get("posts") or [])} post(s)' + ''.join(f'\nnote: {n}' for n in notes))
        return
    notes = []
    path = build(args.out, home=args.home, data_path=args.data, images_dir=args.images, concepts_path=args.concepts, warnings=notes)
    posts = load(args.data).get('posts') or []
    lessons = sum(p.get('kind') == 'lesson' for p in posts)
    print(f'Built {path.name}: {lessons} lesson(s) and {len(posts) - lessons} other post(s), {path.stat().st_size / 1024:.0f} KB')
    for n in notes:
        print('note:', n)

if __name__ == '__main__':
    main()
