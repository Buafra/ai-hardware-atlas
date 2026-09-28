"""Browser test for the Android app download (About section card #android, footer links). Not collected by
`unittest discover` (no test_ prefix).

    python scripts/android_app.py      # fetch and check the newest release into .cache/android
    python scripts/build.py            # copies it to dist/download/
    python tests/e2e_android.py [--shots DIR]

Serves dist/ itself (python -m http.server on a free port) and stops it at the end.
Needs Playwright: pip install playwright && python -m playwright install chromium

In English and Arabic at 375, 768 and 1280 px:
- #android, #contact/android and the footer's "Android app" link open the contact view with the card in view.
- The card shows the version, size and SHA-256 of dist/download/latest.json, in the page's language only.
- The button is a same-origin link to download/Cipher-Lacuna.apk, at least 44 px tall, and inside the card.
- No horizontal page scroll, no console errors, no requests to other hosts.
- The file served at that address is the checked APK (size and SHA-256).
- learn.html's footer link lands on the same card, in Arabic too.
"""
import hashlib
import json
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / 'dist'
SHOTS = Path(sys.argv[sys.argv.index('--shots') + 1]) if '--shots' in sys.argv else None
LATEST = json.loads((DIST / 'download' / 'latest.json').read_text(encoding='utf-8'))
failures, checks = [], 0

def check(ok, msg):
    global checks
    checks += 1
    if not ok:
        failures.append(msg)
        print('FAIL', msg)

def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]

def serve():
    port = free_port()
    proc = subprocess.Popen([sys.executable, '-m', 'http.server', str(port), '--bind', '127.0.0.1', '--directory', str(DIST)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f'http://127.0.0.1:{port}/'
    for _ in range(50):
        try:
            urllib.request.urlopen(base, timeout=1).close()
            return proc, base
        except OSError:
            time.sleep(.1)
    proc.kill()
    raise SystemExit('the local server did not start')

def card_state(page):
    return page.evaluate('''() => {
      const c = document.getElementById('android');
      if (!c) return null;
      const r = c.getBoundingClientRect(), b = c.querySelector('.btn-app'), br = b.getBoundingClientRect();
      const shown = el => [...el.querySelectorAll('[data-lang]')].filter(x => getComputedStyle(x).display !== 'none').map(x => x.dataset.lang);
      return {route: document.documentElement.dataset.route, hash: location.hash, top: r.top, bottom: r.bottom, vh: innerHeight,
              visible: r.height > 0 && getComputedStyle(c).visibility !== 'hidden', text: c.innerText,
              href: b.getAttribute('href'), abs: b.href, bh: br.height, bw: br.width, inCard: br.left >= r.left - 1 && br.right <= r.right + 1,
              langs: [...new Set(shown(c))], scrollX: document.documentElement.scrollWidth - document.documentElement.clientWidth,
              lang: document.documentElement.lang};
    }''')

def main():
    proc, base = serve()
    origin = '{0.scheme}://{0.netloc}'.format(urlparse(base))
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            for lang in ('en', 'ar'):
                for width in (375, 768, 1280):
                    ctx = browser.new_context(viewport={'width': width, 'height': 860})
                    page = ctx.new_page()
                    errors, foreign = [], []
                    page.on('console', lambda m: errors.append(m.text) if m.type == 'error' else None)
                    page.on('pageerror', lambda e: errors.append(str(e)))
                    page.on('request', lambda r: foreign.append(r.url) if not r.url.startswith(origin) and not r.url.startswith('data:') else None)
                    q = '?lang=ar' if lang == 'ar' else ''
                    for entry in ('#android', '#contact/android'):
                        page.goto(base + q + entry)
                        page.wait_for_timeout(700)
                        s = card_state(page)
                        where = f'{lang} {width}px {entry}'
                        check(s is not None, f'{where}: no #android card')
                        if not s:
                            continue
                        check(s['route'] == 'contact', f'{where}: route {s["route"]}, expected contact')
                        check(s['visible'] and s['top'] < s['vh'] and s['bottom'] > 0, f'{where}: card not in view ({s["top"]:.0f}..{s["bottom"]:.0f} of {s["vh"]})')
                        check(s['lang'] == lang and s['langs'] == [lang], f'{where}: languages shown {s["langs"]} on a {s["lang"]} page')
                        check(s['scrollX'] <= 0, f'{where}: horizontal scroll {s["scrollX"]}px')
                        check(s['href'] == 'download/Cipher-Lacuna.apk' and s['abs'].startswith(origin), f'{where}: button link {s["href"]}')
                        check(s['bh'] >= 44 and s['inCard'], f'{where}: button {s["bw"]:.0f}x{s["bh"]:.0f}, inside card {s["inCard"]}')
                        check(LATEST['version'] in s['text'], f'{where}: version {LATEST["version"]} not shown')
                        mb = f'{LATEST["size"] / 1048576:.1f}'
                        check(mb in s['text'], f'{where}: size {mb} not shown')
                        check(('ميجابايت' if lang == 'ar' else 'MB') in s['text'], f'{where}: size unit missing')
                    if SHOTS and entry == '#contact/android':
                        SHOTS.mkdir(parents=True, exist_ok=True)
                        page.locator('#android').screenshot(path=str(SHOTS / f'card-{lang}-{width}.png'))
                    # The SHA-256 behind its summary.
                    page.locator('#android summary').click()
                    code = page.locator('#android code').inner_text().strip()
                    check(code == LATEST['sha256'], f'{lang} {width}px: SHA-256 shown {code[:12]}…')
                    # The footer link, from the top of the overview.
                    page.goto(base + q + '#home')
                    page.wait_for_timeout(500)
                    # app.js turns the no-JavaScript #android into the route #contact/android.
                    link = page.locator('footer .foot-links a[href="#contact/android"]')
                    check(link.count() == 1, f'{lang} {width}px: footer Android link count {link.count()}')
                    if link.count():
                        label = link.inner_text().strip()
                        check(label == ('تطبيق Android' if lang == 'ar' else 'Android app'), f'{lang} {width}px: footer label {label!r}')
                        link.click()
                        page.wait_for_timeout(900)
                        s = card_state(page)
                        check(s and s['route'] == 'contact' and s['top'] < s['vh'] and s['bottom'] > 0, f'{lang} {width}px: footer link did not land on the card ({s and s["top"]})')
                        check(s and s['hash'] == '#contact', f'{lang} {width}px: hash after landing {s and s["hash"]}, expected #contact')
                        if SHOTS and width in (375, 1280):
                            page.screenshot(path=str(SHOTS / f'landed-{lang}-{width}.png'))
                    # learn.html's footer link.
                    page.goto(base + 'learn.html' + q)
                    page.wait_for_timeout(500)
                    ll = page.locator('footer a[href$="#contact/android"]')
                    check(ll.count() == 1, f'{lang} {width}px: learn.html footer Android link count {ll.count()}')
                    if ll.count():
                        ll.click()
                        page.wait_for_load_state('load')
                        page.wait_for_timeout(900)
                        s = card_state(page)
                        check(s and s['route'] == 'contact' and s['top'] < s['vh'] and s['bottom'] > 0, f'{lang} {width}px: learn.html link did not land on the card')
                        check(s and s['lang'] == lang, f'{lang} {width}px: learn.html link opened the overview in {s and s["lang"]}')
                    check(not errors, f'{lang} {width}px: console errors {errors[:3]}')
                    check(not foreign, f'{lang} {width}px: requests to other hosts {foreign[:3]}')
                    ctx.close()
            # The file itself.
            ctx = browser.new_context()
            r = ctx.request.get(base + 'download/Cipher-Lacuna.apk')
            body = r.body()
            check(r.status == 200, f'APK status {r.status}')
            check(len(body) == LATEST['size'] and hashlib.sha256(body).hexdigest() == LATEST['sha256'], 'served APK differs from latest.json')
            check(body[:4] == b'PK\x03\x04', 'served APK is not a ZIP')
            ctx.close()
            browser.close()
    finally:
        proc.kill()
    print(f'{checks - len(failures)}/{checks} checks passed')
    if failures:
        sys.exit(1)
    print('OK')

if __name__ == '__main__':
    main()
