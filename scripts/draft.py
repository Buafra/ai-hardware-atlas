"""Draft catalog records for newly discovered official announcements with Claude.

Drafts go to data/drafts/ and reach the public catalog only after a person reviews
them and runs `python scripts/draft.py --promote data/drafts/<id>.json`.
Every draft must quote the official page verbatim for its key facts; quotes that are
not on the page reject the draft. Without ANTHROPIC_API_KEY the script does nothing.
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent))
from refresh import fetch, official  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DRAFTS = ROOT / 'data/drafts'
STATE = ROOT / 'data/draft-state.json'
MODEL = 'claude-opus-5'
MAX_PER_RUN = 3
DATE = re.compile(r'^\d{4}-(\d{2}(-\d{2})?|Q[1-4]|H[12]|Summer|end)$')

class Draft(BaseModel):
    is_new_product: bool
    vendor: Literal['NVIDIA', 'AMD']
    model: str
    level: Literal['Personal', 'Workstation', 'Enterprise', 'Data center', 'Rack scale']
    type: Literal['GPU', 'System', 'Platform', 'Server class', 'Rack', 'Reference design']
    architecture: str
    memory: str
    memory_gb: Optional[float]
    memory_scope: Literal['Per GPU', 'Shared CPU + GPU', 'System total', 'Rack total']
    announcement: Optional[str]
    release: Optional[str]
    release_kind: str
    power_w: Optional[float]
    use: str
    notes: str
    evidence: list[str]

SYSTEM = """You extract one draft product record for an NVIDIA/AMD AI hardware catalog from an official vendor page.
Rules:
- Use only facts stated on the page. If a value is not stated, use null (or "Not established" for release_kind). Never estimate.
- is_new_product is true only if the page announces or launches a specific GPU, accelerator, AI system or rack product. Earnings, partnerships, software and events without a named new product are false.
- announcement: the date this page announces it (YYYY-MM-DD). release: availability only if the page states it, as YYYY-MM-DD, YYYY-MM, YYYY-Q1..Q4 or YYYY-H1/H2. A future target is still a target; say so in release_kind (e.g. "Vendor target", "Expected", "Released", "Orders opened").
- memory: as the vendor writes it (e.g. "288 GB HBM3E"). memory_gb: the number in GB at the stated memory_scope. Per GPU for one accelerator; Shared CPU + GPU for unified memory; System total / Rack total for aggregates.
- level: Personal (consumer/desktop), Workstation, Enterprise (standard servers), Data center (accelerators/systems for AI data centers), Rack scale (whole racks or rack accelerators).
- use: at most six words describing the best fit. notes: one or two sentences of caveats (targets, configurable power, scope).
- evidence: short verbatim quotes copied exactly from the page that support the model name, memory and each date you give."""

def norm(text):
    return re.sub(r'\s+', ' ', text).strip().casefold()

def slug(model):
    return re.sub(r'[^a-z0-9]+', '-', model.lower()).strip('-')

def check_draft(d, page_text, catalog):
    """Return a rejection reason, or None when the draft may be written for review."""
    if not d['is_new_product']:
        return 'not a new product'
    known = {norm(p['model']) for p in catalog['products']} | {p['id'] for p in catalog['products']}
    if norm(d['model']) in known or slug(d['model']) in known:
        return 'already in catalog'
    if not d['evidence']:
        return 'no evidence quotes'
    page = norm(page_text)
    missing = [q for q in d['evidence'] if norm(q) not in page]
    if missing:
        return 'evidence not found on page: ' + missing[0][:80]
    for k in ('announcement', 'release'):
        if d[k] is not None and not DATE.match(d[k]):
            return f'bad {k} format'
    if d['memory_gb'] is not None and not 0 < d['memory_gb'] <= 2_000_000:
        return 'memory out of range'
    return None

def record(d, url, now):
    evidence = d.pop('evidence')
    d.pop('is_new_product')
    return {**d, 'id': slug(d['model']), 'source_reviewed': None,
            'power_note': 'Draft: confirm against the official specification' if d['power_w'] else 'Not documented in this edition',
            'sources': [{'label': 'Announcement', 'url': url}],
            '_draft': {'model': MODEL, 'created_at': now, 'source_url': url, 'evidence': evidence}}

def extract(client, url, title, text):
    import anthropic
    try:
        response = client.messages.parse(
            model=MODEL, max_tokens=16000, system=SYSTEM, output_format=Draft,
            messages=[{'role': 'user', 'content': f'Source URL: {url}\nHeadline: {title}\n\n<page>\n{text}\n</page>'}])
    except (anthropic.APIConnectionError, anthropic.RateLimitError) as exc:
        return None, 'retry later: ' + type(exc).__name__
    except anthropic.APIStatusError as exc:
        return None, f'api error {exc.status_code}'
    if response.stop_reason != 'end_turn' or response.parsed_output is None:
        return None, 'no draft (' + str(response.stop_reason) + ')'
    return response.parsed_output.model_dump(), None

def run():
    report_path = ROOT / 'data/draft-report.json'
    if not os.environ.get('ANTHROPIC_API_KEY'):
        report_path.write_text(json.dumps({'created': [], 'skipped': 'ANTHROPIC_API_KEY not set'}, indent=2) + '\n', encoding='utf-8', newline='\n')
        print('ANTHROPIC_API_KEY not set; skipping AI drafts.')
        return 0
    import anthropic
    client = anthropic.Anthropic()
    catalog = json.loads((ROOT / 'data/catalog.json').read_text(encoding='utf-8'))
    state = json.loads(STATE.read_text(encoding='utf-8')) if STATE.exists() else {}
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    DRAFTS.mkdir(parents=True, exist_ok=True)
    created, attempted = [], 0
    for item in catalog.get('announcements', []):
        url = item['url']
        if url in state or not official(url) or attempted >= MAX_PER_RUN:
            continue
        attempted += 1
        try:
            page = fetch(url)
        except Exception as exc:
            print(f'{url}: fetch failed ({type(exc).__name__}); will retry')
            continue
        draft, error = extract(client, url, item['title'], page.text)
        if error and error.startswith('retry later'):
            print(f'{url}: {error}')
            continue
        reason = error or check_draft(draft, page.text, catalog)
        state[url] = {'at': now, 'result': reason or 'drafted'}
        if reason:
            print(f'{url}: skipped ({reason})')
            continue
        rec = record(draft, url, now)
        (DRAFTS / f"{rec['id']}.json").write_text(json.dumps(rec, indent=2, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')
        created.append(rec['model'])
        print(f"{url}: drafted {rec['model']}")
    STATE.write_text(json.dumps(state, indent=2) + '\n', encoding='utf-8', newline='\n')
    report_path.write_text(json.dumps({'at': now, 'created': created}, indent=2) + '\n', encoding='utf-8', newline='\n')
    return 0

def promote(path):
    from build import validate
    draft = json.loads(Path(path).read_text(encoding='utf-8'))
    meta = draft.pop('_draft')
    if not draft.get('memory_gb'):
        sys.exit('Add memory_gb before promoting; the catalog requires it.')
    draft['source_reviewed'] = datetime.now(timezone.utc).date().isoformat()
    catalog_path = ROOT / 'data/catalog.json'
    catalog = json.loads(catalog_path.read_text(encoding='utf-8'))
    catalog['products'].append(draft)
    validate(catalog)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    catalog['changes'] = ([{'at': now, 'summary': f"Added {draft['model']} from {meta['source_url']} after review."}] + catalog['changes'])[:80]
    catalog['updated_at'] = now
    catalog_path.write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')
    Path(path).unlink()
    print(f"Promoted {draft['model']} into the catalog.")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--promote', metavar='DRAFT', help='move a reviewed draft into data/catalog.json')
    args = parser.parse_args()
    sys.exit(promote(args.promote) if args.promote else run())
