"""The light/dark switch of the small stand-alone pages: the weekly pages (weekly.py), the app share page (apk_page.py)
and the 404 page (seo.py).

They follow the same choice as the overview's theme button: 'auto' (the phone or computer setting), 'light' or 'dark',
saved in this browser under the overview's key, so a choice made on any page holds on all of them. A script in the head
applies a saved choice before the first paint (no flash); the button cycles Auto -> Light -> Dark like the overview's.
Without JavaScript the pages simply follow the system setting. Each page's CSS keeps its light colours on :root and
gets its dark colours from dark_css(): under prefers-color-scheme unless light was chosen, and always when dark was.
"""
KEY = 'atlas-theme'  # the overview's key (web/app.js, web/template.html)

# Before first paint: a saved light or dark choice; 'auto' or nothing leaves the system setting in charge.
HEAD = ("<script>(function(d){try{var t=localStorage.getItem('" + KEY + "');if(t==='light'||t==='dark')d.dataset.theme=t}"
        "catch(e){}})(document.documentElement)</script>")

# The overview's theme icon (scripts/build.py ICON['theme']).
ICON = ('<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true" focusable="false"><circle cx="12" cy="12" r="8.5" '
        'fill="none" stroke="currentColor" stroke-width="2"/><path d="M12 3.5a8.5 8.5 0 0 1 0 17z" fill="currentColor"/></svg>')

# The overview's own words (web/app.js AR dictionary: 'Auto', 'Light', 'Dark', 'Theme: …').
WORDS = {
    'en': {'auto': 'Auto', 'light': 'Light', 'dark': 'Dark', 'theme': 'Theme'},
    'ar': {'auto': 'تلقائي', 'light': 'فاتح', 'dark': 'داكن', 'theme': 'المظهر'},
}


def _labels(lang):
    """{mode: (visible label, aria-label)}; lang 'both' gives the two languages side by side (bilingual pages)."""
    langs = ('en', 'ar') if lang == 'both' else (lang,)
    out = {}
    for mode in ('auto', 'light', 'dark'):
        out[mode] = (' · '.join(WORDS[l][mode] for l in langs),
                     ' · '.join(f"{WORDS[l]['theme']}: {WORDS[l][mode]}" for l in langs))
    return out


def button(lang, cls='theme-btn'):
    """The switch, labelled Auto until the script reads the saved choice. It needs script(), placed after it."""
    label, aria = _labels(lang)['auto']
    return (f'<button type="button" class="{cls}" id="theme" aria-label="{aria}">{ICON}'
            f'<span id="theme-label">{label}</span></button>')


def script(lang):
    """Shows the saved choice on the button and cycles it on click (Auto -> Light -> Dark), saving it."""
    labels = _labels(lang)
    js_map = ','.join(f"{m}:['{v[0]}','{v[1]}']" for m, v in labels.items())
    return ("<script>(function(){var d=document.documentElement,b=document.getElementById('theme'),"
            "l=document.getElementById('theme-label');if(!b||!l)return;"
            f"var W={{{js_map}}},t='auto';try{{t=localStorage.getItem('{KEY}')||'auto'}}catch(e){{}}"
            "if(!W[t])t='auto';"
            "function show(){if(t==='auto')delete d.dataset.theme;else d.dataset.theme=t;l.textContent=W[t][0];b.setAttribute('aria-label',W[t][1])}"
            "show();b.addEventListener('click',function(){t={auto:'light',light:'dark',dark:'auto'}[t];"
            f"try{{localStorage.setItem('{KEY}',t)}}catch(e){{}}show()}})}})()</script>")


def dark_css(decls, root=':root'):
    """CSS for the dark colours `decls` (custom-property declarations, no braces): from the system setting unless the
    visitor chose light, and always when they chose dark."""
    return (f'@media (prefers-color-scheme:dark){{{root}:not([data-theme="light"]){{{decls}}}}}'
            f'{root}[data-theme="dark"]{{{decls}}}')


def button_css(border='var(--line)', ink='var(--muted)', hover='var(--ink)'):
    """A small pill like the overview's ghost buttons; at least 36px high for touch."""
    return (f'.theme-btn{{display:inline-flex;align-items:center;gap:6px;min-height:36px;padding:4px 12px;border:1px solid {border};'
            f'border-radius:999px;background:none;color:{ink};font:inherit;font-size:13px;font-weight:700;cursor:pointer}}'
            f'.theme-btn:hover{{color:{hover}}}.theme-btn:focus-visible{{outline:3px solid var(--accent);outline-offset:2px}}'
            '.theme-btn svg{flex:none}')
