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
fetch statistics, schedule or newsroom list, the contact card instead of a form with the footer at the bottom of the
window, the estimator wording, and the Qahwa & AI follow button in every view, the footer and the top bar at every
width. Second round: the UAE flag removed again (the generic icon and markers are back), the "Updated <date> · twice a
day" line only once (top of AI news), full summaries in the news and UAE lists (clamped on the overview), the «ترجمة
بالذكاء الاصطناعي» label, and the UAE view and pillar with the latest UAE headlines before the key facts. Learn AI
(learn.html, a separate page): its header link at every width, the three pillars in one row with Learn AI as a
full-width band under them on wide screens (one column below 1000px) with its counts from data/learn, and its links
opening the page and its deep links.
Review of that round: the UAE list in steps of 8 ("Show more"), and Arabic carried across to learn.html by its links.
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
LEARN = [json.loads((DATA / 'learn' / f).read_text(encoding='utf-8')) for f in ('concepts.json', 'stacks.json')]
LEARN_COUNTS = [len(LEARN[0]['concepts']), sum(s['kind'] != 'foundation' for s in LEARN[1]['stacks']), sum(s['kind'] == 'foundation' for s in LEARN[1]['stacks'])]
ITEM_URLS = {i['url'] for i in json.loads((DATA / 'news.json').read_text(encoding='utf-8'))['items']}
HOMEPAGES = {s['homepage'] for s in json.loads((DATA / 'news-sources.json').read_text(encoding='utf-8'))}
# The site's own phrases for what was removed; checked only in the site's own text, never in headlines or summaries.
BACKEND_WORDS = ('feeds responded', 'sources responded', 'responded in the latest run', 'sources reached', 'News sources', 'مصادر الأخبار',
                 'Checked at 07:15', 'Schedule:', 'Source check:', 'GitHub Actions', 'Asia/Dubai', 'الجدولة:', 'آخر فحص للمصادر')
LABELS = {'en': ('AI summary', 'From the publisher'), 'ar': ('ملخص بالذكاء الاصطناعي', 'من الناشر')}
ROUTES = ['home', 'hardware', 'news', 'uae', 'contact']
KEY = {
    'home': ['#home-title', '.pillar.p-hw .stats .stat', '.pillar.p-hw .mini', '.pillar.p-news .heads li .n-title', '.pillar.p-news .heads .n-src', '.pillar.p-uae .fmini', '.pillar.p-uae .p-icon svg', '.pillar.p-uae .heads li .n-title', '.pillar .cta', '.trust', '#home .follow-btn', '.pillar.p-learn .stats .stat', '.pillar.p-learn .lvl .chip', '.pillar.p-learn .cta'],
    'hardware': ['#hardware-title', '#search', '#model', '#params', '#products .product', '#count', '#csv', '#share', '#print', '#hardware a[download]', '.product .price-row', '.product .credit', '.guides', '.changes', '.statusbar', '#view-table', '#sort', '#extra-hint', '#hardware .ihead .follow-btn'],
    'news': ['#news-title', '#news .ifresh', '#news .nlist .nitem', '#news [data-region-chip]', '#news-count', '#news .nlist .n-src', '#news .nlist .n-sum', '#news .nlist .n-by', '#news .ihead .follow-btn'],
    'uae': ['#uae-title', '#uae .uae-facts .fact', '#uae .uae-heads .sec-h h2', '#uae .side-stats .stat', '#uae .nlist .nitem', '#uae .ihead .follow-btn'],
    'contact': ['#contact-title', '#contact .contact-card', '#c-mail', '#contact .contact-card .follow-btn', '#contact .xcard.x-uae .p-icon svg'],
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
    # The UAE flag is gone again: the nav has the same coloured dot as Hardware and AI news, the pillars the generic icon.
    check(page.locator('.flag, .p-flag, .ih-flag, .j-flag').count() == 0, f'{tag} UAE flag still rendered')
    check(page.locator('.nav .n-uae > i.dot').count() == 1, f'{tag} UAE nav marker missing')
    # Learn AI is a separate page: a plain link in the header at every width, never marked as the current view here.
    # In Arabic the link carries ?lang=ar (learn.html would otherwise open in the saved or default language).
    ln = page.locator('.top .nav a.n-learn[href^="learn.html"]')
    check(ln.count() == 1 and ln.is_visible() and ln.get_attribute('aria-current') is None, f'{tag} Learn AI header link hidden or marked current')
    check(ln.get_attribute('href') == ('learn.html', 'learn.html?lang=ar')[lang == 'ar'], f'{tag} Learn AI header link href {ln.get_attribute("href")}')
    shown = page.evaluate("[...document.querySelectorAll('.top .nav a.n-learn span')].filter(s => s.getBoundingClientRect().width > 2).map(s => s.textContent.trim())")
    check(len(shown) == 1 and shown[0] in (('Learn AI', 'Learn'), ('تعلّم الذكاء الاصطناعي', 'تعلّم'))[lang == 'ar'], f'{tag} Learn AI header label {shown}')
    # "Updated <date> · twice a day" appears once on the whole site, at the top of the AI news view.
    fresh = page.evaluate(r"""() => { const t = [...document.querySelectorAll('main, header, footer')].map(e => e.textContent).join(' ');
        return [(t.match(/Updated \d{1,2} [A-Z][a-z]{2} \d{4}/g) || []).length, (t.match(/آخر تحديث \d/g) || []).length,
                (t.match(/twice a day/gi) || []).length, (t.match(/مرتين يومياً/g) || []).length]; }""")
    check(fresh == [1, 1, 1, 1], f'{tag} freshness line / "twice a day" counts {fresh} (want one each)')
    check(page.locator('.ifresh >> visible=true').count() == (1 if route == 'news' else 0), f'{tag} freshness line visible outside #news')
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
        # Full summaries in the lists: no line clamp, nothing cut off.
        cut = page.evaluate(f"""[...document.querySelectorAll('[data-view="{route}"] .nlist[data-lang="{lang}"] .n-sum')].filter(e => e.getClientRects().length)
            .filter(e => getComputedStyle(e).webkitLineClamp !== 'none' || e.scrollHeight > e.clientHeight + 1).length""")
        check(cut == 0, f'{tag} {cut} summaries clamped or cut in the list')
        mt = page.evaluate(f"[...document.querySelectorAll('[data-view=\"{route}\"] .nlist[data-lang=\"{lang}\"] .mt')].map(e => e.textContent)")
        check(all(t == 'ترجمة بالذكاء الاصطناعي' for t in mt) and (lang == 'ar' or not mt), f'{tag} translation labels {sorted(set(mt))}')
        if route == 'uae':
            check(page.locator('#uae .nr-list').count() == 0, f'{tag} UAE newsroom list still rendered')
            # Latest UAE headlines first, then the key facts, each with its "as of" date.
            order = page.evaluate("""() => ['#uae .uae-heads .nitem:not([hidden])', '#uae .uae-facts .fact'].map(s => [...document.querySelectorAll(s)].filter(e => e.getClientRects().length)[0]).map(e => e ? e.getBoundingClientRect().top + scrollY : null)""")
            check(None not in order and order[0] < order[1], f'{tag} UAE headlines should come before the key facts: {order}')
            check(page.locator('#uae .uae-facts .fact .f-date >> visible=true').count() == page.locator('#uae .uae-facts .fact').count(), f'{tag} a key fact lost its date')
            want_h = {'en': ('Latest UAE AI news', 'Key facts'), 'ar': ('أحدث أخبار الذكاء الاصطناعي في الإمارات', 'حقائق رئيسية')}[lang]
            got_h = (page.text_content('#uae-news-h'), page.text_content('#uae-facts-h'))
            check(got_h == want_h, f'{tag} UAE section headings {got_h}')
            if lang == 'en':
                share = sum(c['sum'] for c in cards) / len(cards)
                check(share >= 0.8, f'{tag} only {share:.0%} of UAE headlines have a summary')
    if route == 'home':
        # The UAE pillar: latest UAE headlines, then one highlighted fact. Overview summaries are clamped to three lines.
        tops = page.evaluate("""() => ['.pillar.p-uae .heads', '.pillar.p-uae .fminis'].map(s => [...document.querySelectorAll(s)].filter(e => e.getClientRects().length)[0]).map(e => e ? e.getBoundingClientRect().top : null)""")
        check(None not in tops and tops[0] < tops[1], f'{tag} UAE pillar: headlines should come before the key fact {tops}')
        check(page.locator('.pillar.p-uae .fmini').count() == 1, f'{tag} UAE pillar should show one key fact')
        clamps = page.evaluate("[...document.querySelectorAll('.pillar .heads .n-sum')].filter(e => e.getClientRects().length).map(e => getComputedStyle(e).webkitLineClamp)")
        check(clamps and all(c == '3' for c in clamps), f'{tag} overview summary clamps {sorted(set(clamps))}')
        # From 1000px: the owner's three pillars in one row (level heights), Learn AI a full-width band under them with its
        # concept and stack picks hidden; below 1000px one column with everything shown.
        boxes = page.evaluate("[...document.querySelectorAll('.pillars > .pillar')].map(p => { const r = p.getBoundingClientRect(); return [p.classList[1], Math.round(r.left), Math.round(r.top + scrollY), Math.round(r.height), Math.round(r.width)]; })")
        check([b[0] for b in boxes] == ['p-hw', 'p-news', 'p-uae', 'p-learn'], f'{tag} pillar order {boxes}')
        grid_w = page.evaluate("Math.round(document.querySelector('.pillars').getBoundingClientRect().width)")
        if width >= 1000:
            three, band = boxes[:3], boxes[3]
            check(len({b[2] for b in three}) == 1 and len({b[3] for b in three}) == 1, f'{tag} the three pillars should share one row and height {boxes}')
            check(band[2] > three[0][2] + three[0][3] and abs(band[4] - grid_w) <= 1, f'{tag} Learn AI should be a full-width band under the three {boxes}')
        else:
            check(len({b[2] for b in boxes}) == 4, f'{tag} pillars should stack in one column {boxes}')
        picks = page.locator('.pillar.p-learn .lpicks a >> visible=true').count()
        check((picks == 0) if width >= 1000 else (picks > 0), f'{tag} Learn AI picks visible: {picks}')
        nums = page.evaluate("[...document.querySelectorAll('.pillar.p-learn .stats dd')].map(d => +d.textContent)")
        check(nums == LEARN_COUNTS, f'{tag} Learn AI pillar counts {nums}, want {LEARN_COUNTS}')
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
        # The UAE headlines come in steps of 8 ("Show more"), so the key facts below them stay close.
        go(page, '#uae', 'uae')
        uae_shown = lambda: page.evaluate("[...document.querySelectorAll('#uae .nlist li.nitem')].filter(l => l.getClientRects().length).length")
        uae_total = page.evaluate("document.querySelectorAll('#uae .nlist[data-lang=\"en\"] li.nitem').length")
        check(uae_shown() == min(8, uae_total) and page.locator('#uae-more').is_visible() == (uae_total > 8), f'UAE list: {uae_shown()} of {uae_total} shown first')
        if uae_total > 8:
            page.click('#uae-more'); page.wait_for_timeout(100)
            check(uae_shown() == min(16, uae_total), f'UAE Show more: {uae_shown()} of {uae_total}')

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

        # 10g. Learn AI: the header link and the pillar's button open learn.html; a pick opens its concept there.
        for width in (375, 1280):
            ctx = browser.new_context(viewport={'width': width, 'height': 900})
            page, errors, foreign = ctx.new_page(), [], []
            watch(page, errors, foreign)
            page.goto(BASE); page.wait_for_load_state('networkidle')
            page.click('.top .nav a.n-learn'); page.wait_for_url('**/learn.html')
            check(page.locator('.top .nav a.n-learn[aria-current="page"]').is_visible(), f'[{width}px] header link did not open Learn AI')
            page.go_back(); page.wait_for_load_state('networkidle')
            page.click('.pillar.p-learn .cta'); page.wait_for_url('**/learn.html')
            check(page.evaluate('location.pathname').endswith('/learn.html'), f'[{width}px] Learn AI button opened {page.url}')
            page.go_back(); page.wait_for_load_state('networkidle')
            # Phones show the concept picks; the wide band shows topic chips (their deep links are covered by e2e_learn).
            pick = '.pillar.p-learn .lpicks a >> nth=0' if width < 1000 else '.pillar.p-learn .lvl .chip >> nth=0'
            href = page.get_attribute(pick, 'href')
            page.click(pick); page.wait_for_url('**/' + href); page.wait_for_timeout(200)
            item = href.split('#', 1)[1]
            if item.startswith('concept/'):
                check(page.evaluate('id => { const e = document.getElementById(id); return !!e && e.open && e.getBoundingClientRect().top < innerHeight / 2; }', item), f'[{width}px] {href} did not open its concept')
            else:
                check(page.evaluate('location.hash') == '#' + item, f'[{width}px] {href} opened {page.url}')
            check(not errors and not foreign, f'[{width}px] Learn AI links: errors {errors[:3]} foreign {foreign[:3]}')
            ctx.close()

        # 10h. Arabic opened from a shared ?lang=ar link (nothing saved) stays Arabic on learn.html, whichever link is used.
        for width in (375, 1280):
            for sel in ('.top .nav a.n-learn', '.pillar.p-learn .cta', '.pillar.p-learn .lvl .chip >> nth=0', '.foot a[href^="learn.html"]'):
                ctx = browser.new_context(viewport={'width': width, 'height': 900})
                page, errors, foreign = ctx.new_page(), [], []
                watch(page, errors, foreign)
                page.goto(BASE + '?lang=ar#home'); page.wait_for_load_state('networkidle')
                href = page.get_attribute(sel, 'href')
                page.click(sel); page.wait_for_url(lambda u: '/learn.html' in u); page.wait_for_load_state('load')
                got = page.evaluate("[document.documentElement.lang, document.documentElement.dir, localStorage.getItem('atlas-lang')]")
                check(got == ['ar', 'rtl', None] and re.match(r'^learn\.html\?lang=ar(#|$)', href or ''), f'[{width}px] {sel} ({href}) opened Learn AI as {got}')
                check(not errors and not foreign, f'[{width}px] Arabic Learn link: errors {errors[:3]} foreign {foreign[:3]}')
                ctx.close()
        # English (the default) keeps the plain links.
        ctx = browser.new_context(viewport={'width': 1280, 'height': 900})
        page = ctx.new_page(); page.goto(BASE); page.wait_for_load_state('networkidle')
        hrefs = page.evaluate("[...document.querySelectorAll('a[href*=\"learn.html\"]')].map(a => a.getAttribute('href'))")
        check(hrefs and not any('lang=' in h for h in hrefs), f'English Learn links carry a language: {[h for h in hrefs if "lang=" in h][:3]}')
        # Switching to Arabic on the overview updates the links too.
        page.click('#lang'); page.wait_for_timeout(100)
        hrefs = page.evaluate("[...document.querySelectorAll('a[href*=\"learn.html\"]')].map(a => a.getAttribute('href'))")
        check(hrefs and all(re.match(r'^learn\.html\?lang=ar(#|$)', h) for h in hrefs), f'Learn links after switching to Arabic: {hrefs[:3]}')
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
