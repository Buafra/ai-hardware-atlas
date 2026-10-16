"""The site's language pairs: the overview, Learn AI and the Qahwa & AI lessons page each exist in English at the site
root and in Arabic under /ar/ (index.html, learn.html, qahwa.html), and each copy is served already in its language:
<html lang dir>, title, description and share tags, and the first paint in that language without waiting for a script.

- Each pair links to itself with hreflang (en, ar and x-default = English) and a canonical address per language
  (head_links()); the language button is a link to the other copy of the same page.
- The Arabic copies reuse the site's files (images, brand, fonts, news images, the PDF, the APK): relocate() adds "../" to
  their own relative links, so nothing is copied into ar/. Links between the paired pages stay as they are (learn.html
  in ar/index.html is ar/learn.html).
- Language rule (lang_script(), in each page's head before anything is drawn): the page's language is its address. Links
  shared before the Arabic copies existed still work: ?lang=ar on an English page, or Arabic as the saved choice
  (atlas-lang) with no ?lang=, goes to the Arabic copy; ?lang=en on an Arabic copy goes to the English one. An Arabic
  copy otherwise stays Arabic whatever was saved. The query (without lang) and the #fragment go along.
- The overview's Arabic first paint uses the Arabic strings app.js already has (its AR table, read by js_strings()), and
  the lessons page uses qahwa.js's own T.ar: one copy of every translation.
"""
import html
import json
import re

SITE_URL = 'https://cipherlacuna.ae/'
AR_DIR = 'ar'
PAGES = ('index.html', 'learn.html', 'qahwa.html')  # each has an Arabic copy at ar/<name>
LOCALE = {'en': 'en_US', 'ar': 'ar_AE'}

def url(path):
    """Public address of a page path in dist/: 'index.html' -> https://cipherlacuna.ae/, 'ar/index.html' -> …/ar/,
    'learn.html' -> …/learn.html, 'apk/index.html' -> …/apk/."""
    path = str(path).lstrip('/')
    if path == 'index.html' or path.endswith('/index.html'):
        path = path[:-len('index.html')]
    return SITE_URL + path

def twin(page, lang):
    """The path of `page` (a name in PAGES) in `lang`: ('learn.html', 'ar') -> 'ar/learn.html'."""
    return f'{AR_DIR}/{page}' if lang == 'ar' else page

def head_links(page, lang):
    """Canonical address of this copy and the hreflang alternates of the pair (x-default: English)."""
    en, ar = url(twin(page, 'en')), url(twin(page, 'ar'))
    return (f'<link rel="canonical" href="{en if lang == "en" else ar}">'
            f'<link rel="alternate" hreflang="en" href="{en}"><link rel="alternate" hreflang="ar" href="{ar}">'
            f'<link rel="alternate" hreflang="x-default" href="{en}">')

def lang_script(page_lang, other, navigator=False):
    """The head script's first statement: send the visitor to the other copy (`other`, a relative link such as
    'ar/index.html' or '../learn.html') when the language asked for is not this page's. Asked for: ?lang=ar|en, else on
    the English copy the saved choice (atlas-lang; with `navigator`, the browser's language when nothing is saved), else
    the page's own. A ?lang= visit saves nothing. Over http(s) the link drops a final index.html (/ar/, not
    /ar/index.html); from a file it keeps it. The page is hidden while it goes, so it never shows in the wrong language."""
    assert page_lang in ('en', 'ar') and re.fullmatch(r"[\w./-]+", other), other
    nav = "else if(l!=='ar'&&l!=='en'&&N)l=/^ar\\b/i.test(navigator.language||'')?'ar':'en';"
    return ("(function(P,A,N){var l=null,q=null,s=location.search,r='';try{l=localStorage.getItem('atlas-lang')}catch(e){}"
            "try{q=new URLSearchParams(s).get('lang')}catch(e){}if(q==='ar'||q==='en')l=q;else if(P==='ar')l='ar';" + nav +
            "if((l==='ar'?'ar':'en')===P)return;if(location.protocol!=='file:')A=A.replace(/(^|\\/)index\\.html$/,'$1');"
            "try{var p=new URLSearchParams(s);p.delete('lang');r=p.toString()}catch(e){}"
            "document.documentElement.style.visibility='hidden';location.replace(A+(r?'?'+r:'')+location.hash)})"
            f"('{page_lang}','{other}',{1 if navigator else 0});")

# ---------- the Arabic copies' links ----------

BLOCK = re.compile(r'(<(script|style)\b[^>]*>)(.*?)(</\2\s*>)', re.S | re.I)
LINK_ATTR = re.compile(r'(\s(?:src|href)=")([^"]*)(")')
CSS_URL = re.compile(r'url\(\s*([\'"]?)([^\'")\s]+)\1\s*\)')
ABSOLUTE = re.compile(r'^(?:[a-zA-Z][a-zA-Z0-9+.-]*:|/|#|\.\.?/|$)')

def _segments(text, markup, style=None):
    """Apply markup() to everything outside <script> and <style> blocks and style() to the inside of <style> blocks.
    Scripts (app code, inline JSON data, JSON-LD) are never touched."""
    out, last = [], 0
    for m in BLOCK.finditer(text):
        out.append(markup(text[last:m.start()]))
        body = m.group(3)
        if style and m.group(2).lower() == 'style':
            body = style(body)
        out.append(m.group(1) + body + m.group(4))
        last = m.end()
    out.append(markup(text[last:]))
    return ''.join(out)

def moved(link, prefix='../', keep=PAGES, inside=AR_DIR):
    """One relative link of a root page as seen from a page one folder down: 'brand/x.png' -> '../brand/x.png'. Absolute
    links, data: URIs, #fragments, ../ links and the paired pages (keep) are left as they are. A link into the folder
    the copy is in (`inside`) loses that folder: 'ar/weekly/2026-w42.html' -> 'weekly/2026-w42.html'."""
    if ABSOLUTE.match(link):
        return link
    path = re.split(r'[?#]', link, 1)[0]
    if path in keep:
        return link
    if inside and path.startswith(inside + '/'):
        return link[len(inside) + 1:]
    return prefix + link

def relocate(text, prefix='../', keep=PAGES, inside=AR_DIR):
    """The page's own src/href links and its CSS url()s, rewritten for a copy one folder down (see moved())."""
    def markup(seg):
        return LINK_ATTR.sub(lambda m: m.group(1) + moved(m.group(2), prefix, keep, inside) + m.group(3), seg)
    def style(css):
        return CSS_URL.sub(lambda m: m.group(0) if m.group(2).startswith('data:') else
                           f'url({m.group(1)}{moved(m.group(2), prefix, keep, inside)}{m.group(1)})', css)
    return _segments(text, markup, style)

def relative_links(text):
    """Every relative src/href (outside scripts) and CSS url() of a page: what relocate() changes. For the tests."""
    found = []
    def markup(seg):
        found.extend(v for v in (m.group(2) for m in LINK_ATTR.finditer(seg)) if not ABSOLUTE.match(v) or v.startswith('../'))
        return seg
    def style(css):
        found.extend(m.group(2) for m in CSS_URL.finditer(css) if not m.group(2).startswith('data:') and (not ABSOLUTE.match(m.group(2)) or m.group(2).startswith('../')))
        return css
    _segments(text, markup, style)
    return found

# ---------- the translations that the page scripts already hold ----------

_ESC = re.compile(r'\\(u\{[0-9a-fA-F]+\}|u[0-9a-fA-F]{4}|x[0-9a-fA-F]{2}|.)', re.S)
_SIMPLE = {'n': '\n', 't': '\t', 'r': '\r', 'b': '\b', 'f': '\f', 'v': '\v', '0': '\0'}

def _js_unescape(s):
    def one(m):
        e = m.group(1)
        if e.startswith('u{'):
            return chr(int(e[2:-1], 16))
        if e[0] in 'ux' and len(e) > 1:
            return chr(int(e[1:], 16))
        return _SIMPLE.get(e, '' if e == '\n' else e)
    return _ESC.sub(one, s)

def _entries(js, start):
    """The top-level entries (raw text) of the object literal that opens at js[start] == '{'. Strings, template
    literals, comments and nesting are skipped over, so a comma inside them never splits an entry."""
    assert js[start] == '{'
    i, depth, entries, cur = start + 1, 0, [], []
    n = len(js)
    while i < n:
        c = js[i]
        if c in '\'"`':
            j = i + 1
            while j < n and js[j] != c:
                j += 2 if js[j] == '\\' else 1
            cur.append(js[i:j + 1])
            i = j + 1
            continue
        if js.startswith('//', i):
            i = js.find('\n', i)
            i = n if i < 0 else i
            continue
        if js.startswith('/*', i):
            i = js.index('*/', i) + 2
            continue
        if c in '{[(':
            depth += 1
        elif c in '}])':
            if depth == 0:
                entries.append(''.join(cur))
                return entries
            depth -= 1
        elif c == ',' and depth == 0:
            entries.append(''.join(cur))
            cur = []
            i += 1
            continue
        cur.append(c)
        i += 1
    raise ValueError('unterminated object literal')

_STR = r"""'((?:[^'\\]|\\.)*)'|"((?:[^"\\]|\\.)*)\""""
_ENTRY = re.compile(r'^\s*(?:' + _STR + r'|([A-Za-z_$][\w$]*))\s*:\s*(?:' + _STR + r')\s*$', re.S)

def js_strings(js, opener, after=''):
    """{key: text} for every entry whose value is a plain string literal, in the object literal that starts at the first
    `opener` in the script (after the first `after`, when given): for example "const AR = {" in app.js, or "ar: {" after
    "const T = {" in qahwa.js. Function values and others are skipped."""
    at = js.index(opener, js.index(after) if after else 0) + len(opener) - 1
    out = {}
    for raw in _entries(js, at):
        m = _ENTRY.match(raw)
        if not m:
            continue
        key = m.group(3) if m.group(3) is not None else _js_unescape(m.group(1) if m.group(1) is not None else m.group(2))
        val = m.group(4) if m.group(4) is not None else m.group(5)
        out[key] = _js_unescape(val)
    return out

# ---------- Arabic first paint ----------

I18N_LEAF = re.compile(r'<(?P<tag>[a-zA-Z][a-zA-Z0-9]*)(?P<attrs>(?:\s[^<>]*?)?\sdata-i18n(?=[\s>])[^<>]*)>(?P<text>[^<]*)</(?P=tag)>')
AR_LEAF = re.compile(r'<(?P<tag>[a-zA-Z][a-zA-Z0-9]*)(?P<attrs>(?:\s[^<>]*?)?\sdata-ar="(?P<ar>[^"]*)"[^<>]*)>(?P<text>[^<]*)</(?P=tag)>')
START_TAG = re.compile(r'<[a-zA-Z][a-zA-Z0-9]*\s[^<>]*>')

def _attr(tag, name):
    m = re.search(r'\s' + re.escape(name) + r'="([^"]*)"', tag)
    return html.unescape(m.group(1)) if m else None

def _set_attr(tag, name, value):
    value = html.escape(value, quote=True)
    pat = re.compile(r'(\s' + re.escape(name) + r'=")[^"]*(")')
    if pat.search(tag):
        return pat.sub(lambda m: m.group(1) + value + m.group(2), tag, count=1)
    return re.sub(r'\s*(/?>)$', lambda m: f' {name}="{value}"' + m.group(1), tag, count=1)

def translate_overview(text, ar):
    """The overview in Arabic exactly as app.js's applyLang() would show it, but in the HTML: every [data-i18n] text,
    [data-i18n-ph] placeholder, [data-i18n-aria] label and [data-ar] text in Arabic (`ar`: app.js's AR table; a string
    without an entry stays English, as in app.js). The English source goes into data-en, which app.js reads as the key."""
    def leaf(m):
        en = html.unescape(m.group('text'))
        if en not in ar:
            return m.group(0)
        attrs = m.group('attrs') + f' data-en="{html.escape(en, quote=True)}"'
        return f'<{m.group("tag")}{attrs}>{html.escape(ar[en], quote=False)}</{m.group("tag")}>'
    def own(m):
        value = html.unescape(m.group('ar'))
        if not value:
            return m.group(0)
        en = html.unescape(m.group('text'))
        attrs = m.group('attrs') + f' data-en="{html.escape(en, quote=True)}"'
        return f'<{m.group("tag")}{attrs}>{html.escape(value, quote=False)}</{m.group("tag")}>'
    def tag(m):
        t = m.group(0)
        for marker, target in (('data-i18n-ph', 'placeholder'), ('data-i18n-aria', 'aria-label')):
            key = _attr(t, marker)
            if key is not None and key in ar:
                t = _set_attr(t, target, ar[key])
        return t
    def markup(seg):
        return START_TAG.sub(tag, AR_LEAF.sub(own, I18N_LEAF.sub(leaf, seg)))
    return _segments(text, markup)

def translate_keys(text, strings):
    """A page whose script looks its strings up by key (qahwa.js): [data-i18n="k"] texts, [data-i18n-html="k"] markup,
    [data-i18n-ph="k"] placeholders and [data-i18n-aria="k"] labels filled from `strings` (that script's own table for the
    page's language). Elements whose key has no string, or that hold an element of their own kind, are left as they are."""
    opener = re.compile(r'<(?P<tag>[a-zA-Z][a-zA-Z0-9]*)\s[^<>]*?\bdata-i18n(?P<html>-html)?="(?P<key>[^"]*)"[^<>]*>')
    def elements(seg):
        out, last = [], 0
        for m in opener.finditer(seg):
            if m.start() < last:
                continue
            tag, key = m.group('tag'), m.group('key')
            close = seg.find(f'</{tag}>', m.end())
            inner = seg[m.end():close] if close >= 0 else ''
            if close < 0 or key not in strings or re.search(rf'<{tag}[\s>]', inner):
                continue
            value = strings[key] if m.group('html') else html.escape(strings[key], quote=False)
            out.append(seg[last:m.end()] + value)
            last = close
        return ''.join(out) + seg[last:]
    def tag(m):
        t = m.group(0)
        for marker, target in (('data-i18n-ph', 'placeholder'), ('data-i18n-aria', 'aria-label')):
            key = _attr(t, marker)
            if key is not None and key in strings:
                t = _set_attr(t, target, strings[key])
        return t
    def markup(seg):
        return START_TAG.sub(tag, elements(seg))
    return _segments(text, markup)

def json_ld(obj):
    """A <script type="application/ld+json"> block; <, > and & are escaped so the data can never end the block."""
    data = json.dumps(obj, ensure_ascii=False, separators=(',', ':'))
    data = data.replace('&', '\\u0026').replace('<', '\\u003c').replace('>', '\\u003e')
    return f'<script type="application/ld+json">{data}</script>'
