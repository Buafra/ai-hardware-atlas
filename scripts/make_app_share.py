"""Render the Android app's share kit into web/brand/: the QR code for the short link and two share images.

    python scripts/make_app_share.py

- app-qr.svg   QR code for https://cipherlacuna.ae/apk (the share page, scripts/apk_page.py), embedded in that page.
- app-qr.png   the same code as a 1024 x 1024 picture, to print or send.
- app-og.png   1200 x 630 link preview for the share page (WhatsApp, X, Telegram...), with the QR code.
- app-card.png 1080 x 1350 picture to post in a chat or a status: logo, name, what the app has, the QR code and the link.

The QR code points at the share page, not at the APK itself, so an iPhone gets a page that explains the app is for
Android instead of an unusable file, and an Android phone starts the download from there.

Needs Playwright with Chromium, like make_og.py. The QR modules come from qrcode-generator (MIT, Kazuhiko Arase),
loaded from cdnjs while this script runs; the committed files contain only the finished code, so the site makes no
outside request. The images hold no version number, so they stay valid for every release; run this again only when
the logo, the colours or the link change. Arabic is shaped by Chromium (Arial / Tahoma on Windows).
"""
import base64
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRAND = ROOT / 'web' / 'brand'
SHARE_URL = 'https://cipherlacuna.ae/apk'
SHOWN_URL = 'cipherlacuna.ae/apk'
QR_LIB = 'https://cdnjs.cloudflare.com/ajax/libs/qrcode-generator/1.4.4/qrcode.min.js'
QUIET = 4  # modules of white border the QR standard asks for

FONT = 'Arial,Helvetica,sans-serif'
FONT_AR = 'Arial,Tahoma,"Segoe UI","Noto Sans Arabic","Noto Naskh Arabic",sans-serif'
BASE_CSS = f'''html,body{{margin:0;overflow:hidden}}
body{{position:relative;background:#F5F8FF;font-family:{FONT};color:#0E1222}}
.rule{{position:absolute;inset:0 0 auto 0;height:12px;background:linear-gradient(90deg,#42208D,#753ACA 38%,#D52F89 72%,#22D4D6)}}
.glow{{position:absolute;border-radius:50%;filter:blur(8px)}}
.name{{font-weight:700;line-height:1;letter-spacing:-1px;white-space:nowrap}}
.name b{{font-weight:700;background:linear-gradient(100deg,#42208D,#753ACA 48%,#D52F89);-webkit-background-clip:text;background-clip:text;color:transparent}}
.ar{{font-family:{FONT_AR}}}
.qrbox{{background:#fff;border-radius:28px;box-shadow:0 10px 40px #42208D22, 0 0 0 2px #E4E0F5;display:flex;flex-direction:column;align-items:center}}
.qrbox img{{display:block;image-rendering:pixelated}}
.url{{font-weight:700;color:#42208D;white-space:nowrap}}'''


def qr_matrix(page):
    """Rows of booleans (dark module = True) for SHARE_URL, error correction M, smallest version that fits."""
    page.add_script_tag(url=QR_LIB)
    return page.evaluate("""url => { const q = qrcode(0, 'M'); q.addData(url, 'Byte'); q.make();
        const n = q.getModuleCount(), rows = [];
        for (let r = 0; r < n; r++) { const row = []; for (let c = 0; c < n; c++) row.push(q.isDark(r, c)); rows.push(row); }
        return rows; }""", SHARE_URL)


def qr_svg(rows):
    """Crisp vector QR: one path of 1 x 1 squares on a white background, QUIET modules of margin on every side."""
    n = len(rows) + 2 * QUIET
    cells = ''.join(f'M{c + QUIET} {r + QUIET}h1v1h-1z' for r, row in enumerate(rows) for c, dark in enumerate(row) if dark)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {n} {n}" shape-rendering="crispEdges" role="img" '
            f'aria-label="QR code for {SHOWN_URL}"><rect width="{n}" height="{n}" fill="#fff"/>'
            f'<path fill="#0E1222" d="{cells}"/></svg>\n')


def data_uri(path_or_text, kind='svg'):
    raw = path_or_text.read_bytes() if isinstance(path_or_text, Path) else path_or_text.encode('utf-8')
    return f'data:image/svg+xml;base64,{base64.b64encode(raw).decode("ascii")}'


def og_html(logo, qr):
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><style>{BASE_CSS}
html,body{{width:1200px;height:630px}}
.g1{{width:620px;height:620px;right:-230px;top:-300px;background:radial-gradient(closest-side,#753ACA2e,#753ACA00)}}
.g2{{width:560px;height:560px;left:-220px;bottom:-310px;background:radial-gradient(closest-side,#22D4D633,#22D4D600)}}
.wrap{{position:absolute;inset:12px 0 0 0;display:flex;align-items:center;justify-content:space-between;padding:0 76px}}
.left{{display:flex;flex-direction:column;align-items:flex-start}}
.brand{{display:flex;align-items:center;gap:20px}}
.brand img{{width:112px;height:112px}}
.name{{font-size:60px}}
.h{{font-size:64px;font-weight:700;margin:38px 0 6px;line-height:1.05}}
.h.ar{{font-size:54px;margin:0 0 26px;color:#42208D}}
.sub{{font-size:28px;color:#475069;line-height:1.35}}
.sub.ar{{font-size:30px;margin-top:4px}}
.qrbox{{padding:26px 26px 18px}}
.qrbox img{{width:300px;height:300px}}
.url{{font-size:26px;margin-top:12px}}
</style></head><body><div class="rule"></div><div class="glow g1"></div><div class="glow g2"></div>
<div class="wrap"><div class="left">
<div class="brand"><img src="{logo}" alt=""><div class="name">Cipher <b>Lacuna</b></div></div>
<div class="h">Android app</div><div class="h ar" lang="ar" dir="rtl">تطبيق Android</div>
<div class="sub">Free · AI hardware, AI news, UAE AI, Learn AI</div>
<div class="sub ar" lang="ar" dir="rtl">مجاني · بالعربية والإنجليزية</div></div>
<div class="qrbox"><img src="{qr}" alt=""><div class="url">{SHOWN_URL}</div></div></div></body></html>'''


def card_html(logo, qr):
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><style>{BASE_CSS}
html,body{{width:1080px;height:1350px}}
.rule{{height:16px}}
.g1{{width:760px;height:760px;right:-300px;top:-320px;background:radial-gradient(closest-side,#753ACA2e,#753ACA00)}}
.g2{{width:700px;height:700px;left:-300px;bottom:-300px;background:radial-gradient(closest-side,#22D4D633,#22D4D600)}}
.wrap{{position:absolute;inset:16px 0 0 0;display:flex;flex-direction:column;align-items:center;padding-top:74px;text-align:center}}
.brand{{display:flex;align-items:center;gap:22px}}
.brand img{{width:120px;height:120px}}
.name{{font-size:66px}}
.h{{font-size:62px;font-weight:700;margin-top:52px;line-height:1.1}}
.h.ar{{font-size:58px;margin-top:10px;color:#42208D;line-height:1.3}}
.feat{{font-size:30px;color:#475069;margin-top:22px}}
.feat.ar{{font-size:31px;margin-top:6px}}
.qrbox{{margin-top:46px;padding:30px 30px 22px}}
.qrbox img{{width:420px;height:420px}}
.scan{{font-size:30px;font-weight:700;margin-top:16px}}
.scan .ar{{color:#42208D}}
.url{{font-size:30px;margin-top:6px}}
.note{{position:absolute;bottom:42px;left:50%;transform:translateX(-50%);white-space:nowrap;font-size:24px;color:#6B7390}}
</style></head><body><div class="rule"></div><div class="glow g1"></div><div class="glow g2"></div>
<div class="wrap">
<div class="brand"><img src="{logo}" alt=""><div class="name">Cipher <b>Lacuna</b></div></div>
<div class="h">Get the Android app</div><div class="h ar" lang="ar" dir="rtl">حمّل تطبيق Android</div>
<div class="feat">AI hardware · AI news · UAE AI · Learn AI</div>
<div class="feat ar" lang="ar" dir="rtl">عتاد الذكاء الاصطناعي · الأخبار · الإمارات · تعلّم الذكاء الاصطناعي</div>
<div class="qrbox"><img src="{qr}" alt=""><div class="scan">Scan to download · <span class="ar" lang="ar" dir="rtl">امسح الرمز للتنزيل</span></div>
<div class="url">{SHOWN_URL}</div></div></div>
<div class="note">Free · Android 8.0 or newer · <span class="ar" lang="ar" dir="rtl">مجاني · Android 8.0 أو أحدث</span></div>
</body></html>'''


def shot(page, html, width, height, out, check):
    page.set_viewport_size({'width': width, 'height': height})
    page.set_content(html, wait_until='load')
    page.evaluate('document.fonts.ready')
    # Every block must sit inside the picture with a margin (chat apps crop the edges a little).
    boxes = page.evaluate(f"[...document.querySelectorAll('{check}')].map(e => {{ const r = e.getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom]; }})")
    for b in boxes:
        assert b[0] >= 30 and b[1] >= 30 and b[2] <= width - 30 and b[3] <= height - 30, f'{out.name}: block outside the picture {b}'
    page.screenshot(path=str(out), clip={'x': 0, 'y': 0, 'width': width, 'height': height})


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit('Playwright is needed: pip install playwright && python -m playwright install chromium')
    logo = data_uri(BRAND / 'logo.svg')
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(device_scale_factor=1)
        page.set_content('<!doctype html><meta charset="utf-8">')
        rows = qr_matrix(page)
        svg = qr_svg(rows)
        (BRAND / 'app-qr.svg').write_text(svg, encoding='utf-8', newline='\n')
        qr = data_uri(svg)
        page.set_viewport_size({'width': 1024, 'height': 1024})
        page.set_content(f'<!doctype html><style>html,body{{margin:0}}img{{display:block;width:1024px;height:1024px;image-rendering:pixelated}}</style><img src="{qr}" alt="">', wait_until='load')
        page.screenshot(path=str(BRAND / 'app-qr.png'), clip={'x': 0, 'y': 0, 'width': 1024, 'height': 1024})
        shot(page, og_html(logo, qr), 1200, 630, BRAND / 'app-og.png', '.left, .qrbox')
        shot(page, card_html(logo, qr), 1080, 1350, BRAND / 'app-card.png', '.brand, .h, .feat, .qrbox, .note')
        browser.close()
    print(f'QR version {(len(rows) - 17) // 4} ({len(rows)} x {len(rows)} modules) for {SHARE_URL}; wrote app-qr.svg, app-qr.png, app-og.png, app-card.png in {BRAND.relative_to(ROOT)}')


if __name__ == '__main__':
    main()
