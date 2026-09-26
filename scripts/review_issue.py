"""Open or update one GitHub issue when a source check needs human review.

Runs in GitHub Actions with GH_TOKEN set. Keeps a single open issue labelled
`source-review` and comments on it instead of opening duplicates.
Fetch errors alone do not open an issue; they are listed when one is opened.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LABEL = 'source-review'

def gh(*args):
    return subprocess.run(['gh', *args], check=True, capture_output=True, text=True).stdout

def body(report, drafts):
    lines = [f"Source check at {report['at']} reached {report['health']['successful_sources']}/{report['health']['attempted_sources']} official sources.", '']
    if report['changes']:
        lines += ['**Verified field changes (already applied)**'] + [f'- {c}' for c in report['changes']] + ['']
    if report['review']:
        lines += ['**Needs review**'] + [f"- {r.get('product_id', 'page')}: {r['reason']} - {r['url']}" for r in report['review']] + ['']
    if drafts:
        lines += ['**New AI-drafted product records (see the draft pull request)**'] + [f'- {d}' for d in drafts] + ['']
    if report['errors']:
        lines += ['<details><summary>Fetch errors</summary>', ''] + [f'- {u}: {e}' for u, e in report['errors'].items()] + ['', '</details>']
    return '\n'.join(lines)

def main():
    report = json.loads((ROOT / 'data/refresh-report.json').read_text(encoding='utf-8'))
    drafts_path = ROOT / 'data/draft-report.json'
    drafts = json.loads(drafts_path.read_text(encoding='utf-8')).get('created', []) if drafts_path.exists() else []
    if not (report['changes'] or report['review'] or drafts):
        print('Nothing needs review.')
        return 0
    text = body(report, drafts)
    gh('label', 'create', LABEL, '--color', '6537d7', '--description', 'Official source changes to review', '--force')
    open_issues = json.loads(gh('issue', 'list', '--label', LABEL, '--state', 'open', '--json', 'number', '--limit', '1'))
    if open_issues:
        number = str(open_issues[0]['number'])
        gh('issue', 'comment', number, '--body', text)
        print(f'Commented on issue #{number}')
    else:
        print(gh('issue', 'create', '--title', 'Hardware sources need review', '--label', LABEL, '--body', text).strip())
    return 0

if __name__ == '__main__':
    sys.exit(main())
