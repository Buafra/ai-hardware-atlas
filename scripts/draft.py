"""Draft catalog records for newly discovered official announcements with Claude.

Drafts go to data/drafts/ and reach the public catalog only after a person reviews
them and runs `python scripts/draft.py --promote data/drafts/<id>.json`.
Every draft must quote the official page verbatim for its key facts; quotes that are
not on the page reject the draft. Without ANTHROPIC_API_KEY no new drafts are made.

An announcement counts as done only once its draft is in a pull request. Until then the
draft waits in data/draft-state.json ("pending", with the whole record): every run writes
it to data/drafts/ again (no new Claude request) and the workflow tries the pull request
again; `--pr-result` records what the workflow's pull-request step did (a failure goes to
the review issue through data/draft-report.json). Drafts in a pull request that is still
open are written again too, so a later run adds to that pull request instead of
replacing its files. A draft leaves the state once its product is in the catalog or its
pull request was merged or closed.
"""
import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ai_cost  # noqa: E402
from refresh import fetch, official  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DRAFTS = ROOT / 'data/drafts'
STATE = ROOT / 'data/draft-state.json'
REPORT = ROOT / 'data/draft-report.json'
CATALOG = ROOT / 'data/catalog.json'
PENDING, DRAFTED = 'pending', 'drafted'  # waiting for a pull request / in one (done)
PR_SETTING = ('Settings > Actions > General > Workflow permissions > "Allow GitHub Actions to create and approve '
              'pull requests"')
MODEL = 'claude-sonnet-5-5'
PRICE_IN, PRICE_OUT = 2.0, 10.0  # US dollars per million input / output tokens for MODEL (as in news.py); asked directly
USAGE = {'requests': 0, 'input_tokens': 0, 'output_tokens': 0}  # this run's Claude requests
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
    usage = getattr(response, 'usage', None)  # fake clients in tests carry none
    USAGE['requests'] += 1
    USAGE['input_tokens'] += getattr(usage, 'input_tokens', 0) or 0
    USAGE['output_tokens'] += getattr(usage, 'output_tokens', 0) or 0
    if response.stop_reason != 'end_turn' or response.parsed_output is None:
        return None, 'no draft (' + str(response.stop_reason) + ')'
    return response.parsed_output.model_dump(), None

def usage_report():
    """This run's Claude requests, tokens and estimated cost (for data/draft-report.json and the cost ledger)."""
    return {**USAGE, 'estimated_usd': round((USAGE['input_tokens'] * PRICE_IN + USAGE['output_tokens'] * PRICE_OUT) / 1e6, 4)}

def record_cost():
    """Add this run's estimate to the monthly ledger (data/ai-cost.json); a ledger problem never fails the run."""
    use = usage_report()
    try:
        ai_cost.add(use['estimated_usd'], use['requests'])
    except Exception as exc:
        print(f'AI cost ledger not updated ({type(exc).__name__})', file=sys.stderr)

def _load(path, default):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return default

def _save_state(state):
    STATE.write_text(json.dumps(state, indent=2) + '\n', encoding='utf-8', newline='\n')

def _save_report(report):
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')

def open_drafts(state):
    """(url, entry) of the drafts the owner has not dealt with yet: waiting for a pull request (pending) or in one that
    is still open (drafted). Their records are written to data/drafts/ on every run."""
    return [(url, e) for url, e in state.items() if e.get('draft') and e.get('result') in (PENDING, DRAFTED)]

def _open_report(state):
    """The open drafts for data/draft-report.json (and the review issue): waiting for a pull request, in one, and which."""
    models = lambda result: [e['model'] for _, e in open_drafts(state) if e['result'] == result]
    return {'waiting': models(PENDING), 'in_pull_request': models(DRAFTED),
            'pull_requests': sorted({e['pr'] for _, e in open_drafts(state) if e['result'] == DRAFTED})}

def pr_state(number, run=subprocess.run):
    """'OPEN', 'MERGED' or 'CLOSED' for pull request `number` (gh with GH_TOKEN, read only), or None when that
    cannot be told."""
    try:
        out = run(['gh', 'pr', 'view', str(number), '--json', 'state', '--jq', '.state'], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    state = (out.stdout or '').strip().upper()
    return state if out.returncode == 0 and state in ('OPEN', 'MERGED', 'CLOSED') else None

def settle(state, catalog, ask=pr_state):
    """Drafts that need nothing more leave the state (the outcome stays): the product is in the catalog now (promoted
    or added by hand), or the pull request holding the draft was merged or closed. A pull request whose state cannot
    be told keeps its drafts (written again rather than lost)."""
    ids, prs = {p['id'] for p in catalog['products']}, {}
    for _, e in open_drafts(state):
        if e['result'] == DRAFTED and e['pr'] not in prs:
            prs[e['pr']] = ask(e['pr'])  # once per pull request
        if e['id'] in ids:
            done = 'in catalog'
        elif e['result'] == DRAFTED and prs[e['pr']] in ('MERGED', 'CLOSED'):
            done = 'pull request ' + prs[e['pr']].lower()
        else:
            continue
        del e['draft']
        e['closed'] = done

def write_drafts(state, folder=None):
    """Write every open draft to data/drafts/<id>.json, for the workflow's pull-request step. Returns how many."""
    drafts = open_drafts(state)
    if drafts:
        folder = Path(folder or DRAFTS)
        folder.mkdir(parents=True, exist_ok=True)
        for _, e in drafts:
            (folder / f"{e['id']}.json").write_text(json.dumps(e['draft'], indent=2, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')
    return len(drafts)

def run(client=None, get=fetch, ask=pr_state):
    """Settle drafts the owner dealt with, draft up to MAX_PER_RUN new announcements (needs ANTHROPIC_API_KEY) and
    write every open draft to data/drafts/. A new draft is "pending" until --pr-result sees its pull request."""
    catalog = json.loads(CATALOG.read_text(encoding='utf-8'))
    state = _load(STATE, {})
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    # The old code marked these "drafted" before any pull request existed, and the pull request was never opened: the
    # drafts never reached the owner, so the announcements are drafted again.
    for url in [u for u, e in state.items() if e.get('result') == DRAFTED and 'pr' not in e]:
        del state[url]
    settle(state, catalog, ask)
    created, skipped = [], None
    if not os.environ.get('ANTHROPIC_API_KEY'):
        skipped = 'ANTHROPIC_API_KEY not set'
        print('ANTHROPIC_API_KEY not set; no new AI drafts.')
    else:
        if client is None:
            import anthropic
            client = anthropic.Anthropic()
        attempted = 0
        for item in catalog.get('announcements', []):
            url = item['url']
            if url in state or not official(url) or attempted >= MAX_PER_RUN:
                continue
            attempted += 1
            try:
                page = get(url)
            except Exception as exc:
                print(f'{url}: fetch failed ({type(exc).__name__}); will retry')
                continue
            draft, error = extract(client, url, item['title'], page.text)
            if error and error.startswith('retry later'):
                print(f'{url}: {error}')
                continue
            reason = error or check_draft(draft, page.text, catalog)
            rec = None if reason else record(draft, url, now)
            if rec and rec['id'] in {e['id'] for _, e in open_drafts(state)}:
                reason = 'already drafted'
            if reason:
                state[url] = {'at': now, 'result': reason}
                print(f'{url}: skipped ({reason})')
                continue
            state[url] = {'at': now, 'result': PENDING, 'id': rec['id'], 'model': rec['model'], 'draft': rec}
            created.append(rec['model'])
            print(f"{url}: drafted {rec['model']} (waits for its pull request)")
    written = write_drafts(state)
    _save_state(state)
    report = {'at': now, 'created': created, **_open_report(state), 'usage': usage_report()}
    if skipped:
        report['skipped'] = skipped
    _save_report(report)
    print(f'{written} open draft(s) written to data/drafts/.')
    return 0

def record_pr(outcome, number, now=None):
    """After the workflow's pull-request step: with a pull request number from a successful step, the pending drafts
    are in that pull request and count as done; otherwise they stay pending (the next run tries again) and the
    failure goes into data/draft-report.json for the review issue."""
    state, report = _load(STATE, {}), _load(REPORT, {})
    waiting = [e for _, e in open_drafts(state) if e['result'] == PENDING]
    if not waiting:
        print('No drafts waiting for a pull request.')
        return 0
    now = now or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    number = str(number or '').strip()
    if outcome == 'success' and number.isdigit():
        for e in waiting:
            e.update(result=DRAFTED, pr=int(number), pr_at=now)
        report.pop('pr_error', None)
        report.pop('pr_error_at', None)
        print(f'Pull request #{number} holds {len(waiting)} new draft(s).')
    else:
        what = 'failed' if outcome == 'failure' else f'gave no pull request ({outcome or "did not run"})'
        report['pr_error'] = (f'The pull request step {what}, so {len(waiting)} AI draft(s) are not in a pull request. They are '
                              f'kept and the next run tries again. If GitHub Actions may not open pull requests, enable {PR_SETTING}.')
        report['pr_error_at'] = now
        print(report['pr_error'], file=sys.stderr)
    report.update(_open_report(state))
    _save_state(state)
    _save_report(report)
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
    parser.add_argument('--pr-result', action='store_true',
                        help="record the workflow's pull-request step (env PR_OUTCOME, PR_NUMBER): drafts count as done only once in a pull request")
    args = parser.parse_args()
    if args.promote:
        sys.exit(promote(args.promote))
    if args.pr_result:
        sys.exit(record_pr(os.environ.get('PR_OUTCOME', ''), os.environ.get('PR_NUMBER', '')))
    try:
        sys.exit(run())
    finally:
        record_cost()
