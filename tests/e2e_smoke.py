"""Browser smoke test for the built site. Not collected by `unittest discover` (no test_ prefix).

    python scripts/build.py
    python -m http.server 8791 --directory dist      # or any server for dist/
    python tests/e2e_smoke.py [http://localhost:8791/]

Needs Playwright: pip install playwright && python -m playwright install chromium
Clicks through every view in English and Arabic at 375, 768 and 1280 px and checks: no console
errors, no horizontal page scroll, one visible h1 per view, nav state, key elements, deep links,
query string + hash together, legacy query-only links, deep links on a fresh page, focus after a
view change, Back closing the comparison, Arabic direction, filters, compare, theme, language, no-JavaScript fallback,
no requests to other hosts, and that the contact address is not in the page source. Also the owner's requests of
26 Sep 2026: headline cards with a summary and a small source link to the original article, no public source list or
fetch statistics, schedule or newsroom list, the UAE flag (not mirrored in Arabic, whole-pixel size), the contact card
instead of a form with the footer at the bottom of the window, the estimator wording, and the Qahwa & AI follow button
in every view, the footer and the top bar at every width.
"""
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

BASE = (sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8791/').rstrip('/') + '/'
ORIGIN = '{0.scheme}://{0.netloc}'.format(urlparse(BASE))
DATA = Path(__file__).resolve().parents[1] / 'data'
ITEM_URLS = {i['url'] for i in json.loads((DATA / 'news.json').read_text(encoding='utf-8'))['items']}
HOMEPAGES = {s['homepage'] for s in json.loads((DATA / 'news-sources.json').read_text(encoding='utf-8'))}
# The site's own phrases for what was removed; checked only in the site's own text, never in headlines or summaries.
BACKEND_WORDS = ('feeds responded', 'sources responded', 'responded in the latest run', 'sources reached', 'News sources', 'مصادر الأخبار',
                 'Checked at 07:15', 'Schedule:', 'Source check:', 'GitHub Actions', 'Asia/Dubai', 'الجدولة:', 'آخر فحص للمصادر')
LABELS = {'en': ('AI summary', 'From the publisher'), 'ar': ('ملخص بالذكاء الاصطناعي', 'من الناشر')}
ROUTES = ['home', 'hardware', 'news', 'uae', 'contact']
KEY = {
    'home': ['#home-title', '.pillar.p-hw .stats .stat', '.pillar.p-hw .mini', '.pillar.p-news .heads li .n-title', '.pillar.p-news .heads .n-src', '.pillar.p-uae .fmini', '.pillar.p-uae .p-flag .flag', '.pillar .cta', '.trust', '#home .follow-btn'],
    'hardware': ['#hardware-title', '#search', '#model', '#params', '#products .product', '#count', '#csv', '#share', '#print', '#hardware a[download]', '.product .price-row', '.product .credit', '.guides', '.changes', '.statusbar', '#view-table', '#sort', '#extra-hint', '#hardware .ihead .follow-btn'],
    'news': ['#news-title', '#news .nlist .nitem', '#news [data-region-chip]', '#news-count', '#news .nlist .n-src', '#news .nlist .n-sum', '#news .nlist .n-by', '#news .ihead .follow-btn'],
    'uae': ['#uae-title', '#uae-title .flag', '#uae .fact', '#uae .side-stats .stat', '#uae .nlist .nitem', '#uae .ihead .follow-btn'],
    'contact': ['#contact-title', '#contact .contact-card', '#c-mail', '#contact .contact-card .follow-btn', '#contact .xcard.x-uae .flag'],
}
LATIN_OK = re.compile(r'^(NVIDIA|AMD|CSV|PDF|OpenRouter|Hugging Face|Ada Lovelace|[\d\s.,:/()%+–-]+)$')
failures, checks = [], 0

def check(ok, msg):
    global checks
    checks += 1
    if not ok:
        failures.append(msg)
        print('FAIL', msg)

def watch(page, errors, foreign):
    page.on('console', lambda m: errors.append(f'console: {m.text}') if m.type == 'error' else None)
    page.on('pageerror', lambda e: errors.append(f'pageerror: {e}'))
    page.on('request', lambda r: foreign.append(r.url) if not (r.url.startswith(ORIGIN) or r.url.startswith(('data:', 'blob:'))) else None)

def overflow(page):
    return page.evaluate('document.documentElement.scrollWidth - document.documentElement.clientWidth')

def visible_views(page):
    return page.evaluate("[...document.querySelectorAll('[data-view]')].filter(v => v.offsetParent !== null || v.getClientRects().length).map(v => v.dataset.view)")

def route_checks(page, route, lang, width, hash=None):
    tag = f'[{lang} {width}px #{route}]'
    want = '#' + route if hash is None else hash
    check(page.evaluate('location.hash') == want, f'{tag} hash is {page.evaluate("location.hash")}')
    check(visible_views(page) == [route], f'{tag} visible views {visible_views(page)}')
    h1 = page.evaluate("[...document.querySelectorAll('main h1')].filter(h => h.getClientRects().length).length")
    check(h1 == 1, f'{tag} {h1} visible h1')
    current = page.evaluate("[...document.querySelectorAll('.nav a[aria-current=page]')].map(a => a.dataset.nav)")
    check(current == [route], f'{tag} aria-current on {current}')
    check(overflow(page) <= 0, f'{tag} horizontal overflow {overflow(page)}px')
    check(page.evaluate("(n => n.scrollWidth - n.clientWidth)(document.querySelector('.top .nav'))") <= 0, f'{tag} header nav needs sideways scrolling')
    check(page.locator('.top .brand-logo').is_visible(), f'{tag} logo not visible in the header')
    # Tagline under the wordmark: hidden on the narrowest phones and, below 1000px, inside a section (the section name takes its line).
    want_tag = width > 480 and (route == 'home' or width >= 1000)
    check(page.locator('.top .tagline').is_visible() == want_tag, f'{tag} tagline visible should be {want_tag}')
    # On phones the hero carries the tagline instead.
    if route == 'home':
        check(page.locator('#home .hero-tag').is_visible() == (width <= 480), f'{tag} hero tagline visible should be {width <= 480}')
    # The wordmark text sits next to the logo in both directions (in Arabic its column is as wide as the Arabic tagline).
    gap = page.evaluate("""() => { const l = document.querySelector('.top .brand-logo').getBoundingClientRect(), r = document.createRange();
        r.selectNodeContents(document.querySelector('.top .wordmark')); const t = r.getBoundingClientRect();
        return document.documentElement.dir === 'rtl' ? l.left - t.right : t.left - l.right; }""")
    check(0 <= gap <= 12, f'{tag} wordmark is {gap:.0f}px from the logo')
    for sel in KEY[route]:
        check(page.locator(f'{sel} >> visible=true').count() > 0, f'{tag} missing or hidden: {sel}')
    if route != 'home':
        check(page.locator(f'[data-view="{route}"] a.back[href="#home"]').is_visible(), f'{tag} no visible back link to #home')
    # Qahwa & AI: a follow button in the view, the @qahwa.w.ai pill in the top bar at every width, one in the footer.
    check(page.locator(f'[data-view="{route}"] .follow-btn >> visible=true').count() >= 1, f'{tag} no visible follow button in the view')
    check(page.locator('.top .ig-mini').is_visible(), f'{tag} top-bar @qahwa.w.ai pill hidden')
    check(page.locator('.foot .follow-btn').count() == 1, f'{tag} footer follow button missing')
    # UAE flag in the nav, red band on the left in both directions (flags are not mirrored).
    check(page.locator('.nav .n-uae .flag').is_visible(), f'{tag} UAE flag not visible in the nav')
    red = page.evaluate("""() => { const f = document.querySelector('.nav .n-uae .flag'), r = f.querySelector('rect[fill="#EF3340"]').getBoundingClientRect(), b = f.getBoundingClientRect();
        return [Math.round(r.left - b.left), Math.round(r.width * 4 - b.width)]; }""")
    check(abs(red[0]) <= 1 and abs(red[1]) <= 2, f'{tag} UAE flag red band not a quarter-width band at the left: {red}')
    # Whole-pixel sizes: the red band (width/4) and the stripes (height/3) do not land on half pixels.
    sizes = page.evaluate("[...document.querySelectorAll('.flag')].filter(f => f.getClientRects().length).map(f => { const r = f.getBoundingClientRect(); return [r.width, r.height]; })")
    check(all(w == 2 * h and w % 4 == 0 and (h % 3 == 0 or (w, h) == (32, 16)) for w, h in sizes), f'{tag} UAE flag sizes {sizes}')
    # The site's own text only: headlines and summaries may well say "reached".
    text = page.evaluate("[...document.querySelectorAll('.hero, .trust, .ihead, .side, .p-head, .stats, .live, .xnav, .sec-h, .n-note, .foot, .main-col > h2')].map(e => e.innerText).join(' ')")
    left = [w for w in BACKEND_WORDS if w in text]
    check(not left, f'{tag} public page still shows fetch statistics or the source list: {left}')
    if route in ('news', 'uae'):
        cards = page.evaluate(f"""[...document.querySelectorAll('[data-view="{route}"] .nlist[data-lang="{lang}"] .nitem')].filter(li => li.getClientRects().length).map(li => ({{
            linkInTitle: !!li.querySelector('.n-title a'), href: li.querySelector('.n-src') ? li.querySelector('.n-src').getAttribute('href') : '',
            sum: !!li.querySelector('.n-sum'), label: (li.querySelector('.n-by') || {{}}).textContent || ''}}))""")
        check(cards and not any(c['linkInTitle'] for c in cards), f'{tag} headline titles should be plain text')
        bad = [c['href'] for c in cards if c['href'] not in ITEM_URLS or c['href'] in HOMEPAGES]
        check(not bad, f'{tag} source links must open the original article: {bad[:3]}')
        check(all((c['label'] in LABELS[lang]) == c['sum'] for c in cards), f'{tag} every summary needs its label, and only summaries')
        check(any(c['sum'] for c in cards), f'{tag} no summaries shown')
        if route == 'uae':
            check(page.locator('#uae .nr-list').count() == 0, f'{tag} UAE newsroom list still rendered')
            if lang == 'en':
                share = sum(c['sum'] for c in cards) / len(cards)
                check(share >= 0.8, f'{tag} only {share:.0%} of UAE headlines have a summary')
    if route == 'hardware':
        want = ('Extra memory\u00a0(%)', 'ذاكرة إضافية\u00a0(%)')[lang == 'ar']
        check(page.text_content('label:has(#extra) .fl') == want, f'{tag} estimator label: {page.text_content("label:has(#extra) .fl")}')
        check(page.get_attribute('#extra', 'aria-describedby') == 'extra-hint' and page.locator('#extra-hint').is_visible(), f'{tag} estimator help text')
        hint, field = page.evaluate("['#extra-hint', '#extra'].map(s => document.querySelector(s).getBoundingClientRect()).map(r => [r.top, r.left, r.right])")
        check(hint[0] >= field[0] and hint[1] < field[2] and hint[2] > field[1], f'{tag} help text not under the Extra memory field')
        # The label fits on one line, so the field lines up with the others in its row.
        lines = page.evaluate("(f => Math.round(f.getBoundingClientRect().height / parseFloat(getComputedStyle(f).lineHeight)))(document.querySelector('label:has(#extra) .fl'))")
        check(lines == 1, f'{tag} Extra memory label takes {lines} lines')
        bar = page.evaluate("[...document.querySelectorAll('#hardware .statusbar b')].map(b => b.textContent)")
        check(len(bar) == 2, f'{tag} hardware status bar items {bar}')
    if route == 'contact':
        check(page.locator('#contact form, #contact textarea').count() == 0, f'{tag} contact form still present')
        # A short view still ends with the footer at the bottom of the window, not a band of page background.
        page_h, foot_bottom = page.evaluate("[document.documentElement.scrollHeight, document.querySelector('.foot').getBoundingClientRect().bottom + scrollY]")
        check(abs(page_h - foot_bottom) <= 1, f'{tag} footer ends {page_h - foot_bottom:.0f}px above the end of the page')
    check(page.evaluate('document.documentElement.lang') == lang and page.evaluate('document.documentElement.dir') == ('rtl' if lang == 'ar' else 'ltr'), f'{tag} lang/dir not applied')

def go(page, url, view):
    # Hash-only changes are same-document navigations: wait for the router to settle on the view.
    page.goto(BASE + url)
    page.wait_for_function(f'location.hash === "#{view}" && document.documentElement.dataset.route === "{view}"')
    page.wait_for_timeout(150)

def untranslated(page):
    return page.evaluate(r"""() => [...document.querySelectorAll('[data-i18n]')].map(e => e.textContent.trim())
        .filter(t => /[A-Za-z]{3,}/.test(t) && !/[؀-ۿ]/.test(t))""")

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        # 1. Every view through the top navigation, both languages, three widths.
        for lang in ('en', 'ar'):
            for width in (375, 768, 1280):
                ctx = browser.new_context(viewport={'width': width, 'height': 900})
                page, errors, foreign = ctx.new_page(), [], []
                watch(page, errors, foreign)
                page.goto(BASE + ('?lang=ar' if lang == 'ar' else ''))
                page.wait_for_load_state('networkidle')
                route_checks(page, 'home', lang, width, hash='')  # a bare URL is not given #home (it would move the Tab start)
                for route in ROUTES[1:] + ['home']:
                    page.click(f'.nav a[data-nav="{route}"]')
                    page.wait_for_function(f'location.hash === "#{route}"')
                    route_checks(page, route, lang, width)
                    page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                    check(overflow(page) <= 0, f'[{lang} {width}px #{route}] overflow after scrolling')
                if lang == 'ar':
                    left = [t for t in untranslated(page) if not LATIN_OK.match(t)]
                    check(not left, f'[ar {width}px] untranslated labels: {sorted(set(left))[:10]}')
                    check('Cipher Lacuna' in page.title() and re.search(r'[؀-ۿ]', page.title()), f'[ar] document title not translated: {page.title()}')
                    check(page.text_content('.top .tagline') == 'كشف المجهول في عالم الذكاء الاصطناعي', f'[ar {width}px] tagline not in Arabic')
                    check(page.text_content('.top .wordmark') == 'Cipher Lacuna', f'[ar {width}px] brand name should stay Latin')
                else:
                    check(page.title() == 'Cipher Lacuna | AI hardware, AI news and UAE AI', f'[en] home title: {page.title()}')
                check(not errors, f'[{lang} {width}px] console errors: {errors[:5]}')
                check(not foreign, f'[{lang} {width}px] requests to other hosts: {foreign[:5]}')
                ctx.close()

        ctx = browser.new_context(viewport={'width': 1280, 'height': 900}, permissions=['clipboard-read', 'clipboard-write'])
        page, errors, foreign = ctx.new_page(), [], []
        watch(page, errors, foreign)
        total = page.evaluate('0') or 0

        # 2. Unknown hash falls back to #home; back links return home.
        page.goto(BASE + '#no-such-view'); page.wait_for_load_state('networkidle')
        check(page.evaluate('location.hash') == '#home' and visible_views(page) == ['home'], 'unknown hash did not land on #home')
        total = page.evaluate("JSON.parse(document.getElementById('catalog-data').textContent).products.length")
        page.click('.pillar.p-hw .cta'); page.wait_for_function('location.hash === "#hardware"')
        page.click('#hardware a.back'); page.wait_for_function('location.hash === "#home"')
        check(visible_views(page) == ['home'], 'back link did not show #home')

        # 3. Deep links from the pillars end up as query string + canonical hash.
        page.click('.pillar.p-hw .lvl a.chip >> nth=0')
        page.wait_for_function('location.hash === "#hardware"')
        check('level=Personal' in page.url and page.input_value('#level') == 'Personal', f'level chip did not filter: {page.url}')
        n = int(page.text_content('#count').split()[0])
        check(0 < n < total, f'level filter count {n} of {total}')
        go(page, '#home', 'home')
        page.click('.pillar.p-hw .mini a >> nth=0'); page.wait_for_function('location.hash === "#hardware"')
        page.wait_for_selector('.product.flash', timeout=3000)
        check(page.locator('.product.flash').count() == 1 and page.locator('.product.flash').is_visible(), 'featured product not highlighted')
        go(page, '#p-h200', 'hardware')
        check(visible_views(page) == ['hardware'] and page.locator('#p-h200').is_visible(), 'plain #p-<id> anchor did not open the card')
        go(page, '#hardware/vendor/AMD', 'hardware')
        check(page.url.endswith('vendor=AMD#hardware') and page.input_value('#vendor') == 'AMD', f'vendor deep link: {page.url}')

        # 4. Existing query-string state keeps working next to the hash, and Copy link carries both.
        go(page, '?q=MI3&view=table&sort=memory_gb&dir=desc#hardware', 'hardware')
        check(page.locator('#table-view table').is_visible() and page.input_value('#search') == 'MI3', 'query state (q, view=table) not applied')
        rows = page.locator('#table-view tbody tr').count()
        check(0 < rows < total, f'table rows for q=MI3: {rows}')
        page.click('.nav a[data-nav="news"]'); page.wait_for_function('location.hash === "#news"')
        check('q=MI3' in page.url and 'view=table' in page.url, f'query lost on view change: {page.url}')
        page.click('.nav a[data-nav="hardware"]'); page.wait_for_function('location.hash === "#hardware"')
        page.click('#share'); page.wait_for_timeout(300)
        copied = page.evaluate('navigator.clipboard.readText()')
        check('q=MI3' in copied and 'view=table' in copied and copied.endswith('#hardware'), f'Copy link missing query or hash: {copied}')
        page.go_back(); page.wait_for_function('location.hash === "#news"')
        check(visible_views(page) == ['news'], 'browser back did not return to #news')

        # 5. News region filter and "Show more".
        go(page, '#news', 'news')
        shown = lambda: page.evaluate("[...document.querySelectorAll('#news .nlist li')].filter(l => l.getClientRects().length).map(l => l.dataset.region)")
        before = len(shown())
        page.click('#news-more'); page.wait_for_timeout(100)
        check(len(shown()) > before, 'Show more did not reveal more headlines')
        page.click('#news [data-region-chip="uae"]'); page.wait_for_timeout(100)
        regs = shown()
        check(regs and all('uae' in r.split() for r in regs) and 'region=uae' in page.url, f'UAE region filter: {len(regs)} items, {page.url}')
        go(page, '#news/global', 'news')
        check(all('global' in r.split() for r in shown()) and page.url.endswith('region=global#news'), f'#news/global deep link: {page.url}')
        check(page.locator('#news .n-src[href^="https://"]').count() > 0, 'news cards have no source link')
        check(page.locator('#news .srcs, #news .srcs-grid').count() == 0, 'public news source list still rendered')

        # 6. UAE hardware tags open #hardware filtered.
        go(page, '#uae', 'uae')
        tagtext = page.text_content('#uae .fact a.chip >> nth=0').strip()
        page.click('#uae .fact a.chip >> nth=0'); page.wait_for_function('location.hash === "#hardware"')
        n = int(page.text_content('#count').split()[0])
        check(page.input_value('#search') == tagtext and 0 < n < total, f'UAE hardware tag {tagtext!r} gave {n} products')
        page.go_back(); page.wait_for_function('location.hash === "#uae"')
        check(visible_views(page) == ['uae'], 'back from a hardware tag did not return to #uae')

        # 7. Compare tray and dialog; CSV export.
        go(page, '#hardware', 'hardware')
        page.check('#products .product:visible .cmp-toggle >> nth=0'); page.check('#products .product:visible .cmp-toggle >> nth=1')
        check(page.locator('#tray').is_visible() and 'cmp=' in page.url, 'compare tray not shown')
        page.click('#compare-open')
        check(page.locator('#compare-dlg .cmp-table').is_visible(), 'compare dialog did not open')
        page.click('#compare-close')
        page.click('.nav a[data-nav="news"]'); page.wait_for_function('location.hash === "#news"')
        check(not page.locator('#tray').is_visible(), 'compare tray visible outside #hardware')
        go(page, '?cmp=h200,b200-blackwell#hardware/compare', 'hardware')
        check(page.locator('#compare-dlg[open]').count() == 1, '#hardware/compare did not open the comparison')
        page.keyboard.press('Escape')
        with page.expect_download() as dl:
            page.click('#csv')
        check(dl.value.suggested_filename == 'ai-hardware-atlas.csv', 'CSV download')

        # 8. Theme cycles auto -> light -> dark -> auto; language toggle.
        go(page, '#home', 'home')
        themes = []
        for _ in range(3):
            page.click('#theme'); themes.append(page.evaluate('document.documentElement.dataset.theme || "auto"'))
        check(themes == ['light', 'dark', 'auto'], f'theme cycle {themes}')
        page.click('#lang')
        check(page.evaluate('document.documentElement.dir') == 'rtl' and 'lang=ar' in page.url, 'language toggle')
        page.click('#lang')

        # 9. Page source: contact address assembled in JS only; every new-tab link is noopener noreferrer.
        src = page.request.get(BASE).text()
        check('buafra@gmail.com' not in src, 'contact email appears literally in the HTML source')
        check(page.get_attribute('#c-mail', 'href') == 'mailto:' + 'buafra' + '@' + 'gmail.com', 'contact link not assembled')
        bad = page.evaluate("[...document.querySelectorAll('a[target=_blank]')].filter(a => !/noopener/.test(a.rel) || !/noreferrer/.test(a.rel)).map(a => a.href)")
        check(not bad, f'target=_blank links without rel=noopener noreferrer: {bad[:3]}')
        check('"announcements"' not in src, 'backend-only announcements published in the page')
        # Share preview and home-screen icon: absolute og:image on the live site, the files themselves served next to the page.
        og = page.get_attribute('meta[property="og:image"]', 'content')
        check(og == 'https://buafra.github.io/ai-hardware-atlas/brand/og.png', f'og:image is {og}')
        check(page.get_attribute('meta[name="twitter:card"]', 'content') == 'summary_large_image', 'twitter:card')
        for f in ('brand/og.png', page.get_attribute('link[rel="apple-touch-icon"]', 'href'), page.get_attribute('link[rel="icon"][type="image/png"]', 'href')):
            r = page.request.get(BASE + f)
            check(r.status == 200 and r.headers.get('content-type', '').startswith('image/png'), f'{f}: {r.status} {r.headers.get("content-type")}')
        check(not errors, f'console errors: {errors[:5]}')
        check(not foreign, f'requests to other hosts: {foreign[:5]}')
        ctx.close()

        # 10a. Links shared before the views existed (query string, no hash) open the hardware atlas; a lone region opens the news.
        ctx = browser.new_context(viewport={'width': 1280, 'height': 800})
        page, errors, foreign = ctx.new_page(), [], []
        watch(page, errors, foreign)
        for q, view, sel in (('?q=4090', 'hardware', '#search'), ('?cmp=h200,b200-blackwell', 'hardware', '#tray'), ('?view=table&sort=memory_gb&dir=desc', 'hardware', '#table-view table'), ('?region=uae', 'news', '#news-count')):
            page.goto(BASE + q); page.wait_for_load_state('networkidle')
            check(page.evaluate('document.documentElement.dataset.route') == view and page.locator(sel).is_visible() and not page.evaluate('location.hash'),
                  f'legacy link {q}: route {page.evaluate("document.documentElement.dataset.route")}, url {page.url}')
        page.goto(BASE + '?q=4090'); page.wait_for_load_state('networkidle')
        check(page.text_content('#count').startswith('1 of'), f'legacy ?q=4090 count: {page.text_content("#count")}')
        # 10b. The first Tab on a fresh page reaches the skip link (no hash is written on load).
        page.goto(BASE); page.wait_for_load_state('networkidle'); page.keyboard.press('Tab')
        check(page.evaluate('document.activeElement.id') == 'skip', f'first Tab went to {page.evaluate("document.activeElement.className")}')
        # 10c. Plain view links move focus to the new view's heading.
        for sel, view in (('.nav a[data-nav="news"]', 'news'), ('.nav a[data-nav="uae"]', 'uae'), ('#uae a.back', 'home'), ('.pillar.p-hw .cta', 'hardware')):
            page.click(sel); page.wait_for_function(f'document.activeElement && document.activeElement.id === "{view}-title"', timeout=3000)
        # 10d. Back while the comparison is open closes it and keeps the selection.
        page.check('#p-h200 .cmp-toggle'); page.check('#p-b200-blackwell .cmp-toggle'); page.click('#compare-open')
        page.go_back(); page.wait_for_function('location.hash === "#home"')
        page.wait_for_timeout(200)
        check(not page.evaluate("document.getElementById('compare-dlg').open") and page.text_content('#tray-count').startswith('2'), 'Back did not close the comparison or dropped the selection')
        check(not errors and not foreign, f'legacy/focus section errors {errors[:3]} foreign {foreign[:3]}')
        ctx.close()
        # 10e. Deep links opened in a fresh page (shared link, new tab, reload) end with the target in view and focused.
        for width, height in ((375, 812), (1280, 800)):
            for link, target, focus in (('#hardware/p/h200', '#p-h200', 'p-h200'), ('#uae/f/jais-arabic-llm', '#fact-jais-arabic-llm', 'fact-jais-arabic-llm'), ('#hardware/run', '#estimator', 'model'), ('#p-gb300-nvl72', '#p-gb300-nvl72', 'p-gb300-nvl72')):
                ctx = browser.new_context(viewport={'width': width, 'height': height})
                page = ctx.new_page()
                page.goto(BASE + link); page.wait_for_load_state('load')
                page.wait_for_function(f'document.activeElement && document.activeElement.id === "{focus}"', timeout=5000)
                top, hb, vh = page.evaluate(f"[document.querySelector('{target}').getBoundingClientRect().top, document.querySelector('.top').getBoundingClientRect().bottom, innerHeight]")
                check(hb - 1 <= top < vh / 2, f'[{width}px] fresh {link}: target top {top:.0f}, header {hb:.0f}')
                check(page.evaluate('location.hash') in ('#hardware', '#uae'), f'[{width}px] fresh {link}: hash not canonical {page.evaluate("location.hash")}')
                ctx.close()
        # 10f. Arabic: the model note follows the page direction; dates and the footnote are in Arabic.
        ctx = browser.new_context(viewport={'width': 1280, 'height': 800})
        page = ctx.new_page()
        page.goto(BASE + '?lang=ar&view=table#hardware'); page.wait_for_load_state('networkidle')
        name = page.evaluate("JSON.parse(document.getElementById('models-data').textContent).models.find(m => !m.o).n")
        page.fill('#model', name); page.wait_for_timeout(150)
        check(page.evaluate("getComputedStyle(document.getElementById('model-note')).direction") == 'rtl' and page.locator('#model-note bdi').count() == 1, 'Arabic model note not in page direction')
        check(re.search(r'[؀-ۿ]', page.text_content('#hardware .footnote')) is not None, 'footnote not translated')
        raw = page.evaluate(r"[...document.querySelectorAll('#table-view td, #products dd')].map(e => e.innerText).filter(t => /\d{4}-(Q\d|H\d|Summer|end)/.test(t))")
        check(not raw, f'raw date windows shown in Arabic: {raw[:3]}')
        ctx.close()

        # 10. Without JavaScript every view is rendered, stacked and readable.
        ctx = browser.new_context(viewport={'width': 375, 'height': 900}, java_script_enabled=False)
        page = ctx.new_page()
        page.goto(BASE + '#news')
        check(visible_views(page) == ROUTES, f'no-JS visible views {visible_views(page)}')
        check(page.locator('#products .product:visible').count() == total, 'no-JS: not all products visible')
        check(page.locator('#news .nlist[data-lang="en"] .nitem:visible').count() > 0, 'no-JS: headlines hidden')
        check(overflow(page) <= 0, f'no-JS 375px overflow {overflow(page)}px')
        ctx.close()
        browser.close()
    print(f'{checks - len(failures)}/{checks} checks passed')
    return 1 if failures else 0

if __name__ == '__main__':
    sys.exit(main())
