"""Browser test for the Qahwa & AI library page (qahwa.html). Not collected by `unittest discover` (no test_ prefix).

    python tests/e2e_qahwa.py [http://localhost:8791/] [--no-build] [--shots DIR]

Builds qahwa.html from the published-only sample (tests/fixtures/qahwa-sample.json) into a temporary folder and serves it
in place of the base URL's qahwa.html (and its images/qahwa, brand/qahwa, fonts/qahwa) by request routing, so it never
writes to dist/. --no-build tests the base URL's own qahwa.html instead (it must then hold the sample).
If nothing answers at the base URL on localhost, it serves dist/ itself (python -m http.server) and stops it at the end.
Needs Playwright: pip install playwright && python -m playwright install chromium

In English and Arabic, at 390 and 1280 px, in light and dark: html lang/dir, no console errors, NO requests to other
hosts, no horizontal page scroll, 44 px targets, the skip link, the tabs and their counts, search (lesson number "L01",
Arabic letter variants «المساعد الذكى», diacritics, Arabic-Indic digits, and the hint that points to another tab),
Copy (the exact prompt lands on the clipboard), the reading view (every slide text, Escape, focus back) and its deep
links (#lesson-NN, #post-<id>), stories linking to the Instagram profile (their claim shown once, no repeated
"Myth or fact?"), a lone card spanning the grid, the language and theme buttons (the site's
atlas-lang / atlas-theme keys), links back to the site in the page language. Also: a synthetic page with 120 posts
(Show more, week filter, lesson-number search), the early state with no posts, and the page without JavaScript.
The synthetic and empty pages are built into a temporary folder and served under the same origin by request routing.
Arriving from the rest of the site: a Learn AI lesson chip's link (qahwa.html#lesson-NN, with ?lang=ar in Arabic) opens
that lesson in the page language without saving one, the round trip learn.html -> qahwa.html -> learn.html keeps Arabic,
an English visit (?lang=en) while Arabic is the saved choice links back to the overview and Learn AI with ?lang=en,
and the footer stays tidy (every link on one line, no overflow) from 320 to 1920 px.
"""
import json
import mimetypes
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'tests'))
import qahwa
from test_qahwa import synthetic

SHOTS, ARGS, _argv = None, [], sys.argv[1:]
while _argv:
    _a = _argv.pop(0)
    if _a == '--shots' and _argv:
        SHOTS = Path(_argv.pop(0))
    elif not _a.startswith('--'):
        ARGS.append(_a)
BASE = (ARGS[0] if ARGS else 'http://localhost:8791/').rstrip('/') + '/'
URL = BASE + 'qahwa.html'
ORIGIN = '{0.scheme}://{0.netloc}'.format(urlparse(BASE))
SAMPLE = ROOT / 'tests' / 'fixtures' / 'qahwa-sample.json'
IMAGES = ROOT / 'tests' / 'fixtures' / 'qahwa-images'
DOC = json.loads(SAMPLE.read_text(encoding='utf-8'))
POSTS = DOC['posts']
LESSONS = sorted((p for p in POSTS if p['kind'] == 'lesson'), key=lambda p: (p['published_at'], p['lesson']), reverse=True)
LESSON = next(p for p in POSTS if p['kind'] == 'lesson' and p['lesson'] == 1)
STORY = next(p for p in POSTS if p['kind'] == 'story' and 'المساعد الذكي' in json.dumps(p, ensure_ascii=False))
REEL = next((p for p in POSTS if p['kind'] == 'reel'), None)
N_LESSONS = sum(p['kind'] == 'lesson' for p in POSTS)
N_MORE = len(POSTS) - N_LESSONS
N_PROMPTS = sum(bool(p.get('prompt')) for p in POSTS)
PROFILE = qahwa.PROFILE
failures, checks = [], 0
FIXTURE = None  # the folder the sample page is built into (main); None with --no-build
FIXTURE_PREFIXES = ('/images/qahwa/', '/brand/qahwa/', '/fonts/qahwa/')

def check(ok, msg):
    global checks
    checks += 1
    if not ok:
        failures.append(msg)
        print('FAIL', msg)

def plain(s):
    return ' '.join(str(s or '').replace('==', '').split())

def watch(page, errors, foreign):
    page.on('console', lambda m: errors.append(f'console: {m.text}') if m.type == 'error' else None)
    page.on('pageerror', lambda e: errors.append(f'pageerror: {e}'))
    page.on('request', lambda r: foreign.append(r.url) if not (r.url.startswith(ORIGIN) or r.url.startswith(('data:', 'blob:'))) else None)

def overflow(page):
    return page.evaluate('document.documentElement.scrollWidth - document.documentElement.clientWidth')

def shown(page, sel='#grid > *'):
    return page.evaluate(f"[...document.querySelectorAll('{sel}')].filter(e => e.getClientRects().length).length")

def slugs(page):
    return page.evaluate("[...document.querySelectorAll('#grid > [data-slug]')].map(e => e.dataset.slug)")

def serve_dir(page, prefix, folder):
    """Serve `folder` at ORIGIN/<prefix>/ for this page (same origin, no second server)."""
    def handle(route):
        rel = urlparse(route.request.url).path[len(f'/{prefix}/'):] or 'qahwa.html'
        f = Path(folder) / rel
        if f.is_file():
            route.fulfill(status=200, body=f.read_bytes(), headers={'Content-Type': mimetypes.guess_type(f.name)[0] or 'application/octet-stream'})
        else:
            route.fulfill(status=404, body=b'not found')
    page.route(f'{ORIGIN}/{prefix}/**', handle)

def _fixture_url(url):
    u = urlparse(url)
    return f'{u.scheme}://{u.netloc}' == ORIGIN and (u.path == '/qahwa.html' or u.path.startswith(FIXTURE_PREFIXES))

def _fixture(route):
    f = Path(FIXTURE) / urlparse(route.request.url).path.lstrip('/')
    if f.is_file():
        route.fulfill(status=200, body=f.read_bytes(), headers={'Content-Type': mimetypes.guess_type(f.name)[0] or 'application/octet-stream'})
    else:
        route.fulfill(status=404, body=b'not found')

def new_context(browser, **kw):
    """A browser context in which ORIGIN/qahwa.html and its assets come from the sample build (FIXTURE), not dist/."""
    ctx = browser.new_context(**kw)
    if FIXTURE:
        ctx.route(_fixture_url, _fixture)
    return ctx

def small_targets(page):
    """Visible controls under 44 px tall (inline text links inside sentences are exempt)."""
    return page.evaluate("""() => [...document.querySelectorAll('.tab, .chip, .act, .copy, .icon-btn, .btn, .clear, .guide, .cl, button.next, .foot-links a')]
        .filter(e => e.getClientRects().length && !e.closest('dialog:not([open])'))
        .map(e => [e.className || e.tagName, Math.round(e.getBoundingClientRect().height)]).filter(([, h]) => h < 44)""")

def main_flow(browser, lang, width, scheme):
    tag = f'[{lang} {width}px {scheme}]'
    rtl = lang == 'ar'
    ctx = new_context(browser, viewport={'width': width, 'height': 860}, color_scheme=scheme, locale='en-US',
                              permissions=['clipboard-read', 'clipboard-write'])
    ctx.add_init_script(f"try{{if(!sessionStorage.getItem('seeded')){{localStorage.setItem('atlas-lang','{lang}');localStorage.removeItem('atlas-theme');sessionStorage.setItem('seeded','1')}}}}catch(e){{}}")
    page = ctx.new_page()
    errors, foreign = [], []
    watch(page, errors, foreign)
    page.goto(URL)
    page.wait_for_load_state('networkidle')
    check(page.evaluate('[document.documentElement.lang, document.documentElement.dir]') == [lang, 'rtl' if rtl else 'ltr'], f'{tag} html lang/dir')
    check(page.title() == ('دروس قهوة و AI · Cipher Lacuna' if rtl else 'Qahwa & AI Lessons · Cipher Lacuna'), f'{tag} title {page.title()!r}')
    check(overflow(page) <= 0, f'{tag} horizontal overflow {overflow(page)}px')
    bg = page.evaluate("getComputedStyle(document.body).backgroundColor")
    check((bg == 'rgb(28, 20, 19)') == (scheme == 'dark'), f'{tag} body background {bg} for {scheme}')
    fonts = page.evaluate("document.fonts.ready.then(() => [...document.fonts].filter(f => f.status === 'loaded').map(f => f.family.replace(/\"/g, '')))")
    check(('IBM Plex Sans Arabic' if rtl else 'Outfit') in fonts, f'{tag} self-hosted font not loaded: {fonts}')
    check(not small_targets(page), f'{tag} targets under 44px: {small_targets(page)}')
    # Skip link: the first Tab stop, visible when focused.
    page.keyboard.press('Tab')
    check(page.evaluate("document.activeElement.classList.contains('skip') && document.activeElement.getBoundingClientRect().top >= 0"), f'{tag} skip link is not the first, visible Tab stop')
    # Hub links
    check(page.get_attribute('#followBtn', 'href') == PROFILE, f'{tag} follow button link')
    home = 'index.html?lang=ar' if rtl else 'index.html'
    check(page.get_attribute('.cl', 'href') == home, f'{tag} Part of Cipher Lacuna links to {page.get_attribute(".cl", "href")!r}')
    check(page.get_attribute('[data-learn]', 'href') == ('learn.html?lang=ar' if rtl else 'learn.html'), f'{tag} Learn AI link')
    # Tabs and counts
    counts = page.evaluate("[...document.querySelectorAll('#tabs .tab')].map(b => [b.dataset.tab, +b.querySelector('.n').textContent])")
    check(counts == [['lessons', N_LESSONS], ['more', N_MORE], ['prompts', N_PROMPTS]], f'{tag} tab counts {counts}')
    check(slugs(page) == [f'lesson-{p["lesson"]:02d}' for p in LESSONS], f'{tag} lessons tab shows {slugs(page)}')
    if len(LESSONS) == 1:
        # One card alone spans the list (no half-empty grid on desktop).
        solo = page.evaluate("[document.getElementById('grid').classList.contains('solo'), document.querySelector('#grid .card').getBoundingClientRect().width, document.getElementById('grid').getBoundingClientRect().width]")
        check(solo[0] and solo[1] >= solo[2] - 1, f'{tag} a lone card should span the grid: {solo}')
    check(page.locator('#soon').is_visible(), f'{tag} the "new lessons arrive" note is hidden with few lessons')
    page.click('#tabs [data-tab="more"]')
    check(shown(page) == N_MORE and page.locator('#tabs [data-tab="more"][aria-pressed="true"]').count() == 1, f'{tag} more posts tab shows {shown(page)}')
    story_link = page.get_attribute(f'[data-slug="post-{STORY["id"]}"] .ig-link', 'href')
    check(story_link == PROFILE, f'{tag} story links to {story_link!r}, not the profile')
    # The story card shows the claim as its title and does not repeat "Myth or fact?" under the pill.
    story_card = ' '.join(page.inner_text(f'[data-slug="post-{STORY["id"]}"] .c-main').split())
    mf = 'خرافة أم حقيقة؟' if rtl else 'Myth or fact?'
    check(story_card.lower().count(mf.lower()) == 1 and plain(STORY['title'][lang]) in story_card, f'{tag} story card text {story_card!r}')
    if REEL:
        reel_link = page.get_attribute(f'[data-slug="post-{REEL["id"]}"] .ig-link', 'href')
        check(reel_link == REEL['permalink'], f'{tag} reel links to {reel_link!r}')
    page.click('#tabs [data-tab="prompts"]')
    check(shown(page, '#grid > .pcard') == N_PROMPTS, f'{tag} prompts tab shows {shown(page, "#grid > .pcard")}')
    page.click('#tabs [data-tab="lessons"]')
    # Search: lesson number, letter variants, diacritics, Arabic-Indic digits, and the pointer to another tab.
    page.fill('#q', 'L01')
    check(slugs(page) == ['lesson-01'], f'{tag} search L01 shows {slugs(page)}')
    page.fill('#q', 'الدرس ١')
    check(slugs(page) == ['lesson-01'], f'{tag} search الدرس ١ shows {slugs(page)}')
    page.fill('#q', 'الذَّكاءُ الاصطناعيّ')
    check('lesson-01' in slugs(page), f'{tag} search with diacritics shows {slugs(page)}')
    page.fill('#q', 'المساعد الذكى')
    check(shown(page) == 0 and page.locator('#empty').is_visible(), f'{tag} «المساعد الذكى» should find nothing among lessons')
    hint = page.locator('#empty [data-tab="more"]')
    check(hint.count() == 1, f'{tag} no pointer to the match in More posts')
    if hint.count():
        hint.click()
        check(f'post-{STORY["id"]}' in slugs(page), f'{tag} «المساعد الذكى» in More posts shows {slugs(page)}')
    page.fill('#q', 'zzqqxxyy')
    check(page.locator('#empty').is_visible() and page.locator('#empty [data-reset]').count() == 1, f'{tag} no-match message with Clear filters')
    page.press('#q', 'Escape')
    check(page.input_value('#q') == '' and shown(page) == N_MORE, f'{tag} Escape clears the search')
    page.click('#tabs [data-tab="lessons"]')
    # Copy puts the exact prompt (page language) on the clipboard.
    want = LESSON['prompt'][lang].replace('==', '')
    page.click('#grid .card .copy')
    page.wait_for_timeout(150)
    got = page.evaluate('navigator.clipboard.readText()')
    check(got == want, f'{tag} clipboard {got!r} != {want!r}')
    check(page.locator('#toast.on').count() == 1, f'{tag} no "copied" toast')
    # Reading view: open, every slide text, Escape, focus back, hash.
    opener = page.locator('#grid .card .act.primary')
    opener.click()
    check(page.evaluate("document.getElementById('detail').open"), f'{tag} reading view did not open')
    check(page.evaluate('location.hash') == '#lesson-01', f'{tag} hash {page.evaluate("location.hash")}')
    body = ' '.join(page.evaluate("document.getElementById('detail').textContent").split())
    missing = []
    for s in LESSON['slides']:
        x = s[lang]
        for k in ('title', 'body', 'prompt', 'myth', 'fact'):
            if x.get(k) and plain(x[k]) not in body and not (s['type'] == 'cover' and k == 'title'):
                missing.append(plain(x[k])[:40])
        for item in x.get('items') or []:
            if plain(item) not in body:
                missing.append(plain(item)[:40])
        if s.get('next') and qahwa.teaser_target(s['next'], POSTS) and plain(s['next'][lang]) not in body:
            missing.append(plain(s['next'][lang])[:40])
    check(not missing, f'{tag} slide text missing from the reading view: {missing}')
    check(plain(LESSON['title'][lang]) in body, f'{tag} reading view title')
    check(overflow(page) <= 0, f'{tag} overflow with the reading view open')
    page.keyboard.press('Escape')
    page.wait_for_timeout(100)  # the dialog's close event comes in a later task
    check(not page.evaluate("document.getElementById('detail').open"), f'{tag} Escape did not close the reading view')
    check(page.evaluate('location.hash') == '', f'{tag} hash left after closing: {page.evaluate("location.hash")}')
    check(page.evaluate("document.activeElement && document.activeElement.classList.contains('primary')"), f'{tag} focus did not return to the opener')
    # Language and theme buttons (the site's keys).
    page.click('#langBtn')
    other = 'en' if rtl else 'ar'
    check(page.evaluate('[document.documentElement.lang, localStorage.getItem("atlas-lang")]') == [other, other], f'{tag} language button')
    page.click('#langBtn')
    page.click('#themeBtn')
    flipped = 'light' if scheme == 'dark' else 'dark'
    check(page.evaluate('[document.documentElement.dataset.theme, localStorage.getItem("atlas-theme")]') == [flipped, flipped], f'{tag} theme button')
    page.click('#themeBtn')
    # Deep links on a fresh page.
    for hash_, want_title in ((f'#lesson-{LESSON["lesson"]:02d}', LESSON['title'][lang]), (f'#post-{STORY["id"]}', STORY['title'][lang])):
        p2 = ctx.new_page()
        watch(p2, errors, foreign)
        p2.goto(URL + hash_)
        p2.wait_for_timeout(150)
        ok = p2.evaluate("document.getElementById('detail').open")
        check(ok and plain(want_title) in p2.inner_text('#dTitle'), f'{tag} deep link {hash_} did not open its post')
        if ok and hash_.startswith('#post-'):
            dtext = ' '.join(p2.inner_text('#dBody').split())
            check(dtext.count(plain(STORY['title'][lang])) == 1, f'{tag} the story claim should appear once in the reading view')
        if ok:
            p2.click('#dClose')
            check(not p2.evaluate("document.getElementById('detail').open"), f'{tag} Close button after deep link')
        p2.close()
    if SHOTS and ((rtl and width == 390) or (not rtl and width == 1280 and scheme == 'light')):
        SHOTS.mkdir(parents=True, exist_ok=True)
        page.goto(URL)
        page.wait_for_load_state('networkidle')
        name = f'phone-390-ar-{scheme}' if rtl else 'desktop-1280-en'
        page.screenshot(path=str(SHOTS / f'{name}.png'), full_page=True)
        page.click('#grid .card .act.primary')
        page.wait_for_timeout(200)
        page.screenshot(path=str(SHOTS / f'{name}-reading.png'))
    check(not errors, f'{tag} console errors: {errors}')
    check(not foreign, f'{tag} requests to other hosts: {foreign[:5]}')
    ctx.close()

def many_flow(browser, folder, width):
    tag = f'[many posts {width}px]'
    ctx = new_context(browser, viewport={'width': width, 'height': 860})
    page = ctx.new_page()
    errors, foreign = [], []
    watch(page, errors, foreign)
    serve_dir(page, '__many', folder)
    page.goto(f'{ORIGIN}/__many/qahwa.html?lang=en')
    page.wait_for_load_state('networkidle')
    counts = page.evaluate("[...document.querySelectorAll('#tabs .tab')].map(b => +b.querySelector('.n').textContent)")
    check(counts == [100, 20, 100], f'{tag} tab counts {counts}')
    check(shown(page) == 24 and page.locator('#moreBtn').is_visible(), f'{tag} first page shows {shown(page)}')
    check(page.locator('#soon').is_hidden(), f'{tag} the few-lessons note shows with 100 lessons')
    page.click('#moreBtn')
    check(shown(page) == 48, f'{tag} Show more gives {shown(page)}')
    check(page.locator('#weekRow').is_visible() and page.locator('#topicRow').is_visible(), f'{tag} week and topic filters hidden')
    page.click('#weekChips [data-week="3"]')
    weeks = page.evaluate("[...document.querySelectorAll('#grid > [data-slug]')].map(e => e.dataset.slug)")
    check(len(weeks) == 5 and all(s.startswith('lesson-') for s in weeks), f'{tag} week 3 shows {weeks}')
    page.click('#weekChips [data-week="all"]')
    page.fill('#q', 'L42')
    check(slugs(page) == ['lesson-42'], f'{tag} search L42 shows {slugs(page)}')
    page.fill('#q', 'lesson ٧')
    check(slugs(page) == ['lesson-07'], f'{tag} search lesson ٧ shows {slugs(page)}')
    page.fill('#q', '')
    check(overflow(page) <= 0, f'{tag} horizontal overflow {overflow(page)}px')
    page.goto(f'{ORIGIN}/__many/qahwa.html?lang=ar#lesson-100')
    page.wait_for_timeout(150)
    check(page.evaluate("document.getElementById('detail').open"), f'{tag} deep link #lesson-100')
    check(page.locator('#detail .guide').count() >= 1, f'{tag} related guide missing for lesson 100')
    href = page.get_attribute('#detail .guide', 'href') if page.locator('#detail .guide').count() else ''
    check(href == 'learn.html?lang=ar#concept/tokens', f'{tag} guide link {href!r}')
    check(not errors, f'{tag} console errors: {errors}')
    check(not foreign, f'{tag} requests to other hosts: {foreign[:5]}')
    ctx.close()

def empty_flow(browser, folder):
    tag = '[no posts]'
    for lang in ('en', 'ar'):
        ctx = new_context(browser, viewport={'width': 390, 'height': 800})
        page = ctx.new_page()
        errors, foreign = [], []
        watch(page, errors, foreign)
        serve_dir(page, '__empty', folder)
        page.goto(f'{ORIGIN}/__empty/qahwa.html?lang={lang}')
        page.wait_for_load_state('networkidle')
        check(page.locator('#early').is_visible() and page.locator('#libTools').is_hidden(), f'{tag} [{lang}] early state not shown')
        text = page.inner_text('#early')
        want = 'تُضاف الدروس الجديدة هنا مع نشرها على Instagram' if lang == 'ar' else 'New lessons arrive here as they are published on Instagram'
        check(want in text, f'{tag} [{lang}] early text {text!r}')
        check(overflow(page) <= 0, f'{tag} [{lang}] overflow')
        check(not errors and not foreign, f'{tag} [{lang}] errors {errors} / foreign {foreign[:3]}')
        ctx.close()

def nojs_flow(browser):
    ctx = new_context(browser, viewport={'width': 390, 'height': 800}, java_script_enabled=False)
    page = ctx.new_page()
    foreign = []
    page.on('request', lambda r: foreign.append(r.url) if not (r.url.startswith(ORIGIN) or r.url.startswith('data:')) else None)
    page.goto(URL)
    links = page.evaluate("[...document.querySelectorAll('.nojs a')].filter(a => a.getClientRects().length).map(a => a.href)")
    check(len(links) == len(POSTS), f'[no JS] list shows {len(links)} posts')
    check(all(qahwa.instagram_url(h) for h in links), f'[no JS] links {links}')
    check(page.locator('#tabs').is_hidden() and page.locator('#q').is_hidden(), '[no JS] controls should be hidden')
    check(overflow(page) <= 0, f'[no JS] overflow {overflow(page)}')
    check(not foreign, f'[no JS] requests to other hosts: {foreign[:3]}')
    ctx.close()

def site_links_flow(browser):
    """The links the rest of the site uses to reach this page (Learn AI chips and card, the overview's footer and About)."""
    for lang in ('en', 'ar'):
        tag = f'[site links {lang}]'
        q = '?lang=ar' if lang == 'ar' else ''
        ctx = new_context(browser, viewport={'width': 1280, 'height': 860})
        page = ctx.new_page()
        errors, foreign = [], []
        watch(page, errors, foreign)
        # A lesson chip on learn.html links to qahwa.html#lesson-NN (qahwa.lesson_url), with ?lang=ar in Arabic.
        page.goto(BASE + qahwa.lesson_url(LESSON['lesson'], DOC).replace('qahwa.html', 'qahwa.html' + q))
        page.wait_for_function('document.getElementById("detail").open', timeout=5000)
        got = page.evaluate("[document.documentElement.lang, location.hash, localStorage.getItem('atlas-lang'), document.getElementById('dBody').innerText]")
        check(got[:3] == [lang, f'#lesson-{LESSON["lesson"]:02d}', None], f'{tag} lesson deep link opened as {got[:3]}')
        check(plain(LESSON['title'][lang]).split('\n')[0][:12] in got[3], f'{tag} reading view is not lesson {LESSON["lesson"]} in {lang}')
        page.keyboard.press('Escape')
        # Round trip: the footer's Learn AI link keeps the language, and learn.html's card leads back here in it.
        if (ROOT / 'dist' / 'learn.html').exists():
            page.click('.foot-links a[data-learn]')
            page.wait_for_url(lambda u: '/learn.html' in u)
            page.wait_for_load_state('load')
            check(page.evaluate('document.documentElement.lang') == lang, f'{tag} Learn AI opened in {page.evaluate("document.documentElement.lang")}')
            href = page.get_attribute('a.l-qahwa', 'href')
            check(href == 'qahwa.html' + q, f'{tag} Learn AI card links to {href!r}')
            page.click('a.l-qahwa')
            page.wait_for_url(lambda u: '/qahwa.html' in u)
            page.wait_for_load_state('load')
            check(page.evaluate("[document.documentElement.lang, localStorage.getItem('atlas-lang')]") == [lang, None], f'{tag} back on the lessons page in the wrong language')
        check(not errors and not foreign, f'{tag} errors {errors[:3]} foreign {foreign[:3]}')
        ctx.close()
    # Saved language Arabic, English visit (?lang=en, e.g. from an English Learn AI page): the links back keep English.
    tag = '[site links en, saved ar]'
    ctx = new_context(browser, viewport={'width': 1280, 'height': 860})
    ctx.add_init_script("try{if(!sessionStorage.getItem('seeded')){localStorage.setItem('atlas-lang','ar');sessionStorage.setItem('seeded','1')}}catch(e){}")
    page = ctx.new_page()
    errors, foreign = [], []
    watch(page, errors, foreign)
    page.goto(URL + '?lang=en')
    page.wait_for_load_state('networkidle')
    check(page.evaluate('document.documentElement.lang') == 'en', f'{tag} page opened in {page.evaluate("document.documentElement.lang")}')
    homes = page.evaluate("[...document.querySelectorAll('[data-home]')].map(a => a.getAttribute('href'))")
    learns = page.evaluate("[...document.querySelectorAll('[data-learn]')].map(a => a.getAttribute('href'))")
    check(homes and all(h == 'index.html?lang=en' for h in homes), f'{tag} overview links {homes}')
    check(learns and all(h == 'learn.html?lang=en' for h in learns), f'{tag} Learn AI links {learns}')
    for sel, name in (('.foot-links a[data-learn]', '/learn.html'), ('.foot-links a[data-home]', '/index.html')):
        if not (ROOT / 'dist' / name.lstrip('/')).exists() or not page.locator(sel).count():
            continue
        page.click(sel)
        page.wait_for_url(lambda u, n=name: n in u)
        page.wait_for_load_state('load')
        check(page.evaluate('document.documentElement.lang') == 'en', f'{tag} {name} opened in {page.evaluate("document.documentElement.lang")}')
        page.goto(URL + '?lang=en')
        page.wait_for_load_state('networkidle')
    # After the language button the choice is saved, so no parameter is needed.
    page.click('#langBtn')
    page.click('#langBtn')
    homes = page.evaluate("[...document.querySelectorAll('[data-home]')].map(a => a.getAttribute('href'))")
    check(page.evaluate("localStorage.getItem('atlas-lang')") == 'en' and all(h == 'index.html' for h in homes), f'{tag} after the language button {homes}')
    check(not errors and not foreign, f'{tag} errors {errors[:3]} foreign {foreign[:3]}')
    ctx.close()
    # The footer stays tidy from 320 to 1920 px.
    for lang in ('en', 'ar'):
        for width in (320, 375, 414, 768, 1024, 1280, 1440, 1920):
            tag = f'[footer {lang} {width}px]'
            ctx = new_context(browser, viewport={'width': width, 'height': 860})
            page = ctx.new_page()
            page.goto(URL + ('?lang=ar' if lang == 'ar' else ''))
            page.wait_for_load_state('networkidle')
            got = page.evaluate("""() => { const f = document.querySelector('.foot'), fr = f.getBoundingClientRect();
                const links = [...f.querySelectorAll('.foot-links a')];
                return {n: links.length, broken: links.filter(a => [...a.getClientRects()].length !== 1 || new Set([...a.getClientRects()].map(r => Math.round(r.top))).size > 1
                          || a.getBoundingClientRect().height > 2 * parseFloat(getComputedStyle(a).lineHeight || 20) + 24).map(a => a.textContent),
                        outside: links.filter(a => { const r = a.getBoundingClientRect(); return r.left < fr.left - 1 || r.right > fr.right + 1; }).map(a => a.textContent),
                        over: document.documentElement.scrollWidth - document.documentElement.clientWidth}; }""")
            check(got['n'] == 3 and not got['broken'] and not got['outside'] and got['over'] <= 0, f'{tag} footer {got}')
            ctx.close()

def server_up():
    try:
        urllib.request.urlopen(BASE, timeout=2)
        return True
    except Exception:
        return False

def main():
    global FIXTURE
    server = None
    if not server_up() and urlparse(BASE).hostname in ('localhost', '127.0.0.1'):
        server = subprocess.Popen([sys.executable, '-m', 'http.server', str(urlparse(BASE).port or 80), '--directory', str(ROOT / 'dist')],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(50):
            if server_up():
                break
            time.sleep(0.1)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            if '--no-build' not in sys.argv:
                FIXTURE = Path(tmp) / 'sample'
                qahwa.build(FIXTURE, data_path=SAMPLE, images_dir=IMAGES)
            many, empty = Path(tmp) / 'many', Path(tmp) / 'empty'
            data = Path(tmp) / 'many.json'
            data.write_text(json.dumps(synthetic(), ensure_ascii=False), encoding='utf-8')
            qahwa.build(many, data_path=data, images_dir=Path(tmp))
            qahwa.build(empty, data_path=Path(tmp) / 'missing.json', images_dir=Path(tmp))
            with sync_playwright() as pw:
                browser = pw.chromium.launch()
                for lang in ('en', 'ar'):
                    for width in (390, 1280):
                        for scheme in ('light', 'dark'):
                            main_flow(browser, lang, width, scheme)
                for width in (390, 1280):
                    many_flow(browser, many, width)
                empty_flow(browser, empty)
                nojs_flow(browser)
                site_links_flow(browser)
                browser.close()
    finally:
        if server:
            server.terminate()
    print(f'{checks - len(failures)}/{checks} checks passed')
    if SHOTS:
        print('Screenshots:', ', '.join(sorted(p.name for p in SHOTS.glob('*.png'))))
    sys.exit(1 if failures else 0)

if __name__ == '__main__':
    main()
