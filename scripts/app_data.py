"""Export the site's public data as JSON for the Cipher Lacuna Android app (dist/app/).

The app ships with a copy of these files and refreshes them from GitHub Pages; its background notification check
reads news.json. Everything here is already public on the site, and the same rules decide what is shown: the news
list is build.news_items() (AI-focused items only, and items that mention the UAE or a GCC state only with a passing
content-policy verdict, see scripts/policy.py), summaries come from build.summary_of(), backend-only catalog
fields stay out, and a concept's related_lessons lists only the Qahwa & AI lessons already published on qahwa.html
(learn.published_lessons(), the rule behind Learn AI's lesson chips), so a future lesson's title never reaches the app. manifest.json lists each file's SHA-256 so the app downloads only what changed.
"""
import hashlib
import json
import sys
from pathlib import Path

import build
import learn
import qahwa

APP_SCHEMA = 1
APP_DIR = 'app'
MODEL_KEYS = ('id', 'name', 'hf', 'params_b', 'params_source', 'open', 'moe', 'context')
ABOUT = build.ROOT / 'data' / 'about.json'  # the About text the site and the app share

def load_about(path=ABOUT):
    return json.loads(Path(path).read_text(encoding='utf-8'))

def news_entry(i, src):
    """One headline with everything the app shows: region tags, which language lists carry it, and per language the
    summary with its kind ('ai' or 'publisher'), exactly as the site decides them."""
    s = src[i['source']]
    out = {'id': i['id'], 'url': i['url'], 'source': i['source'], 'source_name': s['name'], 'source_name_ar': s.get('name_ar') or s['name'],
           'lang': i['lang'], 'regions': build.regions(i, src), 'uae': bool(i.get('uae')), 'published': i['published'],
           'title': i['title'], 'title_ar': i.get('title_ar'), 'in_en': build.in_lang(i, 'en'), 'in_ar': build.in_lang(i, 'ar')}
    for lang in ('en', 'ar'):
        text, kind = build.summary_of(i, lang)
        out[f'summary_{lang}'], out[f'summary_kind_{lang}'] = text, kind
    return out

def app_concepts(concepts_doc, lessons_doc):
    """The concepts with related_lessons cut to the published lessons, each with its qahwa.html deep link ('url')."""
    return [{**c, 'related_lessons': [{**les, 'url': url} for les, url in learn.published_lessons(c, lessons_doc)]}
            for c in concepts_doc['concepts']]

def payloads(data, feed, sources, uae, models, concepts_doc, stacks_doc, about=None, lessons_doc=None):
    """Return {file name: JSON-ready dict}. Pure: writes nothing. `data` must already be prepared (build.prepare).
    lessons_doc: the published Qahwa & AI posts (qahwa.page_doc()); None means none are published (no related lessons)."""
    if lessons_doc is None:
        lessons_doc = qahwa.empty_doc()
    c = build.context(data, feed, sources, uae)
    src = c['src']
    featured = [p['id'] for p in c['featured']]
    highlights = [f['id'] for f in c['highlights']]
    catalog = {k: v for k, v in data.items() if k not in build.BACKEND_ONLY}
    facts = sorted((uae or {}).get('facts', []), key=lambda f: str(f.get('as_of') or ''), reverse=True)
    return {
        'catalog.json': {'schema': APP_SCHEMA, **catalog, 'featured': featured, 'levels': build.LEVELS},
        'news.json': {'schema': APP_SCHEMA, 'updated_at': (feed or {}).get('updated_at'), 'schedule': build.schedule_times(data),
                      'sources': len(sources), 'items': [news_entry(i, src) for i in c['items']]},
        'uae.json': {'schema': APP_SCHEMA, 'checked': (uae or {}).get('checked'), 'highlights': highlights, 'facts': facts},
        'learn.json': {'schema': APP_SCHEMA, 'groups': concepts_doc['groups'], 'concepts': app_concepts(concepts_doc, lessons_doc),
                       'stacks': sorted(stacks_doc['stacks'], key=lambda s: s.get('order', 0))},
        'models.json': {'schema': APP_SCHEMA, 'updated_at': models.get('updated_at'), 'source': models.get('source'),
                        'models': [{k: m.get(k) for k in MODEL_KEYS} for m in models.get('models', [])]},
        'about.json': {'schema': APP_SCHEMA, **(about if about is not None else load_about())},
    }

def encode(payload):
    return (json.dumps(payload, ensure_ascii=False, separators=(',', ':')) + '\n').encode('utf-8')

def write(out_dir, data, feed, sources, uae, models, concepts_doc=None, stacks_doc=None, about=None, lessons_doc=None):
    """Write dist/app/*.json and manifest.json; return the manifest.
    lessons_doc: the published Qahwa & AI posts (default: learn.lessons_doc_safe(), from data/qahwa.json, as learn.html)."""
    if lessons_doc is None:
        lessons_doc = learn.lessons_doc_safe()
    if concepts_doc is None or stacks_doc is None:
        concepts_doc, stacks_doc = learn.load()
    target = Path(out_dir) / APP_DIR
    target.mkdir(parents=True, exist_ok=True)
    files = {}
    for name, payload in payloads(data, feed, sources, uae, models, concepts_doc, stacks_doc, about, lessons_doc).items():
        raw = encode(payload)
        (target / name).write_bytes(raw)
        files[name] = {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
    manifest = {'schema': APP_SCHEMA, 'generated_at': data.get('last_check_at') or data.get('updated_at'),
                'news_updated_at': (feed or {}).get('updated_at'), 'files': files}
    (target / 'manifest.json').write_bytes(encode(manifest))
    return manifest

def main():
    data, feed, sources, uae, models = build.load_all()
    manifest = write(build.OUT, data, feed, sources, uae, models)
    total = sum(f['bytes'] for f in manifest['files'].values())
    print(f"App data: {len(manifest['files'])} files, {total / 1024:.0f} KB in {build.OUT / APP_DIR}")
    return 0

if __name__ == '__main__':
    sys.exit(main())
