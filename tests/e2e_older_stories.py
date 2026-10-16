"""Browser test for "Search older stories" (the news archive) in AI news and UAE AI. Not collected by `unittest
discover` (no test_ prefix).

    python scripts/build.py
    python tests/e2e_older_stories.py [--shots DIR]

It needs an archive with stories in it, which data/ may not have yet, so it builds its own copy of the site in a temporary
folder (the repository's data/ and dist/ are never written): dist/ is copied, the oldest stories of data/news.json (real,
vetted stories) are archived with the real rule (news_archive.append) and leave the current list, and copies of a few of
them dated a month earlier make a second month file (for "Search earlier months"). The English and Arabic overviews and
the archive's files are written again from that, and the copy is served on a free local port.

In English and Arabic, at 1280 px:
- A search, then "Search older stories": the older stories that match, under the current results.
- The same view again with a new search (the button comes back once the field is cleared and a word is typed): the new
  matches, never "Loading older stories…" for good (a load that ends at once must not stay "running").
- "Search earlier months" loads the next month file and then hides itself (one month file per press).
- UAE AI after AI news has loaded the archive (they share it): its own matches, not stuck either.
- Each older card's share button is named after its headline (aria-labelledby: the button, then the card's title, an
  id that exists once on the page).
- No console errors and no requests to other hosts.
With --shots DIR it saves older-{news|uae}-{en|ar}.png.
"""
import json
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import timedelta
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build, lang_pages, news_archive  # noqa: E402

ARGS = sys.argv[1:]
SHOTS = Path(ARGS[ARGS.index('--shots') + 1]) if '--shots' in ARGS else None
LEAVING = 60  # the oldest stories of data/news.json that "leave" into the archive
failures, checks = [], 0

def check(ok, msg):
    global checks
    checks += 1
    if not ok:
        failures.append(msg)
        print('FAIL', msg)
    return ok

def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]

def site(tmp):
    """The site copy with an archive of two months; returns (folder, the archive's shown stories)."""
    out, arch = tmp / 'site', tmp / 'archive'
    shutil.copytree(ROOT / 'dist', out)
    data, feed, sources, uae, models = build.load_all()
    items = sorted(feed['items'], key=lambda i: i['published'])
    leaving, staying = items[:LEAVING], items[LEAVING:]
    news_archive.append(leaving, sources, arch)
    # A month earlier: copies of ten archived stories (other ids and links), so the archive has a second month file.
    first = news_archive.load(arch)
    earlier = []
    for n, i in enumerate(first[:10]):
        d = news_archive.uae_time(i['published']) - timedelta(days=31)
        earlier.append({**{k: i[k] for k in news_archive.FIELDS}, 'id': f'prev{n:04d}', 'url': i['url'] + f'?prev={n}', 'published': d.isoformat()})
    month = news_archive.month_of(earlier[0])
    (arch / f'{month}.json').write_text(json.dumps({'month': month, 'policy_version': news_archive.policy.POLICY_VERSION, 'items': earlier},
                                                   ensure_ascii=False), encoding='utf-8')
    feed2 = {**feed, 'items': staying}
    archived = news_archive.load(arch)
    company = build.news_images.run(out, build.news_items(feed2, sources), {s['id']: s for s in sources}, network=False)
    for lang, path in (('en', out / 'index.html'), ('ar', out / lang_pages.AR_DIR / 'index.html')):
        text, _ = build.render_page(data, feed2, sources, uae, models, company=company, archive=archived, lang=lang)
        path.write_text(text, encoding='utf-8', newline='\n')
    older = build.older_stories(build.news_items(feed2, sources), archived, sources)
    news_archive.publish(out, older, sources)
    return out, older

def serve(folder):
    port = free_port()
    proc = subprocess.Popen([sys.executable, '-m', 'http.server', str(port), '--bind', '127.0.0.1', '--directory', str(folder)],
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

def word(stories, lang, uae=False, avoid=()):
    """A word of an older story's headline as the page in `lang` shows it (Latin letters for English, Arabic script for
    Arabic), from a story of the newest month; None when there is none."""
    newest = news_archive.month_of(stories[0]) if stories else None
    pat = re.compile(r'[A-Za-z]{5,}' if lang == 'en' else r'[ء-ي]{5,}')
    for s in stories:
        if news_archive.month_of(s) != newest or (uae and not s.get('uae')):
            continue
        if lang == 'en':
            title = s['title'] if s['lang'] == 'en' else None
        else:
            title = s['title'] if s['lang'] == 'ar' else s.get('title_ar')
        for w in pat.findall(title or ''):
            if w.lower() not in avoid:
                return w.lower() if lang == 'en' else w
    return None

def state(page, view):
    return page.evaluate('''(view) => {
      const $ = id => document.getElementById(id), lis = [...$(view + '-older-list').querySelectorAll('li')];
      return {count: $(view + '-older-count').textContent, items: lis.length, btn: !$(view + '-older-btn').hidden,
              back: !$(view + '-older-back').hidden,
              named: lis.map(li => { const b = li.querySelector('.n-share'); if (!b) return true;
                const ids = (b.getAttribute('aria-labelledby') || '').split(' ');
                return ids.length === 2 && ids[0] === b.id && document.querySelectorAll('[id="' + ids[1] + '"]').length === 1
                  && document.getElementById(ids[1]).classList.contains('n-title'); }).every(Boolean)};
    }''', view)

def search(page, view, w):
    page.fill(f'#{view}-q', '')
    page.wait_for_timeout(150)
    page.fill(f'#{view}-q', w)
    page.wait_for_timeout(300)

def settled(page, view):
    """Wait until the older-stories count no longer says it is loading (a load that never ends is a failure, not a hang)."""
    try:
        page.wait_for_function(f"!/…|\\.\\.\\./.test(document.getElementById('{view}-older-count').textContent)", timeout=8000)
    except PlaywrightTimeout:
        pass  # the caller's check reports the count still saying "Loading older stories…"
    page.wait_for_timeout(150)

def press_older(page, view):
    page.click(f'#{view}-older-btn')
    settled(page, view)

LOADING = {'en': 'Loading older stories…', 'ar': 'جارٍ تحميل الأخبار الأقدم…'}

def main():
    with tempfile.TemporaryDirectory() as t:
        folder, older = site(Path(t))
        proc, base = serve(folder)
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                for lang in ('en', 'ar'):
                    tag = f'[{lang}]'
                    ctx = browser.new_context(viewport={'width': 1280, 'height': 900})
                    page = ctx.new_page()
                    errors, foreign = [], []
                    page.on('console', lambda m: errors.append(m.text) if m.type == 'error' else None)
                    page.on('pageerror', lambda e: errors.append(str(e)))
                    page.on('request', lambda r: foreign.append(r.url) if not r.url.startswith(base) and not r.url.startswith('data:') else None)
                    home = base + ('ar/' if lang == 'ar' else '')
                    page.goto(home + '#news')
                    page.wait_for_load_state('load')
                    page.wait_for_timeout(400)
                    w1 = word(older, lang)
                    w2 = word(older, lang, avoid={w1})
                    if not check(bool(w1 and w2), f'{tag} two words from older headlines ({w1!r}, {w2!r})'):
                        ctx.close()
                        continue
                    # First press: the matches of the newest month file.
                    search(page, 'news', w1)
                    check(page.locator('#news-older-btn').is_visible(), f'{tag} the button shows while searching')
                    press_older(page, 'news')
                    s = state(page, 'news')
                    check(s['items'] > 0 and not s['btn'], f'{tag} first press lists older stories {s}')
                    check(s['named'], f'{tag} older share buttons named after their headline')
                    check(s['back'], f'{tag} "Search earlier months" offered (two month files, one loaded)')
                    if SHOTS:
                        SHOTS.mkdir(parents=True, exist_ok=True)
                        page.evaluate("document.getElementById('news-older').scrollIntoView({block:'start'}); window.scrollBy(0, -80)")
                        page.wait_for_timeout(200)
                        page.screenshot(path=str(SHOTS / f'older-news-{lang}.png'))
                    # Clear, search again, press again: nothing left to fetch, and it must not stay "loading".
                    search(page, 'news', w2)
                    check(page.locator('#news-older-btn').is_visible(), f'{tag} the button is back for a new search')
                    press_older(page, 'news')
                    s = state(page, 'news')
                    check(s['count'] != LOADING[lang] and s['items'] > 0, f'{tag} second press is not stuck loading {s}')
                    # Earlier months: one more file, then the button hides (no month left).
                    before = page.evaluate("document.getElementById('news-older-list').children.length")
                    page.click('#news-older-back')
                    settled(page, 'news')
                    s = state(page, 'news')
                    check(s['count'] != LOADING[lang] and not s['back'] and s['items'] >= before, f'{tag} earlier months loaded {s}')
                    # A press after every month is loaded: still not stuck.
                    search(page, 'news', w1)
                    press_older(page, 'news')
                    s = state(page, 'news')
                    check(s['count'] != LOADING[lang] and s['items'] > 0, f'{tag} third press after all months {s}')
                    # UAE AI after AI news loaded the shared archive.
                    wu = word(older, lang, uae=True)
                    if wu:
                        page.goto(home + '#uae')
                        page.wait_for_timeout(300)
                        search(page, 'uae', wu)
                        press_older(page, 'uae')
                        s = state(page, 'uae')
                        check(s['count'] != LOADING[lang] and s['items'] > 0 and s['named'], f'{tag} UAE AI after AI news {wu!r} {s}')
                        if SHOTS:
                            page.evaluate("document.getElementById('uae-older').scrollIntoView({block:'start'}); window.scrollBy(0, -80)")
                            page.wait_for_timeout(200)
                            page.screenshot(path=str(SHOTS / f'older-uae-{lang}.png'))
                    else:
                        print(f'note: {tag} no UAE story in the archive copy; UAE AI step skipped')
                    check(not errors, f'{tag} console errors {errors[:3]}')
                    check(not foreign, f'{tag} requests to other hosts {foreign[:3]}')
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
