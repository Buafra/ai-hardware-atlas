"""Browser test for the news search: the #news-q field in AI news and #uae-q in UAE AI. Not collected by
`unittest discover` (no test_ prefix).

    python scripts/build.py
    python tests/e2e_news_search.py [http://127.0.0.1:8791/] [--shots DIR]

Without a URL it serves dist/ itself (python -m http.server on a free port) and stops it at the end.
Needs Playwright: pip install playwright && python -m playwright install chromium

data/news.json changes twice a day, so no word or count is fixed here: every query is picked from the headlines on the
page, and the expected results come from a Python copy of the matching rules (normText in web/app.js), applied to what
each card shows (headline, summary, publisher). In English and Arabic at 375 and 1280 px, for #news and #uae:
- No search: the full list in steps (30 in #news, 8 in #uae), the build's count line, no (x), the translated label,
  placeholder and (x) name (in Arabic the English placeholder is invisible until app.js has translated it). One
  character shows the (x) but starts no search, and moves nothing on the page.
- A word: exactly the matching cards, in order, no day heading without a card, the count "Results: …" in the page
  language, the region chips counting the matches; Global and UAE give the intersection; a word with no match in the
  chosen region says so; "Show more" pages through the matches only; the key facts of #uae always show.
- Arabic: a headline word written with أ/إ/آ/ة/ى is found from its plain spelling (and from its own).
- No match: the message (never the query) takes the count line's place, as in the app: no "No results" line above it,
  "Times in UAE time" hidden, the count (the live region) holding the message and the box's copy hidden from screen
  readers, so it is in the accessibility tree once. "Clear search" brings the list back and focuses the field from a
  mouse or the keyboard; Escape empties the field and keeps the focus there.
- The (x): pressing it never takes the focus out of the field (no blur); from the keyboard it gives the focus back.
- The URL: ?nq= / ?uq= without changing the view; reload, Back and Forward restore it; a #news/global link keeps it; a
  link with only ?nq= (no hash) opens AI news and writes #news once the field is emptied; the hardware Reset keeps
  both searches; switching the language filters the other list with the same query.
- Wide screens: typing after scrolling far down the list brings the top of the results into view.
- Touch (375 px, coarse pointer), #news and #uae: a 16px field, a tap on the (x) keeps the focus in the field (no
  blur, so the keyboard stays open), Enter closes the keyboard, a tap on "Clear search" puts the focus on the list's
  heading (not the field, which would open the keyboard, and not the page, which would lose a screen reader's place).
- Without JavaScript the field is hidden and every headline shows; a page without the news or UAE view has no errors.
- No horizontal page scroll, no console errors and no requests to other hosts.
With --shots DIR it saves search-{news|uae}-{en|ar}-{375|1280}.png (a search with results) and the same names with
-empty (a search without results) for the owner.
"""
import re
import socket
import subprocess
import sys
import time
import unicodedata
import urllib.request
from pathlib import Path
from urllib.parse import urlparse, parse_qs, quote
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / 'dist'
ARGS = sys.argv[1:]
SHOTS = Path(ARGS[ARGS.index('--shots') + 1]) if '--shots' in ARGS else None
URL = next((a for a in ARGS if a.startswith('http')), None)
STEP = {'news': 30, 'uae': 8}
FIELD = {'news': 'nq', 'uae': 'uq'}
TEXT = {
    'en': {'label': 'Search', 'ph': 'Search news…', 'clear': 'Clear search', 'results': 'Results: {m}', 'paged': 'Results: {m} · showing {n}',
           'none': 'No results', 'nomatch': 'No matches. Try another word or clear the search.',
           'region': 'No headlines in this region match this search. Choose All to search every region.',
           'showing': 'Showing {n} of {m}', 'uae': '{m} · times in UAE time'},
    'ar': {'label': 'بحث', 'ph': 'ابحث في الأخبار…', 'clear': 'مسح البحث', 'results': 'النتائج: {m}', 'paged': 'النتائج: {m} · المعروض منها {n}',
           'none': 'لا توجد نتائج', 'nomatch': 'لا توجد نتائج. جرّب كلمة أخرى أو امسح البحث.',
           'region': 'لا توجد عناوين في هذا النطاق تطابق هذا البحث. اختر «الكل» للبحث في كل النطاقات.',
           'showing': 'المعروض {n} من أصل {m}', 'uae': '{m} · الأوقات بتوقيت الإمارات'},
}
# Names a visitor would type, tried first for the owner's screenshots (in either language the Arabic list keeps company
# names in Latin letters in translated headlines).
SHOWCASE = {'news': ['openai', 'nvidia', 'google', 'anthropic', 'microsoft', 'إنفيديا', 'جوجل'],
            'uae': ['g42', 'microsoft', 'openai', 'nvidia', 'falcon', 'abu dhabi', 'أبوظبي', 'دبي', 'dubai']}
NONSENSE = 'qzxqzj'
failures, checks, notes = [], 0, []

def check(ok, msg):
    global checks
    checks += 1
    if not ok:
        failures.append(msg)
        print('FAIL', msg)
    return ok

def note(msg):
    notes.append(msg)
    print('note:', msg)

# ---------- the matching rules, as in web/app.js (normText, searchWords, matchesWords) ----------
FOLD = {'\u0671': '\u0627', '\u0649': '\u064A', '\u06CC': '\u064A', '\u0629': '\u0647', '\u06A9': '\u0643', '\u06AF': '\u0643',
        '\u06A4': '\u0641', '\u067E': '\u0628', '\u0686': '\u062C'}

def norm(s):
    out, space = [], False
    for ch in unicodedata.normalize('NFKD', s or '').lower():
        cat = unicodedata.category(ch)
        if cat[0] == 'M' or cat == 'Cf' or ch == '\u0640':
            continue
        ch = FOLD.get(ch, ch)
        if '\u0660' <= ch <= '\u0669':
            ch = str(ord(ch) - 0x660)
        elif '\u06F0' <= ch <= '\u06F9':
            ch = str(ord(ch) - 0x6f0)
        if unicodedata.category(ch)[0] in 'LN':
            if space and out:
                out.append(' ')
            out.append(ch)
            space = False
        else:
            space = True
    return ''.join(out)

def words(q):
    n = norm(q[:100])
    return [] if len(n) < 2 else n.split(' ')

def matches(card, ws):
    return all(w in card['norm'] or w in card['compact'] for w in ws)

def count_label(n, lang):
    if lang != 'ar':
        return f'{n} {"headline" if n == 1 else "headlines"}'
    if n == 1:
        return 'عنوان واحد'
    if n == 2:
        return 'عنوانان'
    r = n % 100
    return f'{n} {"عناوين" if 3 <= r <= 10 else "عنواناً" if 11 <= r <= 99 else "عنوان"}'

# ---------- page helpers ----------
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

CARDS = r'''(view) => {
  const lang = document.documentElement.lang, list = document.querySelector(`#${view} .nlist[data-lang="${lang}"]`);
  const text = (li, s) => { const e = li.querySelector(s); return e ? e.textContent : ''; };
  return list ? [...list.querySelectorAll('li.nitem')].map(li => ({title: text(li, '.n-title'), sum: text(li, '.n-sum'),
    src: text(li, 'a.n-src'), region: li.dataset.region || ''})) : [];
}'''

STATE = r'''(view) => {
  const $ = id => document.getElementById(id), vis = el => !!el && !el.hidden && el.getClientRects().length > 0;
  const lang = document.documentElement.lang, root = $(view), list = root.querySelector(`.nlist[data-lang="${lang}"]`);
  const lis = list ? [...list.querySelectorAll('li.nitem')] : [], days = list ? [...list.querySelectorAll('.nday')] : [];
  const input = $(view + '-q'), x = $(view + '-q-clear'), first = lis.find(vis), col = root.querySelector('.main-col');
  const rect = el => { const r = el.getBoundingClientRect(); return [r.left, r.top, r.width, r.height].map(v => Math.round(v * 10) / 10); };
  const count = $(view === 'news' ? 'news-count' : 'uae-count'), act = document.activeElement;
  const head = view === 'news' ? root.querySelector('.main-col > h2') : $('uae-news-h');
  return {lang, dir: document.documentElement.dir, route: document.documentElement.dataset.route, q: input.value,
    clear: vis(x), clearLabel: x.getAttribute('aria-label'), placeholder: input.placeholder, label: document.querySelector(`label[for="${view}-q"]`).textContent,
    count: count.innerText.trim(), countShown: vis(count) && count.getBoundingClientRect().width > 1,
    beside: view === 'news' ? vis(count.nextElementSibling) : null,
    emptyMsgAria: $(view + '-empty-msg').getAttribute('aria-hidden'),
    focusHead: !!head && act === head, activeTag: act ? act.tagName : '', events: window.__qev ? [...window.__qev] : null,
    shown: lis.map((li, i) => vis(li) ? i : -1).filter(i => i >= 0), cards: lis.length,
    emptyDays: days.filter(d => vis(d) && !d.querySelector('li.nitem:not([hidden])')).length,
    hiddenDaysWithCards: days.filter(d => !vis(d) && [...d.querySelectorAll('li.nitem')].some(li => !li.hidden)).length,
    more: vis($(view + '-more')), empty: vis($(view + '-empty')), emptyMsg: $(view + '-empty-msg').textContent,
    emptyBdi: !!$(view + '-empty').querySelector('bdi'),
    chips: view === 'news' ? Object.fromEntries([...root.querySelectorAll('[data-region-chip]')].map(b => [b.dataset.regionChip, +b.querySelector(`.n [data-lang="${lang}"]`).textContent])) : null,
    pressed: view === 'news' ? [...root.querySelectorAll('[data-region-chip][aria-pressed="true"]')].map(b => b.dataset.regionChip) : null,
    facts: [...root.querySelectorAll('.uae-facts .fact')].filter(vis).length, factsAll: root.querySelectorAll('.uae-facts .fact').length,
    search: location.search, hash: location.hash, active: document.activeElement ? document.activeElement.id : '',
    inputRect: rect(input), firstTop: first ? Math.round(first.getBoundingClientRect().top * 10) / 10 : null,
    colTop: col.getBoundingClientRect().top, barBottom: document.querySelector('.top').getBoundingClientRect().bottom,
    fontSize: getComputedStyle(input).fontSize, coarse: matchMedia('(pointer: coarse)').matches,
    scrollX: document.documentElement.scrollWidth - document.documentElement.clientWidth};
}'''

def cards(page, view):
    out = page.evaluate(CARDS, view)
    for c in out:
        src = re.sub(r'^\s*(?:Source|المصدر):\s*', '', c['src']).replace('↗', '')
        c['norm'] = norm(' '.join((c['title'], c['sum'], src)))
        c['compact'] = c['norm'].replace(' ', '')
    return out

def state(page, view):
    return page.evaluate(STATE, view)

def settle(page, ms=120):
    page.wait_for_timeout(ms)

def waited(page, expr, ms=5000):
    try:
        page.wait_for_function(expr, timeout=ms)
        return True
    except PlaywrightTimeout:
        return False

def qs(s):
    return parse_qs(s['search'].lstrip('?'))

def hits(cs, q, region=''):
    ws = words(q)
    return [i for i, c in enumerate(cs) if (not ws or matches(c, ws)) and (not region or region in c['region'].split())]

def region_counts(cs, q):
    ws = words(q)
    out = {'': 0, 'global': 0, 'uae': 0}
    for c in cs:
        if not ws or matches(c, ws):
            out[''] += 1
            for r in c['region'].split():
                out[r] = out.get(r, 0) + 1
    return out

def count_text(view, lang, q, total, shown, in_region=False):
    L = TEXT[lang]
    if words(q):
        if not total:
            # As in the app, the no-match message takes the count line's place (the live region holds it for screen
            # readers, the box under the list shows it). "No results" only above a language without any headline.
            return L['region'] if in_region else L['nomatch']
        m = count_label(total, lang)
        return L['paged'].format(m=m, n=shown) if shown < total else L['results'].format(m=m)
    return L['showing'].format(n=shown, m=count_label(total, lang)) if view == 'news' else None

def pick(cs, view, lang, lo, hi, want=None, region_free=None):
    """A word from the headlines on the page with lo..hi matches (fewer than all cards). With `want`, only words that
    contain one of those raw letters (in the headline as written); with region_free, only words whose matches are all
    outside that region. Deterministic: the word nearest to the middle of the range, then alphabetical."""
    seen, best = set(), None
    for c in cs:
        for raw in re.findall(r'[^\W_]+', unicodedata.normalize('NFC', c['title'])):
            if want and not any(ch in raw for ch in want):
                continue
            w = norm(raw)
            if len(w) < 4 or ' ' in w or w.isdigit() or w in seen:
                continue
            seen.add(w)
            hs = [i for i, x in enumerate(cs) if matches(x, [w])]
            if not (lo <= len(hs) <= hi and len(hs) < len(cs)):
                continue
            if region_free and any(region_free in cs[i]['region'].split() for i in hs):
                continue
            key = (abs(len(hs) - (lo + hi) / 2), w)
            if best is None or key < best[0]:
                best = (key, raw, w, hs)
    return (best[1], best[2], best[3]) if best else (None, None, None)

def expect_list(s, cs, view, lang, q, region, limit, where):
    """The visible cards are the first `limit` matches (search and region), in order, with the count line to match."""
    hs = hits(cs, q, region)
    want = hs[:limit]
    ok = check(s['shown'] == want, f'{where}: shown {s["shown"][:12]}… ({len(s["shown"])}) want {want[:12]}… ({len(want)})')
    check(s['emptyDays'] == 0 and s['hiddenDaysWithCards'] == 0, f'{where}: day headings {s["emptyDays"]} empty, {s["hiddenDaysWithCards"]} hidden with cards')
    want_count = count_text(view, lang, q, len(hs), len(want), in_region=bool(region) and region_counts(cs, q)[''] > 0)
    if want_count is not None:
        check(s['count'] == want_count, f'{where}: count {s["count"]!r} want {want_count!r}')
    # No match: the count line is off the screen ("Times in UAE time" too) and the box shows the same message, hidden
    # from screen readers. Otherwise the count line is on the screen and the box hidden.
    none = bool(words(q)) and not hs
    check(s['countShown'] != none and (view != 'news' or s['beside'] != none) and s['empty'] == none,
          f'{where}: count line on screen {s["countShown"]}, Times in UAE time {s["beside"]}, no-match box {s["empty"]} (no match {none})')
    if none:
        check(s['emptyMsg'] == s['count'] and s['emptyMsgAria'] == 'true', f'{where}: box message {s["emptyMsg"]!r} (aria-hidden {s["emptyMsgAria"]}), count {s["count"]!r}')
    check(s['more'] == (len(want) < len(hs)), f'{where}: Show more {s["more"]} with {len(want)} of {len(hs)}')
    if view == 'news':
        rc = region_counts(cs, q)
        check(s['chips'] == rc, f'{where}: chip counts {s["chips"]} want {rc}')
    else:
        check(s['facts'] == s['factsAll'] > 0, f'{where}: key facts shown {s["facts"]} of {s["factsAll"]}')
    check(s['scrollX'] <= 0, f'{where}: horizontal scroll {s["scrollX"]}px')
    return ok, hs

def fill(page, view, q):
    page.fill(f'#{view}-q', q)
    settle(page)
    return state(page, view)

RECORD = r'''(view) => {
  const el = document.getElementById(view + '-q');
  if (!el.__rec) { el.__rec = true; ['focus', 'blur'].forEach(t => el.addEventListener(t, () => window.__qev.push(t))); }
  window.__qev = [];
}'''

def record(page, view):
    """From now on, state()['events'] lists the field's focus and blur events."""
    page.evaluate(RECORD, view)

def read_once(page, view, msg, none, where):
    """In the accessibility tree of the list column the message is there once (the count line), and "No results" never."""
    snap = page.locator(f'#{view} .main-col').aria_snapshot()
    values = [line.split(': ', 1)[1].strip().strip('"') for line in snap.splitlines() if ': ' in line]
    check(snap.count(msg) == 1, f'{where}: the message is {snap.count(msg)} times in the accessibility tree')
    check(none not in values, f'{where}: {none!r} in the accessibility tree')

def start(lang):
    return '?lang=ar' if lang == 'ar' else ''

def shot(page, view, lang, width, suffix=''):
    if not SHOTS:
        return
    page.evaluate('document.activeElement && document.activeElement.blur()')
    page.set_viewport_size({'width': width, 'height': 1000 if width < 640 else 900})
    page.evaluate('''(view) => { const top = document.querySelector('.top').getBoundingClientRect().height;
      const el = document.querySelector(`#${view} .split-layout`); window.scrollTo(0, el.getBoundingClientRect().top + scrollY - top - 12); }''', view)
    settle(page, 400)  # lazy images
    page.screenshot(path=str(SHOTS / f'search-{view}-{lang}-{width}{suffix}.png'))
    page.set_viewport_size({'width': width, 'height': 860})
    page.evaluate('window.scrollTo(0, 0)')

# ---------- the checks ----------
def view_checks(page, base, lang, width, view):
    L, key, step, where = TEXT[lang], FIELD[view], STEP[view], f'{lang} {width}px #{view}'
    other = 'ar' if lang == 'en' else 'en'
    page.goto(base + start(lang) + '#' + view)
    page.wait_for_load_state('load')
    settle(page, 400)
    cs = cards(page, view)
    if not check(len(cs) >= 3, f'{where}: only {len(cs)} headlines on the page'):
        return
    s = state(page, view)
    check(s['lang'] == lang and s['route'] == view, f'{where}: lang {s["lang"]} route {s["route"]}')
    check((s['label'], s['placeholder'], s['clearLabel']) == (L['label'], L['ph'], L['clear']), f'{where}: label/placeholder/(x) name {s["label"]!r} {s["placeholder"]!r} {s["clearLabel"]!r}')
    check(s['q'] == '' and not s['clear'] and not s['empty'], f'{where}: start q {s["q"]!r}, (x) {s["clear"]}, empty {s["empty"]}')
    if lang == 'ar':
        # Before app.js runs (the head script's i18n-wait), the English placeholder is invisible, like the English labels.
        ph = page.evaluate('''(id) => { const d = document.documentElement, f = document.getElementById(id), was = d.classList.contains('i18n-wait');
          d.classList.add('i18n-wait'); const c = getComputedStyle(f, '::placeholder').color; if (!was) d.classList.remove('i18n-wait');
          return [c, getComputedStyle(f, '::placeholder').color]; }''', f'{view}-q')
        check(ph[0] == 'rgba(0, 0, 0, 0)' and ph[1] != ph[0], f'{where}: placeholder colour while waiting for app.js {ph[0]}, after {ph[1]}')
    expect_list(s, cs, view, lang, '', '', step, f'{where} no search')
    if view == 'uae':
        check(s['count'] == L['uae'].format(m=count_label(len(cs), lang)), f'{where}: built count line {s["count"]!r}')
    built = s['count']

    # One character: the (x) shows, no search starts, nothing moves (the field keeps room for the (x)).
    s1 = fill(page, view, 'a')
    check(s1['clear'] and s1['count'] == built and s1['shown'] == s['shown'], f'{where} one letter: (x) {s1["clear"]}, count {s1["count"]!r}')
    check(s1['inputRect'] == s['inputRect'] and s1['firstTop'] == s['firstTop'], f'{where} one letter: field {s["inputRect"]}->{s1["inputRect"]}, list top {s["firstTop"]}->{s1["firstTop"]}')
    check(key not in qs(s1) or qs(s1)[key] == ['a'], f'{where} one letter: URL {s1["search"]}')
    # The (x) with the mouse: the field never loses the focus (no blur, then focus again).
    record(page, view)
    page.click(f'#{view}-q-clear')
    settle(page)
    s1 = state(page, view)
    check(s1['q'] == '' and not s1['clear'] and s1['active'] == f'{view}-q' and s1['count'] == built, f'{where} (x): q {s1["q"]!r}, (x) {s1["clear"]}, focus {s1["active"]!r}')
    check(s1['events'] == [], f'{where} (x): field events {s1["events"]}')
    check(key not in qs(s1) and s1['hash'] == '#' + view, f'{where} (x): URL {s1["search"]}{s1["hash"]}')
    # The (x) from the keyboard: Tab reaches it, Enter empties the field and gives the focus back to it.
    fill(page, view, 'ab')
    page.focus(f'#{view}-q')
    page.keyboard.press('Tab')
    on_x = state(page, view)['active'] == f'{view}-q-clear'
    page.keyboard.press('Enter')
    settle(page)
    s1 = state(page, view)
    check(on_x and s1['q'] == '' and not s1['clear'] and s1['active'] == f'{view}-q' and s1['count'] == built, f'{where} (x) from the keyboard: on (x) {on_x}, q {s1["q"]!r}, focus {s1["active"]!r}')

    # A word with a few matches (all on the first page): exactly those cards, the URL keeps it, the view stays.
    raw, w, hs = pick(cs, view, lang, 2, min(step, 12))
    if check(w is not None, f'{where}: no headline word with 2-{min(step, 12)} matches'):
        s2 = fill(page, view, raw)
        expect_list(s2, cs, view, lang, raw, '', step, f'{where} {raw!r}')
        check(s2['clear'] and not s2['empty'] and qs(s2).get(key) == [raw] and s2['hash'] == '#' + view and s2['route'] == view,
              f'{where} {raw!r}: (x) {s2["clear"]}, empty {s2["empty"]}, URL {s2["search"]}{s2["hash"]}')
        if lang == 'en':
            s3 = fill(page, view, raw.upper())
            check(s3['shown'] == s2['shown'], f'{where} {raw.upper()!r}: case changes the results')
        # Escape empties the field and keeps the focus; a second Escape does nothing.
        page.focus(f'#{view}-q')
        page.keyboard.press('Escape')
        settle(page)
        s3 = state(page, view)
        check(s3['q'] == '' and s3['active'] == f'{view}-q' and s3['count'] == built and key not in qs(s3), f'{where} Escape: q {s3["q"]!r}, focus {s3["active"]!r}, count {s3["count"]!r}')
        page.keyboard.press('Escape')
        check(state(page, view)['q'] == '', f'{where} second Escape')

    # Arabic: a headline word written with hamza on alef, and one with ta marbuta or alef maqsura, is found from its
    # plain spelling (and from its own).
    if lang == 'ar':
        for letters in ('أإآ', 'ةى'):
            raw, w, hs = pick(cs, view, lang, 1, step, want=letters)
            if raw is None:
                note(f'{where}: no headline word with one of {letters} and 1-{step} matches')
                continue
            check(w != raw, f'{where}: {raw!r} has no variant spelling')
            s3 = fill(page, view, w)
            expect_list(s3, cs, view, lang, w, '', step, f'{where} plain {w!r} for {raw!r}')
            check(hs and all(i in s3['shown'] for i in hs), f'{where} plain {w!r}: cards with {raw!r} missing')
            s4 = fill(page, view, raw)
            check(s4['shown'] == s3['shown'], f'{where} {raw!r} as written: {len(s4["shown"])} cards, plain {len(s3["shown"])}')

    # Many matches: "Show more" pages through the matches only.
    raw, w, hs = pick(cs, view, lang, step + 1, len(cs) - 1)
    if raw is None:
        note(f'{where}: no headline word with more than {step} matches; "Show more" with a search not checked')
    else:
        s3 = fill(page, view, raw)
        expect_list(s3, cs, view, lang, raw, '', step, f'{where} many {raw!r}')
        page.click(f'#{view}-more')
        settle(page)
        expect_list(state(page, view), cs, view, lang, raw, '', 2 * step, f'{where} many {raw!r} + Show more')
        s3 = fill(page, view, raw + ' ')  # a trailing space is the same search: paging stays
        check(len(s3['shown']) == min(2 * step, len(hs)) and qs(s3).get(key) == [raw], f'{where} trailing space: {len(s3["shown"])} shown, URL {s3["search"]}')

    # Region and search together (AI news): the intersection, chips counting the matches; a region without any.
    if view == 'news':
        raw, w, hs = pick(cs, view, lang, 2, len(cs) - 1, region_free='uae')
        if raw is None:
            note(f'{where}: every word matches a UAE headline; region checks skipped')
        else:
            fill(page, view, raw)
            page.click('#news [data-region-chip="global"]')
            settle(page)
            s3 = state(page, view)
            expect_list(s3, cs, view, lang, raw, 'global', step, f'{where} {raw!r} + Global')
            check(s3['pressed'] == ['global'] and qs(s3).get('region') == ['global'] and qs(s3).get('nq') == [raw], f'{where} {raw!r} + Global: pressed {s3["pressed"]}, URL {s3["search"]}')
            page.click('#news [data-region-chip="uae"]')
            settle(page)
            s3 = state(page, view)
            expect_list(s3, cs, view, lang, raw, 'uae', step, f'{where} {raw!r} + UAE')
            check(s3['shown'] == [] and s3['empty'] and s3['emptyMsg'] == L['region'] and s3['count'] == L['region'] and not s3['countShown'],
                  f'{where} {raw!r} + UAE: shown {len(s3["shown"])}, empty {s3["empty"]}, message {s3["emptyMsg"]!r}, count {s3["count"]!r} on screen {s3["countShown"]}')
            read_once(page, view, L['region'], L['none'], f'{where} {raw!r} + UAE')
            check(s3['chips'] == region_counts(cs, raw), f'{where} {raw!r} + UAE: chips {s3["chips"]}')
            # A #news/global link keeps the search.
            page.evaluate("location.hash = 'news/global'")
            page.wait_for_function("location.hash === '#news'")
            settle(page)
            s3 = state(page, view)
            check(qs(s3).get('region') == ['global'] and qs(s3).get('nq') == [raw] and s3['q'] == raw, f'{where} #news/global link: URL {s3["search"]}, field {s3["q"]!r}')
            expect_list(s3, cs, view, lang, raw, 'global', step, f'{where} #news/global link')
            page.click('#news [data-region-chip=""]')
            settle(page)

    # No match: the message (never the query), "Clear search" from the mouse and from the keyboard.
    check(not hits(cs, NONSENSE), f'{where}: {NONSENSE!r} matches a headline')
    s3 = fill(page, view, NONSENSE)
    expect_list(s3, cs, view, lang, NONSENSE, '', step, f'{where} no match')
    check(s3['shown'] == [] and s3['empty'] and s3['emptyMsg'] == L['nomatch'] and s3['count'] == L['nomatch'] and not s3['countShown'] and not s3['more'],
          f'{where} no match: shown {len(s3["shown"])}, empty {s3["empty"]}, message {s3["emptyMsg"]!r}, count {s3["count"]!r} on screen {s3["countShown"]}, more {s3["more"]}')
    read_once(page, view, L['nomatch'], L['none'], f'{where} no match')
    check(NONSENSE not in s3['emptyMsg'] and not s3['emptyBdi'], f'{where} no match: the message repeats the query')
    check(s3['emptyDays'] == 0 and s3['hiddenDaysWithCards'] == 0 and s3['scrollX'] <= 0, f'{where} no match: days {s3["emptyDays"]}, scroll {s3["scrollX"]}')
    if view == 'uae':
        check(s3['facts'] == s3['factsAll'] > 0, f'{where} no match: key facts {s3["facts"]} of {s3["factsAll"]}')
    btn = page.locator(f'#{view}-empty button')
    check(btn.text_content() == L['clear'], f'{where}: Clear search label {btn.text_content()!r}')
    btn.click()
    settle(page)
    s3 = state(page, view)
    check(s3['q'] == '' and s3['active'] == f'{view}-q' and not s3['empty'] and s3['count'] == built and key not in qs(s3) and s3['hash'] == '#' + view,
          f'{where} Clear search (mouse): q {s3["q"]!r}, focus {s3["active"]!r}, empty {s3["empty"]}, URL {s3["search"]}{s3["hash"]}')
    expect_list(s3, cs, view, lang, '', '', step, f'{where} after Clear search')
    fill(page, view, NONSENSE)
    page.focus(f'#{view}-empty button')
    page.keyboard.press('Enter')
    settle(page)
    s3 = state(page, view)
    check(s3['q'] == '' and s3['active'] == f'{view}-q', f'{where} Clear search (keyboard): q {s3["q"]!r}, focus {s3["active"]!r}')

    # Reload, Back and Forward restore the search; the other view's links keep it in the URL.
    raw, w, hs = pick(cs, view, lang, 2, len(cs) - 1)
    if raw:
        nav_other = 'uae' if view == 'news' else 'news'
        fill(page, view, raw)
        page.reload()
        page.wait_for_load_state('load')
        settle(page, 300)
        s3 = state(page, view)
        check(s3['q'] == raw and s3['route'] == view, f'{where} reload: field {s3["q"]!r}, view {s3["route"]}')
        expect_list(s3, cs, view, lang, raw, '', step, f'{where} reload')
        page.click(f'.nav a[data-nav="{nav_other}"]')
        page.wait_for_function(f"location.hash === '#{nav_other}'")
        check(parse_qs(urlparse(page.url).query).get(key) == [raw], f'{where} nav to #{nav_other}: URL {page.url}')
        page.click(f'.nav a[data-nav="{view}"]')
        page.wait_for_function(f"location.hash === '#{view}'")
        settle(page)
        fill(page, view, '')
        # The emptied search leaves this entry's URL (replaceState) before Back is pressed.
        check(waited(page, f"!new URLSearchParams(location.search).has('{key}') && location.hash === '#{view}'"), f'{where}: emptying the field left {page.url}')
        page.go_back()
        page.wait_for_function(f"location.hash === '#{nav_other}'")
        settle(page)
        check(page.input_value(f'#{view}-q') == raw, f'{where} Back: field {page.input_value(f"#{view}-q")!r}')
        page.go_forward()
        page.wait_for_function(f"location.hash === '#{view}'")
        settle(page)
        s3 = state(page, view)
        check(s3['q'] == '', f'{where} Forward: field {s3["q"]!r}')
        expect_list(s3, cs, view, lang, '', '', step, f'{where} Forward')

        # The language switch filters the other list with the same search, and switches the labels.
        fill(page, view, raw)
        page.click('#lang')
        settle(page, 200)
        cs2 = cards(page, view)
        s3 = state(page, view)
        check((s3['label'], s3['placeholder'], s3['clearLabel']) == (TEXT[other]['label'], TEXT[other]['ph'], TEXT[other]['clear']), f'{where} → {other}: labels {s3["label"]!r} {s3["placeholder"]!r}')
        expect_list(s3, cs2, view, other, raw, '', step, f'{where} → {other} {raw!r}')
        check(s3['empty'] == (not hits(cs2, raw)), f'{where} → {other} {raw!r}: empty {s3["empty"]}')
        if s3['empty']:
            check(s3['emptyMsg'] == TEXT[other]['nomatch'], f'{where} → {other}: message {s3["emptyMsg"]!r}')
        page.click('#lang')
        settle(page, 200)
        expect_list(state(page, view), cs, view, lang, raw, '', step, f'{where} back to {lang}')
        fill(page, view, '')

    # A link with only the search (no hash) opens the view; emptying the field then writes the view's hash.
    raw, w, hs = pick(cs, view, lang, 2, len(cs) - 1)
    if raw:
        page.goto(base + '?' + ('lang=ar&' if lang == 'ar' else '') + f'{key}={quote(raw)}')
        page.wait_for_load_state('load')
        settle(page, 400)
        s3 = state(page, view)
        check(s3['route'] == view and s3['hash'] == '' and s3['q'] == raw, f'{where} ?{key}= without hash: view {s3["route"]}, hash {s3["hash"]!r}, field {s3["q"]!r}')
        expect_list(s3, cs, view, lang, raw, '', step, f'{where} ?{key}= without hash')
        page.click(f'#{view}-q-clear')
        settle(page)
        s3 = state(page, view)
        check(s3['hash'] == '#' + view and key not in qs(s3) and s3['route'] == view, f'{where} cleared after ?{key}=: URL {s3["search"]}{s3["hash"]}')

    # Wide screens: after scrolling far down the list, typing brings the top of the results into view.
    if width >= 1100 and len(cs) > 10:
        raw, w, hs = pick(cs, view, lang, 2, len(cs) - 1)
        page.goto(base + start(lang) + '#' + view)
        settle(page, 400)
        page.evaluate(f"document.querySelector('#{view} .nlist li.nitem:nth-child(1)') && window.scrollTo(0, document.querySelector('#{view} .main-col').getBoundingClientRect().bottom + scrollY - innerHeight - 50)")
        settle(page, 200)
        s3 = state(page, view)
        if s3['colTop'] < s3['barBottom']:
            s3 = fill(page, view, raw)
            check(s3['barBottom'] - 1 <= s3['colTop'] <= 430, f'{where} typed after scrolling: list top at {s3["colTop"]:.0f}, header ends {s3["barBottom"]:.0f}')
            fill(page, view, '')
        else:
            note(f'{where}: list too short to scroll past its top')

def touch_checks(browser, base, lang):
    """A phone (coarse pointer), #news and #uae: 16px text in the field; a tap on the (x) keeps the focus in the field
    (no blur, so the keyboard stays open); Enter closes the keyboard; a tap on "Clear search" puts the focus on the
    list's heading, not on the field (the keyboard would open) and not on the page (a screen reader would lose its place)."""
    ctx = browser.new_context(viewport={'width': 375, 'height': 812}, is_mobile=True, has_touch=True, device_scale_factor=2)
    page = ctx.new_page()
    for view in ('news', 'uae'):
        page.goto(base + start(lang) + '#' + view)
        settle(page, 400)
        s = state(page, view)
        where = f'{lang} touch #{view}'
        if not s['coarse']:
            note(f'{where}: this browser does not report a coarse pointer; touch checks skipped')
            break
        check(s['fontSize'] == '16px', f'{where}: field font size {s["fontSize"]}')
        page.tap(f'#{view}-q')
        page.keyboard.type('ab')
        settle(page)
        record(page, view)
        page.tap(f'#{view}-q-clear')
        settle(page)
        s = state(page, view)
        check(s['q'] == '' and s['active'] == f'{view}-q' and s['events'] == [], f'{where}: tap on (x): q {s["q"]!r}, focus {s["active"]!r}, field events {s["events"]}')
        page.keyboard.type('ab')
        page.keyboard.press('Enter')
        settle(page)
        check(state(page, view)['active'] != f'{view}-q', f'{where}: Enter left the focus in the field')
        page.fill(f'#{view}-q', NONSENSE)
        settle(page)
        page.tap(f'#{view}-empty button')
        settle(page)
        s = state(page, view)
        check(s['q'] == '' and s['focusHead'] and not s['empty'] and s['countShown'],
              f'{where}: tap on Clear search: q {s["q"]!r}, focus {s["activeTag"]} #{s["active"]} (list heading {s["focusHead"]}), empty {s["empty"]}')
    ctx.close()

def page_checks(browser, base, origin, lang, width):
    ctx = browser.new_context(viewport={'width': width, 'height': 860})
    page = ctx.new_page()
    errors, foreign = [], []
    page.on('console', lambda m: errors.append(m.text) if m.type == 'error' else None)
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.on('request', lambda r: foreign.append(r.url) if not r.url.startswith(origin) and not r.url.startswith(('data:', 'blob:')) else None)
    for view in ('news', 'uae'):
        view_checks(page, base, lang, width, view)
    # The hardware Reset keeps both news searches.
    page.goto(base + '?' + ('lang=ar&' if lang == 'ar' else '') + 'nq=openai&uq=falcon&vendor=AMD#hardware')
    settle(page, 300)
    page.click('#reset')
    settle(page)
    q = parse_qs(urlparse(page.url).query)
    check(q.get('nq') == ['openai'] and q.get('uq') == ['falcon'] and 'vendor' not in q, f'{lang} {width}px: hardware Reset URL {page.url}')
    check(page.input_value('#news-q') == 'openai' and page.input_value('#uae-q') == 'falcon', f'{lang} {width}px: fields after Reset')
    if SHOTS:
        for view in ('news', 'uae'):
            page.goto(base + start(lang) + '#' + view)
            settle(page, 300)
            cs = cards(page, view)
            q = next((w for w in SHOWCASE[view] if 2 <= len(hits(cs, w)) < len(cs)), None) or pick(cs, view, lang, 2, 12)[0]
            fill(page, view, q)
            shot(page, view, lang, width)
            fill(page, view, NONSENSE)
            shot(page, view, lang, width, '-empty')
            fill(page, view, '')
    check(not errors, f'{lang} {width}px: console errors {errors[:3]}')
    check(not foreign, f'{lang} {width}px: requests to other hosts {foreign[:3]}')
    ctx.close()

def fallback_checks(browser, base):
    # Without JavaScript: no field, every headline shown.
    ctx = browser.new_context(viewport={'width': 1280, 'height': 860}, java_script_enabled=False)
    page = ctx.new_page()
    page.goto(base)
    vis = page.locator('#news-q').is_visible() or page.locator('#uae-q').is_visible()
    check(not vis, 'no JavaScript: a search field is visible')
    n_all = page.locator('#news .nlist[data-lang="en"] li.nitem').count()
    n_vis = page.locator('#news .nlist[data-lang="en"] li.nitem >> visible=true').count()
    check(n_all > 0 and n_vis == n_all, f'no JavaScript: {n_vis} of {n_all} English headlines visible')
    check(page.locator('.n-empty >> visible=true').count() == 0, 'no JavaScript: a no-match message is visible')
    ctx.close()
    # A build without the news or the UAE view (no sources, no UAE data): app.js starts without errors.
    html = (DIST / 'index.html').read_text(encoding='utf-8')
    news, uae, contact = (html.index(f'<section id="{v}" class="view') for v in ('news', 'uae', 'contact'))
    for name, cut in (('no news and no UAE view', html[:news] + html[contact:]), ('no UAE view', html[:uae] + html[contact:])):
        ctx = browser.new_context(viewport={'width': 1280, 'height': 860})
        page = ctx.new_page()
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.on('console', lambda m: errors.append(m.text) if m.type == 'error' else None)
        page.route(lambda u: urlparse(u).path in ('/', '/index.html'), lambda r: r.fulfill(status=200, content_type='text/html; charset=utf-8', body=cut))
        for path in ('?nq=openai&uq=falcon#hardware', '?nq=openai', '?uq=falcon', '#news'):
            page.goto(base + path)
            settle(page, 300)
        page.goto(base + '#hardware')
        settle(page, 300)
        page.fill('#search', 'h200')
        settle(page)
        check(not errors, f'{name}: errors {errors[:3]}')
        check(page.locator('#products .product >> visible=true').count() > 0, f'{name}: the hardware search stopped working')
        if name == 'no UAE view':
            page.goto(base + '#news')
            settle(page, 300)
            page.fill('#news-q', NONSENSE)
            settle(page)
            check(page.locator('#news-empty').is_visible() and not errors, f'{name}: the news search stopped working {errors[:3]}')
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
                    page_checks(browser, base, origin, lang, width)
                touch_checks(browser, base, lang)
            fallback_checks(browser, base)
            browser.close()
    finally:
        if proc:
            proc.kill()
    print(f'{checks - len(failures)}/{checks} checks passed' + (f', {len(notes)} notes' if notes else ''))
    if failures:
        sys.exit(1)
    print('OK')

if __name__ == '__main__':
    main()
