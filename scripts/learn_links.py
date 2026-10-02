"""Check every link in the Learn AI data (data/learn/*.json): reports, stacks and concepts.

    python scripts/learn_links.py            # writes data/learn-links.json and prints a short report

A link is "ok" (2xx/3xx), "blocked" (401, 403 or 429: the site refuses automated checks, so check it by hand), or
"broken" (404, 410, other errors, timeouts). No AI is used and nothing is changed; the monthly Learn AI refresh reads
the report and fixes or replaces broken links. Each host is asked at most once at a time, politely.
"""
import concurrent.futures
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
FILES = [ROOT / 'data/learn/reports.json', ROOT / 'data/learn/stacks.json', ROOT / 'data/learn/concepts.json']
OUT = ROOT / 'data/learn-links.json'
UA = 'AI-Hardware-Atlas/1.1 (link check; +https://cipherlacuna.ae/)'
TIMEOUT = 25

def links(paths=FILES):
    """{url: [where it appears]} for every https URL in the files (any key named url, or a string that is a URL)."""
    found = {}
    def walk(o, where):
        if isinstance(o, dict):
            for k, v in o.items():
                walk(v, f'{where}.{k}' if where else k)
        elif isinstance(o, list):
            for n, v in enumerate(o):
                label = v.get('id') if isinstance(v, dict) and v.get('id') else n
                walk(v, f'{where}[{label}]')
        elif isinstance(o, str) and o.startswith('https://') and ' ' not in o:
            found.setdefault(o, []).append(where)
    for p in paths:
        walk(json.loads(Path(p).read_text(encoding='utf-8')), p.stem)
    return found

def check(url):
    """('ok' | 'blocked' | 'broken', detail)."""
    for method in ('HEAD', 'GET'):  # some sites refuse HEAD
        try:
            req = Request(url, method=method, headers={'User-Agent': UA, 'Accept': 'text/html,application/pdf,*/*;q=0.5'})
            with urlopen(req, timeout=TIMEOUT) as r:
                return 'ok', f'{r.status}'
        except HTTPError as e:
            if method == 'HEAD' and e.code in (400, 403, 404, 405, 429, 500, 501, 503):
                continue  # try GET before deciding
            if e.code in (401, 403, 429):
                return 'blocked', f'HTTP {e.code}'
            return 'broken', f'HTTP {e.code}'
        except (URLError, TimeoutError, OSError) as e:
            if method == 'HEAD':
                continue
            return 'broken', f'{type(e).__name__}: {getattr(e, "reason", e)}'[:160]
    return 'broken', 'no answer'

def main():
    found = links()
    by_host = {}
    for url in found:
        by_host.setdefault(urlparse(url).netloc, []).append(url)

    def host_run(urls):  # one host at a time, with a short pause between its links
        out = []
        for u in urls:
            out.append((u, *check(u)))
            time.sleep(1)
        return out

    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        for rows in pool.map(host_run, by_host.values()):
            for url, status, detail in rows:
                results[url] = {'status': status, 'detail': detail, 'where': found[url]}
    counts = {s: sum(1 for r in results.values() if r['status'] == s) for s in ('ok', 'blocked', 'broken')}
    OUT.write_text(json.dumps({'checked_at': datetime.now(timezone.utc).replace(microsecond=0).isoformat(), 'counts': counts,
                               'links': dict(sorted(results.items()))}, indent=1, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')
    print(f"Learn AI links: {len(results)} checked, {counts['ok']} ok, {counts['blocked']} blocked (check by hand), {counts['broken']} broken")
    for url, r in sorted(results.items()):
        if r['status'] != 'ok':
            print(f"  {r['status'].upper():7} {r['detail']:<28} {url}  ({', '.join(r['where'][:3])})")
    return 0

if __name__ == '__main__':
    sys.exit(main())
