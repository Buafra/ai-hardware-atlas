"""Weekly pages (owner request, Oct 2026): "AI this week" and "UAE AI this week", one permanent page per ISO week (UAE
time) in English and in Arabic, and weekly/index.html listing the weeks. Rule-based, no AI and no network: every vetted
story of the week, from the current AI news list and the news archive (the stories the site itself shows, see
build.news_items and news_archive.shown), grouped by day (newest first) and then by topic (scripts/topics.py, the rule
behind the topic images), each with the summary the site shows and its link to the original article.

Paths (page_path): weekly/YYYY-wNN.html and weekly/uae-YYYY-wNN.html in English; weekly/ar-YYYY-wNN.html and
weekly/ar-uae-YYYY-wNN.html in Arabic (the site has no /ar/ folder: AR_PREFIX is the one place to change that). A page
exists for every week with at least one story of its kind; its other-language page exists too and says so when that
language has no story. The pages are static: no script, one same-origin stylesheet (weekly/weekly.css, from
web/weekly.css), the site's own icons and share preview, Open Graph and X card tags for sharing. Nothing is loaded from
another host. The "Updated" line belongs to AI news only, so these pages have none.
"""
import html
import re
import shutil
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import topics

ROOT = Path(__file__).resolve().parents[1]
SITE = 'https://cipherlacuna.ae/'
DIR = 'weekly'
AR_PREFIX = 'ar-'   # Arabic pages: weekly/ar-<name>.html
CSS = ROOT / 'web' / 'weekly.css'
UAE_TZ = timezone(timedelta(hours=4))
KINDS = ('all', 'uae')
TITLE = {('all', 'en'): 'AI this week', ('all', 'ar'): 'الذكاء الاصطناعي هذا الأسبوع',
         ('uae', 'en'): 'UAE AI this week', ('uae', 'ar'): 'الذكاء الاصطناعي في الإمارات هذا الأسبوع'}
REVIEW = {'en': 'Week in review', 'ar': 'حصاد الأسبوع'}
ALL_WEEKS = {'en': 'All weeks', 'ar': 'كل الأسابيع'}
WEEK = {'en': 'Week {w}', 'ar': 'الأسبوع {w}'}
OG_ALT = 'Cipher Lacuna cube logo with the tagline Decoding the gaps in AI knowledge, in English and Arabic'

def _b():
    import build  # lazily: build.py imports this module
    return build

E = lambda v: html.escape(str(v if v is not None else ''))

def week_of(published):
    """(ISO year, ISO week) of a timestamp in UAE time."""
    d = _b().to_uae(published)
    y, w, _ = d.isocalendar()
    return y, w

def week_days(y, w):
    """The week's Monday and Sunday."""
    monday = date.fromisocalendar(y, w, 1)
    return monday, monday + timedelta(days=6)

def range_text(y, w, lang):
    """'12–18 Oct 2026', '28 Sep – 4 Oct 2026', '29 Dec 2025 – 4 Jan 2026'; Arabic month names in Arabic."""
    b = _b()
    months = b.AR_MONTHS if lang == 'ar' else b.EN_MONTHS
    a, z = week_days(y, w)
    if a.year != z.year:
        return f'{a.day} {months[a.month - 1]} {a.year} – {z.day} {months[z.month - 1]} {z.year}'
    if a.month != z.month:
        return f'{a.day} {months[a.month - 1]} – {z.day} {months[z.month - 1]} {z.year}'
    return f'{a.day}–{z.day} {months[z.month - 1]} {z.year}'

def page_name(kind, y, w):
    return f'{"uae-" if kind == "uae" else ""}{y}-w{w:02d}.html'

def page_path(kind, y, w, lang):
    """The page's path from the site root: weekly/2026-w42.html, weekly/ar-uae-2026-w42.html ..."""
    return f'{DIR}/{AR_PREFIX if lang == "ar" else ""}{page_name(kind, y, w)}'

def _rel(path, target):
    """`target` (a path from the site root) relative to the page at `path`."""
    up = '../' * path.count('/')
    here = path.rsplit('/', 1)[0] + '/' if '/' in path else ''
    return target[len(here):] if here and target.startswith(here) and '/' not in target[len(here):] else up + target

def stories(current, archived, sources):
    """The stories the weekly pages list, newest first, one per id and per link: the current list first (full news.json
    items), then the archive's (news_archive.shown()). Each gets '_topic' and '_week'."""
    src = {s['id']: s for s in sources}
    seen, out = set(), []
    for item, is_archived in [(i, False) for i in current] + [(i, True) for i in archived]:
        if item.get('source') not in src or item['id'] in seen or ('url', item['url']) in seen:
            continue
        seen.update((item['id'], ('url', item['url'])))
        story = dict(item)
        if is_archived:
            # The archive keeps AI summaries only, so an archived summary is the AI's (build.summary_of reads this).
            story['summary_source'] = 'ai' if item.get('summary_en') and item.get('summary_ar') else None
            topic = item.get('topic') if item.get('topic') in topics.TOPICS else topics.topic_of(item, src[item['source']])
        else:
            topic = topics.topic_of(item, src[item['source']])
        story['_topic'], story['_week'] = topic, week_of(item['published'])
        out.append(story)
    return sorted(out, key=lambda i: i['published'], reverse=True)

def group_weeks(all_stories):
    """{(year, week): {'all': [...], 'uae': [...]}}, newest first within each; 'uae' only for weeks with UAE stories."""
    out = {}
    for s in all_stories:
        wk = out.setdefault(s['_week'], {'all': [], 'uae': []})
        wk['all'].append(s)
        if s.get('uae'):
            wk['uae'].append(s)
    return out

def _story(i, lang, src):
    b = _b()
    s, d = src[i['source']], b.to_uae(i['published'])
    title, mt = b.headline_text(i, lang)
    ar = lang == 'ar'
    text_dir = f'lang="{lang}" dir="{"rtl" if ar else "ltr"}"'
    text, kind = b.summary_of(i, lang)
    summary = f'<p class="w-sum" {text_dir}>{E(text)}</p><p class="w-by">{b.SUMMARY_LABEL[kind][lang]}</p>' if text else ''
    name = s.get('name_ar') or s['name'] if ar else s['name']
    link = (f'<a class="w-src" href="{E(i["url"])}" target="_blank" rel="noopener noreferrer">{"المصدر" if ar else "Source"}: {E(name)} '
            f'<span aria-hidden="true">↗</span></a>')
    return (f'<li class="w-item" id="s-{E(i["id"])}"><h4 {text_dir}>{E(title)}</h4>{summary}'
            f'<p class="w-meta">{link}<time datetime="{E(i["published"])}"><bdi>{d:%H:%M}</bdi></time>{mt}</p></li>')

def _days(pool, lang, src):
    """Stories grouped by day (UAE time, newest first), then by topic (topics.TOPICS order)."""
    b = _b()
    out, days = '', {}
    for i in pool:
        days.setdefault(b.to_uae(i['published']).date(), []).append(i)
    for day in sorted(days, reverse=True):
        by_topic = {}
        for i in days[day]:
            by_topic.setdefault(i['_topic'], []).append(i)
        groups = ''.join(f'<section class="w-topic"><h3>{E(topics.label(t, lang))} <span class="n">{len(by_topic[t])}</span></h3>'
                         f'<ol>{"".join(_story(i, lang, src) for i in by_topic[t])}</ol></section>' for t in topics.TOPICS if t in by_topic)
        out += f'<section class="w-day"><h2>{b.day_label(day, lang)}</h2>{groups}</section>'
    return out

def _head(path, lang, title, desc, alt_path, logo):
    url = SITE + path
    en_url, ar_url = (url, SITE + alt_path) if lang == 'en' else (SITE + alt_path, url)
    up = '../' * path.count('/')
    locale, other = ('ar_AE', 'en_US') if lang == 'ar' else ('en_US', 'ar_AE')
    return (f'<!doctype html>\n<html lang="{lang}" dir="{"rtl" if lang == "ar" else "ltr"}"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light dark">'
            f'<meta name="theme-color" content="#6537d7"><title>{E(title)}</title><meta name="description" content="{E(desc)}">'
            f'<meta name="author" content="Cipher Lacuna"><link rel="canonical" href="{E(url)}">'
            f'<link rel="alternate" hreflang="en" href="{E(en_url)}"><link rel="alternate" hreflang="ar" href="{E(ar_url)}">'
            f'<link rel="icon" type="image/png" sizes="32x32" href="{up}brand/icon-32.png"><link rel="apple-touch-icon" href="{up}brand/apple-touch-icon.png">'
            f'<link rel="stylesheet" href="{_rel(path, DIR + "/weekly.css")}">\n'
            f'<meta property="og:type" content="website"><meta property="og:site_name" content="Cipher Lacuna"><meta property="og:title" content="{E(title)}">'
            f'<meta property="og:description" content="{E(desc)}"><meta property="og:url" content="{E(url)}"><meta property="og:image" content="{SITE}brand/og.png">'
            f'<meta property="og:image:type" content="image/png"><meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">'
            f'<meta property="og:image:alt" content="{E(OG_ALT)}"><meta property="og:locale" content="{locale}"><meta property="og:locale:alternate" content="{other}">\n'
            f'<meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="{E(title)}"><meta name="twitter:description" content="{E(desc)}">'
            f'<meta name="twitter:image" content="{SITE}brand/og.png"><meta name="twitter:image:alt" content="{E(OG_ALT)}">\n</head>\n')

def _top(path, lang, other_path, logo, home='index.html'):
    """The page header: the brand (to the overview), AI news, UAE AI, all weeks and the other language."""
    up = '../' * path.count('/')
    ar = lang == 'ar'
    q = '?lang=ar' if ar else ''
    switch = (f'<a class="w-lang" href="{_rel(path, other_path)}" lang="{"en" if ar else "ar"}" hreflang="{"en" if ar else "ar"}">'
              f'{"English" if ar else "العربية"}</a>')
    return (f'<body><a class="w-skip" href="#main">{"انتقل إلى المحتوى" if ar else "Skip to content"}</a>'
            f'<header class="w-top"><div class="w-wrap w-top-in"><a class="w-brand" href="{up}{home}{q}">{logo}'
            f'<span class="w-word" lang="en" dir="ltr">Cipher <b>Lacuna</b></span></a>'
            f'<nav class="w-nav" aria-label="{"الأقسام" if ar else "Sections"}"><a href="{up}{home}{q}#news">{"أخبار الذكاء الاصطناعي" if ar else "AI news"}</a>'
            f'<a href="{up}{home}{q}#uae">{"الذكاء الاصطناعي في الإمارات" if ar else "UAE AI"}</a>'
            f'<a href="{_rel(path, DIR + "/index.html")}{"#ar" if ar else ""}">{ALL_WEEKS[lang]}</a>{switch}</nav></div></header>\n')

def _foot(lang, year):
    ar = lang == 'ar'
    note = ('الملخصات الموسومة «ملخص بالذكاء الاصطناعي» يكتبها الذكاء الاصطناعي من نص المقال أو من وصف الناشر، والعناوين الموسومة «ترجمة بالذكاء الاصطناعي» '
            'يترجمها الذكاء الاصطناعي، وقد تحتوي على أخطاء. اتبع رابط المصدر لقراءة الخبر كاملاً.' if ar else
            'Summaries marked "AI summary" are machine-written from the article or the publisher\'s description and may contain mistakes. '
            'Follow the source link to read the full story.')
    rights = ('العناوين ومقتطفات الناشرين © لناشريها، مع روابط إلى المقالات الأصلية.' if ar else
              'Headlines and publisher excerpts © their publishers, with links to the original articles.')
    return (f'<p class="w-note">{note}</p></main>\n<footer class="w-foot"><div class="w-wrap"><p><bdi lang="en">© {year} Cipher Lacuna.</bdi> '
            f'{"جميع الحقوق محفوظة." if ar else "All rights reserved."}</p><p>{rights}</p></div></footer>\n</body></html>\n')

def render_week(kind, key, pool, lang, src, ctx):
    """One weekly page. `pool`: the week's stories of this kind (all languages); `ctx`: paths, neighbours, notes."""
    b = _b()
    y, w = key
    ar = lang == 'ar'
    path, other = page_path(kind, y, w, lang), page_path(kind, y, w, 'en' if ar else 'ar')
    shown = [i for i in pool if b.in_lang(i, lang)]
    n = len(shown)
    rng = range_text(y, w, lang)
    title = f'{TITLE[(kind, lang)]}: {rng} | Cipher Lacuna'
    if ar:
        desc = (f'{b.cnt(n, "story", "ar")} من {rng}، مرتبة حسب اليوم والموضوع، مع ملخص كل خبر ورابط إلى المقال الأصلي.' if n else
                f'لا توجد أخبار بالعربية في {rng}.')
        desc = ('عن الذكاء الاصطناعي في الإمارات: ' if kind == 'uae' else 'عن الذكاء الاصطناعي: ') + desc
    else:
        about = 'AI in the UAE' if kind == 'uae' else 'AI'
        desc = (f'{b.cnt(n, "story", "en")} about {about} from {rng}, grouped by day and topic, each with its summary and a link to the original article.'
                if n else f'No English stories about {about} from {rng}.')
    head = _head(path, lang, title, desc, other, ctx['logo'])
    top = _top(path, lang, other, ctx['logo'], ctx['home'])
    week_label = WEEK[lang].format(w=w)
    crumbs = (f'<nav class="w-crumbs" aria-label="{"مسار التنقل" if ar else "Breadcrumb"}"><a href="{"../" * path.count("/")}{ctx["home"]}{"?lang=ar" if ar else ""}">'
              f'<bdi lang="en">Cipher Lacuna</bdi></a><span aria-hidden="true">/</span><a href="{_rel(path, DIR + "/index.html")}{"#ar" if ar else ""}">{REVIEW[lang]}</a>'
              f'<span aria-hidden="true">/</span><span aria-current="page">{week_label}</span></nav>')
    count = b.cnt(n, 'story', lang)
    lead = (('كل خبر عن الذكاء الاصطناعي في الإمارات نشرناه هذا الأسبوع' if kind == 'uae' else 'كل خبر عن الذكاء الاصطناعي نشرناه هذا الأسبوع')
            + '، مرتباً حسب اليوم والموضوع، مع ملخصه ورابط إلى المقال الأصلي. الأوقات بتوقيت الإمارات.' if ar else
            ('Every UAE AI story' if kind == 'uae' else 'Every AI story') + ' we listed this week, grouped by day and topic, with its summary and a link to the original article. Times in UAE time.')
    notes = ''
    monday, sunday = week_days(y, w)
    if sunday >= ctx['today']:
        notes += f'<p class="w-flag">{"هذا الأسبوع لم ينته بعد: تضاف الأخبار فور نشرها." if ar else "This week is still in progress: stories are added as they are published."}</p>'
    if ctx['since'] and monday < ctx['since'] <= sunday:
        since = f'{ctx["since"].day} {(b.AR_MONTHS if ar else b.EN_MONTHS)[ctx["since"].month - 1]} {ctx["since"].year}'
        notes += f'<p class="w-flag">{f"تبدأ هذه الصفحة في {since}، تاريخ بدء الأرشيف." if ar else f"This page starts on {since}, when the archive began."}</p>'
    tcount = {}
    for i in shown:
        tcount[i['_topic']] = tcount.get(i['_topic'], 0) + 1
    chips = ''.join(f'<li>{E(topics.label(t, lang))} <span class="n">{tcount[t]}</span></li>' for t in topics.TOPICS if t in tcount)
    chips = f'<ul class="w-topics" aria-label="{"المواضيع" if ar else "Topics"}">{chips}</ul>' if chips else ''
    pager = ''
    for rel, nb in (('prev', ctx['prev']), ('next', ctx['next'])):
        if nb:
            label = WEEK[lang].format(w=nb[1])
            arrow = ('→' if rel == 'prev' else '←') if ar else ('←' if rel == 'prev' else '→')
            text = f'{arrow} {label}' if rel == 'prev' else f'{label} {arrow}'
            pager += f'<a class="w-{rel}" rel="{rel}" href="{_rel(path, page_path(kind, nb[0], nb[1], lang))}">{text}</a>'
    pager = f'<nav class="w-pager" aria-label="{"الأسابيع" if ar else "Weeks"}">{pager}</nav>' if pager else ''
    if shown:
        body = _days(shown, lang, src)
    else:
        body = (f'<p class="w-empty">{"لا توجد أخبار بالعربية هذا الأسبوع." if ar else "No English stories this week."} '
                f'<a href="{_rel(path, other)}" lang="{"en" if ar else "ar"}">{"اقرأ الصفحة الإنجليزية" if ar else "Read the Arabic page"}</a></p>')
    other_kind = 'all' if kind == 'uae' else 'uae'
    also = ''
    if ctx['has_other']:
        also = (f'<p class="w-also"><a href="{_rel(path, page_path(other_kind, y, w, lang))}">{TITLE[(other_kind, lang)]}</a></p>')
    main = (f'<main class="w-wrap" id="main" tabindex="-1">{crumbs}<h1>{TITLE[(kind, lang)]}</h1>'
            f'<p class="w-range"><span>{rng}</span><span>{week_label}</span><span>{count}</span></p><p class="w-lead">{lead}</p>'
            f'{notes}{chips}{also}{pager}{body}{pager}')
    return head + top + main + _foot(lang, ctx['year'])

def render_index(weeks, ctx):
    """weekly/index.html: every week, newest first, in English and then in Arabic (#ar), with each page's story count."""
    b = _b()
    path = f'{DIR}/index.html'
    rows = {'en': '', 'ar': ''}
    for (y, w) in sorted(weeks, reverse=True):
        for lang in ('en', 'ar'):
            cells = ''
            for kind in KINDS:
                pool = weeks[(y, w)][kind]
                if not pool:
                    continue
                n = sum(b.in_lang(i, lang) for i in pool)
                cells += (f'<a class="w-wk-{kind}" href="{_rel(path, page_path(kind, y, w, lang))}">{TITLE[(kind, lang)]}'
                          f' <span class="n">{E(b.cnt(n, "story", lang))}</span></a>')
            rows[lang] += (f'<li><span class="w-wk"><b>{WEEK[lang].format(w=w)}</b> · {range_text(y, w, lang)}</span>'
                           f'<span class="w-wk-links">{cells}</span></li>')
    title = 'Week in review: AI and UAE AI, week by week | Cipher Lacuna'
    desc = ('Every week of AI news on Cipher Lacuna, in English and Arabic: the AI stories and the UAE AI stories of each week, '
            'grouped by day and topic, with summaries and links to the original articles.')
    head = _head(path, 'en', title, desc, path, ctx['logo'])
    head = head.replace(f'<link rel="alternate" hreflang="ar" href="{SITE}{path}">', f'<link rel="alternate" hreflang="ar" href="{SITE}{path}#ar">')
    up = '../'
    top = (f'<body><a class="w-skip" href="#main">Skip to content</a><header class="w-top"><div class="w-wrap w-top-in">'
           f'<a class="w-brand" href="{up}{ctx["home"]}">{ctx["logo"]}<span class="w-word" lang="en" dir="ltr">Cipher <b>Lacuna</b></span></a>'
           f'<nav class="w-nav" aria-label="Sections"><a href="{up}{ctx["home"]}#news">AI news</a><a href="{up}{ctx["home"]}#uae">UAE AI</a>'
           f'<a class="w-lang" href="#ar" lang="ar">العربية</a></nav></div></header>\n')
    empty = {'en': '<p class="w-empty">No weeks yet.</p>', 'ar': '<p class="w-empty">لا توجد أسابيع بعد.</p>'}
    en = (f'<section class="w-ix" aria-labelledby="ix-en"><h1 id="ix-en">{REVIEW["en"]}</h1>'
          f'<p class="w-lead">The AI stories and the UAE AI stories of each week, grouped by day and topic, with their summaries and links to the original articles. Weeks run Monday to Sunday, UAE time.</p>'
          + (f'<ol class="w-weeks">{rows["en"]}</ol>' if rows['en'] else empty['en']) + '</section>')
    ar = (f'<section class="w-ix" id="ar" lang="ar" dir="rtl" aria-labelledby="ix-ar"><h2 id="ix-ar" class="w-h1">{REVIEW["ar"]}</h2>'
          f'<p class="w-lead">أخبار الذكاء الاصطناعي وأخبار الذكاء الاصطناعي في الإمارات لكل أسبوع، مرتبة حسب اليوم والموضوع، مع ملخصاتها وروابط إلى المقالات الأصلية. يبدأ الأسبوع يوم الاثنين وينتهي يوم الأحد بتوقيت الإمارات.</p>'
          + (f'<ol class="w-weeks">{rows["ar"]}</ol>' if rows['ar'] else empty['ar']) + '</section>')
    foot = (f'</main>\n<footer class="w-foot"><div class="w-wrap"><p><bdi lang="en">© {ctx["year"]} Cipher Lacuna.</bdi> All rights reserved.</p>'
            f'<p lang="ar" dir="rtl">جميع الحقوق محفوظة.</p></div></footer>\n</body></html>\n')
    return head + top + f'<main class="w-wrap" id="main" tabindex="-1">{en}{ar}' + foot

def pages(current, archived, sources, now, logo='', home='index.html'):
    """({path: page text}, links) for every week. Pure: writes nothing. `links`: the newest week of each kind, for the
    AI news and UAE AI views: {'all'|'uae': {'en': path, 'ar': path, 'range_en', 'range_ar', 'week'}} (a kind without
    stories is left out). `now`: the reference time (the in-progress note). `home`: the overview's file name beside the
    weekly folder (index.html; the --standalone copy has its own)."""
    src = {s['id']: s for s in sources}
    all_stories = stories(current, archived, sources)
    weeks = group_weeks(all_stories)
    today = now.astimezone(UAE_TZ).date()
    since = min((_b().to_uae(s['published']).date() for s in all_stories), default=None)
    ctx = {'logo': logo, 'today': today, 'since': since, 'year': today.year, 'home': home}
    out = {}
    for kind in KINDS:
        keys = sorted(k for k in weeks if weeks[k][kind])
        for n, key in enumerate(keys):
            other_kind = 'uae' if kind == 'all' else 'all'
            c = {**ctx, 'prev': keys[n - 1] if n else None, 'next': keys[n + 1] if n + 1 < len(keys) else None,
                 'has_other': bool(weeks[key][other_kind])}
            for lang in ('en', 'ar'):
                out[page_path(kind, *key, lang)] = render_week(kind, key, weeks[key][kind], lang, src, c)
    out[f'{DIR}/index.html'] = render_index(weeks, ctx)
    return out, _links(weeks)

def _links(weeks):
    links = {}
    for kind in KINDS:
        keys = sorted(k for k in weeks if weeks[k][kind])
        if keys:
            y, w = keys[-1]
            links[kind] = {'en': page_path(kind, y, w, 'en'), 'ar': page_path(kind, y, w, 'ar'), 'week': w,
                           'range_en': range_text(y, w, 'en'), 'range_ar': range_text(y, w, 'ar')}
    return links

def latest(current, archived, sources):
    """The newest weekly page of each kind, as pages() gives it (for the links in AI news and UAE AI), without
    rendering any page."""
    return _links(group_weeks(stories(current, archived, sources)))

def write(out_dir, built):
    """Write the pages of pages() and weekly.css into out_dir; pages of an earlier build that are not in `built` go."""
    out_dir = Path(out_dir)
    folder = out_dir / DIR
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob('*.html'):
        if f'{DIR}/{old.name}' not in built:
            old.unlink()
    for path, text in built.items():
        target = out_dir / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding='utf-8', newline='\n')
    shutil.copyfile(CSS, folder / 'weekly.css')
    return sorted(built)
