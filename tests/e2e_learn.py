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
Qahwa & AI lessons (qahwa.html): the card near the top and the footer link (after Learn AI) open it, carrying ?lang=ar in
Arabic; a concept's lesson chips show only the lessons published on that page (data/qahwa.json as the page shows it),
checked on the real data and on a copy of the page where a concept lists a published lesson (served by the test itself),
whose chip opens that lesson on qahwa.html. The footer stays tidy from 320 to 1920 px.
Reports tab (#reports, data/learn/reports.json): the tab and its badge, the source chips, topic and year menus (alone and
combined, with live counts in the page language), search in English and Arabic (letter variants), "No matches" under
the menus, #report/<id> deep links (also while filters hide the card), links that open the publisher's own page in a
new tab, right-to-left layout, no horizontal scroll from 320 to 1920 px with a card open, and no requests to other hosts.
Counts come from data/learn, so adding or removing a concept, stack or report does not break this test.
"""
import gzip
import json
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import learn  # noqa: E402  (renders the chip fixture page; works without reportlab)
import qahwa  # noqa: E402
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
# Qahwa & AI: the posts qahwa.html shows, the lesson chips learn.html should have, and a chip fixture.
QDOC = qahwa.page_doc()[0]
CHIPS = {c['id']: [f'qahwa.html#lesson-{x["lesson"]:02d}' for x in c.get('related_lessons') or [] if qahwa.lesson_url(x['lesson'], QDOC)]
         for c in CONCEPTS['concepts']}
PUBLISHED = sorted(p['lesson'] for p in QDOC['posts'] if p.get('kind') == 'lesson')
FIXTURE = 'learn-lessons-fixture.html'  # served by page.route (never written to dist/)
REPORTS = learn.sorted_reports(learn.load_reports())
N_R = len(REPORTS)
R_GROUP = {g: [r['id'] for r in REPORTS if learn.report_group(r) == g] for g, _, _ in learn.REPORT_GROUPS}
R_DOMAINS = [d for _, _, ds in learn.REPORT_ORGS.values() for d in ds]

def fixture_page():
    """learn.html with the llm concept listing the first published lesson (next to its unpublished ones)."""
    import copy
    c = copy.deepcopy(CONCEPTS)
    n = PUBLISHED[0]
    post = next(p for p in QDOC['posts'] if p.get('kind') == 'lesson' and p['lesson'] == n)
    llm = next(x for x in c['concepts'] if x['id'] == 'llm')
    llm['related_lessons'] = [x for x in llm['related_lessons'] if x['lesson'] != n] + [{'lesson': n, 'title_en': post['title']['en'], 'title_ar': post['title']['ar']}]
    catalog = json.loads((ROOT / 'data' / 'catalog.json').read_text(encoding='utf-8'))
    return learn.render(c, STACKS, catalog, lessons_doc=QDOC), n, [x['lesson'] for x in llm['related_lessons'] if x['lesson'] != n]

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
            # Qahwa & AI lessons: the card under the page header and the footer link after Learn AI, in the page language
            # (an Arabic visit always carries ?lang=ar to qahwa.html).
            q = '?lang=ar' if rtl else ''
            card = page.evaluate("""(a => a && [a.getAttribute('href'), a.querySelector('b').innerText.trim(), a.getClientRects().length > 0,
                a.getBoundingClientRect().top < document.querySelector('.l-tools').getBoundingClientRect().top,
                a.getBoundingClientRect().top > document.querySelector('.ihead').getBoundingClientRect().bottom - 1])(document.querySelector('a.l-qahwa'))""")
            check(card == ['qahwa.html' + q, 'دروس يومية من قهوة و AI' if rtl else 'Daily lessons from Qahwa & AI', True, True, True], f'{tag} Qahwa & AI card {card}')
            foot = page.evaluate("[...document.querySelectorAll('.foot-links a')].map(a => a.getAttribute('href'))")
            check(foot == ['index.html', 'index.html#hardware', 'index.html#news', 'index.html#uae', 'learn.html', 'qahwa.html' + q, 'index.html#contact', 'index.html#contact/about'], f'{tag} footer links {foot}')
            foot_q = page.evaluate("(a => a.innerText.trim())(document.querySelector('.foot-links a[href^=\"qahwa.html\"]'))")
            check(foot_q == ('دروس قهوة و AI' if rtl else 'Qahwa & AI lessons'), f'{tag} footer lessons link text {foot_q!r}')
            # Lesson chips: only the lessons already on qahwa.html; a concept with none has no lessons block.
            chips = page.evaluate("""Object.fromEntries([...document.querySelectorAll('#concepts .l-item')].map(d => [d.id.slice(8),
                [...d.querySelectorAll('a.lchip.lesson')].map(a => a.getAttribute('href'))]))""")
            want = {k: [h.replace('qahwa.html', 'qahwa.html' + q) for h in v] for k, v in CHIPS.items()}
            check(chips == want, f'{tag} lesson chips {[(k, v) for k, v in chips.items() if v != want[k]][:3]}')
            blocks = page.evaluate("[...document.querySelectorAll('#concepts .l-item')].filter(d => [...d.querySelectorAll('h5')].some(h => /Qahwa & AI lessons|دروس قهوة و AI/.test(h.textContent))).map(d => d.id.slice(8))")
            check(sorted(blocks) == sorted(k for k, v in CHIPS.items() if v), f'{tag} lessons blocks on {blocks}')
            # Visible text is in the page language.
            first = page.evaluate("document.querySelector('#concepts .l-item .it-t').innerText")
            check(any('؀' <= ch <= 'ۿ' for ch in first) == rtl, f'{tag} first title in the wrong language: {first!r}')
            # Tabs
            check(shown(page, 'concepts') == N_C and shown(page, 'stacks') == 0 and shown(page, 'reports') == 0,
                  f'{tag} concepts tab shows {shown(page, "concepts")}, stacks {shown(page, "stacks")}, reports {shown(page, "reports")}')
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
            check(shown(page, 'stacks') == N_S and shown(page, 'concepts') == 0 and shown(page, 'reports') == 0, f'{tag} stacks tab shows {shown(page, "stacks")}')
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
                # Its Arabic and Latin runs are separate boxes; on one line they share a top. Every visible one: the card,
                # the header's follow button, the footer, and the note and chips when a lesson is published.
                lines = page.evaluate("[...document.querySelectorAll('.l-nw')].filter(e => e.getClientRects().length).map(e => new Set([...e.getClientRects()].map(r => Math.round(r.top))).size)")
                check(len(lines) >= 3 and set(lines) == {1}, f'{tag} series name breaks across lines: {lines}')
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
    # A copy of the page where the llm concept lists a published lesson: its chip (and no unpublished one) opens that
    # lesson on qahwa.html, in the page language.
    if PUBLISHED:
        html, n, hidden = fixture_page()
        for lang in ('en', 'ar'):
            for width in (375, 1280):
                tag = f'[chip fixture {lang} {width}px]'
                ctx = browser.new_context(viewport={'width': width, 'height': 900})
                ctx.route(BASE + FIXTURE + '*', lambda route: route.fulfill(status=200, content_type='text/html; charset=utf-8', body=html))
                page = ctx.new_page()
                errors, foreign = [], []
                watch(page, errors, foreign)
                page.goto(BASE + FIXTURE + ('?lang=ar' if lang == 'ar' else '') + '#concept/llm')
                page.wait_for_timeout(150)
                hrefs = page.evaluate("[...document.getElementById('concept/llm').querySelectorAll('a.lchip.lesson')].map(a => a.getAttribute('href'))")
                want = f'qahwa.html{"?lang=ar" if lang == "ar" else ""}#lesson-{n:02d}'
                check(hrefs == [want], f'{tag} llm lesson chips {hrefs}')
                text = page.evaluate("document.getElementById('concept/llm').innerText")
                check(not any(f'{k:02d}:' in text for k in hidden), f'{tag} an unpublished lesson is named: {[k for k in hidden if f"{k:02d}:" in text]}')
                page.click('[id="concept/llm"] a.lchip.lesson >> visible=true')
                page.wait_for_url(lambda u: '/qahwa.html' in u)
                page.wait_for_function('document.getElementById("detail") && document.getElementById("detail").open', timeout=5000)
                got = page.evaluate("[document.documentElement.lang, location.hash, localStorage.getItem('atlas-lang')]")
                check(got == [lang, f'#lesson-{n:02d}', None], f'{tag} chip opened qahwa.html as {got}')
                check(not errors and not foreign, f'{tag} errors {errors[:3]} foreign {foreign[:3]}')
                ctx.close()
    else:
        print('note: no Qahwa & AI lesson is published yet; the chip fixture is skipped')
    # The footer stays tidy from 320 to 1920 px in both languages.
    for lang in ('en', 'ar'):
        for width in (320, 375, 414, 768, 1024, 1280, 1440, 1920):
            ctx = browser.new_context(viewport={'width': width, 'height': 900})
            page = ctx.new_page()
            page.goto(URL + ('?lang=ar' if lang == 'ar' else ''))
            footer_tidy(page, f'[{lang} {width}px footer]')
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
        # The Qahwa & AI card and footer link open qahwa.html in Arabic too, without saving a language.
        for sel in ('a.l-qahwa', '.foot-links a[href^="qahwa.html"]'):
            page.goto(URL + '?lang=ar')
            href = page.get_attribute(sel, 'href')
            page.click(sel)
            page.wait_for_url(lambda u: '/qahwa.html' in u)
            page.wait_for_load_state('load')
            got = page.evaluate("[document.documentElement.lang, document.documentElement.dir, localStorage.getItem('atlas-lang')]")
            check(href == 'qahwa.html?lang=ar' and got == ['ar', 'rtl', None], f'{tag} {sel} ({href}) opened the lessons page as {got}')
        page.goto(URL + '?lang=ar')
        page.click('#lang')
        q_links = page.evaluate("[...document.querySelectorAll('a[href^=\"qahwa.html\"]')].map(a => a.getAttribute('href'))")
        check(q_links and not any('?lang=' in h for h in q_links), f'{tag} lessons links after switching to English {q_links[:3]}')
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
        check(shown(page, 'concepts') == N_C and shown(page, 'stacks') == N_S and shown(page, 'reports') == N_R,
              f'{tag} items shown {shown(page, "concepts")}/{shown(page, "stacks")}/{shown(page, "reports")}')
        check(page.locator('.r-selects').is_hidden(), f'{tag} report menus visible without JavaScript')
        check(page.locator('#lq').is_hidden() and page.locator('#lang').is_hidden(), f'{tag} JS-only controls visible')
        page.click('[id="stack/arabic-first"] > summary')
        check(is_open(page, 'stack/arabic-first'), f'{tag} details do not open without JavaScript')
        check(overflow(page) <= 0, f'{tag} horizontal overflow {overflow(page)}px')
        check(not foreign, f'{tag} requests to other hosts {foreign[:3]}')
        ctx.close()
    reports_run(browser)
    browser.close()

def visible_ids(page):
    return page.evaluate("[...document.querySelectorAll('#reports .l-item')].filter(e => e.getClientRects().length).map(e => e.id.slice(7))")

def on_domain(url):
    host = urlparse(url).hostname or ''
    return any(host == d or host.endswith('.' + d) for d in R_DOMAINS)

def reports_run(browser):
    """The Reports tab in both languages at phone and desktop widths, then no horizontal scroll from 320 to 1920 px."""
    for lang in ('en', 'ar'):
        rtl = lang == 'ar'
        for width in (375, 1280):
            tag = f'[reports {lang} {width}px]'
            ctx = browser.new_context(viewport={'width': width, 'height': 900})
            ctx.add_init_script(f"try{{if(!sessionStorage.getItem('seeded')){{localStorage.setItem('atlas-lang','{lang}');sessionStorage.setItem('seeded','1')}}}}catch(e){{}}")
            page = ctx.new_page()
            errors, foreign = [], []
            watch(page, errors, foreign)
            page.goto(URL)
            # The tab: its badge, then a click opens it (#reports) with every report shown, newest first.
            check(page.locator('.l-tab [data-count="reports"]').inner_text() == str(N_R), f'{tag} reports badge')
            page.click('.l-tab[data-tab="reports"]')
            check(page.evaluate('[location.hash, document.documentElement.dataset.ltab]') == ['#reports', 'reports'], f'{tag} reports tab hash/tab')
            check(page.locator('.l-tab[data-tab="reports"][aria-current="true"]').count() == 1, f'{tag} reports tab not current')
            check(visible_ids(page) == [r['id'] for r in REPORTS], f'{tag} reports shown in order: {len(visible_ids(page))} of {N_R}')
            check(shown(page, 'concepts') == 0 and shown(page, 'stacks') == 0, f'{tag} other panels shown with reports')
            check(page.evaluate('[document.documentElement.lang, document.documentElement.dir]') == [lang, 'rtl' if rtl else 'ltr'], f'{tag} lang/dir')
            intro = page.evaluate("document.querySelector('#reports .p-intro p').innerText")
            check(('تقارير مجانية' in intro) if rtl else intro.startswith('Free reports on AI'), f'{tag} intro line {intro[:40]!r}')
            first = page.evaluate("document.querySelector('#reports .l-item .it-t').innerText")
            check(any('؀' <= ch <= 'ۿ' for ch in first) == rtl, f'{tag} first report title in the wrong language: {first!r}')
            check(overflow(page) <= 0, f'{tag} horizontal overflow {overflow(page)}px')
            check(page.evaluate("(n => n.scrollWidth - n.clientWidth)(document.querySelector('.l-tabs'))") <= 0, f'{tag} tabs overflow')
            # Source chips
            for g, ids in R_GROUP.items():
                page.click(f'#reports .fchip[data-filter="{g}"]')
                check(visible_ids(page) == ids, f'{tag} source {g} shows {len(visible_ids(page))}, want {len(ids)}')
            page.click('#reports .fchip[data-filter="gcc"]')
            count = page.locator('#l-count').inner_text()
            n_gcc = len(R_GROUP['gcc'])
            want = f'عدد النتائج {n_gcc} من أصل {learn.cnt(N_R, "report", "ar")}' if rtl else f'Showing {n_gcc} of {N_R} reports'
            check(count == want, f'{tag} count line {count!r}, want {want!r}')
            # Topic menu on top of the source chip: both apply, and each chip counts what it would show.
            topic = 'agents'
            page.select_option('#r-topic', topic)
            both = [r['id'] for r in REPORTS if learn.report_group(r) == 'gcc' and topic in r['topics']]
            check(visible_ids(page) == both, f'{tag} gcc + {topic} shows {visible_ids(page)}')
            chips = page.evaluate("Object.fromEntries([...document.querySelectorAll('#reports .fchip')].map(b => [b.dataset.filter, +b.querySelector('.n').textContent]))")
            want_chips = {'': sum(topic in r['topics'] for r in REPORTS),
                          **{g: sum(topic in r['topics'] for r in REPORTS if learn.report_group(r) == g) for g in R_GROUP}}
            check(chips == want_chips, f'{tag} source chip counts with topic {topic}: {chips} vs {want_chips}')
            label = page.evaluate("document.querySelector('#r-topic option[value=agents]').textContent")
            n_label = sum(topic in r['topics'] for r in REPORTS if learn.report_group(r) == 'gcc')
            want_label = f'{"الوكلاء الذكيون" if rtl else "AI agents"} ({n_label})'
            check(label == want_label, f'{tag} topic option label {label!r}, want {want_label!r}')
            # Year menu: all three filters together, then back to everything.
            year = REPORTS[-1]['published'][:4]
            page.click('#reports .fchip[data-filter=""]')
            page.select_option('#r-year', year)
            want_ids = [r['id'] for r in REPORTS if topic in r['topics'] and r['published'][:4] == year]
            check(visible_ids(page) == want_ids, f'{tag} {topic} + {year} shows {len(visible_ids(page))}, want {len(want_ids)}')
            page.select_option('#r-topic', '')
            page.select_option('#r-year', '')
            check(len(visible_ids(page)) == N_R and page.locator('#l-count').inner_text() == '', f'{tag} filters cleared')
            # Search: English publisher names, Arabic with letter variants (a bare alef finds «الإمارات»).
            word, must = ('الامارات', 'pwc-uae-ai-jobs-barometer-2026') if rtl else ('Deloitte', 'deloitte-state-of-ai-enterprise-2026')
            page.fill('#lq', word)
            ids = visible_ids(page)
            check(must in ids and 1 <= len(ids) < N_R, f'{tag} search {word!r} shows {len(ids)} (must include {must})')
            badge = page.locator('.l-tab [data-count="reports"]').inner_text()
            check(badge == str(len(ids)), f'{tag} reports badge during search {badge!r} vs {len(ids)} shown')
            page.fill('#lq', 'zzqqxxyy')
            where = page.evaluate("(e => [e.hidden, e.closest('[data-panel]') && e.closest('[data-panel]').id, !!e.previousElementSibling && e.previousElementSibling.classList.contains('r-selects')])(document.getElementById('l-empty'))")
            check(where == [False, 'reports', True] and not visible_ids(page), f'{tag} "No matches" under the report menus: {where}')
            page.press('#lq', 'Escape')
            check(len(visible_ids(page)) == N_R, f'{tag} Escape clears the search')
            # Open a card: its findings, the links to the publisher's own page (a new tab, no referrer), the address bar.
            rid = REPORTS[0]['id']
            page.click(f'[id="report/{rid}"] > summary')
            page.wait_for_timeout(50)  # the address bar follows the toggle event
            check(is_open(page, f'report/{rid}') and page.evaluate('location.hash') == f'#report/{rid}', f'{tag} opening a report')
            lis = page.locator(f'[id="report/{rid}"] .it-list[data-lang="{lang}"] li').count()
            check(lis == len(REPORTS[0][f'findings_{lang}']), f'{tag} findings shown {lis}')
            links = page.evaluate("[...document.querySelectorAll('#reports a.r-link')].map(a => [a.href, a.target, a.rel])")
            bad = [l for l in links if not (l[0].startswith('https://') and l[1] == '_blank' and l[2] == 'noopener noreferrer' and on_domain(l[0]))]
            check(len(links) >= N_R and not bad, f'{tag} report links {bad[:2]}')
            check(overflow(page) <= 0, f'{tag} overflow with a report open {overflow(page)}px')
            # Deep links: a fresh page, and a card the current filters hide (they are cleared so it shows).
            last = REPORTS[-1]['id']
            page.goto(f'{URL}#report/{last}')
            page.wait_for_timeout(100)
            check(page.evaluate('document.documentElement.dataset.ltab') == 'reports' and is_open(page, f'report/{last}')
                  and in_view(page, f'report/{last}'), f'{tag} deep link to a report')
            page.click('#reports .fchip[data-filter="gcc"]')
            hidden = next(r['id'] for r in REPORTS if learn.report_group(r) != 'gcc' and r['id'] != last)
            page.evaluate(f"location.hash = '#report/{hidden}'")
            page.wait_for_timeout(100)
            check(is_open(page, f'report/{hidden}') and in_view(page, f'report/{hidden}') and len(visible_ids(page)) == N_R,
                  f'{tag} deep link to a filtered-out report')
            # The language button turns the menus into the other language.
            page.click('#lang')
            other = page.evaluate("document.querySelector('#r-year option').textContent")
            check(other == ('All years' if rtl else 'كل السنوات'), f'{tag} year menu after the language button {other!r}')
            page.click('#lang')
            check(not errors, f'{tag} console errors {errors[:3]}')
            check(not foreign, f'{tag} requests to other hosts {foreign[:3]}')
            ctx.close()
    # No horizontal scroll from 320 to 1920 px, in both languages, with the report with the longest title open.
    longest = max(REPORTS, key=lambda r: len(r['title_en']) + len(r['publisher']))['id']
    for lang in ('en', 'ar'):
        for width in (320, 375, 414, 768, 1024, 1280, 1440, 1920):
            tag = f'[reports {lang} {width}px]'
            ctx = browser.new_context(viewport={'width': width, 'height': 900})
            page = ctx.new_page()
            foreign = []
            page.on('request', lambda r: foreign.append(r.url) if not (r.url.startswith(ORIGIN) or r.url.startswith(('data:', 'blob:'))) else None)
            page.goto(URL + ('?lang=ar' if lang == 'ar' else '') + f'#report/{longest}')
            page.wait_for_timeout(80)
            check(overflow(page) <= 0, f'{tag} horizontal overflow {overflow(page)}px')
            wide = page.evaluate("""[...document.querySelectorAll('#reports .l-item, #reports .r-selects, #reports .l-filter, .l-tabs, .l-tab')].filter(e => {
                const r = e.getBoundingClientRect(); return r.width && (r.left < -1 || r.right > innerWidth + 1); }).map(e => e.id || e.className)""")
            check(not wide, f'{tag} parts outside the screen {wide[:3]}')
            tabs = page.evaluate("(n => n.scrollWidth - n.clientWidth)(document.querySelector('.l-tabs'))")
            check(tabs <= 0, f'{tag} tabs need {tabs}px more')
            check(not foreign, f'{tag} requests to other hosts {foreign[:3]}')
            ctx.close()

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
