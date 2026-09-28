"""Browser test for AI models in the hardware search (#hardware, the #search box). Not collected by
`unittest discover` (no test_ prefix).

    python scripts/build.py
    python tests/e2e_model_search.py [http://127.0.0.1:8791/] [--shots DIR]

Without a URL it serves dist/ itself (python -m http.server on a free port) and stops it at the end.
Needs Playwright: pip install playwright && python -m playwright install chromium

The search box covers the hardware; a model name such as "qwen" used to end in "No matches". In English and Arabic at
375 and 1280 px:
- "qwen": the "AI models (53)" card, open with the first 3 models (name and size), "Show all 53 models" showing all 53
  in place and "Show fewer" folding them again; the empty text says no hardware matches; the count is in a live region.
- Picking "Qwen2.5 Coder 32B Instruct" clears the search (the products come back), sets the estimator (#model and a size
  of 32.76), brings #estimator into view with #model focused, and keeps the URL in step (m and p, no q).
- "nvidia": the products stay and the card is only its title line with "Show models" (which opens and closes it).
- "nvidia" with the AMD vendor filter: no hardware, the card open, the empty text asks to reset the filters.
- "H100" and a single letter: no card. Switching the language re-renders the card.
- Buttons at least 44 px tall on phones, a visible keyboard focus, no horizontal page scroll, no console errors and no
  requests to other hosts.
With --shots DIR it saves the owner's mock: qwen-<lang>-<width>.png (card open) and nvidia-<lang>-<width>.png (the
title line above the first products).
"""
import json
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / 'dist'
ARGS = [a for a in sys.argv[1:]]
SHOTS = Path(ARGS[ARGS.index('--shots') + 1]) if '--shots' in ARGS else None
URL = next((a for a in ARGS if a.startswith('http')), None)
PRODUCTS = len(json.loads((ROOT / 'data' / 'catalog.json').read_text(encoding='utf-8'))['products'])
TEXT = {
    'en': {'title': 'AI models ({n})', 'lead': 'The atlas lists hardware. Pick a model to see which hardware can run it.',
           'all': 'Show all {n} models', 'fewer': 'Show fewer', 'show': 'Show models', 'hide': 'Hide models',
           'none': 'No hardware matches this search.', 'filters': 'No hardware matches this search with these filters. Reset the filters to see more.',
           'plain': 'No matches. Try another search or reset the filters.'},
    'ar': {'title': 'نماذج الذكاء الاصطناعي ({n})', 'lead': 'الأطلس يعرض العتاد. اختر نموذجاً لترى العتاد القادر على تشغيله.',
           'all': 'عرض كل النماذج ({n})', 'fewer': 'عرض أقل', 'show': 'عرض النماذج', 'hide': 'إخفاء النماذج',
           'none': 'لا يوجد عتاد مطابق لهذا البحث.', 'filters': 'لا يوجد عتاد يطابق هذا البحث مع هذه الفلاتر. أعد ضبط الفلاتر لترى المزيد.',
           'plain': 'لا توجد نتائج. جرّب بحثاً آخر أو أعد ضبط الفلاتر.'},
}
PICK = 'Qwen2.5 Coder 32B Instruct'
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

STATE = '''() => {
  const $ = id => document.getElementById(id), card = $('model-hits'), shown = el => !!el && !el.hidden && el.getClientRects().length > 0;
  const rows = [...card.querySelectorAll('#mh-list .mh-pick')].filter(shown);
  const products = [...document.querySelectorAll('#products .product')].filter(p => !p.hidden);
  const r = card.getBoundingClientRect(), first = products.length ? products[0].getBoundingClientRect() : null;
  const est = $('estimator').getBoundingClientRect();
  return {card: shown(card), title: $('mh-title').textContent, live: $('mh-live').textContent, liveAttr: $('mh-live').getAttribute('aria-live'),
          liveShown: getComputedStyle($('mh-live')).display !== 'none',
          lead: card.querySelector('.mh-lead').textContent, body: shown($('mh-body')),
          toggle: shown($('mh-toggle')) ? $('mh-toggle').textContent : null, toggleExp: $('mh-toggle').getAttribute('aria-expanded'),
          more: shown($('mh-more')) ? $('mh-more').textContent : null, moreExp: $('mh-more').getAttribute('aria-expanded'),
          rows: rows.map(b => ({name: b.querySelector('.mh-name').textContent, size: b.querySelector('.mh-size').textContent, h: b.getBoundingClientRect().height, tag: b.tagName})),
          btnH: [$('mh-toggle'), $('mh-more')].filter(shown).map(b => b.getBoundingClientRect().height),
          empty: shown($('empty')) ? $('empty').textContent : null, products: products.length, productsShown: shown($('products')),
          cardTop: r.top, cardBottom: r.bottom, cardH: r.height, firstTop: first ? first.top : null,
          estTop: est.top, vh: innerHeight, active: document.activeElement && document.activeElement.id,
          model: $('model').value, params: $('params').value, search: $('search').value, note: $('model-note').textContent,
          url: location.search, hash: location.hash, lang: document.documentElement.lang, dir: document.documentElement.dir,
          scrollX: document.documentElement.scrollWidth - document.documentElement.clientWidth};
}'''

def search(page, text):
    page.fill('#search', text)
    page.wait_for_timeout(120)
    return page.evaluate(STATE)

def mock(browser, base, lang, width):
    """The owner's mock, from a fresh page: the header, the filters, the estimator, the count and the card, plus the first
    products for "nvidia". The window is made as tall as that stretch, so the sticky header sits where a visitor sees it."""
    ctx = browser.new_context(viewport={'width': width, 'height': 860})
    page = ctx.new_page()
    page.goto(base + ('?lang=ar' if lang == 'ar' else '') + '#hardware')
    page.wait_for_timeout(500)
    for q, below in (('qwen', 24), ('nvidia', 560 if width < 640 else 470)):
        page.set_viewport_size({'width': width, 'height': 860})
        page.fill('#search', q)
        page.wait_for_timeout(150)
        page.evaluate('document.activeElement.blur()')
        m = page.evaluate('''() => ({stick: document.querySelector('.top').getBoundingClientRect().height,
          top: document.querySelector('.filters').getBoundingClientRect().top + scrollY,
          bottom: document.getElementById('model-hits').getBoundingClientRect().bottom + scrollY})''')
        top = m['top'] - 12
        page.set_viewport_size({'width': width, 'height': int(m['stick'] + m['bottom'] + below - top + .5)})
        page.evaluate(f'window.scrollTo(0, {top - m["stick"]})')
        page.wait_for_timeout(200)
        page.screenshot(path=str(SHOTS / f'{q}-{lang}-{width}.png'))
    ctx.close()

def run(browser, base, origin, lang, width):
    L, where = TEXT[lang], f'{lang} {width}px'
    ctx = browser.new_context(viewport={'width': width, 'height': 860})
    page = ctx.new_page()
    errors, foreign = [], []
    page.on('console', lambda m: errors.append(m.text) if m.type == 'error' else None)
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.on('request', lambda r: foreign.append(r.url) if not r.url.startswith(origin) and not r.url.startswith('data:') else None)
    page.goto(base + ('?lang=ar' if lang == 'ar' else '') + '#hardware')
    page.wait_for_timeout(500)
    s = page.evaluate(STATE)
    check(not s['card'] and s['live'] == '', f'{where}: card shown before any search')
    check(s['lang'] == lang and s['dir'] == ('rtl' if lang == 'ar' else 'ltr'), f'{where}: page lang/dir {s["lang"]}/{s["dir"]}')

    # "qwen": no hardware, so the card is open with the first three models.
    s = search(page, 'qwen')
    title = L['title'].format(n=53)
    check(s['card'] and s['title'] == title, f'{where} qwen: card {s["card"]} title {s["title"]!r}')
    check(s['live'] == title and s['liveAttr'] == 'polite' and s['liveShown'], f'{where} qwen: live region {s["live"]!r} {s["liveAttr"]}')
    check(s['lead'] == L['lead'], f'{where} qwen: lead {s["lead"]!r}')
    check(s['body'] and s['toggle'] is None, f'{where} qwen: open {s["body"]}, toggle {s["toggle"]!r}')
    check(len(s['rows']) == 3 and all(r['tag'] == 'BUTTON' for r in s['rows']), f'{where} qwen: {len(s["rows"])} rows')
    check([r['name'] for r in s['rows']][:2] == ['Qwen2.5 72B Instruct', PICK], f'{where} qwen: rows {[r["name"] for r in s["rows"]]}')
    check(s['rows'] and s['rows'][0]['size'] == '72.71 B', f'{where} qwen: first size {s["rows"] and s["rows"][0]["size"]!r}')
    check(s['more'] == L['all'].format(n=53) and s['moreExp'] == 'false', f'{where} qwen: more {s["more"]!r}')
    check(s['empty'] == L['none'] and s['products'] == 0, f'{where} qwen: empty {s["empty"]!r}, {s["products"]} products')
    check(s['scrollX'] <= 0, f'{where} qwen: horizontal scroll {s["scrollX"]}px')
    if width < 640:
        small = [h for h in [r['h'] for r in s['rows']] + s['btnH'] if h < 44]
        check(not small, f'{where} qwen: buttons under 44px {small}')
    # Keyboard focus is visible on a model button.
    page.focus('#mh-list .mh-pick')
    page.keyboard.press('Tab')
    page.keyboard.press('Shift+Tab')
    ring = page.evaluate('''() => { const a = document.activeElement, cs = getComputedStyle(a);
      return {pick: a.classList.contains('mh-pick'), fv: a.matches(':focus-visible'), style: cs.outlineStyle, width: parseFloat(cs.outlineWidth)}; }''')
    check(ring['pick'] and ring['fv'] and ring['style'] != 'none' and ring['width'] >= 2, f'{where} qwen: focus ring {ring}')

    # "Show all 53" in place, then "Show fewer".
    page.click('#mh-more')
    page.wait_for_timeout(80)
    s = page.evaluate(STATE)
    check(len(s['rows']) == 53 and s['more'] == L['fewer'] and s['moreExp'] == 'true', f'{where} show all: {len(s["rows"])} rows, {s["more"]!r}')
    check(s['title'] == title and s['scrollX'] <= 0, f'{where} show all: title {s["title"]!r}, scroll {s["scrollX"]}')
    page.click('#mh-more')
    page.wait_for_timeout(80)
    s = page.evaluate(STATE)
    check(len(s['rows']) == 3 and s['more'] == L['all'].format(n=53), f'{where} show fewer: {len(s["rows"])} rows, {s["more"]!r}')

    # Language switch re-renders the card.
    other = 'ar' if lang == 'en' else 'en'
    page.click('#lang')
    page.wait_for_timeout(150)
    s = page.evaluate(STATE)
    check(s['title'] == TEXT[other]['title'].format(n=53) and s['empty'] == TEXT[other]['none'] and s['more'] == TEXT[other]['all'].format(n=53)
          and s['lead'] == TEXT[other]['lead'], f'{where} language switch: {s["title"]!r} {s["empty"]!r} {s["more"]!r}')
    page.click('#lang')
    page.wait_for_timeout(150)
    s = page.evaluate(STATE)
    check(s['title'] == title and s['lang'] == lang, f'{where} language back: {s["title"]!r}')

    # Picking a model: search cleared, estimator set, products back, estimator in view with #model focused.
    page.locator('#mh-list .mh-pick', has_text=PICK).first.click()
    page.wait_for_timeout(300)
    s = page.evaluate(STATE)
    check(s['search'] == '' and not s['card'] and s['live'] == '', f'{where} pick: search {s["search"]!r}, card {s["card"]}')
    check(s['model'] == PICK and s['params'] == '32.76', f'{where} pick: model {s["model"]!r} params {s["params"]!r}')
    check('32.76' in s['note'], f'{where} pick: model note {s["note"]!r}')
    check(s['products'] == PRODUCTS and s['productsShown'] and s['empty'] is None, f'{where} pick: {s["products"]}/{PRODUCTS} products, empty {s["empty"]!r}')
    check(0 <= s['estTop'] < s['vh'] * .5, f'{where} pick: #estimator top at {s["estTop"]:.0f} of {s["vh"]}')
    check(s['active'] == 'model', f'{where} pick: focus on {s["active"]!r}')
    qs = parse_qs(s['url'].lstrip('?'))
    check('q' not in qs and qs.get('m') == [PICK] and qs.get('p') == ['32.76'], f'{where} pick: URL {s["url"]}')
    check(s['hash'] == '#hardware', f'{where} pick: hash {s["hash"]}')

    # "nvidia": hardware matches too, so the products stay and the card is its title line.
    s = search(page, 'nvidia')
    check(s['products'] > 0 and s['productsShown'] and s['empty'] is None, f'{where} nvidia: {s["products"]} products, empty {s["empty"]!r}')
    check(s['card'] and s['title'] == L['title'].format(n=6) and not s['body'], f'{where} nvidia: card {s["card"]} {s["title"]!r} open {s["body"]}')
    check(s['toggle'] == L['show'] and s['toggleExp'] == 'false', f'{where} nvidia: toggle {s["toggle"]!r} {s["toggleExp"]}')
    check(s['cardH'] < 90 and s['firstTop'] is not None and s['firstTop'] > s['cardBottom'], f'{where} nvidia: card {s["cardH"]:.0f}px tall, first product at {s["firstTop"]}')
    check(s['scrollX'] <= 0, f'{where} nvidia: horizontal scroll {s["scrollX"]}px')
    if width < 640:
        check(all(h >= 44 for h in s['btnH']), f'{where} nvidia: toggle height {s["btnH"]}')
    page.click('#mh-toggle')
    page.wait_for_timeout(80)
    s = page.evaluate(STATE)
    check(s['body'] and len(s['rows']) == 3 and s['toggle'] == L['hide'] and s['toggleExp'] == 'true' and s['more'] == L['all'].format(n=6),
          f'{where} nvidia open: body {s["body"]}, {len(s["rows"])} rows, {s["toggle"]!r}, {s["more"]!r}')
    check(all(r['name'].startswith('NVIDIA: Nemotron') for r in s['rows']), f'{where} nvidia open: rows {[r["name"] for r in s["rows"]]}')
    page.click('#mh-toggle')
    page.wait_for_timeout(80)
    s = page.evaluate(STATE)
    check(not s['body'] and s['toggle'] == L['show'], f'{where} nvidia closed again: body {s["body"]}, {s["toggle"]!r}')

    # A filter hides the hardware: the card opens and the empty text points at the filters.
    page.select_option('#vendor', 'AMD')
    page.wait_for_timeout(120)
    s = page.evaluate(STATE)
    check(s['products'] == 0 and s['card'] and s['body'] and s['toggle'] is None, f'{where} nvidia+AMD: {s["products"]} products, open {s["body"]}')
    check(s['empty'] == L['filters'], f'{where} nvidia+AMD: empty {s["empty"]!r}')
    page.select_option('#vendor', '')
    page.wait_for_timeout(80)

    # Hardware names and a single letter never show the card.
    for q in ('H100', 'RTX 4090', 'MI300X', 'q'):
        s = search(page, q)
        check(not s['card'] and s['live'] == '', f'{where} {q}: card shown ({s["title"]!r})')
        if s['products'] == 0:
            check(s['empty'] == L['plain'], f'{where} {q}: empty {s["empty"]!r}')
    s = search(page, 'zzzz-nothing')
    check(not s['card'] and s['empty'] == L['plain'], f'{where} nothing: empty {s["empty"]!r}')
    page.fill('#search', '')
    check(not errors, f'{where}: console errors {errors[:3]}')
    check(not foreign, f'{where}: requests to other hosts {foreign[:3]}')
    ctx.close()

def main():
    proc, base = (None, URL.rstrip('/') + '/') if URL else serve()
    origin = '{0.scheme}://{0.netloc}'.format(urlparse(base))
    if SHOTS:
        SHOTS.mkdir(parents=True, exist_ok=True)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            for lang in ('en', 'ar'):
                for width in (375, 1280):
                    run(browser, base, origin, lang, width)
                    if SHOTS:
                        mock(browser, base, lang, width)
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
