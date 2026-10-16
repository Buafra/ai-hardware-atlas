"""RSS 2.0 feeds of the site's headlines, written by scripts/build.py next to the pages:

    news-en.xml  AI news in English          news-ar.xml  AI news in Arabic
    uae-en.xml   UAE AI news in English      uae-ar.xml   UAE AI news in Arabic

Each feed holds the newest 50 headlines of exactly the list the page shows in that language (build.news_items():
vetted sources, https links, the content policy, items not mainly about AI left out; the Arabic list adds English
headlines that carry an AI translation, as on the page). An item has the headline, the link to the original article,
the summary the page shows (the AI summary, or the publisher's own excerpt in its language) with a line saying who
wrote it, the publisher and "via cipherlacuna.ae", the publication time, a guid (the article address) and its topic
(the item's "topic" from scripts/news.py when it has one, else topics.topic_of(), the rule the topic images use).
Feeds are only read by the reader's app; nothing is posted anywhere.
"""
import html
import re
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from xml.sax.saxutils import escape

import lang_pages
import topics

SITE_URL = lang_pages.SITE_URL
LIMIT = 50
KINDS = ('news', 'uae')
FILES = {(k, l): f'{k}-{l}.xml' for k in KINDS for l in ('en', 'ar')}
TITLE = {('news', 'en'): 'Cipher Lacuna · AI news', ('news', 'ar'): 'Cipher Lacuna · أخبار الذكاء الاصطناعي',
         ('uae', 'en'): 'Cipher Lacuna · UAE AI news', ('uae', 'ar'): 'Cipher Lacuna · أخبار الذكاء الاصطناعي في الإمارات'}
ABOUT = {('news', 'en'): 'The latest AI headlines in English, each with a link to the original article.',
         ('news', 'ar'): 'أحدث عناوين الذكاء الاصطناعي بالعربية، ولكل عنوان رابط إلى المقال الأصلي.',
         ('uae', 'en'): 'The latest AI headlines about the UAE or from UAE newsrooms, in English, each with a link to the original article.',
         ('uae', 'ar'): 'أحدث عناوين الذكاء الاصطناعي عن الإمارات أو من غرف الأخبار الإماراتية، بالعربية، ولكل عنوان رابط إلى المقال الأصلي.'}
SOURCE = {'en': 'Source', 'ar': 'المصدر'}
VIA = {'en': 'via', 'ar': 'عبر'}
HEADLINE_MT = {'en': 'Headline: AI translation', 'ar': 'العنوان: ترجمة بالذكاء الاصطناعي'}
CONTROL = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]')

def _site():
    import build  # the page's own helpers (the same lists and labels as the page); build.py imports this module
    return build

def clean(text):
    return CONTROL.sub('', str(text or ''))

def home(lang, kind):
    """The feed's page: the AI news or UAE AI view of the overview in that language."""
    return lang_pages.url(lang_pages.twin('index.html', lang)) + '#' + kind

def rfc822(iso):
    d = datetime.fromisoformat(str(iso).replace('Z', '+00:00'))
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return format_datetime(d.astimezone(timezone.utc), usegmt=True)

def pool(items, kind, lang):
    """The headlines of one feed, newest first (items: build.news_items(), already newest first)."""
    b = _site()
    return [i for i in items if b.in_lang(i, lang) and (kind == 'news' or i.get('uae'))][:LIMIT]

def topic(i, source):
    t = i.get('topic')
    return t if t in topics.TOPICS else topics.topic_of(i, source)

def description(i, lang, source):
    """The item's description (HTML, escaped once more by the XML): the summary the page shows, then who wrote it, the
    publisher, a note on an AI-translated headline and "via cipherlacuna.ae"."""
    b = _site()
    text, kind = b.summary_of(i, lang)
    dir_ = ' dir="rtl"' if lang == 'ar' else ''
    site = lang_pages.url(lang_pages.twin('index.html', lang))
    name = source['name_ar'] if lang == 'ar' and source.get('name_ar') else source['name']
    parts = [f'{SOURCE[lang]}: {html.escape(clean(name), quote=False)}']
    if text:
        parts.append(b.SUMMARY_LABEL[kind][lang])
    if lang == 'ar' and i['lang'] == 'en' and i.get('title_ar'):
        parts.append(HEADLINE_MT['ar'])
    parts.append(f'{VIA[lang]} <a href="{site}">cipherlacuna.ae</a>')
    body = f'<p{dir_}>{html.escape(clean(text), quote=False)}</p>' if text else ''
    return body + f'<p{dir_}>{" · ".join(parts)}</p>'

def rss(kind, lang, items, src, updated_at=None):
    """One feed as RSS 2.0 text."""
    b = _site()
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">', '<channel>',
           f'<title>{escape(TITLE[kind, lang])}</title>', f'<link>{escape(home(lang, kind))}</link>',
           f'<atom:link href="{SITE_URL}{FILES[kind, lang]}" rel="self" type="application/rss+xml"/>',
           f'<description>{escape(ABOUT[kind, lang])}</description>', f'<language>{lang}</language>']
    if updated_at:
        out.append(f'<lastBuildDate>{rfc822(updated_at)}</lastBuildDate>')
    for i in pool(items, kind, lang):
        s = src[i['source']]
        title, _ = b.headline_text(i, lang)
        out.append('<item>'
                   f'<title>{escape(clean(title))}</title>'
                   f'<link>{escape(i["url"])}</link>'
                   f'<description>{escape(description(i, lang, s))}</description>'
                   f'<category>{escape(topics.name(topic(i, s), lang))}</category>'
                   f'<pubDate>{rfc822(i["published"])}</pubDate>'
                   f'<guid isPermaLink="true">{escape(i["url"])}</guid>'
                   '</item>')
    out += ['</channel>', '</rss>', '']
    return '\n'.join(out)

def write(out_dir, feed, sources):
    """Write the four feeds (nothing without news sources). Returns the file names written."""
    if not sources:
        return []
    b = _site()
    items, src = b.news_items(feed, sources), {s['id']: s for s in sources}
    updated = (feed or {}).get('updated_at')
    out_dir = Path(out_dir)
    for (kind, lang), name in FILES.items():
        (out_dir / name).write_text(rss(kind, lang, items, src, updated), encoding='utf-8', newline='\n')
    return list(FILES.values())

def head_links(lang, prefix=''):
    """<link rel="alternate" type="application/rss+xml"> for the page's language (both feeds)."""
    return ''.join(f'<link rel="alternate" type="application/rss+xml" title="{escape(TITLE[kind, lang], {chr(34): "&quot;"})}" '
                   f'href="{prefix}{FILES[kind, lang]}">' for kind in KINDS)
