"""Browser test for "Show more" on the landing's headline cards (the AI news and UAE AI pillars, scripts/build.py MORE,
web/app.js watchHeads). Not collected by `unittest discover` (no test_ prefix).

    python scripts/build.py
    python tests/e2e_home_expand.py [http://127.0.0.1:8791/] [--shots DIR]

Without a URL it serves dist/ itself (python -m http.server on a free port) and stops it at the end.
Needs Playwright: pip install playwright && python -m playwright install chromium

data/news.json changes twice a day, so nothing here depends on which headlines are cut: each card is measured. On / and
/ar/ at 375 and 1280 px:
- Every visible card shows "Show more" (in the page language) exactly when its headline or summary is cut, and no card
  is cut without it.
- "Show more" opens the card: the whole headline and summary show, the button says "Show less" with aria-expanded true;
  pressing it again cuts the card again. Enter on the focused button does the same.
- A tap on a cut headline or summary opens the card; on an open card a tap, a double click or a triple click (selecting
  its text) keeps it open, and only "Show less" closes it; a tap on the source link or on text being selected changes
  nothing; one card's button opens only that card.
- On a touch screen the button is at least 40px high.
- A card measured while the overview was hidden (a page opened at #news) gets its button once the overview shows; a
  wider or narrower window measures again.
- Without JavaScript nothing is cut and no button shows.
- No horizontal page scroll, no console errors.
With --shots DIR it saves home-expand-{en|ar}-{375|1280}-{closed|open}.png of the AI news pillar for the owner.
"""
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / 'dist'
ARGS = sys.argv[1:]
SHOTS = Path(ARGS[ARGS.index('--shots') + 1]) if '--shots' in ARGS else None
URL = next((a for a in ARGS if a.startswith('http')), None)
WORDS = {'en': ('Show more', 'Show less'), 'ar': ('عرض المزيد', 'عرض أقل')}
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

# Each visible card of the two pillars: open, button shown, its label as shown, aria-expanded, and whether its headline or
# summary is cut right now.
CARDS = r'''() => [...document.querySelectorAll('.heads')].filter(o => o.offsetParent).flatMap(o => [...o.querySelectorAll('li')].map(li => {
  const b = li.querySelector('.n-more');
  return {open: li.classList.contains('open'), btn: !!b && !b.hidden && !!b.offsetParent, label: b && b.offsetParent ? b.innerText.trim() : '',
          exp: b ? b.getAttribute('aria-expanded') : null,
          cut: [...li.querySelectorAll('.n-title, .n-sum')].some(e => e.scrollHeight > e.clientHeight + 1)};
}))'''
VISIBLE = '.heads:visible li'

def settle(page):
    page.wait_for_timeout(250)  # a ResizeObserver callback runs before the next frame

def consistent(page, where):
    cards = page.evaluate(CARDS)
    check(len(cards) > 0, f'{where}: headline cards on the overview')
    for n, c in enumerate(cards):
        if not c['open']:
            check(c['btn'] == c['cut'], f'{where}: card {n} cut={c["cut"]} but button shown={c["btn"]}')
    return cards

def page_checks(browser, base, lang, width):
    where = f'{lang} {width}px'
    more, less = WORDS[lang]
    ctx = browser.new_context(viewport={'width': width, 'height': 900}, device_scale_factor=2 if width < 500 else 1)
    page = ctx.new_page()
    errors = []
    page.on('console', lambda m: errors.append(m.text) if m.type == 'error' else None)
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.goto(base + ('ar/' if lang == 'ar' else ''))
    settle(page)
    cards = consistent(page, where)
    for n, c in enumerate(cards):
        if c['btn']:
            check(c['label'] == more and c['exp'] == 'false', f'{where}: card {n} label {c["label"]!r} aria-expanded {c["exp"]}')
    shown = [n for n, c in enumerate(cards) if c['btn']]
    if not shown:
        print(f'note: {where}: no card is cut at this width; the open/close checks are skipped')
    pillar = page.locator('.p-news')
    if SHOTS and shown:
        pillar.screenshot(path=str(SHOTS / f'home-expand-{lang}-{width}-closed.png'))
    if shown:
        n = shown[0]
        li = page.locator(VISIBLE).nth(n)
        btn = li.locator('.n-more')
        # The button opens this card only.
        btn.click()
        settle(page)
        after = page.evaluate(CARDS)
        check(after[n]['open'] and after[n]['exp'] == 'true' and after[n]['label'] == less, f'{where}: Show more opens card {n}: {after[n]}')
        check(not after[n]['cut'], f'{where}: an open card shows its whole headline and summary')
        check(sum(c['open'] for c in after) == 1, f'{where}: only the pressed card opens')
        if SHOTS:
            pillar.screenshot(path=str(SHOTS / f'home-expand-{lang}-{width}-open.png'))
        btn.click()
        settle(page)
        after = page.evaluate(CARDS)
        check(not after[n]['open'] and after[n]['exp'] == 'false' and after[n]['label'] == more and after[n]['cut'], f'{where}: Show less closes card {n}: {after[n]}')
        # The keyboard: Enter on the focused button.
        btn.focus()
        page.keyboard.press('Enter')
        settle(page)
        check(page.evaluate(CARDS)[n]['open'], f'{where}: Enter opens card {n}')
        page.keyboard.press('Enter')
        settle(page)
        check(not page.evaluate(CARDS)[n]['open'], f'{where}: Enter closes card {n}')
        # A tap on the headline or the summary opens the card; on an open card it changes nothing (only "Show less"
        # closes it), so a double or triple click selecting its text keeps it open.
        li.locator('.n-title').click()
        settle(page)
        check(page.evaluate(CARDS)[n]['open'], f'{where}: a tap on the headline opens card {n}')
        target = li.locator('.n-sum') if li.locator('.n-sum').count() else li.locator('.n-title')
        target.click()
        settle(page)
        check(page.evaluate(CARDS)[n]['open'], f'{where}: a second tap leaves card {n} open')
        box = li.locator('.n-title').bounding_box()  # on the first line: the middle of a two-line headline is between lines
        li.locator('.n-title').dblclick(position={'x': box['width'] / 2, 'y': 9})
        settle(page)
        check(page.evaluate(CARDS)[n]['open'] and page.evaluate('String(getSelection())').strip(), f'{where}: a double click selects a word and keeps card {n} open')
        target.click(click_count=3)
        settle(page)
        check(page.evaluate(CARDS)[n]['open'] and page.evaluate('String(getSelection())').strip(), f'{where}: a triple click selects the text and keeps card {n} open')
        check(sum(c['open'] for c in page.evaluate(CARDS)) == 1, f'{where}: selecting text opened no other card')
        page.evaluate('getSelection().removeAllRanges()')
        btn.click()
        settle(page)
        check(not page.evaluate(CARDS)[n]['open'], f'{where}: Show less closes card {n}')
        # A click that ends a text selection, and a click on the source link, change nothing.
        selected = li.evaluate('''li => { const t = li.querySelector('.n-title'), r = document.createRange(); r.selectNodeContents(t);
            const s = getSelection(); s.removeAllRanges(); s.addRange(r); t.click(); const open = li.classList.contains('open'); s.removeAllRanges(); return open; }''')
        check(not selected, f'{where}: a click with text selected leaves card {n} closed')
        linked = li.evaluate('''li => { const a = li.querySelector('a.n-src'), stop = e => e.preventDefault();
            document.addEventListener('click', stop, true); a.click(); document.removeEventListener('click', stop, true); return li.classList.contains('open'); }''')
        check(not linked, f'{where}: a click on the source link leaves card {n} closed')
        # A card that fits at the current width has no button and a tap on it does nothing.
        fits = [m for m, c in enumerate(page.evaluate(CARDS)) if not c['cut'] and not c['open']]
        if fits:
            m = fits[0]
            page.locator(VISIBLE).nth(m).locator('.n-title').click()
            settle(page)
            check(not page.evaluate(CARDS)[m]['open'], f'{where}: a tap on a card that fits does nothing')
    # Another width measures again.
    page.set_viewport_size({'width': 1280 if width < 500 else 375, 'height': 900})
    settle(page)
    consistent(page, f'{where} -> resized')
    page.set_viewport_size({'width': width, 'height': 900})
    settle(page)
    consistent(page, f'{where} -> back')
    check(page.evaluate('document.documentElement.scrollWidth - innerWidth') <= 0, f'{where}: no horizontal scroll')
    check(not errors, f'{where}: console errors {errors}')
    ctx.close()

def hidden_first_checks(browser, base, lang):
    # Opened at AI news, the overview (and its cards) is hidden; going to the overview measures them then.
    where = f'{lang} hidden first'
    ctx = browser.new_context(viewport={'width': 375, 'height': 900})
    page = ctx.new_page()
    page.goto(base + ('ar/' if lang == 'ar' else '') + '#news')
    settle(page)
    check(page.evaluate(CARDS) == [], f'{where}: the overview is hidden at #news')
    page.evaluate("location.hash = '#home'")
    settle(page)
    cards = consistent(page, where)
    check(any(c['btn'] for c in cards) == any(c['cut'] for c in cards), f'{where}: buttons once shown')
    ctx.close()

def touch_checks(browser, base, lang):
    where = f'{lang} touch'
    ctx = browser.new_context(viewport={'width': 375, 'height': 812}, has_touch=True, is_mobile=True, device_scale_factor=2)
    page = ctx.new_page()
    page.goto(base + ('ar/' if lang == 'ar' else ''))
    settle(page)
    check(page.evaluate("matchMedia('(pointer: coarse)').matches"), f'{where}: a coarse pointer')
    heights = page.locator('.heads li .n-more').evaluate_all('bs => bs.filter(b => b.offsetParent).map(b => b.getBoundingClientRect().height)')
    check(all(h >= 40 for h in heights), f'{where}: buttons at least 40px high {heights}')
    shown = [n for n, c in enumerate(page.evaluate(CARDS)) if c['btn']]
    if shown:
        page.locator(VISIBLE).nth(shown[0]).locator('.n-more').tap()
        settle(page)
        check(page.evaluate(CARDS)[shown[0]]['open'], f'{where}: a tap on Show more opens the card')
    ctx.close()

def no_js_checks(browser, base, lang):
    where = f'{lang} without JavaScript'
    ctx = browser.new_context(viewport={'width': 375, 'height': 900}, java_script_enabled=False)
    page = ctx.new_page()
    page.goto(base + ('ar/' if lang == 'ar' else ''))
    cards = page.locator('.heads li').evaluate_all(
        '''lis => lis.filter(li => li.offsetParent).map(li => ({btn: !!li.querySelector('.n-more') && !!li.querySelector('.n-more').offsetParent,
            cut: [...li.querySelectorAll('.n-title, .n-sum')].some(e => e.scrollHeight > e.clientHeight + 1)}))''')
    check(len(cards) > 0, f'{where}: headline cards')
    check(not any(c['btn'] for c in cards), f'{where}: no button')
    check(not any(c['cut'] for c in cards), f'{where}: nothing cut')
    ctx.close()

def main():
    proc, base = (None, URL.rstrip('/') + '/') if URL else serve()
    if SHOTS:
        SHOTS.mkdir(parents=True, exist_ok=True)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            for lang in ('en', 'ar'):
                for width in (375, 1280):
                    page_checks(browser, base, lang, width)
                hidden_first_checks(browser, base, lang)
                touch_checks(browser, base, lang)
                no_js_checks(browser, base, lang)
            browser.close()
    finally:
        if proc:
            proc.kill()
    print(f'{checks - len(failures)}/{checks} checks passed')
    if failures:
        sys.exit(1)
    print('OK')

if __name__ == '__main__':
    main()
