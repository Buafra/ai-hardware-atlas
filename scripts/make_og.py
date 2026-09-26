"""Render the share preview web/brand/og.png (1200 x 630) from the owner's logo and the Cipher Lacuna taglines.

    python scripts/make_og.py

Needs Playwright with Chromium (pip install playwright && python -m playwright install chromium), like
tests/e2e_smoke.py. The PNG is committed; run this again only when the logo or the taglines change.
Arabic is shaped by Chromium, so the line renders correctly (joined letters, right to left) given a font
with Arabic glyphs: Arial and Tahoma on Windows and macOS, Noto Sans Arabic on Linux.
"""
import base64
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRAND = ROOT / 'web' / 'brand'
OUT = BRAND / 'og.png'
W, H = 1200, 630
NAME = ('Cipher', 'Lacuna')
TAGLINE_EN = 'Decoding the gaps in AI knowledge'
TAGLINE_AR = 'كشف المجهول في عالم الذكاء الاصطناعي'

def page_html():
    logo = 'data:image/svg+xml;base64,' + base64.b64encode((BRAND / 'logo.svg').read_bytes()).decode('ascii')
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><style>
html,body{{margin:0;width:{W}px;height:{H}px;overflow:hidden}}
body{{position:relative;background:#F5F8FF;font-family:Arial,Helvetica,sans-serif;color:#0E1222}}
/* Subtle brand accents: the palette as a top rule, two soft glows in the corners. */
.rule{{position:absolute;inset:0 0 auto 0;height:12px;background:linear-gradient(90deg,#42208D,#753ACA 38%,#D52F89 72%,#22D4D6)}}
.glow{{position:absolute;border-radius:50%;filter:blur(8px)}}
.g1{{width:620px;height:620px;right:-230px;top:-300px;background:radial-gradient(closest-side,#753ACA2e,#753ACA00)}}
.g2{{width:560px;height:560px;left:-220px;bottom:-310px;background:radial-gradient(closest-side,#22D4D633,#22D4D600)}}
.g3{{width:420px;height:420px;right:120px;bottom:-300px;background:radial-gradient(closest-side,#D52F8922,#D52F8900)}}
.lockup{{position:absolute;inset:12px 0 0 0;display:flex;align-items:center;justify-content:center;gap:52px}}
.logo{{width:232px;height:232px;flex:none}}
.text{{display:flex;flex-direction:column;align-items:flex-start}}
.name{{font-size:100px;font-weight:700;line-height:1;letter-spacing:-1px;white-space:nowrap}}
.name b{{font-weight:700;background:linear-gradient(100deg,#42208D,#753ACA 48%,#D52F89);-webkit-background-clip:text;background-clip:text;color:transparent}}
.bar{{width:88px;height:6px;border-radius:3px;margin:30px 0 26px;background:linear-gradient(90deg,#753ACA,#D52F89 60%,#22D4D6)}}
.en{{font-size:36px;font-weight:600;color:#475069;line-height:1.2;white-space:nowrap}}
.ar{{display:inline-block;margin-top:14px;font-family:Arial,Tahoma,"Segoe UI","Noto Sans Arabic","Noto Naskh Arabic",sans-serif;font-size:40px;font-weight:600;color:#475069;line-height:1.35;white-space:nowrap}}
</style></head><body>
<div class="rule"></div><div class="glow g1"></div><div class="glow g2"></div><div class="glow g3"></div>
<div class="lockup"><img class="logo" src="{logo}" alt="">
<div class="text"><div class="name">{NAME[0]} <b>{NAME[1]}</b></div><div class="bar"></div>
<div class="en">{TAGLINE_EN}</div><div class="ar" lang="ar" dir="rtl">{TAGLINE_AR}</div></div></div>
</body></html>'''

def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit('Playwright is needed: pip install playwright && python -m playwright install chromium')
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width': W, 'height': H}, device_scale_factor=1)
        page.set_content(page_html(), wait_until='load')
        page.evaluate('document.fonts.ready')
        # Everything must sit inside the card, with room to spare for platforms that crop to 2:1.
        box = page.evaluate("(() => { const r = document.querySelector('.text').getBoundingClientRect(), l = document.querySelector('.logo').getBoundingClientRect();"
                            " return [Math.min(r.left, l.left), Math.min(r.top, l.top), Math.max(r.right, l.right), Math.max(r.bottom, l.bottom)]; })()")
        assert box[0] >= 40 and box[2] <= W - 40 and box[1] >= 40 and box[3] <= H - 40, f'lockup does not fit: {box}'
        page.screenshot(path=str(OUT), clip={'x': 0, 'y': 0, 'width': W, 'height': H})
        browser.close()
    print(f'Wrote {OUT.relative_to(ROOT)} ({W}x{H})')

if __name__ == '__main__':
    main()
