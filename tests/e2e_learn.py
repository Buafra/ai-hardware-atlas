"""Browser test for the Learn AI page. Not collected by `unittest discover` (no test_ prefix).

    python -m http.server 8791 --directory dist      # or any server for dist/
    python tests/e2e_learn.py [http://localhost:8791/] [--no-build]

Builds dist/learn.html first (python scripts/learn.py; works without reportlab), then needs Playwright:
pip install playwright && python -m playwright install chromium
In English and Arabic at 375 and 1280 px: no console errors, no requests to other hosts, no horizontal page scroll,
the header nav without sideways scrolling, the logo, follow buttons and the current nav item, the tabs, the topic
filter, search (including Arabic letter variants), opening a stack with its options table, flow arrows that flip in
Arabic, related chips inside the page, Back after a chip, deep links on a fresh page, links to the hardware atlas,
the language and theme buttons (shared localStorage keys), ?lang=ar (and its links back to the overview, which open it
in Arabic), and the page without JavaScript. Also: the AI
stacks badge agrees with the status bar, topic chips count search matches, "No matches" sits under the chips, a stack's
icon stays beside its title, #group/<id> links open their tab with the chip pressed, a UAE chip opens the fact it
names on the overview, and the Arabic series name never breaks across lines.
Counts come from data/learn, so adding or removing a concept or stack does not break this test.
"""
import gzip
import json
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
ARGS = [a for a in sys.argv[1:] if not a.startswith('--')]
BASE = (ARGS[0] if ARGS else 'http://localhost:8791/').rstrip('/') + '/'
URL = BASE + 'learn.html'
ORIGIN = '{0.scheme}://{0.netloc}'.format(urlparse(BASE))
failures, checks = [], 0
CONCEPTS, STACKS = (json.loads((ROOT / 'data' / 'learn' / f).read_text(encoding='utf-8')) for f in ('concepts.json', 'stacks.json'))
N_C = len(CONCEPTS['concepts'])
N_CORE = sum(s['kind'] != 'foundation' for s in STACKS['stacks'])
N_FOUND = len(STACKS['stacks']) - N_CORE
N_S = N_CORE + N_FOUND
BY_GROUP = {g['id']: sum(c['group'] == g['id'] for c in CONCEPTS['concepts']) for g in CONCEPTS['groups']}
G_FILTER = 'g3' if 'g3' in BY_GROUP else CONCEPTS['groups'][-1]['id']

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

def shown(page, panel):
    return page.evaluate(f"[...document.querySelectorAll('#{panel} .l-item')].filter(e => e.getClientRects().length).length")

def in_view(page, item_id):
    return page.evaluate("""id => { const r = document.getElementById(id).getBoundingClientRect();
        return r.top >= 0 && r.top < innerHeight * 0.6 && r.bottom > 0; }""", item_id)

def is_open(page, item_id):
    return page.evaluate('id => document.getElementById(id).open', item_id)

def run(pw):
    browser = pw.chromium.launch()
    for lang in ('en', 'ar'):
        for width in (375, 1280):
            tag = f'[{lang} {width}px]'
            ctx = browser.new_context(viewport={'width': width, 'height': 900})
            ctx.add_init_script(f"try{{if(!sessionStorage.getItem('seeded')){{localStorage.setItem('atlas-lang','{lang}');localStorage.removeItem('atlas-theme');sessionStorage.setItem('seeded','1')}}}}catch(e){{}}")
            page = ctx.new_page()
            errors, foreign = [], []
            watch(page, errors, foreign)
            page.goto(URL)
            rtl = lang == 'ar'
            check(page.evaluate('[document.documentElement.lang, document.documentElement.dir]') == [lang, 'rtl' if rtl else 'ltr'], f'{tag} html lang/dir')
            want_title = 'تعلّم الذكاء الاصطناعي · Cipher Lacuna' if rtl else 'Learn AI · Cipher Lacuna'
            check(page.title() == want_title, f'{tag} title {page.title()!r}')
            h1 = page.evaluate("[...document.querySelectorAll('main h1')].filter(h => h.getClientRects().length).map(h => h.innerText.trim())")
            check(h1 == ['تعلّم الذكاء الاصطناعي' if rtl else 'Learn AI'], f'{tag} visible h1 {h1}')
            check(overflow(page) <= 0, f'{tag} horizontal overflow {overflow(page)}px')
            check(page.evaluate("(n => n.scrollWidth - n.clientWidth)(document.querySelector('.top .nav'))") <= 0, f'{tag} header nav needs sideways scrolling')
            check(page.locator('.top .brand-logo').is_visible(), f'{tag} logo hidden')
            check(page.locator('.top .ig-mini').is_visible(), f'{tag} top-bar @qahwa.w.ai pill hidden')
            check(page.locator('.ihead .follow-btn').is_visible(), f'{tag} follow button in the page header hidden')
            check(page.locator('.foot .follow-btn').count() == 1, f'{tag} footer follow button')
            check(page.locator('.nav a.n-learn[aria-current="page"]').is_visible(), f'{tag} Learn AI not marked current in the nav')
            nav = page.evaluate("[...document.querySelectorAll('.top .nav a')].map(a => a.getAttribute('href'))")
            check(nav == ['index.html', 'index.html#hardware', 'index.html#news', 'index.html#uae', 'learn.html', 'index.html#contact'], f'{tag} nav links {nav}')
            # Visible text is in the page language.
            first = page.evaluate("document.querySelector('#concepts .l-item .it-t').innerText")
            check(any('؀' <= ch <= 'ۿ' for ch in first) == rtl, f'{tag} first title in the wrong language: {first!r}')
            # Tabs
            check(shown(page, 'concepts') == N_C and shown(page, 'stacks') == 0, f'{tag} concepts tab shows {shown(page, "concepts")}, stacks {shown(page, "stacks")}')
            check(page.locator('.l-tab[data-tab="concepts"][aria-current="true"]').count() == 1, f'{tag} concepts tab not current')
            # The AI stacks badge counts the AI stacks, like the status bar; foundations are counted on their own chip.
            badge = page.locator('.l-tab [data-count="stacks"]').inner_text()
            check(badge == str(N_CORE), f'{tag} AI stacks badge {badge!r}, status bar says {N_CORE}')
            # Topic filter
            page.click(f'#concepts .fchip[data-filter="{G_FILTER}"]')
            g_n = BY_GROUP[G_FILTER]
            check(shown(page, 'concepts') == g_n, f'{tag} topic filter {G_FILTER} shows {shown(page, "concepts")}')
            count = page.locator('#l-count').inner_text()
            check((f'عدد النتائج {g_n} من أصل {N_C}' in count) if rtl else count == f'Showing {g_n} of {N_C} concepts', f'{tag} count line {count!r}')
            other = next(g for g in BY_GROUP if g != G_FILTER)
            check(page.locator(f'#concepts .l-group[data-group="{other}"]').is_hidden(), f'{tag} empty topic group still shown')
            page.click('#concepts .fchip[data-filter=""]')
            check(shown(page, 'concepts') == N_C, f'{tag} All topics shows {shown(page, "concepts")}')
            # Search
            page.fill('#lq', 'التكميم' if rtl else 'quantization')
            n = shown(page, 'concepts')
            check(1 <= n < N_C and page.locator('[id="concept/quantization"]').is_visible(), f'{tag} search for quantization shows {n}')
            badge = page.locator('.l-tab [data-count="stacks"]').inner_text()
            check(badge.isdigit() and int(badge) <= N_CORE, f'{tag} stacks badge during search {badge!r}')
            # While searching, each topic chip counts its matches, and All counts every match.
            chip_n = page.evaluate("Object.fromEntries([...document.querySelectorAll('#concepts .fchip')].map(b => [b.dataset.filter, +b.querySelector('.n').textContent]))")
            per_group = page.evaluate("Object.fromEntries([...document.querySelectorAll('#concepts .l-group')].map(g => [g.dataset.group, [...g.querySelectorAll('.l-item')].filter(e => !e.hidden).length]))")
            check(chip_n.get('') == n and all(chip_n.get(g) == k for g, k in per_group.items()), f'{tag} chip counts during search {chip_n} vs {per_group}')
            page.fill('#lq', 'zzqqxxyy')
            check(shown(page, 'concepts') == 0 and page.locator('#l-empty').is_visible(), f'{tag} no-match message')
            where = page.evaluate("(e => [e.closest('[data-panel]') && e.closest('[data-panel]').id, e.previousElementSibling && e.previousElementSibling.classList.contains('l-filter')])(document.getElementById('l-empty'))")
            check(where == ['concepts', True], f'{tag} "No matches" should sit under the topic chips: {where}')
            zeros = page.evaluate("[...document.querySelectorAll('#concepts .fchip .n')].map(s => s.textContent)")
            check(set(zeros) == {'0'}, f'{tag} chips should show 0 matches: {zeros}')
            page.press('#lq', 'Escape')
            check(shown(page, 'concepts') == N_C and page.locator('#l-empty').is_hidden(), f'{tag} Escape clears the search')
            back = page.evaluate("+document.querySelector('#concepts .fchip[data-filter=\"\"] .n').textContent")
            check(back == N_C, f'{tag} All topics chip after clearing the search: {back}')
            if rtl:
                # Letter variants: "اخطاء" (bare alef) finds "أخطاء" in every concept's mistakes heading.
                page.fill('#lq', 'اخطاء')
                check(shown(page, 'concepts') == N_C, f'{tag} Arabic normalisation: {shown(page, "concepts")} hits for اخطاء')
                page.fill('#lq', '')
            # Stacks tab, open a stack, the options table and the flow arrows
            page.click('.l-tab[data-tab="stacks"]')
            check(shown(page, 'stacks') == N_S and shown(page, 'concepts') == 0, f'{tag} stacks tab shows {shown(page, "stacks")}')
            check(page.evaluate('location.hash') == '#stacks', f'{tag} stacks tab hash {page.evaluate("location.hash")}')
            # A stack's icon stays on its title's first line, never alone above it.
            lonely = page.evaluate("""[...document.querySelectorAll('#stacks .l-item')].filter(el => {
                const ic = el.querySelector('.s-ic'); if (!ic) return false;
                const t = [...el.querySelectorAll('.it-t [data-lang]')].find(s => s.getClientRects().length);
                const r = t.getClientRects()[0], i = ic.getBoundingClientRect();
                return Math.abs((i.top + i.bottom) / 2 - (r.top + r.bottom) / 2) > 8; }).map(el => el.id)""")
            check(not lonely, f'{tag} stack icons not beside their titles: {lonely}')
            page.click('#stacks .fchip[data-filter="foundation"]')
            check(shown(page, 'stacks') == N_FOUND, f'{tag} foundations filter shows {shown(page, "stacks")}')
            count = page.locator('#l-count').inner_text()
            want = f'عدد النتائج {N_FOUND} من أصل {N_CORE} تركيبة و{N_FOUND} أسس' if rtl else f'Showing {N_FOUND} of {N_CORE} AI stacks and {N_FOUND} foundations'
            check(count == want, f'{tag} stacks count line {count!r}')
            page.click('#stacks .fchip[data-filter=""]')
            page.click('[id="stack/rag-memory"] > summary')
            check(is_open(page, 'stack/rag-memory'), f'{tag} stack did not open')
            check(page.evaluate('location.hash') == '#stack/rag-memory', f'{tag} opened stack hash {page.evaluate("location.hash")}')
            check(overflow(page) <= 0, f'{tag} horizontal overflow with a stack open {overflow(page)}px')
            check(page.locator('[id="stack/rag-memory"] table.opt tbody.layer').count() >= 3, f'{tag} options table missing')
            check(page.locator('[id="stack/rag-memory"] .pick >> visible=true').count() >= 3, f'{tag} starter picks hidden')
            cols = page.evaluate("[...document.getElementById('stack/rag-memory').querySelectorAll('td[data-col]')].map(td => td.dataset.col)")
            check({'local', 'cloud', 'uae'} <= set(cols), f'{tag} option columns {set(cols)}')
            arrow = page.evaluate(f"getComputedStyle(document.getElementById('stack/rag-memory').querySelector('.flow[data-lang=\"{lang}\"] li'), '::after').transform")
            check(arrow == ('matrix(-1, 0, 0, 1, 0, 0)' if rtl else 'none'), f'{tag} flow arrows should point the reading direction: transform {arrow}')
            hw = page.evaluate("[...document.getElementById('stack/rag-memory').querySelectorAll('a.lchip.hw')].map(a => a.getAttribute('href'))")
            check(hw and all(h.startswith('index.html#hardware') for h in hw) and any(h.startswith('index.html#hardware/p/') for h in hw), f'{tag} hardware links {hw}')
            ext = page.evaluate("[...document.querySelectorAll('a[href^=\"http\"]')].filter(a => a.target !== '_blank' || a.rel !== 'noopener noreferrer').length")
            check(ext == 0, f'{tag} {ext} external links without target=_blank rel="noopener noreferrer"')
            # A related-concept chip opens the concept in the other tab; Back returns to the stack.
            page.click('[id="stack/rag-memory"] a.lchip.rel[href="#concept/rag"] >> visible=true')
            page.wait_for_timeout(50)
            check(page.evaluate('document.documentElement.dataset.ltab') == 'concepts', f'{tag} chip did not switch to concepts')
            check(is_open(page, 'concept/rag') and in_view(page, 'concept/rag'), f'{tag} related chip did not open and show concept/rag')
            page.go_back()
            page.wait_for_timeout(50)
            check(page.evaluate('location.hash') == '#stack/rag-memory' and page.evaluate('document.documentElement.dataset.ltab') == 'stacks', f'{tag} Back after a chip: {page.evaluate("location.hash")}')
            # Deep links on a fresh page
            for item_id, want_tab in (('concept/prompt-injection', 'concepts'), ('stack/local-private', 'stacks')):
                page.goto(f'{URL}#{item_id}')
                page.wait_for_timeout(100)
                check(page.evaluate('document.documentElement.dataset.ltab') == want_tab, f'{tag} deep link #{item_id} tab')
                check(is_open(page, item_id) and in_view(page, item_id), f'{tag} deep link #{item_id} not open or not in view')
                check(overflow(page) <= 0, f'{tag} overflow on #{item_id}')
            # Group links (the overview's "Browse by topic", the core stacks, the foundations): their tab, chip pressed, in view.
            g4 = 'g4' if 'g4' in BY_GROUP else G_FILTER
            for group, want_tab, want_n in ((g4, 'concepts', BY_GROUP[g4]), ('core', 'stacks', N_CORE), ('foundation', 'stacks', N_FOUND)):
                page.goto(f'{URL}#group/{group}')
                page.wait_for_timeout(100)
                panel = 'stacks' if want_tab == 'stacks' else 'concepts'
                got = page.evaluate("""([p, g]) => [document.documentElement.dataset.ltab,
                    (document.querySelector('#' + p + ' .fchip[aria-pressed="true"]') || {}).dataset?.filter,
                    document.getElementById('group/' + g).getClientRects().length > 0]""", [panel, group])
                check(got == [want_tab, group, True], f'{tag} #group/{group}: tab, pressed chip, shown = {got}')
                check(shown(page, panel) == want_n and in_view(page, f'group/{group}'), f'{tag} #group/{group} shows {shown(page, panel)} and in view {in_view(page, f"group/{group}")}')
            # A UAE chip opens the fact it names on the overview, not the top of the UAE view (headlines come first there).
            page.goto(f'{URL}#concept/reasoning-models')
            page.wait_for_timeout(100)
            chip = page.locator('[id="concept/reasoning-models"] a.lchip.site[href$="#uae/f/mbzuai-k2-think"] >> visible=true')
            check(chip.count() == 1, f'{tag} K2 Think chip missing')
            if chip.count() == 1:
                chip.click()
                page.wait_for_url(lambda u: '/index.html' in u and '#uae' in u)  # the overview may add ?lang=ar
                page.wait_for_timeout(400)
                top = page.evaluate("(e => e ? e.getBoundingClientRect().top : null)(document.getElementById('fact-mbzuai-k2-think'))")
                check(top is not None and 0 <= top < 450, f'{tag} K2 Think chip landed {top}px from the top of the fact')
            page.goto(URL)
            # The Arabic series name stays on one line in the editorial note.
            if rtl:
                # Its Arabic and Latin runs are separate boxes; on one line they share a top.
                lines = page.evaluate("new Set([...document.querySelector('.l-note [data-lang=\"ar\"] .l-nw').getClientRects()].map(r => Math.round(r.top))).size")
                check(lines == 1, f'{tag} series name in the note breaks across {lines} lines')
            # Language and theme buttons share the overview's keys.
            page.click('#lang')
            other = 'en' if rtl else 'ar'
            check(page.evaluate('document.documentElement.lang') == other, f'{tag} language button')
            check(page.evaluate("localStorage.getItem('atlas-lang')") == other, f'{tag} atlas-lang not stored')
            check(overflow(page) <= 0, f'{tag} overflow after switching language')
            page.click('#lang')
            page.click('#theme')
            check(page.evaluate("[document.documentElement.dataset.theme, localStorage.getItem('atlas-theme')]") == ['light', 'light'], f'{tag} theme button (light)')
            page.click('#theme')
            check(page.evaluate("[document.documentElement.dataset.theme, localStorage.getItem('atlas-theme')]") == ['dark', 'dark'], f'{tag} theme button (dark)')
            label = page.locator('#theme-label').inner_text()
            check(label == ('داكن' if rtl else 'Dark'), f'{tag} theme label {label!r}')
            page.reload()
            check(page.evaluate('document.documentElement.dataset.theme') == 'dark', f'{tag} theme not kept on reload')
            check(not errors, f'{tag} console errors {errors[:3]}')
            check(not foreign, f'{tag} requests to other hosts {foreign[:3]}')
            ctx.close()
    # ?lang=ar wins over the stored language, as on the overview.
    ctx = browser.new_context(viewport={'width': 1280, 'height': 900})
    page = ctx.new_page()
    page.goto(URL + '?lang=ar')
    check(page.evaluate('[document.documentElement.lang, document.documentElement.dir]') == ['ar', 'rtl'], '?lang=ar')
    ctx.close()
    # A ?lang=ar visit saves nothing, so every link back to the overview carries ?lang=ar (before any #fragment) and the
    # overview opens in Arabic, whichever link is used; after the language button they are plain again.
    home_links = "[...document.querySelectorAll('a[href]')].map(a => a.getAttribute('href')).filter(h => /^index\\.html([?#]|$)/.test(h))"
    for width in (375, 1280):
        tag = f'[?lang=ar {width}px]'
        ctx = browser.new_context(viewport={'width': width, 'height': 900})
        page = ctx.new_page()
        errors, foreign = [], []
        watch(page, errors, foreign)
        page.goto(URL + '?lang=ar')
        hrefs = page.evaluate(home_links)
        check(hrefs and all(h == 'index.html?lang=ar' or h.startswith('index.html?lang=ar#') for h in hrefs), f'{tag} links back to the overview {[h for h in hrefs if "?lang=ar" not in h][:3]}')
        for sel, want_hash in (('.top .nav a.n-home', ''), ('.top .nav a[href$="#hardware"]', '#hardware'), ('.foot a.brand', ''),
                               ('[id="stack/rag-memory"] a.lchip.hw[href*="#hardware/p/"] >> visible=true >> nth=0', '#hardware')):  # the overview then shortens it to #hardware
            page.goto(URL + '?lang=ar' + ('#stack/rag-memory' if 'rag-memory' in sel else ''))
            page.wait_for_timeout(100)
            if 'rag-memory' in sel:
                page.evaluate("document.getElementById('stack/rag-memory').open = true")
            page.locator(sel).first.click()
            page.wait_for_url(lambda u: '/index.html' in u)
            page.wait_for_load_state('load')
            got = page.evaluate('[document.documentElement.lang, document.documentElement.dir, location.search, location.hash]')
            check(got[:2] == ['ar', 'rtl'] and 'lang=ar' in got[2] and got[3].startswith(want_hash), f'{tag} {sel} opened the overview as {got}')
            check(page.evaluate("localStorage.getItem('atlas-lang')") is None, f'{tag} following {sel} saved a language')
        page.goto(URL + '?lang=ar')
        page.click('#lang')
        hrefs = page.evaluate(home_links)
        check(hrefs and not any('?lang=' in h for h in hrefs), f'{tag} links back still carry a language after the language button {[h for h in hrefs if "?lang=" in h][:3]}')
        check(not errors, f'{tag} console errors {errors[:3]}')
        check(not foreign, f'{tag} requests to other hosts {foreign[:3]}')
        ctx.close()
    # Without JavaScript every concept and stack is on the page, both panels shown, the JS-only controls hidden.
    for width in (375, 1280):
        ctx = browser.new_context(viewport={'width': width, 'height': 900}, java_script_enabled=False)
        page = ctx.new_page()
        foreign = []
        page.on('request', lambda r: foreign.append(r.url) if not (r.url.startswith(ORIGIN) or r.url.startswith(('data:', 'blob:'))) else None)
        page.goto(URL)
        tag = f'[no JS {width}px]'
        check(shown(page, 'concepts') == N_C and shown(page, 'stacks') == N_S, f'{tag} items shown {shown(page, "concepts")}/{shown(page, "stacks")}')
        check(page.locator('#lq').is_hidden() and page.locator('#lang').is_hidden(), f'{tag} JS-only controls visible')
        page.click('[id="stack/arabic-first"] > summary')
        check(is_open(page, 'stack/arabic-first'), f'{tag} details do not open without JavaScript')
        check(overflow(page) <= 0, f'{tag} horizontal overflow {overflow(page)}px')
        check(not foreign, f'{tag} requests to other hosts {foreign[:3]}')
        ctx.close()
    browser.close()

def main():
    if '--no-build' not in sys.argv:
        subprocess.run([sys.executable, str(ROOT / 'scripts' / 'learn.py')], check=True)
    page = ROOT / 'dist' / 'learn.html'
    if page.exists():
        raw = page.read_bytes()
        print(f'dist/learn.html: {len(raw) / 1024:.0f} KB, {len(gzip.compress(raw, 9)) / 1024:.0f} KB gzipped')
    with sync_playwright() as pw:
        run(pw)
    print(f'{checks} checks, {len(failures)} failed')
    sys.exit(1 if failures else 0)

if __name__ == '__main__':
    main()
