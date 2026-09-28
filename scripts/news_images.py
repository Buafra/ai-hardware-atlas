"""Company images for news cards (the owner's hybrid plan, Sep 2026).

A story from an official company source (a news-sources.json record with kind "primary" and an "image_hosts"
allow-list) shows the company's own image from its post; every other story shows the site's own topic image
(web/news-img/<topic>.svg, see scripts/topics.py). UAE/GCC official sources (WAM, the Dubai Media Office, Sharjah24,
anything in region "uae" or marked "official_region") always get the UAE topic image: their photos often show leaders.
So does any company story whose headline or excerpt names a country, a government or a national event (NVIDIA's
AI Day Egypt photo showed the Egyptian flag; a GCC partnership photo can show a head of state): see place_story().
News-agency photos are never used: an image is taken only from the company's own post, and only from a host on that
source's allow-list.

For each shown story that qualifies, the image URL is the item's own "image" (when a feed gave one), else the og:image
or twitter:image of the article page (fetched once: the news monitor's user agent, robots.txt respected, redirects
kept on the source's domains, 15 s timeout, at most 1.5 MB of HTML). The image is downloaded (image/* only, at most
5 MB, redirects kept on the allow-list), converted to WebP at most 480 px wide and 40 KB, and served from the site as
images/news/<item id>.webp, so the page loads nothing from other hosts.

.cache/news-img/ keeps each converted image and an index (item id -> file, image and page URL, fetched-at), so every
image is fetched once; a story whose page has no usable image is remembered too, and one that failed on a network
error is tried again on later runs (at most TRIES times). An image URL a source uses for two or more stories (a generic
logo card) and one matching the source's "image_skip" pattern fall back to the topic image. Nothing here fails the
build: any error means the topic image. Logs give counts only.

Per-source settings in news-sources.json:
  image_hosts: ["host", "host/path-prefix/"]   where the source's own images live: a whole host, or a path prefix on
                                                a shared CDN (Contentful, Google Cloud Storage)
  image_credit: "OpenAI"                        the name in the credit line ("Image: OpenAI" / «الصورة: OpenAI»)
  image_skip: "<regex>"                         image URLs that are generic cards, not the story's picture
  image_page_hosts: ["host"]                    more of the company's own domains an article page may redirect to
                                                when read for its image (DeepMind posts move to blog.google)
  image_page_paths: "<regex>"                   article paths that are the company's own posts; any other gets the
                                                topic image (Hugging Face: /blog/<slug> is HF's, /blog/<org>/<slug>
                                                a partner's post with the partner's picture)
"""
import concurrent.futures
import html
import io
import json
import re
import shutil
import time
import warnings
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

import topics

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / '.cache' / 'news-img'
INDEX = 'index.json'
OUT_DIR = 'images/news'   # inside dist/, and the site-relative path on the page
TOPIC_DIR = 'news-img'    # dist/news-img/<topic>.svg, copied from web/news-img
TOPIC_SRC = ROOT / 'web' / 'news-img'
TOPIC_SIZE = (640, 360)
MAX_WIDTH = 480
MAX_OUT = 40_000
MIN_WIDTH = 200
MAX_DOWNLOAD = 5_000_000
PAGE_BYTES = 1_500_000
TIMEOUT = 15              # per socket operation
DEADLINE = 30             # for one whole download
RUN_BUDGET = 240          # seconds for all fetches of one build; the rest wait for the next build
WORKERS = 6
TRIES = 3                 # network failures in a row; after that a story is tried once per RETRY_AFTER
RETRY_AFTER = timedelta(days=1)
KEEP_DAYS = 30            # cache entries of stories no longer shown are dropped after this
FORMATS = {'JPEG', 'PNG', 'WEBP', 'GIF'}
MAX_PIXELS = 40_000_000
META = re.compile(r'<meta\b[^>]*>', re.I)
IMAGE_KEYS = ('og:image:secure_url', 'og:image', 'og:image:url', 'twitter:image', 'twitter:image:src')

class Skip(Exception):
    """No usable company image for this story (permanent: remembered in the cache)."""

class Retry(Exception):
    """A network failure: tried again on a later build."""

def _news():
    import news  # the news monitor's user agent, robots.txt check and site-bound fetch
    return news

# ---------- rules ----------

# A company story that names a country, a government or a national event gets the topic image: such photos often show
# a flag, a head of state or a minister (the owner's no-flags rule and the UAE/GCC policy). Checked on the headline, its
# Arabic translation and the excerpt. A false match only costs one company image.
COUNTRIES_EN = [
    # UAE and GCC first: the UAE/GCC policy.
    r'uae', r'u\.a\.e\.?', r'emirates?', r'emirati', r'abu dhabi', r'dubai', r'sharjah', r'ajman', r'ras al khaimah',
    r'fujairah', r'umm al quwain', r'saudi(?: arabia)?', r'saudis', r'(?-i:KSA)', r'riyadh', r'jeddah', r'neom', r'humain',
    r'qatar\w*', r'doha', r'bahrain\w*', r'manama', r'kuwait\w*', r'oman', r'omani', r'muscat', r'gcc',
    r'gulf cooperation council', r'gulf states',
    r'afghanistan', r'albania', r'algeria', r'andorra', r'angola', r'argentina', r'armenia', r'australia', r'austria',
    r'azerbaijan', r'bahamas', r'bangladesh', r'barbados', r'belarus', r'belgium', r'belize', r'benin', r'bhutan',
    r'bolivia', r'bosnia', r'botswana', r'brazil', r'brunei', r'bulgaria', r'burkina faso', r'burundi', r'cambodia',
    r'cameroon', r'canada', r'cape verde', r'chad', r'chile', r'china', r'colombia', r'comoros', r'congo',
    r'costa rica', r'croatia', r'cuba', r'cyprus', r'czechia', r'czech republic', r'denmark', r'djibouti',
    r'dominican republic', r'ecuador', r'egypt\w*', r'el salvador', r'eritrea', r'estonia', r'eswatini', r'ethiopia',
    r'fiji', r'finland', r'france', r'gabon', r'gambia', r'georgia', r'germany', r'ghana', r'greece', r'guatemala',
    r'guinea', r'guyana', r'haiti', r'honduras', r'hong kong', r'hungary', r'iceland', r'india', r'indonesia', r'iran',
    r'iraq', r'ireland', r'israel', r'italy', r'ivory coast', r'jamaica', r'japan', r'jordan', r'kazakhstan', r'kenya',
    r'kosovo', r'kyrgyzstan', r'laos', r'latvia', r'lebanon', r'lesotho', r'liberia', r'libya', r'liechtenstein',
    r'lithuania', r'luxembourg', r'madagascar', r'malawi', r'malaysia', r'maldives', r'mali', r'malta', r'mauritania',
    r'mauritius', r'mexico', r'moldova', r'monaco', r'mongolia', r'montenegro', r'morocco', r'mozambique', r'myanmar',
    r'namibia', r'nepal', r'netherlands', r'new zealand', r'nicaragua', r'niger', r'nigeria', r'north korea',
    r'north macedonia', r'norway', r'pakistan', r'palestin\w*', r'panama', r'papua new guinea', r'paraguay', r'peru',
    r'philippines', r'poland', r'portugal', r'romania', r'russia', r'rwanda', r'senegal', r'serbia', r'seychelles',
    r'sierra leone', r'singapore', r'slovakia', r'slovenia', r'somalia', r'south africa', r'south korea', r'korea',
    r'south sudan', r'spain', r'sri lanka', r'sudan', r'suriname', r'sweden', r'switzerland', r'syria', r'taiwan',
    r'tajikistan', r'tanzania', r'thailand', r'togo', r'trinidad', r'tunisia', r'turkey', r't\u00fcrkiye', r'turkiye',
    r'turkmenistan', r'uganda', r'ukraine', r'united kingdom', r'(?-i:UK)', r'u\.k\.', r'britain', r'england', r'scotland',
    r'wales', r'united states', r'u\.s\.(?:a\.)?', r'(?-i:US)', r'usa', r'america', r'uruguay', r'uzbekistan', r'vatican',
    r'venezuela', r'vietnam', r'viet nam', r'yemen', r'zambia', r'zimbabwe',
    r'european union', r'european commission', r'(?-i:EU)', r'united nations', r'(?-i:UN)', r'nato', r'african union',
]
STATE_EN = [
    r'governments?', r'governmental', r'ministry', r'ministries', r'ministers?', r'prime minister', r'president',
    r'presidential', r'head of state', r'state visit', r'kings?', r'queen', r'royal', r'princes?', r'crown prince',
    r'sheikh\w*', r'emir', r'his highness', r'her highness', r'sultan\w*', r'national day', r'national',
    r'nations?', r'sovereign\w*', r'ai day', r'embass(?:y|ies)', r'ambassadors?', r'parliament\w*', r'congress',
    r'senate', r'white house', r'pentagon', r'military', r'armed forces', r'department of (?:defen[cs]e|war|state)',
    r'public sector', r'countries', r'country', r'national flags?',
]
PLACE_AR = [
    'الإمارات', 'الامارات', 'إماراتي', 'اماراتي', 'أبوظبي', 'ابوظبي', 'أبو ظبي', 'دبي', 'الشارقة', 'عجمان',
    'رأس الخيمة', 'الفجيرة', 'أم القيوين', 'السعودية', 'سعودي', 'سعودية', 'المملكة', 'الرياض', 'جدة', 'نيوم', 'هيوماين',
    'قطر', 'قطري', 'قطرية', 'الدوحة', 'البحرين', 'بحريني', 'بحرينية', 'المنامة', 'الكويت', 'كويتي', 'كويتية', 'عمان',
    'عُمان', 'عماني', 'عمانية', 'مسقط', 'الخليج', 'الخليجي', 'الخليجية', 'مجلس التعاون', 'مصر', 'مصري', 'مصرية',
    'الأردن', 'العراق', 'سوريا', 'لبنان', 'فلسطين', 'اليمن', 'ليبيا', 'تونس', 'الجزائر', 'المغرب', 'السودان',
    'موريتانيا', 'الصومال', 'جيبوتي', 'جزر القمر', 'الصين', 'الهند', 'اليابان', 'كوريا', 'روسيا', 'أوكرانيا',
    'تركيا', 'إيران', 'باكستان', 'إندونيسيا', 'ماليزيا', 'سنغافورة', 'تايوان', 'فرنسا', 'ألمانيا', 'بريطانيا',
    'المملكة المتحدة', 'إيطاليا', 'إسبانيا', 'الولايات المتحدة', 'أمريكا', 'أميركا', 'كندا', 'البرازيل', 'أستراليا',
    'الاتحاد الأوروبي', 'الأمم المتحدة', 'دولة', 'دول', 'الدولة', 'حكومة', 'حكومي', 'حكومية', 'الحكومات', 'وزير',
    'وزيرة', 'وزارة', 'وزراء', 'رئيس الدولة', 'رئيس الوزراء', 'رئيس الجمهورية', 'الملك', 'الأمير', 'ولي العهد', 'سمو',
    'الشيخ', 'السلطان', 'اليوم الوطني', 'الوطني', 'الوطنية', 'سيادي', 'سيادية', 'السيادة', 'سفارة', 'سفير', 'البرلمان',
]
PLACE_RX = topics._compile({'en': COUNTRIES_EN + STATE_EN, 'ar': PLACE_AR}, whole_ar=True)

def place_story(item):
    """The first country / government / national-event word in the story's headline, its Arabic translation or its
    excerpt ('' when none): such a story gets the topic image, never the company's photo."""
    text = ' \n '.join(x for x in (item.get('title'), item.get('title_ar'), item.get('excerpt')) if isinstance(x, str) and x)
    return next(iter(topics._hits(PLACE_RX, text)), '')

def own_post(item, source):
    """Is the article one of the company's own posts? (the source's "image_page_paths" regex on the page path)"""
    pattern = (source or {}).get('image_page_paths')
    if not pattern:
        return True
    try:
        return bool(re.search(pattern, urlparse(item.get('url') or '').path))
    except (re.error, ValueError):
        return False

def eligible(item, source):
    """May this story show a company image? An official company source (kind "primary") with an image allow-list and
    the company's own post; never a UAE/GCC official source, a UAE story or a story about a country or government."""
    return bool(source and source.get('kind') == 'primary' and source.get('image_hosts') and source.get('region') != 'uae'
                and not topics.uae_official(source) and not item.get('uae') and own_post(item, source)
                and not place_story(item))

def host_ok(url, source):
    """Is this an https URL on the source's image allow-list ("host" or "host/path-prefix")?"""
    try:
        u = urlparse(url)
    except ValueError:
        return False
    host = (u.hostname or '').lower()
    if u.scheme != 'https' or u.username or u.password or u.port not in (None, 443) or not host:
        return False
    # "/allowed-prefix/../other-bucket/x.png" and its encoded forms would pass a plain prefix check.
    path = unquote(u.path)
    if '\\' in path or '%' in path or any(seg in ('.', '..') for seg in path.split('/')):
        return False
    for entry in (source or {}).get('image_hosts', []):
        h, _, prefix = entry.partition('/')
        if host == h.lower() and (not prefix or u.path.startswith('/' + prefix)):
            return True
    return False

def usable(url, source):
    skip = (source or {}).get('image_skip')
    return host_ok(url, source) and not (skip and re.search(skip, url))

def page_images(page, base):
    """og:image / twitter:image URLs of an HTML page, in IMAGE_KEYS order, made absolute against `base`."""
    found = {}
    for m in META.finditer(page):
        tag = m.group(0)
        key = re.search(r'\b(?:property|name)\s*=\s*["\']([^"\']+)["\']', tag, re.I)
        val = re.search(r'\bcontent\s*=\s*["\']([^"\']*)["\']', tag, re.I)
        if key and val and key.group(1).strip().lower() in IMAGE_KEYS and val.group(1).strip():
            found.setdefault(key.group(1).strip().lower(), urljoin(base, html.unescape(val.group(1).strip())))
    return list(dict.fromkeys(found[k] for k in IMAGE_KEYS if k in found))

def credit(source):
    return (source or {}).get('image_credit') or (source or {}).get('name') or ''

# ---------- network (replaced by fakes in the unit tests) ----------

class _StayOnImageHosts(HTTPRedirectHandler):
    def __init__(self, source):
        self.source = source

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not host_ok(newurl, self.source):
            raise HTTPError(newurl, code, 'Redirect off the image hosts', headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, newurl)

def _transient(exc):
    if isinstance(exc, HTTPError):
        # 401/403/429 are often a bot wall seen from one runner's address, not a lasting answer: tried again later.
        return exc.code in (401, 403, 408, 425, 429) or exc.code >= 500
    return isinstance(exc, (URLError, TimeoutError, ConnectionError, OSError))

def fetch_page(url, source):
    """The article page's HTML (at most PAGE_BYTES), read like the news monitor reads it."""
    news = _news()
    if source.get('image_page_hosts'):
        source = {**source, 'link_hosts': list(source.get('link_hosts', [])) + list(source['image_page_hosts'])}
    if source.get('read_pages') is False or not news.allowed(url, source):
        raise Skip('page off the source')
    url = quote(url, safe=":/?#[]@!$&'()*+,;=%~")
    try:
        if not news.robots_allowed(url, source):
            # news._robots sets disallow_all only when robots.txt could not be read (network error, 5xx, 401/403);
            # a robots.txt that says no never sets it (RobotFileParser.parse does not). The first is tried again.
            rp = news._ROBOTS.get(urlparse(url).hostname or '')
            raise (Retry if getattr(rp, 'disallow_all', False) else Skip)('robots')
        with news._open(url, source, 'text/html,application/xhtml+xml') as r:
            if not news.allowed(r.geturl(), source) or 'html' not in (r.headers.get('Content-Type') or '').lower():
                raise Skip('not an html page')
            charset = r.headers.get_content_charset() or 'utf-8'
            raw = news._read(r, PAGE_BYTES, time.monotonic() + DEADLINE)
    except (Skip, Retry):
        raise
    except Exception as exc:
        raise (Retry if _transient(exc) else Skip)(type(exc).__name__) from None
    try:
        return raw.decode(charset, errors='replace')
    except LookupError:
        return raw.decode('utf-8', errors='replace')

def download(url, source):
    """The image bytes: image/* only (not SVG), at most MAX_DOWNLOAD, redirects kept on the allow-list."""
    if not host_ok(url, source):
        raise Skip('image host not allowed')
    news = _news()
    req = Request(quote(url, safe=":/?#[]@!$&'()*+,;=%~"), headers={'User-Agent': news.UA, 'Accept': 'image/webp,image/png,image/jpeg,image/gif;q=0.9'})
    try:
        with build_opener(_StayOnImageHosts(source)).open(req, timeout=TIMEOUT) as r:
            kind = (r.headers.get('Content-Type') or '').split(';')[0].strip().lower()
            if not host_ok(r.geturl(), source):
                raise Skip('image host not allowed')
            if not kind.startswith('image/') or 'svg' in kind:
                raise Skip('not an image')
            size = r.headers.get('Content-Length')
            if size and size.isdigit() and int(size) > MAX_DOWNLOAD:
                raise Skip('image too large')
            raw = news._read(r, MAX_DOWNLOAD + 1, time.monotonic() + DEADLINE)
    except (Skip, Retry):
        raise
    except Exception as exc:
        raise (Retry if _transient(exc) else Skip)(type(exc).__name__) from None
    if len(raw) > MAX_DOWNLOAD:
        raise Skip('image too large')
    return raw

# ---------- conversion ----------

def to_webp(raw):
    """(WebP bytes, width, height): at most MAX_WIDTH wide and MAX_OUT bytes, flattened on white (a transparent logo
    stays readable in dark mode), first frame of an animation. Raises Skip for anything else."""
    from PIL import Image, ImageOps
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            im = Image.open(io.BytesIO(raw))
            if im.format not in FORMATS:
                raise Skip('image format')
            im.seek(0)
            im.load()
    except (Skip, Retry):
        raise
    except Exception:
        raise Skip('unreadable image') from None
    try:
        im = ImageOps.exif_transpose(im)  # a photo stored sideways with an EXIF "rotate" tag
    except Exception:
        pass
    if im.width < 32 or im.height < 32:
        raise Skip('image too small')
    im = im.convert('RGBA')
    flat = Image.new('RGB', im.size, (255, 255, 255))
    flat.paste(im, mask=im.getchannel('A'))
    width = min(MAX_WIDTH, flat.width)
    while width >= MIN_WIDTH:
        height = max(1, round(flat.height * width / flat.width))
        small = flat.resize((width, height), Image.LANCZOS) if width != flat.width else flat
        for quality in (80, 70, 60, 50, 40):
            buf = io.BytesIO()
            small.save(buf, 'WEBP', quality=quality, method=6)
            if buf.tell() <= MAX_OUT:
                return buf.getvalue(), width, height
        width = int(width * 0.8)
    raise Skip('cannot fit the size limit')

# ---------- cache ----------

def _now():
    return datetime.now(timezone.utc).replace(microsecond=0)

def load_index(cache_dir):
    try:
        data = json.loads((Path(cache_dir) / INDEX).read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}

def save_index(cache_dir, index):
    path = Path(cache_dir) / INDEX
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(index, indent=1, ensure_ascii=False, sort_keys=True) + '\n', encoding='utf-8')
    tmp.replace(path)

def _hosts_key(source):
    return sorted(source.get('image_hosts', [])) + [source.get('image_skip') or ''] + sorted(source.get('image_page_hosts', []))

def fetch_one(item, source, cache_dir):
    """Find, download and convert one story's company image into the cache. Returns the index entry."""
    entry = {'source': item['source'], 'page_url': item['url'], 'fetched_at': _now().isoformat(), 'hosts': _hosts_key(source)}
    try:
        candidates = [item['image']] if isinstance(item.get('image'), str) and item['image'].startswith('https://') else []
        if not any(usable(u, source) for u in candidates):
            candidates = page_images(fetch_page(item['url'], source), item['url'])
        url = next((u for u in candidates if usable(u, source)), None)
        if not url:
            raise Skip('no allowed image' if candidates else 'no image on the page')
        webp, w, h = to_webp(download(url, source))
        name = f'{item["id"]}.webp'
        (Path(cache_dir) / name).write_bytes(webp)
        entry.update(status='ok', file=name, image_url=url, width=w, height=h)
    except Retry as exc:
        entry.update(status='retry', reason=str(exc))
    except Skip as exc:
        entry.update(status='none', reason=str(exc))
    except Exception as exc:  # never fail the build
        entry.update(status='none', reason=type(exc).__name__)
    return entry

def _needs_fetch(entry, source, cache_dir):
    if not entry:
        return True
    if entry.get('hosts') != _hosts_key(source):
        return True  # the allow-list changed since: look again
    if entry.get('status') == 'ok':
        return not (Path(cache_dir) / entry.get('file', '')).is_file()
    if entry.get('status') == 'retry':
        # A few tries in a row, then one a day: an outage or a bot wall never takes a company image for good.
        return entry.get('tries', 1) < TRIES or _older(entry, _now() - RETRY_AFTER)
    return False

def run(out_dir, items, src, cache_dir=None, network=True, log=print):
    """Company images for the shown `items`: {item id: {'file', 'width', 'height', 'credit'}} (file relative to the
    site root), with each file copied into out_dir/images/news. Never raises; returns {} on any trouble."""
    try:
        return _run(Path(out_dir), items, src, Path(cache_dir) if cache_dir else CACHE, network, log)
    except Exception as exc:
        log(f'News images: skipped ({type(exc).__name__}); topic images used')
        return {}

def _run(out_dir, items, src, cache_dir, network, log):
    cache_dir.mkdir(parents=True, exist_ok=True)
    index = load_index(cache_dir)
    wanted = [(i, src[i['source']]) for i in items if eligible(i, src.get(i['source']))]
    todo = [(i, s) for i, s in wanted if _needs_fetch(index.get(i['id']), s, cache_dir)] if network else []
    fresh, failed = set(), 0
    if todo:
        start = time.monotonic()
        def task(pair):
            if time.monotonic() - start > RUN_BUDGET:
                return pair[0]['id'], None
            return pair[0]['id'], fetch_one(pair[0], pair[1], cache_dir)
        with concurrent.futures.ThreadPoolExecutor(WORKERS) as pool:
            for item_id, entry in pool.map(task, todo):
                if entry is None:
                    continue
                old = index.get(item_id) or {}
                if entry['status'] == 'retry':
                    entry['tries'] = (old.get('tries', 0) if old.get('status') == 'retry' else 0) + 1
                index[item_id] = entry
                if entry['status'] == 'ok':
                    fresh.add(item_id)
                failed += entry['status'] != 'ok'
    # A picture a source uses for several stories is a generic card (a logo), not the story's image.
    uses = {}
    for e in index.values():
        if e.get('status') == 'ok':
            key = (e.get('source'), e.get('image_url'))
            uses[key] = uses.get(key, 0) + 1
    out, target = {}, out_dir / OUT_DIR
    for i, s in wanted:
        try:  # a bad entry (hand-edited, an older format) costs only its own story's image
            e = index.get(i['id']) or {}
            if e.get('status') != 'ok' or not isinstance(e.get('file'), str) or not e['file']:
                continue
            f = cache_dir / Path(e['file']).name
            w, h = int(e['width']), int(e['height'])
            if (w <= 0 or h <= 0 or not f.is_file() or not usable(e.get('image_url', ''), s)
                    or uses.get((e.get('source'), e.get('image_url')), 0) > 1):
                continue
            target.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(f, target / f.name)
            out[i['id']] = {'file': f'{OUT_DIR}/{f.name}', 'width': w, 'height': h, 'credit': credit(s)}
        except Exception:
            continue
    # An image left in the output by an earlier build (a story no longer shown, or no longer allowed a company image)
    # must not stay published.
    keep = {Path(v['file']).name for v in out.values()}
    for f in (target.glob('*.webp') if target.is_dir() else []):
        if f.name not in keep:
            f.unlink(missing_ok=True)
    # Forget stories no longer shown once they are old.
    shown, cutoff = {i['id'] for i in items}, _now() - timedelta(days=KEEP_DAYS)
    for item_id in [k for k, e in index.items() if k not in shown and _older(e, cutoff)]:
        e = index.pop(item_id)
        if e.get('file'):
            (cache_dir / e['file']).unlink(missing_ok=True)
    save_index(cache_dir, index)
    new = len(fresh & set(out))
    log(f'News images: {len(out)} company images ({new} new, {len(out) - new} from cache), '
        f'{len(items) - len(out)} topic images; {failed} fetches without an image this run')
    return out

def _older(entry, cutoff):
    try:
        return datetime.fromisoformat(entry.get('fetched_at', '')) < cutoff
    except (TypeError, ValueError):
        return True

def copy_topic_images(out_dir):
    """web/news-img/*.svg -> out_dir/news-img/."""
    target = Path(out_dir) / TOPIC_DIR
    target.mkdir(parents=True, exist_ok=True)
    for f in TOPIC_SRC.glob('*.svg'):
        shutil.copyfile(f, target / f.name)

def pictures(items, src, company=None):
    """{item id: picture} for every shown item: the company image from `company` (run()'s result) when there is one,
    else the topic image. A picture is {'file', 'width', 'height', 'credit' (company images) or 'topic'}."""
    company = company or {}
    out = {}
    for i in items:
        s = src.get(i['source'])
        t = topics.topic_of(i, s)
        if i['id'] in company and eligible(i, s):
            out[i['id']] = {**company[i['id']], 'topic': t}
        else:
            out[i['id']] = {'file': f'{TOPIC_DIR}/{t}.svg', 'width': TOPIC_SIZE[0], 'height': TOPIC_SIZE[1], 'topic': t}
    return out
