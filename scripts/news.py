"""Collect AI headlines twice a day from vetted feeds in data/news-sources.json.

Only titles, links, source names and dates are stored - never article text.
Item links must stay on the source's own domains. General-news feeds are kept only
for items that mention AI. With ANTHROPIC_API_KEY set, recent English headlines get an
Arabic translation from Claude, marked as machine-translated on the page.
A failing feed keeps its previous items; nothing is deleted because a fetch failed.
"""
import concurrent.futures
import hashlib
import html
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / 'data/news-sources.json'
OUT = ROOT / 'data/news.json'
MODEL = 'claude-opus-5'
KEEP_DAYS = 14
PER_FEED = 25
RAW_LIMIT = 80  # some feeds (OpenAI, Hugging Face) return their whole archive
TRANSLATE_PER_RUN = 20
ATOM = '{http://www.w3.org/2005/Atom}'
AI_EN = re.compile(r"\b(AI|A\.I\.|artificial intelligence|machine learning|deep learning|LLMs?|large language models?|generative|chatbots?|GPUs?|data ?cent(?:er|re)s?|supercomput\w*|OpenAI|Anthropic|Claude|ChatGPT|Gemini|DeepMind|Copilot|NVIDIA|AMD Instinct|G42|MBZUAI|Falcon LLM|Stargate|neural|robot\w*)\b", re.I)
AI_AR = re.compile(r'الذكاء الاصطناعي|الذكاء الإصطناعي|ذكاء اصطناعي|تعلم الآلة|التعلم الآلي|التعلم العميق|نماذج لغوية|النماذج اللغوية|روبوت|الرقائق|أشباه الموصلات|مراكز البيانات|مركز بيانات|إنفيديا|انفيديا|أوبن إيه آي|شات ?جي ?بي ?تي|جيميني|\bAI\b|G42')
UAE = re.compile(r'\b(UAE|U\.A\.E\.|Emirat\w*|Abu Dhabi|Dubai|Sharjah|MBZUAI|G42|Khazna|Stargate UAE)\b|الإمارات|الامارات|أبوظبي|أبو ظبي|دبي|الشارقة|إماراتي', re.I)

def domains(source):
    hosts = {urlparse(source['homepage']).hostname or ''} | set(source.get('link_hosts', []))
    return {h[4:] if h.startswith('www.') else h for h in hosts if h}

def allowed(url, source):
    u = urlparse(url)
    host = u.hostname or ''
    return u.scheme == 'https' and not u.username and u.port in (None, 443) and any(host == d or host.endswith('.' + d) for d in domains(source))

def clean(text):
    text = html.unescape(re.sub(r'<[^>]+>', ' ', text or ''))
    return re.sub(r'\s+', ' ', text).strip()[:240]

def parse_date(value):
    if not value:
        return None
    value = value.strip()
    try:
        d = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        try:
            d = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            return None
    return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)

def parse_feed(raw):
    """Yield (title, link, published) from RSS 2.0 or Atom bytes."""
    root = ET.fromstring(raw)
    for item in root.iter('item'):
        yield clean(item.findtext('title')), (item.findtext('link') or '').strip(), parse_date(item.findtext('pubDate') or item.findtext('{http://purl.org/dc/elements/1.1/}date'))
    for entry in root.iter(ATOM + 'entry'):
        link = ''
        for l in entry.findall(ATOM + 'link'):
            if l.get('rel', 'alternate') == 'alternate':
                link = l.get('href', '')
                break
        yield clean(entry.findtext(ATOM + 'title')), link.strip(), parse_date(entry.findtext(ATOM + 'published') or entry.findtext(ATOM + 'updated'))

def fetch(url):
    req = Request(url, headers={'User-Agent': 'AI-Hardware-Atlas/1.0 (news monitor)', 'Accept': 'application/rss+xml, application/atom+xml, application/xml, text/xml'})
    with urlopen(req, timeout=25) as r:
        raw = r.read(8_000_001)
    if len(raw) > 8_000_000:
        raise ValueError('Feed exceeded size limit')
    return raw

def collect(source, now):
    items = []
    for n, (title, link, published) in enumerate(parse_feed(fetch(source['feed']))):
        if n >= RAW_LIMIT:
            break
        if not title or not published or not allowed(link, source) or published > now + timedelta(hours=6):
            continue
        if now - published > timedelta(days=KEEP_DAYS):
            continue
        if not source['ai_only'] and not (AI_AR if source['lang'] == 'ar' else AI_EN).search(title):
            continue
        items.append({'id': hashlib.sha1(link.encode()).hexdigest()[:12], 'title': title, 'url': link, 'source': source['id'],
                      'lang': source['lang'], 'uae': source['region'] == 'uae' or bool(UAE.search(title)), 'published': published.replace(microsecond=0).isoformat()})
        if len(items) >= PER_FEED:
            break
    return items

class Translation(BaseModel):
    id: str
    title_ar: str

class Translations(BaseModel):
    translations: list[Translation]

def translate(items):
    """Add title_ar to up to TRANSLATE_PER_RUN recent English items. Returns count translated."""
    if not os.environ.get('ANTHROPIC_API_KEY'):
        return 0
    import anthropic
    todo = [i for i in items if i['lang'] == 'en' and not i.get('title_ar')][:TRANSLATE_PER_RUN]
    if not todo:
        return 0
    listing = '\n'.join(f"{i['id']}\t{i['title']}" for i in todo)
    try:
        response = anthropic.Anthropic().messages.parse(
            model=MODEL, max_tokens=16000, output_format=Translations,
            system='Translate English news headlines into natural Modern Standard Arabic for a Gulf audience. Keep the meaning exact: do not add, soften or exaggerate claims. Keep product, company and model names in Latin script (e.g. NVIDIA, GPT-5, Instinct MI355X). Return one translation per id.',
            messages=[{'role': 'user', 'content': 'Headlines (id<TAB>headline):\n' + listing}])
    except (anthropic.APIConnectionError, anthropic.APIStatusError) as exc:
        print(f'Translation skipped: {type(exc).__name__}', file=sys.stderr)
        return 0
    if response.stop_reason != 'end_turn' or response.parsed_output is None:
        return 0
    wanted = {i['id']: i for i in todo}
    done = 0
    for t in response.parsed_output.translations:
        text = clean(t.title_ar)
        if t.id in wanted and re.search(r'[؀-ۿ]', text):
            wanted[t.id]['title_ar'] = text
            done += 1
    return done

def main():
    sources = json.loads(SOURCES.read_text(encoding='utf-8'))
    previous = json.loads(OUT.read_text(encoding='utf-8')) if OUT.exists() else {'items': []}
    now = datetime.now(timezone.utc).replace(microsecond=0)
    fresh, errors = {}, {}
    def load(source):
        try:
            return source['id'], collect(source, now), None
        except Exception as exc:
            return source['id'], None, type(exc).__name__
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        for sid, items, error in pool.map(load, sources):
            if error:
                errors[sid] = error
            else:
                fresh[sid] = items
    by_url = {}
    for item in previous['items']:
        # Items from a feed that failed this run are carried over unchanged.
        if item['source'] in errors or item['source'] not in fresh:
            by_url[item['url']] = item
    for items in fresh.values():
        for item in items:
            old = next((p for p in previous['items'] if p['url'] == item['url']), None)
            if old and old.get('title_ar') and old['title'] == item['title']:
                item['title_ar'] = old['title_ar']
            by_url[item['url']] = item
    cutoff = now - timedelta(days=KEEP_DAYS)
    items = sorted((i for i in by_url.values() if datetime.fromisoformat(i['published']) >= cutoff), key=lambda i: i['published'], reverse=True)
    translated = translate(items)
    data = {'updated_at': now.isoformat(), 'health': {'ok': len(fresh), 'failed': len(errors), 'sources': len(sources)}, 'errors': errors, 'items': items[:200]}
    tmp = OUT.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')
    tmp.replace(OUT)
    print(f"News: {len(fresh)}/{len(sources)} feeds, {len(items)} items, {sum(i['uae'] for i in items)} UAE, {translated} translated")
    return 0

if __name__ == '__main__':
    sys.exit(main())
