"""The news archive (owner request, Oct 2026): every vetted story that leaves the AI news window is kept, so it can still
be searched, listed in the weekly pages and read in the Android app. Rule-based, no AI, no network.

Files: data/news-archive/YYYY-MM.json, one per month of publication (UAE time), written by scripts/news.py:

    {"month": "2026-10", "policy_version": 1, "items": [slim item, ...]}      newest first

A slim item has exactly FIELDS: id, source, lang, uae, topic, published, title, title_ar, url, summary_en, summary_ar,
excerpt (null when the story has none). `topic` is the id scripts/topics.py gives the story (the rule behind its topic
image); summary_en and summary_ar are the AI summaries the site showed (summary_source "ai"), never a publisher's text;
title_ar is the AI translation of an English headline. `policy_version` is the lowest content-policy version
(scripts/policy.py) any item of the file was checked under.

  append()   news.py: the stories that leave the window this run (age or the item cap). Only stories the site could show:
             a passing content-policy verdict at the current version for their current texts (policy.verified), not
             judged "not mainly about AI", from a followed source, with an https link. Idempotent: one entry per id (and
             per link) in a month, rewritten only when something changed.
  drop()     news.py, every run: archived stories now on the content-policy block list (scripts/blocklist.py,
             data/news-blocked.json) are taken out of the newest REUSE_MONTHS month files. A story that comes back into
             the window is checked again, and one that then fails is removed and blocked: its archived copy goes too.
  begin()    news.py, every run: records the day the archive began (UAE time) in started.json, once, after the run's
             stories were archived. started() reads it (None before the first run): the weekly pages start that day.
  lookup()   news.py: the newest months by id and by link. reuse() gives a story that comes back into the window (same id
             or link) its archived AI summary and Arabic headline, so Claude is not paid twice for them. The content
             check still runs on it like on any story entering the window: its verdict is not reused.
  shown()    build.py and app_data.py: the archived stories the site may still show (a story that mentions the UAE or a
             GCC state only from a source that may cover the region and only from a file checked under the current
             policy version, never a story on the block list), without the stories already in the current list.
  publish()  build.py: dist/news-archive/index.json and dist/news-archive/YYYY-MM.json, the same-origin files the AI news
             and UAE AI "Search older stories" option loads on demand.
  app_items(): app_data.py: dist/app/archive.json, the last APP_DAYS days, newest first (app_data keeps it under
             APP_MAX_BYTES: the app downloads it beside news.json).
"""
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import blocklist
import policy
import topics

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / 'data' / 'news-archive'
PUBLIC_DIR = 'news-archive'  # dist/news-archive/
FIELDS = ('id', 'source', 'lang', 'uae', 'topic', 'published', 'title', 'title_ar', 'url', 'summary_en', 'summary_ar', 'excerpt')
UAE_TZ = timezone(timedelta(hours=4))
# The Android app's archive.json: the last APP_DAYS days (about 90 stories a day leave the window, about 2 KB each), and
# never more than APP_MAX_BYTES (app_data drops the oldest stories beyond it; the app refuses a file over 16 MiB).
APP_DAYS = 14
APP_MAX_BYTES = 4_000_000
REUSE_MONTHS = 3    # months read when a story comes back (a feed is read back KEEP_DAYS days only)
MONTH = re.compile(r'^(\d{4})-(0[1-9]|1[0-2])$')
SCHEMA = 1
START = 'started.json'  # the day the archive began (begin / started)
DAMAGED = set()  # months whose file could not be read by append() (news.py logs the count)

def uae_time(iso):
    """A stored timestamp in UAE time (naive timestamps count as UTC)."""
    d = datetime.fromisoformat(str(iso).replace('Z', '+00:00'))
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(UAE_TZ)

def month_of(item):
    """'YYYY-MM' of the story's publication, in UAE time."""
    return uae_time(item['published']).strftime('%Y-%m')

def _https(url):
    u = urlparse(str(url or ''))
    return u.scheme == 'https' and bool(u.hostname)

def _published_ok(item):
    try:
        uae_time(item.get('published'))
        return True
    except (TypeError, ValueError):
        return False

def archivable(item, source):
    """May this story enter the archive? Only one the site could show: a followed source, an https link, not judged
    "not mainly about AI", and a passing content-policy verdict at the current version for its current texts."""
    return (bool(source) and isinstance(item, dict) and bool(item.get('id')) and bool(item.get('title')) and _https(item.get('url'))
            and item.get('lang') in ('en', 'ar') and _published_ok(item) and item.get('ai_focus') is not False
            and policy.verified(item) and policy.shown_ok(item, source))

def slim(item, source=None):
    """The archive's copy of one story: exactly FIELDS, null for what the story does not have."""
    out = dict.fromkeys(FIELDS)
    for k in ('id', 'source', 'lang', 'published', 'title', 'url'):
        out[k] = item.get(k)
    out['uae'] = bool(item.get('uae'))
    out['topic'] = topics.topic_of(item, source)
    if item.get('lang') == 'en' and item.get('title_ar'):
        out['title_ar'] = item['title_ar']
    if item.get('summary_source') == 'ai' and item.get('summary_en') and item.get('summary_ar'):
        out['summary_en'], out['summary_ar'] = item['summary_en'], item['summary_ar']
    out['excerpt'] = item.get('excerpt') or None
    return out

def _order(items):
    return sorted(items, key=lambda i: (str(i.get('published') or ''), str(i.get('id') or '')), reverse=True)

def months(folder=DIR):
    """The months the archive has files for, newest first."""
    folder = Path(folder)
    if not folder.is_dir():
        return []
    return sorted((p.stem for p in folder.glob('*.json') if MONTH.match(p.stem)), reverse=True)

def read(path):
    """One month file as {'month', 'policy_version', 'items'}, or None when it is missing or unreadable (a damaged file
    never stops a run or a build: the build leaves it out, and append() leaves it untouched for a person to repair)."""
    try:
        doc = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    if not isinstance(doc, dict) or not isinstance(doc.get('items'), list):
        return None
    items = [i for i in doc['items'] if isinstance(i, dict) and i.get('id') and i.get('url') and _published_ok(i)]
    pv = doc.get('policy_version')
    return {'month': doc.get('month'), 'policy_version': pv if isinstance(pv, int) else 0, 'items': items}

def _write(path, month, policy_version, items):
    doc = {'month': month, 'policy_version': policy_version, 'items': _order(items)}
    text = json.dumps(doc, indent=1, ensure_ascii=False) + '\n'
    path = Path(path)
    if path.exists() and path.read_text(encoding='utf-8') == text:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(text, encoding='utf-8', newline='\n')
    tmp.replace(path)
    return True

def append(leaving, sources, folder=DIR, policy_version=None):
    """Add the stories leaving the window (news.py) to their month files. Only archivable() ones. One entry per id and
    per link in a month: a story archived before is replaced by its newer copy. A month's policy_version becomes the
    lowest version its items were checked under. Returns the number of entries added or changed."""
    policy_version = policy.POLICY_VERSION if policy_version is None else policy_version
    src = {s['id']: s for s in sources}
    by_month = {}
    for item in leaving:
        s = src.get((item or {}).get('source'))
        if archivable(item, s):
            entry = slim(item, s)
            by_month.setdefault(month_of(entry), {})[entry['id']] = entry
    changed = 0
    for month, entries in sorted(by_month.items()):
        path = Path(folder) / f'{month}.json'
        old = read(path)
        if old is None and path.exists():
            DAMAGED.add(month)  # left as it is for a person to repair: never overwritten with this run's stories only
            continue
        old = old or {'policy_version': policy_version, 'items': []}
        new_urls = {e['url'] for e in entries.values()}
        kept = [i for i in old['items'] if i['id'] not in entries and i['url'] not in new_urls]
        before = {i['id']: i for i in old['items']}
        changed += sum(1 for e in entries.values() if before.get(e['id']) != e)
        version = min(old['policy_version'], policy_version) if kept else policy_version
        _write(path, month, version, kept + list(entries.values()))
    return changed

def drop(blocked, folder=DIR, limit=REUSE_MONTHS):
    """Take the stories on the block list (`blocked`: {id: day}, blocklist.load()) out of the newest `limit` month files
    (a blocked story was in the window within the last KEEP_DAYS days, so its archived copy is in one of them). A
    damaged month is left as it is (shown() still hides its blocked stories). Returns the number of entries removed."""
    if not blocked:
        return 0
    removed = 0
    for month in months(folder)[:limit]:
        path = Path(folder) / f'{month}.json'
        doc = read(path)
        if doc is None:
            continue
        kept = [i for i in doc['items'] if not blocklist.is_blocked(i, blocked)]
        if len(kept) != len(doc['items']):
            removed += len(doc['items']) - len(kept)
            _write(path, month, doc['policy_version'], kept)
    return removed

def begin(now, folder=DIR):
    """Record the day the archive began (UAE time) in started.json, once: from that day on, every story the site lists is
    either still in news.json or archived when it leaves. Returns True when it was written now."""
    path = Path(folder) / START
    if started(folder) is not None:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = {'about': 'The day the news archive began (UAE time): the weekly pages start on it.',
           'started': now.astimezone(UAE_TZ).date().isoformat()}
    path.write_text(json.dumps(doc, indent=1) + '\n', encoding='utf-8', newline='\n')
    return True

def started(folder=DIR):
    """The day the archive began (a date), or None before the first run that archived (or a damaged started.json)."""
    try:
        return datetime.strptime(json.loads((Path(folder) / START).read_text(encoding='utf-8'))['started'], '%Y-%m-%d').date()
    except (OSError, ValueError, KeyError, TypeError):
        return None

def load(folder=DIR, limit=None):
    """Every archived story, newest month first, each with its file's policy version under '_pv' (a working key that
    shown() drops). `limit`: only the newest that many months."""
    out = []
    for month in months(folder)[:limit]:
        doc = read(Path(folder) / f'{month}.json')
        for item in (doc or {}).get('items', []):
            out.append({**item, '_pv': doc['policy_version']})
    return out

def lookup(folder=DIR, limit=REUSE_MONTHS):
    """{id: story} and {link: story} of the newest months, for reuse()."""
    by = {}
    for item in load(folder, limit):
        by.setdefault(('id', item['id']), item)
        by.setdefault(('url', item['url']), item)
    return by

def reuse(items, archived, summary_version):
    """Give stories that came back into the window what the archive kept of them (matched by id, else by link): the AI
    summary (when the story has none) and the Arabic headline (when it has none and the English headline is unchanged).
    Returns the number of stories that got something back."""
    n = 0
    for item in items:
        old = archived.get(('id', item.get('id'))) or archived.get(('url', item.get('url')))
        if not old:
            continue
        got = False
        if item.get('lang') == 'en' and not item.get('title_ar') and old.get('title_ar') and old.get('title') == item.get('title'):
            item['title_ar'] = old['title_ar']
            got = True
        if not item.get('summary_en') and old.get('summary_en') and old.get('summary_ar'):
            item.update(summary_en=old['summary_en'], summary_ar=old['summary_ar'], summary_source='ai',
                        summary_version=summary_version, ai_focus=True)
            item.pop('summary_attempts', None)
            item.pop('summary_attempts_version', None)
            got = True
        n += got
    return n

def shown(archived, sources, exclude=(), blocked=None):
    """The archived stories the site may show, newest first, each with exactly FIELDS: from a source still followed,
    with an https link; a story that mentions the UAE or a GCC state only from a source that may cover the region
    (rule M1) and only from a file checked under the current policy version (fail closed when the policy changed);
    never a story on the block list (`blocked`, blocklist.load(): drop() takes those out of the files, this is the
    second guard). One per id and per link; `exclude`: ids already in the current list."""
    src = {s['id']: s for s in sources}
    seen, out = set(exclude), []
    for item in _order(archived):
        s = src.get(item.get('source'))
        if not s or not _https(item.get('url')) or item.get('lang') not in ('en', 'ar') or not item.get('title'):
            continue
        if blocked and blocklist.is_blocked(item, blocked):
            continue
        if item['id'] in seen or ('url', item['url']) in seen:
            continue
        if policy.item_mentions_region(item) and not (policy.may_cover_region(s) and item.get('_pv', 0) >= policy.POLICY_VERSION):
            continue
        seen.update((item['id'], ('url', item['url'])))
        clean = {k: item.get(k) for k in FIELDS}
        clean['uae'] = bool(clean['uae'])
        if clean['topic'] not in topics.TOPICS:
            clean['topic'] = topics.topic_of(clean, s)
        out.append(clean)
    return out

def public_sources(sources):
    """What the older-stories search needs of each source: its names (the card's "Source:" link) and region."""
    return {s['id']: {'name': s['name'], 'name_ar': s.get('name_ar') or s['name'], 'region': s.get('region', 'global')} for s in sources}

def publish(out_dir, items, sources):
    """Write dist/news-archive/: index.json (months with their file and count, the sources' names and regions) and one
    file per month ({'month', 'items'}, FIELDS only, newest first) of shown() stories. Month files left from an earlier
    build are removed. Returns the index."""
    target = Path(out_dir) / PUBLIC_DIR
    by_month = {}
    for item in items:
        by_month.setdefault(month_of(item), []).append(item)
    target.mkdir(parents=True, exist_ok=True)
    for old in target.glob('*.json'):
        if old.name != 'index.json' and old.stem not in by_month:
            old.unlink()
    index = {'schema': SCHEMA, 'count': len(items), 'months': [], 'sources': public_sources(sources)}
    for month in sorted(by_month, reverse=True):
        part = _order(by_month[month])
        (target / f'{month}.json').write_text(json.dumps({'month': month, 'items': part}, ensure_ascii=False, separators=(',', ':')) + '\n',
                                               encoding='utf-8', newline='\n')
        index['months'].append({'month': month, 'file': f'{month}.json', 'count': len(part)})
    (target / 'index.json').write_text(json.dumps(index, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8', newline='\n')
    return index

def app_items(items, now, days=APP_DAYS):
    """The archived stories of the last `days` days before `now`, newest first (the app's archive.json)."""
    cutoff = now - timedelta(days=days)
    return [i for i in _order(items) if uae_time(i['published']) >= cutoff]
