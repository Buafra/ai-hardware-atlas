"""Keep the owner informed in one GitHub issue (label `source-review`) without an email every run.

Runs in GitHub Actions with GH_TOKEN set, after the data is saved. Every run edits ONE status comment in the open
issue (found by a hidden marker, written by github-actions[bot]; editing a comment sends no email): source health, the
month's estimated AI cost, the AI news steps, how late scheduled runs start, AI drafts, ageing prices, changed pages and
failing sources. A new comment (an email) is posted only when the owner must act, once per event: a verified
specification change, a newly failing source (FAILING_AFTER failed checks in a row), AI drafts waiting (a new draft, or
the pull request could not be opened), a price reaching STALE_PRICE_DAYS days. What was already announced is kept as a
hidden list at the end of the status comment. With no open issue, one is opened only when the owner must act.
The issue is public: news counts only, never a news title, link or reason.
"""
import json
import re
import statistics
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ai_cost  # noqa: E402
import run_timing  # noqa: E402
from refresh import FAILING_AFTER  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
LABEL = 'source-review'
STALE_PRICE_DAYS = 30  # a price is flagged on the day it reaches this age
MARKER = '<!-- cipher-lacuna:review-status -->'
BOT = 'github-actions[bot]'
ALERTED = re.compile(r'<!-- alerted: (\[.*?\]) -->', re.S)
LIST_MAX = 120     # lines in one folded list of the status comment
MAX_BODY = 60000   # GitHub accepts 65,536 characters per comment

def gh(*args, data=None):
    """Run gh and return its output; `data` goes to its stdin as JSON (gh api --input -)."""
    return subprocess.run(['gh', *args], check=True, capture_output=True, text=True,
                          input=None if data is None else json.dumps(data)).stdout

def _load(path, default):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return default

def stale_prices(catalog, today):
    """Products whose approximate price was checked STALE_PRICE_DAYS days or more before `today`, oldest first."""
    out = []
    for p in catalog['products']:
        checked = (p.get('price') or {}).get('checked')
        if checked and (today - date.fromisoformat(checked)).days >= STALE_PRICE_DAYS:
            out.append({'id': p['id'], 'model': p['model'], 'checked': checked, 'days': (today - date.fromisoformat(checked)).days})
    return sorted(out, key=lambda s: (s['checked'], s['model']))

def alerts(report, draft_report, stale):
    """(key, line) for everything the owner must act on now. A key is announced once (a new comment); it leaves the
    list when the matter is settled, so it is announced again if it comes back."""
    out = [(f"change:{report['at']}:{c}", f'Verified specification change (already applied): {c}') for c in report.get('changes', [])]
    errors = report.get('errors') or {}
    out += [(f"fail:{url}:{report['at']}", f'Source failing in {FAILING_AFTER} checks in a row: {url} ({errors.get(url, "error")})')
            for url in report.get('new_errors', [])]
    prs = ', '.join(f'#{n}' for n in draft_report.get('pull_requests', []))
    for model in draft_report.get('waiting', []):
        out.append((f'draft:{model}', f'AI draft waiting for its pull request: {model}'))
    for model in draft_report.get('in_pull_request', []):
        out.append((f'draft:{model}', f'AI draft to check in pull request {prs or "ai-drafts"}: {model}'))
    if draft_report.get('pr_error'):
        out.append(('drafts-pr-failed', draft_report['pr_error']))
    out += [(f"price:{s['id']}:{s['checked']}", f"Approximate price {s['days']} days old: {s['model']} (checked {s['checked']}); "
             'check it and update `price` in data/catalog.json') for s in stale]
    return out

def read_alerted(body):
    """The keys already announced, from the hidden list at the end of a status comment."""
    m = ALERTED.search(body or '')
    try:
        keys = json.loads(m.group(1)) if m else []
    except ValueError:
        return set()
    return {k for k in keys if isinstance(k, str)} if isinstance(keys, list) else set()

def find_status(comments):
    """The status comment: the newest written by github-actions[bot] that starts with the marker (a comment by anyone
    else is never trusted, whatever it says)."""
    mine = [c for c in comments if c.get('user') == BOT and (c.get('body') or '').startswith(MARKER)]
    return mine[-1] if mine else None

def list_comments(number, run=gh):
    out = run('api', '--paginate', f'repos/{{owner}}/{{repo}}/issues/{number}/comments?per_page=100',
              '--jq', '.[] | {id: .id, user: .user.login, body: .body}')
    return [json.loads(line) for line in out.splitlines() if line.strip()]

def drafts_status(draft_report):
    """The AI drafts that are not in a pull request because the workflow's pull-request step failed (from
    data/draft-report.json, written by draft.py --pr-result), or ''."""
    if not (draft_report or {}).get('pr_error'):
        return ''
    waiting = ''.join(f'\n- {m}' for m in draft_report.get('waiting', []))
    return f"**AI drafts waiting for a pull request:** {draft_report['pr_error']}{waiting}"

def ai_status(path=ROOT / 'data/news.json'):
    """One line on the optional AI news steps when they did not run cleanly (from news.json "ai"), else ''."""
    try:
        ai = json.loads(Path(path).read_text(encoding='utf-8')).get('ai') or {}
    except (OSError, ValueError):
        return ''
    if ai and not ai.get('key_set'):
        return ('**AI news steps:** ANTHROPIC_API_KEY is not set, so no Arabic headline translations, AI summaries or content-policy '
                'checks were done; news items that mention the UAE or the GCC stay hidden until they pass the check.')
    if ai.get('problems'):
        problems = ', '.join(f'{k} x{v}' for k, v in ai['problems'].items())
        return f"**AI news steps:** {ai.get('translated', 0)} translated, {ai.get('summarised', 0)} summarised; problems: {problems}."
    return ''

def policy_status(path=ROOT / 'data/news.json'):
    """One line of counts from the content-policy step (news.json "ai"), or '' when it recorded none. This issue is
    public: counts only, never a title, a link or a reason (the owner gets those privately, if Telegram is set up)."""
    try:
        ai = json.loads(Path(path).read_text(encoding='utf-8')).get('ai') or {}
    except (OSError, ValueError):
        return ''
    if 'policy_version' not in ai:
        return ''
    n = lambda k: int(ai.get(k) or 0)
    return (f"**Content policy (UAE/GCC), last news run:** {n('policy_checked')} checked, {n('policy_blocked')} removed, "
            f"{n('m1_dropped')} dropped from non-regional sources, {n('policy_pending')} of {n('regional')} UAE/GCC items hidden until verified.")

def timing_status(path=None):
    """How late scheduled runs started (data/run-timing.json), or ''."""
    log = [e for e in run_timing.load(path or run_timing.LOG) if isinstance(e, dict) and isinstance(e.get('delay_min'), (int, float))][-20:]
    if not log:
        return ''
    median = statistics.median(e['delay_min'] for e in log)
    return (f"**Scheduled runs:** the last one started {log[-1]['delay_min']:g} min after its slot; median {median:g} min "
            f"over the last {len(log)}.")

def _folded(title, lines):
    if not lines:
        return ''
    shown = lines[:LIST_MAX] + ([f'- … and {len(lines) - LIST_MAX} more'] if len(lines) > LIST_MAX else [])
    return f'<details><summary>{title} ({len(lines)})</summary>\n\n' + '\n'.join(shown) + '\n\n</details>'

def status_text(report, draft_report, stale, keys, now, news_path=None, cost_path=None, timing_path=None):
    """The status comment: the marker first, the announced keys (hidden) last."""
    health = report['health']
    lines = [MARKER, f"**Status, updated {now:%Y-%m-%d %H:%M} UTC.** Every run edits this comment (no email); a new comment "
             'appears only when something needs you.', '',
             f"- **Official sources:** {health['successful_sources']}/{health['attempted_sources']} reached at {report['at']}; "
             f"{len(report.get('errors') or {})} failing (below)."]
    for line in (ai_cost.month_line(now, cost_path), ai_status(news_path or ROOT / 'data/news.json'),
                 policy_status(news_path or ROOT / 'data/news.json'), timing_status(timing_path)):
        if line:
            lines.append('- ' + line)
    open_drafts = len(draft_report.get('waiting', [])) + len(draft_report.get('in_pull_request', []))
    if draft_report.get('pr_error'):
        lines.append('- ' + drafts_status(draft_report).replace('\n- ', '\n  - '))
    elif open_drafts:
        prs = ', '.join(f'#{n}' for n in draft_report.get('pull_requests', [])) or 'ai-drafts'
        lines.append(f"- **AI drafts:** {open_drafts} to check in pull request {prs}: " + ', '.join(draft_report.get('in_pull_request', []) + draft_report.get('waiting', [])))
    else:
        lines.append('- **AI drafts:** none open.')
    if stale:
        lines.append(f'- **Approximate prices {STALE_PRICE_DAYS} days old or more:** ' + ', '.join(f"{s['model']} ({s['checked']})" for s in stale))
    if report.get('changes'):
        lines.append('- **Verified specification changes this run (already applied):** ' + '; '.join(report['changes']))
    folded = [_folded('Official pages that changed since the last check: inspect the timeline and unparsed specifications',
                      [f"- {r.get('product_id', 'page')}: {r['reason']} - {r['url']}" for r in report.get('review', [])]),
              _folded('Failing sources (kept as they were)', [f'- {u}: {e}' for u, e in (report.get('errors') or {}).items()])]
    text = '\n'.join(lines) + ''.join('\n\n' + f for f in folded if f)
    # The announced keys; '>' is escaped so no key can end the HTML comment early.
    tail = '\n\n<!-- alerted: ' + json.dumps(sorted(set(keys)), ensure_ascii=False).replace('>', '\\u003e') + ' -->'
    if len(text) + len(tail) > MAX_BODY:
        text = text[:MAX_BODY - len(tail) - 40] + '\n\n… (cut to fit one comment)'
    return text + tail

def alert_text(new):
    return ('**Needs you:**\n' + '\n'.join(f'- {line}' for _, line in new) +
            '\n\nEverything else is in the status comment, which every run edits.')

def main(run=gh, now=None):
    report = json.loads((ROOT / 'data/refresh-report.json').read_text(encoding='utf-8'))
    draft_report = _load(ROOT / 'data/draft-report.json', {})
    catalog = json.loads((ROOT / 'data/catalog.json').read_text(encoding='utf-8'))
    now = now or datetime.now(timezone.utc)
    stale = stale_prices(catalog, date.fromisoformat(report['at'][:10]))
    current = alerts(report, draft_report, stale)
    issues = json.loads(run('issue', 'list', '--label', LABEL, '--state', 'open', '--json', 'number', '--limit', '1'))
    if issues:
        number = issues[0]['number']
        existing = find_status(list_comments(number, run))
        announced = read_alerted(existing['body']) if existing else set()
        new = [(k, line) for k, line in current if k not in announced]
    elif current:
        run('label', 'create', LABEL, '--color', '6537d7', '--description', 'Official source changes to review', '--force')
        number = json.loads(run('api', '-X', 'POST', 'repos/{owner}/{repo}/issues', '--input', '-',
                                data={'title': 'Hardware sources need review', 'body': alert_text(current), 'labels': [LABEL]}))['number']
        existing, new = None, []  # the new issue itself carries the alert
        print(f'Opened issue #{number}')
    else:
        print('Nothing needs the owner and no review issue is open.')
        return 0
    text = status_text(report, draft_report, stale, [k for k, _ in current], now, ROOT / 'data/news.json',
                       ROOT / 'data/ai-cost.json', ROOT / 'data/run-timing.json')
    if existing:
        run('api', '-X', 'PATCH', f"repos/{{owner}}/{{repo}}/issues/comments/{existing['id']}", '--input', '-', data={'body': text})
        print(f'Status comment updated on issue #{number}')
    else:
        run('api', '-X', 'POST', f'repos/{{owner}}/{{repo}}/issues/{number}/comments', '--input', '-', data={'body': text})
        print(f'Status comment added to issue #{number}')
    if new:
        run('api', '-X', 'POST', f'repos/{{owner}}/{{repo}}/issues/{number}/comments', '--input', '-', data={'body': alert_text(new)})
        print(f'{len(new)} new item(s) need the owner: commented on issue #{number}')
    else:
        print('Nothing new needs the owner: no new comment.')
    return 0

if __name__ == '__main__':
    sys.exit(main())
