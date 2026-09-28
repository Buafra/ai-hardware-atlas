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
About Cipher Lacuna (data/about.json): the section under the contact card in both languages, its area links, no update
schedule in it, the #contact/about deep link and the footer's About link landing on it, and no overflow at 375 and 1280 px.
Qahwa & AI lessons page (qahwa.html, a separate page): the footer link after Learn AI in every view and the About link
beside the follow button, both carrying ?lang=ar in Arabic like the links to learn.html (and opening the page in Arabic
without saving a language), and a tidy footer (every link on one line, no overflow) from 320 to 1920 px.
News images (the owner's hybrid plan): every headline card in #news, #uae and the overview's pillars has an image served
from the site itself (a company image from an official company source with its "Image: <company>" credit, or the site's
topic image), loaded lazily and loaded once scrolled into view, beside the text on wide screens (on the start side, so on
the right in Arabic), a 96x72 thumbnail beside the title on phones, 80x60 on the pillars, with no overflow from 320 to
1920 px in both languages, in light and dark mode, and no request to another host.
"""
import json
import re
import sys
import urllib.request
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

BASE = (sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8791/').rstrip('/') + '/'
ORIGIN = '{0.scheme}://{0.netloc}'.format(urlparse(BASE))
DATA = Path(__file__).resolve().parents[1] / 'data'
LEARN = [json.loads((DATA / 'learn' / f).read_text(encoding='utf-8')) for f in ('concepts.json', 'stacks.json')]
LEARN_COUNTS = [len(LEARN[0]['concepts']), sum(s['kind'] != 'foundation' for s in LEARN[1]['stacks']), sum(s['kind'] == 'foundation' for s in LEARN[1]['stacks'])]
# How often the site says it updates, worded as build.schedule_phrase() words it from data/catalog.json.
_RUNS = len(re.findall(r'\b\d{1,2}:\d{2}\b', json.loads((DATA / 'catalog.json').read_text(encoding='utf-8')).get('schedule') or ''))
PHRASE = ({1: 'once a day', 2: 'twice a day'}.get(_RUNS, f'{_RUNS} times a day'), {1: 'مرة يومياً', 2: 'مرتين يومياً'}.get(_RUNS, f'{_RUNS} مرات يومياً'))
ABOUT = json.loads((DATA / 'about.json').read_text(encoding='utf-8'))
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
    'contact': ['#contact-title', '#contact .contact-card', '#c-mail', '#contact .xcard.x-uae .p-icon svg', '#about #about-title', '#about .ab-area', '#about .follow-btn'],
}
LATIN_OK = re.compile(r'^(NVIDIA|AMD|CSV|PDF|OpenRouter|Hugging Face|Ada Lovelace|[\d\s.,:/()%+–-]+)$')
failures, checks = [], 0
def has_android():
    """The site serves the Android app (dist/download/, scripts/android_app.py): the footer then ends with its link."""
    try:
        with urllib.request.urlopen(BASE + 'download/latest.json', timeout=5) as r:
            return r.status == 200
    except OSError:
        return False

ANDROID = has_android()
FOOT_LABELS = {'en': ['Overview', 'Hardware', 'AI news', 'UAE AI', 'Learn AI', 'Qahwa & AI lessons', 'Contact', 'About'] + (['Android app'] if ANDROID else []),
               'ar': ['الرئيسية', 'العتاد', 'أخبار الذكاء الاصطناعي', 'الذكاء الاصطناعي في الإمارات', 'تعلّم الذكاء الاصطناعي', 'دروس قهوة و AI', 'تواصل معنا', 'عن الموقع'] + (['تطبيق Android'] if ANDROID else [])}

def foot_hrefs(lang):
    """The footer links after app.js has run: the separate pages carry ?lang=ar in an Arabic visit."""
    q = '?lang=ar' if lang == 'ar' else ''
    return ['#home', '#hardware', '#news', '#uae', 'learn.html' + q, 'qahwa.html' + q, '#contact', '#contact/about'] + (['#contact/android'] if ANDROID else [])

def footer_tidy(page, tag):
    """Every footer link on one line, at least 24 px tall (WCAG 2.2 SC 2.5.8) and inside the footer, the follow button's
    "Follow Qahwa & AI" on one line, and no horizontal page scroll."""
    got = page.evaluate("""() => { const f = document.querySelector('.foot'), fr = f.getBoundingClientRect();
        const links = [...f.querySelectorAll('.foot-links a')];
        return {broken: links.filter(a => { const r = [...a.getClientRects()]; return r.length !== 1 || r[0].height > 2 * parseFloat(getComputedStyle(a).fontSize) + 22; }).map(a => a.textContent),
                outside: links.filter(a => { const r = a.getBoundingClientRect(); return r.left < fr.left - 1 || r.right > fr.right + 1; }).map(a => a.textContent),
                small: links.filter(a => a.getClientRects().length && a.getBoundingClientRect().height < 24).map(a => a.textContent),
                label: [...f.querySelectorAll('.follow-btn > span')].filter(s => s.getClientRects().length).map(s => {
                    const rg = document.createRange(); rg.selectNodeContents(s);
                    return new Set([...rg.getClientRects()].map(r => Math.round(r.top))).size; }),
                over: document.documentElement.scrollWidth - document.documentElement.clientWidth}; }""")
    check(not got['broken'], f'{tag} footer links break across lines: {got["broken"]}')
    check(not got['small'], f'{tag} footer links under 24 px tall: {got["small"]}')
    check(got['label'] and all(n == 1 for n in got['label']), f'{tag} follow button label lines: {got["label"]}')
    check(not got['outside'], f'{tag} footer links outside the footer: {got["outside"]}')
    check(got['over'] <= 0, f'{tag} horizontal overflow {got["over"]}px')

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
    # Footer links: the views, Learn AI, the Qahwa & AI lessons page, Contact and About, in the page language.
    foot = page.evaluate("[...document.querySelectorAll('.foot-links a')].map(a => [a.getAttribute('href'), a.textContent.trim()])")
    check(foot == [list(x) for x in zip(foot_hrefs(lang), FOOT_LABELS[lang])], f'{tag} footer links {foot}')
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
    # "Updated <date> · 6 times a day" (whatever the schedule says) appears once on the whole site, at the top of AI news.
    fresh = page.evaluate(r"""([en, ar]) => { const t = [...document.querySelectorAll('main, header, footer')].map(e => e.textContent).join(' ');
        return [(t.match(/Updated \d{1,2} [A-Z][a-z]{2} \d{4}/g) || []).length, (t.match(/آخر تحديث \d/g) || []).length,
                t.split(en).length - 1, t.split(ar).length - 1]; }""", list(PHRASE))
    check(fresh == [1, 1, 1, 1], f'{tag} freshness line / {PHRASE[0]!r} counts {fresh} (want one each)')
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
        about_checks(page, tag, lang)
    check(page.evaluate('document.documentElement.lang') == lang and page.evaluate('document.documentElement.dir') == ('rtl' if lang == 'ar' else 'ltr'), f'{tag} lang/dir not applied')

def about_checks(page, tag, lang):
    # About Cipher Lacuna: under the email card, the owner's text as written, four area links, the follow button.
    got = page.evaluate("""() => { const s = document.getElementById('about'), vis = e => e.getClientRects().length > 0;
        return {title: s.querySelector('#about-title').innerText.trim(), paras: [...s.querySelectorAll('.ab-intro p')].map(p => p.innerText.trim()),
            name: s.querySelector('.ab-name p').innerText.trim(), trust: s.querySelector('.ab-trust p').innerText.trim(),
            qahwa: s.querySelector('.ab-qahwa p').innerText.trim(), follow: vis(s.querySelector('.ab-qahwa .follow-btn')),
            areas: [...s.querySelectorAll('.ab-area')].filter(vis).map(a => [a.getAttribute('href'), a.querySelector('.x-sub').innerText.trim(), !!a.querySelector('.p-icon svg')]),
            text: s.innerText, over: s.scrollWidth - s.clientWidth,
            after: document.querySelector('#contact .contact-card').getBoundingClientRect().bottom <= s.getBoundingClientRect().top,
            follows: document.querySelectorAll('#contact .follow-btn').length,
            lessons: [...s.querySelectorAll('.ab-qahwa a.ab-lessons')].filter(vis).map(a => [a.getAttribute('href'), a.innerText.trim(), !a.target,
                ((f, l) => Math.abs((f.top + f.bottom) / 2 - (l.top + l.bottom) / 2) < 4 || l.top >= f.bottom - 1)(s.querySelector('.ab-qahwa .follow-btn').getBoundingClientRect(), a.getBoundingClientRect())])}; }""")
    check(got['title'] == ('About Cipher Lacuna', 'عن Cipher Lacuna')[lang == 'ar'], f'{tag} About title {got["title"]!r}')
    check(got['paras'] == ABOUT['about'][lang], f'{tag} About paragraphs not verbatim: {got["paras"]}')
    check([got['name'], got['trust'], got['qahwa']] == [ABOUT[k][lang] for k in ('name_story', 'trust', 'qahwa')], f'{tag} About name/trust/qahwa not verbatim')
    hrefs = ['#hardware', '#news', '#uae', ('learn.html', 'learn.html?lang=ar')[lang == 'ar']]
    check(got['areas'] == [[h, a[lang], True] for h, a in zip(hrefs, ABOUT['areas'])], f'{tag} About areas {got["areas"]}')
    check(got['follow'] and got['after'], f'{tag} About: follow button hidden or section not under the email card')
    # One follow button in the contact view (beside the Qahwa & AI line), not a second one on the email card.
    check(got['follows'] == 1, f'{tag} {got["follows"]} follow buttons in #contact, expected 1')
    check(got['over'] <= 0, f'{tag} About section overflows by {got["over"]}px')
    # Beside the follow button (same row, or the next one on a phone): the link to the Qahwa & AI lessons page.
    want = [[('qahwa.html', 'qahwa.html?lang=ar')[lang == 'ar'], ('Qahwa & AI lessons', 'دروس قهوة و AI')[lang == 'ar'], True, True]]
    check(got['lessons'] == want, f'{tag} About lessons link {got["lessons"]}')
    left = [w for w in (PHRASE[0], PHRASE[1], 'Updated', 'آخر تحديث', 'a day', 'يومياً') if w in got['text']]
    check(not left, f'{tag} About mentions the update schedule: {left}')

def go(page, url, view):
    # Hash-only changes are same-document navigations: wait for the router to settle on the view.
    page.goto(BASE + url)
    page.wait_for_function(f'location.hash === "#{view}" && document.documentElement.dataset.route === "{view}"')
    page.wait_for_timeout(150)

def untranslated(page):
    return page.evaluate(r"""() => [...document.querySelectorAll('[data-i18n]')].map(e => e.textContent.trim())
        .filter(t => /[A-Za-z]{3,}/.test(t) && !/[؀-ۿ]/.test(t))""")

def news_image_checks(browser):
    """Images on the news cards: same origin, loaded when scrolled into view, sizes and sides, credits, no overflow."""
    for scheme in ('light', 'dark'):
        for lang in ('en', 'ar'):
            for width in (320, 390, 768, 1280, 1920):
                tag = f'[images {lang} {width}px {scheme}]'
                ctx = browser.new_context(viewport={'width': width, 'height': 900}, color_scheme=scheme)
                page, errors, foreign = ctx.new_page(), [], []
                watch(page, errors, foreign)
                for view in ('news', 'uae', 'home'):
                    go(page, ('?lang=ar' if lang == 'ar' else '') + '#' + view, view)
                    sel = {'news': '#news .nlist li.nitem', 'uae': '#uae .nlist li.nitem', 'home': '.pillar.p-news .heads li'}[view]
                    # Bring the first visible cards (the current language's list) into view one by one so their lazy images load.
                    n = page.evaluate("sel => Math.min([...document.querySelectorAll(sel)].filter(li => li.getClientRects().length).length, 4)", sel)
                    for k in range(n):
                        page.evaluate("([sel, k]) => [...document.querySelectorAll(sel)].filter(li => li.getClientRects().length)[k].scrollIntoView({block: 'center'})", [sel, k])
                        page.wait_for_timeout(120)
                    page.wait_for_timeout(300)
                    got = page.evaluate("""([sel, n]) => [...document.querySelectorAll(sel)].filter(li => li.getClientRects().length).slice(0, n).map(li => {
                        const img = li.querySelector(':scope > img.n-img'), t = li.querySelector('.n-title');
                        if (!img) return {missing: true};
                        const r = img.getBoundingClientRect(), tr = t.getBoundingClientRect(), lr = li.getBoundingClientRect();
                        return {src: img.currentSrc || img.src, loaded: img.complete && img.naturalWidth > 0, lazy: img.loading, alt: img.alt,
                                w: Math.round(r.width), h: Math.round(r.height), imgMid: (r.left + r.right) / 2, liMid: (lr.left + lr.right) / 2,
                                besideTitle: r.top < tr.bottom && r.bottom > tr.top, credit: (li.querySelector('.n-credit') || {}).textContent || '',
                                company: /\/images\/news\//.test(img.src), dark: getComputedStyle(document.documentElement).colorScheme}; })""", [sel, n])
                    check(n > 0 and len(got) == n and not any(g.get('missing') for g in got), f'{tag} #{view}: cards without an image {got[:2]}')
                    for g in got:
                        if g.get('missing'):
                            continue
                        check(g['src'].startswith(ORIGIN + '/'), f'{tag} #{view}: image from another host {g["src"]}')
                        check(g['loaded'], f'{tag} #{view}: image not loaded {g["src"]}')
                        check(g['lazy'] == 'lazy' and g['alt'], f'{tag} #{view}: image not lazy or no alt text')
                        want = (80, 60) if view == 'home' else (96, 72) if width < 640 else (184, 104)
                        check((g['w'], g['h']) == want, f'{tag} #{view}: image {g["w"]}x{g["h"]}, expected {want}')
                        # Wide screens: the image on the start side (left in English, right in Arabic). Phones: the thumbnail on the end side,
                        # beside the title (as in the approved mock).
                        start_left = (lang == 'en') != (view != 'home' and width < 640)
                        check((g['imgMid'] < g['liMid']) == start_left, f'{tag} #{view}: image on the wrong side')
                        if view != 'home' and width < 640:
                            check(g['besideTitle'], f'{tag} #{view}: phone thumbnail not beside the title')
                        if g['company']:
                            want_credit = ('Image: ', 'الصورة: ')[lang == 'ar']
                            check(g['credit'].startswith(want_credit) and g['alt'].startswith(want_credit.strip()), f'{tag} #{view}: company image credit {g["credit"]!r} alt {g["alt"]!r}')
                        else:
                            check(not g['credit'], f'{tag} #{view}: topic image with a credit line')
                        check(g['dark'] == ('dark' if scheme == 'dark' else 'light'), f'{tag} colour scheme {g["dark"]}')
                    page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                    check(overflow(page) <= 0, f'{tag} #{view}: horizontal overflow {overflow(page)}px')
                check(not errors, f'{tag} console errors: {errors[:3]}')
                check(not foreign, f'{tag} requests to other hosts: {foreign[:3]}')
                ctx.close()
    # A company image and its credit are on the page (the build found at least one), and every image is served by the site.
    ctx = browser.new_context(viewport={'width': 1280, 'height': 900})
    page = ctx.new_page()
    go(page, '#news', 'news')
    srcs = page.evaluate("[...document.querySelectorAll('img.n-img')].map(i => i.getAttribute('src'))")
    check(srcs and all(re.match(r'^(news-img/[a-z]+\.svg|images/news/[0-9a-f]+\.webp)$', u) for u in srcs), f'image paths {[u for u in srcs if not re.match(r"^(news-img|images/news)/", u)][:3]}')
    company = [u for u in srcs if u.startswith('images/news/')]
    if company:
        r = page.request.get(BASE + company[0])
        body = r.body()  # (a local test server may not know the WebP type; GitHub Pages sends image/webp)
        check(r.ok and body[:4] == b'RIFF' and body[8:12] == b'WEBP' and len(body) <= 40_000, f'company image {company[0]}: {r.status} {len(body)} bytes')
    else:
        print('note: no company images in this build (no cache and no network): topic images only')
    ctx.close()

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
        check(og == 'https://cipherlacuna.ae/brand/og.png', f'og:image is {og}')
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
        # 10e2. About Cipher Lacuna: #contact/about on a fresh page, in both languages, ends with the section in view and
        # focused (hash reduced to #contact); the footer's About link does the same from another view. No overflow.
        for lang in ('en', 'ar'):
            for width, height in ((375, 812), (1280, 800)):
                ctx = browser.new_context(viewport={'width': width, 'height': height})
                page, errors, foreign = ctx.new_page(), [], []
                watch(page, errors, foreign)
                q = '?lang=ar' if lang == 'ar' else ''
                page.goto(BASE + q + '#contact/about'); page.wait_for_load_state('load')
                page.wait_for_function('document.activeElement && document.activeElement.id === "about"', timeout=5000)
                tag = f'[{lang} {width}px #contact/about]'
                top, hb = page.evaluate("[document.getElementById('about').getBoundingClientRect().top, document.querySelector('.top').getBoundingClientRect().bottom]")
                check(hb - 1 <= top < height / 2, f'{tag} fresh deep link: section top {top:.0f}, header {hb:.0f}')
                check(page.evaluate('location.hash') == '#contact' and visible_views(page) == ['contact'], f'{tag} hash {page.evaluate("location.hash")}, views {visible_views(page)}')
                check(overflow(page) <= 0, f'{tag} horizontal overflow {overflow(page)}px')
                about_checks(page, tag, lang)
                # The footer's About link (#contact/about once app.js has run) from the overview.
                go(page, q + '#home', 'home')
                link = page.locator('.foot-links a[data-route="contact/about"]')
                check(link.get_attribute('href') == '#contact/about' and link.text_content() == ('About', 'عن الموقع')[lang == 'ar'], f'{tag} footer About link {link.get_attribute("href")} {link.text_content()!r}')
                link.click()
                page.wait_for_function('document.activeElement && document.activeElement.id === "about"', timeout=5000)
                top = page.evaluate("document.getElementById('about').getBoundingClientRect().top")
                check(hb - 1 <= top < height / 2 and visible_views(page) == ['contact'], f'{tag} footer About link: section top {top:.0f}, views {visible_views(page)}')
                check(not errors and not foreign, f'{tag} errors {errors[:3]} foreign {foreign[:3]}')
                ctx.close()

        # 10f. Arabic: the model note follows the page direction; dates and the footnote are in Arabic.
        ctx = browser.new_context(viewport={'width': 1280, 'height': 800})
        page = ctx.new_page()
        page.goto(BASE + '?lang=ar&view=table#hardware'); page.wait_for_load_state('networkidle')
        name = page.evaluate("JSON.parse(document.getElementById('models-data').textContent).models.find(m => !m.o).n")
        page.fill('#model', name); page.wait_for_timeout(150)
        check(page.evaluate("getComputedStyle(document.getElementById('model-note')).direction") == 'rtl' and page.locator('#model-note bdi').count() == 1, 'Arabic model note not in page direction')
        check(re.search(r'[؀-ۿ]', page.text_content('#hardware .footnote')) is not None, 'footnote not translated')
        raw = page.evaluate(r"[...document.querySelectorAll('#table-view td, #products dd')].map(e => e.innerText).filter(t => /\d{4}-(Q\d|H\d|Summer|end)\b/.test(t))")
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

        # 10g2. The Qahwa & AI lessons page from the footer and the About section, in English: the page opens.
        ctx = browser.new_context(viewport={'width': 1280, 'height': 900})
        page, errors, foreign = ctx.new_page(), [], []
        watch(page, errors, foreign)
        for start, sel in (('#home', '.foot a[href^="qahwa.html"]'), ('#contact', '#about a.ab-lessons')):
            page.goto(BASE + start); page.wait_for_load_state('networkidle')
            page.click(sel); page.wait_for_url('**/qahwa.html'); page.wait_for_load_state('load')
            got = page.evaluate("[document.documentElement.lang, !!document.getElementById('library'), document.title]")
            check(got[:2] == ['en', True] and 'Qahwa' in got[2], f'{sel} opened {page.url} as {got}')
        check(not errors and not foreign, f'Qahwa lessons links: errors {errors[:3]} foreign {foreign[:3]}')
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
            # The same for the Qahwa & AI lessons page: the footer link and the About link carry ?lang=ar.
            for start, sel in (('#home', '.foot a[href^="qahwa.html"]'), ('#contact', '#about a.ab-lessons')):
                ctx = browser.new_context(viewport={'width': width, 'height': 900})
                page, errors, foreign = ctx.new_page(), [], []
                watch(page, errors, foreign)
                page.goto(BASE + '?lang=ar' + start); page.wait_for_load_state('networkidle')
                href = page.get_attribute(sel, 'href')
                page.click(sel); page.wait_for_url(lambda u: '/qahwa.html' in u); page.wait_for_load_state('load')
                got = page.evaluate("[document.documentElement.lang, document.documentElement.dir, localStorage.getItem('atlas-lang')]")
                check(got == ['ar', 'rtl', None] and href == 'qahwa.html?lang=ar', f'[{width}px] {sel} ({href}) opened the lessons page as {got}')
                check(not errors and not foreign, f'[{width}px] Arabic lessons link: errors {errors[:3]} foreign {foreign[:3]}')
                ctx.close()
        # English (the default) keeps the plain links.
        ctx = browser.new_context(viewport={'width': 1280, 'height': 900})
        page = ctx.new_page(); page.goto(BASE); page.wait_for_load_state('networkidle')
        hrefs = page.evaluate("[...document.querySelectorAll('a[href*=\"learn.html\"], a[href*=\"qahwa.html\"]')].map(a => a.getAttribute('href'))")
        check(len([h for h in hrefs if h.startswith('qahwa.html')]) == 2, f'links to the lessons page (footer, About): {hrefs}')
        check(hrefs and not any('lang=' in h for h in hrefs), f'English Learn/lessons links carry a language: {[h for h in hrefs if "lang=" in h][:3]}')
        # Switching to Arabic on the overview updates the links too.
        page.click('#lang'); page.wait_for_timeout(100)
        hrefs = page.evaluate("[...document.querySelectorAll('a[href*=\"learn.html\"], a[href*=\"qahwa.html\"]')].map(a => a.getAttribute('href'))")
        check(hrefs and all(re.match(r'^(learn|qahwa)\.html\?lang=ar(#|$)', h) for h in hrefs), f'Learn/lessons links after switching to Arabic: {hrefs[:3]}')
        ctx.close()

        # 10i. The footer stays tidy from 320 to 1920 px, in both languages (eight links, each on one line).
        for lang in ('en', 'ar'):
            for width in (320, 375, 414, 768, 1024, 1280, 1440, 1920):
                ctx = browser.new_context(viewport={'width': width, 'height': 900})
                page = ctx.new_page()
                page.goto(BASE + ('?lang=ar' if lang == 'ar' else '') + '#contact'); page.wait_for_load_state('networkidle')
                footer_tidy(page, f'[{lang} {width}px footer]')
                ctx.close()

        # 10. Without JavaScript every view is rendered, stacked and readable.
        ctx = browser.new_context(viewport={'width': 375, 'height': 900}, java_script_enabled=False)
        page = ctx.new_page()
        page.goto(BASE + '#news')
        check(visible_views(page) == ROUTES, f'no-JS visible views {visible_views(page)}')
        check(page.locator('#products .product:visible').count() == total, 'no-JS: not all products visible')
        check(page.locator('#news .nlist[data-lang="en"] .nitem:visible').count() > 0, 'no-JS: headlines hidden')
        check(overflow(page) <= 0, f'no-JS 375px overflow {overflow(page)}px')
        check(page.locator('#about .ab-area').count() == 4 and page.get_attribute('.foot-links a[data-route="contact/about"]', 'href') == '#about', 'no-JS: About section or its footer anchor')
        check(page.get_attribute('.foot-links a[href^="qahwa.html"]', 'href') == 'qahwa.html' and page.locator('#about a.ab-lessons').is_visible(), 'no-JS: lessons links')
        ctx.close()

        # 11. News images.
        news_image_checks(browser)
        browser.close()
    print(f'{checks - len(failures)}/{checks} checks passed')
    return 1 if failures else 0

if __name__ == '__main__':
    sys.exit(main())
