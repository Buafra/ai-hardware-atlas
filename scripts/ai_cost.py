"""Monthly ledger of the estimated Claude cost: data/ai-cost.json, {"YYYY-MM": {"usd": 1.23, "runs": 14}}.

news.py and draft.py each add their own run's estimate when they end (tokens at list prices, the Batch API at half
price, as they print in the workflow log). "runs" counts the workflow runs that used Claude: the two scripts of one
run count once (GITHUB_RUN_ID and attempt, kept as "last_run"); "from" is the first day counted. The newest KEEP_MONTHS
months are kept. The review issue's status comment shows the current month; the file is saved with the refreshed
data and is not published.
"""
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / 'data/ai-cost.json'
KEEP_MONTHS = 24

def load(path=None):
    try:
        data = json.loads(Path(path or LEDGER).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}

def _run_id():
    run = os.environ.get('GITHUB_RUN_ID')
    return f"{run}-{os.environ.get('GITHUB_RUN_ATTEMPT', '1')}" if run else None

def add(usd, requests, now=None, run=None, path=None):
    """Add one script's estimate to its month. Nothing is written when it made no Claude request. Returns the month's
    entry (or None)."""
    if not requests:
        return None
    path = Path(path or LEDGER)
    now = now or datetime.now(timezone.utc)
    run = run if run is not None else _run_id()
    ledger = load(path)
    # "from": the first day counted, so a month the ledger started in mid-way is labelled as partial.
    entry = ledger.setdefault(now.strftime('%Y-%m'), {'usd': 0.0, 'runs': 0, 'from': now.date().isoformat()})
    entry['usd'] = round(float(entry.get('usd') or 0) + float(usd or 0), 4)
    if not run or entry.get('last_run') != run:
        entry['runs'] = int(entry.get('runs') or 0) + 1
    if run:
        entry['last_run'] = run
    ledger = {m: ledger[m] for m in sorted(ledger)[-KEEP_MONTHS:]}
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(ledger, indent=2) + '\n', encoding='utf-8', newline='\n')
    temp.replace(path)
    return entry

def month_line(now=None, path=None):
    """'**AI cost (estimate):** $4.12 in October 2026 over 20 runs (September: $9.80, 58 runs).' or '' when nothing
    was spent this month or last."""
    now = now or datetime.now(timezone.utc)
    ledger = load(path)
    this = now.strftime('%Y-%m')
    last = (now.replace(day=1) - timedelta(days=1)).strftime('%Y-%m')
    if this not in ledger and last not in ledger:
        return ''
    cur = ledger.get(this) or {'usd': 0, 'runs': 0}
    since = str(cur.get('from') or '')
    since = f' (counted from {int(since[8:10])} {now:%b})' if since[:7] == this and since[8:10] not in ('', '01') else ''
    text = f"**AI cost (estimate):** ${cur['usd']:.2f} in {now:%B %Y}{since} over {cur['runs']} run{'s' if cur['runs'] != 1 else ''}"
    if last in ledger:
        prev = ledger[last]
        text += f" ({datetime.strptime(last, '%Y-%m'):%B}: ${prev['usd']:.2f}, {prev['runs']} run{'s' if prev['runs'] != 1 else ''})"
    return text + '.'
