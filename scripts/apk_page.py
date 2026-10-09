"""The app share page: https://cipherlacuna.ae/apk (dist/apk/index.html), the link to send to friends.

Shared in WhatsApp (or any chat), the link shows a preview card (brand/app-og.png, made by make_app_share.py).
- Android phone: the page starts the download of download/Cipher-Lacuna.apk by itself, once per visit (a tap on the
  button cancels the timer, so the file never arrives twice), shows the install steps, and says the download started
  only when it really asked for it.
- iPhone (no app yet): it shows how to add the WEBSITE to the Home Screen, from the home page, so the icon never
  depends on this page. A Home Screen launch of this page itself still goes to the website (fallback).
- Inside another app's browser (Instagram, Facebook, TikTok, Snapchat, Android WebViews), which can neither install
  an APK nor add a Home Screen icon: no automatic download, and a note to open the page in the phone's browser.
- Computer: both sections and the QR code (brand/app-qr.svg) to scan with a phone. A Share button sends the link on.

Both languages are on the page, English first, like the share images. The page is self-contained (inline style,
script, logo and QR code as data: images) and makes no outside request. It is written on every build: without a
checked APK it says the Android download is not available right now and keeps the iPhone steps, so the link and
the QR codes already shared never lead to a missing page.
"""
import html
from pathlib import Path

import android_app

DIR = 'apk'                                    # dist/apk/index.html -> https://cipherlacuna.ae/apk/
URL = android_app.SITE_URL + DIR               # the address people share (the server adds the final slash)
SHOWN = 'cipherlacuna.ae/apk'
OG_IMAGE = android_app.SITE_URL + 'brand/app-og.png'
APK = f'../{android_app.PUBLIC_APK}'
E = html.escape

TITLE_EN = 'Cipher Lacuna for Android'
TITLE_AR = 'تطبيق Cipher Lacuna لأجهزة Android'
TITLE_NO_APK = 'Cipher Lacuna on your phone'
TITLE_NO_APK_AR = 'Cipher Lacuna على هاتفك'
ABOUT_EN = 'Cipher Lacuna on your phone, free: hardware, AI news, UAE AI and Learn AI in English and Arabic.'
ABOUT_AR = 'Cipher Lacuna على هاتفك مجاناً: العتاد وأخبار الذكاء الاصطناعي والإمارات وتعلّم الذكاء الاصطناعي بالعربية والإنجليزية.'
APP_EN = 'The Android app also tells you when new AI news arrives.'
APP_AR = 'ويُعلمك تطبيق Android بوصول أخبار الذكاء الاصطناعي الجديدة.'
INAPP_EN = ('This page is open inside another app, which cannot install apps or add icons. Open it in your phone\'s browser '
            'first: tap <b>•••</b> or <b>⋮</b> and choose <b>Open in browser</b> (Open in Safari or Open in Chrome).')
INAPP_AR = ('هذه الصفحة مفتوحة داخل تطبيق آخر لا يستطيع تثبيت التطبيقات أو إضافة الأيقونات. افتحها أولاً في متصفح هاتفك: '
            'اضغط <b>•••</b> أو <b>⋮</b> واختر <b>الفتح في المتصفح</b> (Safari أو Chrome).')
STEPS_EN = ('On an Android phone the download starts by itself; if not, tap <b>Download</b>. If your browser warns about the file type, choose <b>Download anyway</b>.',
            'Open the file from the notification or from Downloads.',
            'If Android asks, allow installs from the app that opened the file (your browser, or Files if you opened it from Downloads), then tap <b>Install</b>.',
            'If Google Play Protect shows a warning, tap <b>More details</b> and then <b>Install anyway</b>, or choose <b>Scan app</b>.')
STEPS_AR = ('على هاتف Android يبدأ التنزيل تلقائياً، وإن لم يبدأ فاضغط <b>نزّل التطبيق</b>. وإذا حذّرك المتصفح من نوع الملف فاختر <b>التنزيل على أي حال</b>.',
            'افتح الملف من الإشعار أو من مجلد التنزيلات.',
            'إذا طلب Android ذلك، فاسمح بالتثبيت من التطبيق الذي فتح الملف (المتصفح، أو تطبيق الملفات إن فتحته من مجلد التنزيلات)، ثم اضغط <b>تثبيت</b>.',
            'إذا ظهر تنبيه من Google Play Protect فاضغط <b>مزيد من التفاصيل</b> ثم <b>التثبيت على أي حال</b>، أو اختر <b>فحص التطبيق</b>.')
IOS_EN = ('Use <b>Safari</b>. If this page opened inside Instagram, Facebook or another app, tap <b>•••</b> (or the compass) and choose <b>Open in external browser</b> or <b>Open in Safari</b>.',
          'Tap <b>Open the website</b> above. On the website, tap <b>Share</b> (the square with an arrow); if you don\'t see it, tap <b>•••</b> first, then Share.',
          'Scroll down (or tap <b>View More</b>), choose <b>Add to Home Screen</b>, keep it opening as a web app if asked, then tap <b>Add</b>.')
IOS_AR = ('استخدم <b>Safari</b>. وإذا فُتحت هذه الصفحة داخل Instagram أو Facebook أو تطبيق آخر فاضغط <b>•••</b> (أو زر البوصلة) واختر <b>الفتح في متصفح خارجي</b> أو <b>فتح في Safari</b>.',
          'اضغط <b>افتح الموقع</b> أعلاه، ثم اضغط في الموقع زر <b>المشاركة</b> (المربع والسهم)؛ وإذا لم تجده فاضغط <b>•••</b> أولاً ثم «مشاركة».',
          'مرّر للأسفل (أو اضغط <b>عرض المزيد</b>) واختر <b>إضافة إلى الشاشة الرئيسية</b>، وأبقِ خيار فتحه كتطبيق ويب مفعّلاً إن ظهر، ثم اضغط <b>إضافة</b>.')

steps = lambda items: ''.join(f'<li>{s}</li>' for s in items)


def android_sections(info, qr):
    """The Android download card and install steps, or, without a checked APK, a short 'not available' card."""
    if not info:
        return ('<section class="card for-android"><p class="kicker">Android</p>'
                '<p>The Android download is not available right now. Please try again later, or use the website.<br>'
                '<span lang="ar" dir="rtl">تنزيل تطبيق Android غير متاح حالياً. حاول لاحقاً، أو استخدم الموقع.</span></p>'
                '<a class="btn2" href="../">Open the website · <span lang="ar">افتح الموقع</span></a></section>')
    v, mb, need = E(info['version']), android_app.size_mb(info['size']), android_app.MIN_ANDROID
    return f'''<section class="card for-android">
<p class="kicker">Android</p>
<p>{APP_EN}<br><span lang="ar" dir="rtl">{APP_AR}</span></p>
<a class="dl" id="dl" href="{APK}" download="{android_app.ASSET}" type="application/vnd.android.package-archive">Download for Android <small lang="ar">· نزّل التطبيق</small></a>
<p class="meta">Version <bdi>{v}</bdi> · <bdi>{mb}</bdi> MB · Android <bdi>{need}</bdi> or newer · Free<br><span lang="ar" dir="rtl">الإصدار <bdi>{v}</bdi> · <bdi>{mb}</bdi> ميجابايت · <bdi>Android {need}</bdi> أو أحدث · مجاني</span></p>
<p class="status" id="st" role="status" hidden>Your download should start now. If nothing happens, tap Download.<br><span lang="ar" dir="rtl">سيبدأ التنزيل الآن. وإذا لم يحدث شيء فاضغط «نزّل التطبيق».</span></p>
{qr}
</section>
<section class="card cols for-android">
<div><h2>How to install on Android</h2><ol>{steps(STEPS_EN)}</ol></div>
<div lang="ar" dir="rtl"><h2>طريقة التثبيت على Android</h2><ol>{steps(STEPS_AR)}</ol></div>
<p class="muted">Not from Google Play. Each new version installs over the old one and keeps your settings.<br><span lang="ar" dir="rtl">التطبيق ليس من Google Play، ويُثبَّت كل إصدار جديد فوق القديم مع الاحتفاظ بإعداداتك.</span></p>
<details><summary>Check the file (SHA-256) · <span lang="ar">تحقق من الملف</span></summary><code lang="en" dir="ltr">{E(info["sha256"])}</code></details>
</section>'''


def render(info, logo_uri='', icon_uri='', qr_uri=''):
    """The page; `info` is the checked APK of android_app.load() (version, size, SHA-256), or None without one."""
    if info:
        v, mb = E(info['version']), android_app.size_mb(info['size'])
        title, title_ar = TITLE_EN, TITLE_AR
        desc = (f'Free Android app: AI hardware, AI news, UAE AI and Learn AI in English and Arabic. Version {v}, {mb} MB, '
                f'Android {android_app.MIN_ANDROID} or newer. On iPhone, add the website to your Home Screen.')
    else:
        title, title_ar = TITLE_NO_APK, TITLE_NO_APK_AR
        desc = ('Cipher Lacuna on your phone: AI hardware, AI news, UAE AI and Learn AI in English and Arabic. '
                'On iPhone, add the website to your Home Screen.')
    logo = f'<img class="logo" src="{logo_uri}" alt="">' if logo_uri else ''
    qr = (f'<figure class="qr"><img src="{qr_uri}" width="220" height="220" alt="QR code for {SHOWN}">'
          f'<figcaption>Scan with an Android phone<br><span lang="ar" dir="rtl">امسح الرمز بهاتف Android</span></figcaption></figure>') if qr_uri else ''
    return f'''<!doctype html>
<html lang="en" dir="ltr" data-device="other"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<meta name="color-scheme" content="light dark"><meta name="theme-color" content="#6537d7">
<title>{title} | {title_ar}</title><meta name="description" content="{E(desc)}">
<link rel="canonical" href="{URL}/"><link rel="icon" type="image/png" sizes="32x32" href="../brand/icon-32.png">{f'<link rel="icon" type="image/svg+xml" href="{icon_uri}">' if icon_uri else ''}<link rel="apple-touch-icon" href="../brand/apple-touch-icon.png">
<meta name="apple-mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-title" content="Cipher Lacuna"><meta name="apple-mobile-web-app-status-bar-style" content="default">
<meta property="og:type" content="website"><meta property="og:site_name" content="Cipher Lacuna"><meta property="og:title" content="{title}">
<meta property="og:description" content="{E(desc)}"><meta property="og:url" content="{URL}/">
<meta property="og:image" content="{OG_IMAGE}"><meta property="og:image:type" content="image/png"><meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">
<meta property="og:image:alt" content="Cipher Lacuna Android app, with a QR code for {SHOWN}"><meta property="og:locale" content="en_US"><meta property="og:locale:alternate" content="ar_AE">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="{title}"><meta name="twitter:description" content="{E(desc)}"><meta name="twitter:image" content="{OG_IMAGE}">
<style>
:root{{--bg:#F5F8FF;--card:#fff;--ink:#0E1222;--muted:#5A6380;--line:#E4E0F5;--accent:#6537d7;--accent-ink:#fff;--deep:#42208D;--soft:#F1ECFD;--warn:#FFF4DB;--warn-line:#F0D48A}}
@media (prefers-color-scheme:dark){{:root{{--bg:#0E1222;--card:#161b30;--ink:#EEF0FA;--muted:#A6AEC8;--line:#2A3150;--accent:#8A63F0;--deep:#B9A2FF;--soft:#211d3d;--warn:#3a2f14;--warn-line:#6b5520}}}}
*{{box-sizing:border-box}}
[hidden]{{display:none!important}}
body{{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 "Segoe UI",system-ui,-apple-system,Roboto,Arial,sans-serif}}
[lang="ar"]{{font-family:"Segoe UI",Tahoma,"Geeza Pro","Noto Sans Arabic","Noto Naskh Arabic",Arial,sans-serif;line-height:1.75}}
.rule{{height:6px;background:linear-gradient(90deg,#42208D,#753ACA 38%,#D52F89 72%,#22D4D6)}}
main{{max-width:560px;margin:0 auto;padding:28px 16px 40px}}
.brand{{display:flex;align-items:center;gap:12px;text-decoration:none;color:inherit;font-weight:700;font-size:22px}}
.brand b{{color:var(--deep)}}
.logo{{width:44px;height:44px;margin:-6px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:22px 20px;margin-top:18px}}
h1{{margin:0;font-size:28px;line-height:1.2}}
h1 span{{display:block;color:var(--deep);font-size:24px;margin-top:4px}}
p{{margin:10px 0 0}}
.muted{{color:var(--muted);font-size:14.5px}}
.kicker{{margin:0 0 4px;font-size:13px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}}
.inapp-note{{display:none;margin-top:14px;padding:12px 14px;border-radius:12px;background:var(--warn);border:1px solid var(--warn-line);font-size:15px}}
.inapp .inapp-note{{display:block}}
.dl{{display:flex;align-items:center;justify-content:center;gap:10px;margin-top:16px;padding:15px 18px;border-radius:14px;background:var(--accent);color:var(--accent-ink);
  font-weight:700;font-size:18px;text-decoration:none;text-align:center}}
.dl:focus-visible,.share:focus-visible,a:focus-visible{{outline:3px solid #22D4D6;outline-offset:2px}}
.dl small{{font-weight:600;opacity:.9}}
.btn2{{display:block;margin-top:16px;padding:13px 16px;border-radius:14px;border:2px solid var(--accent);color:var(--deep);font-weight:700;text-align:center;text-decoration:none}}
.meta{{text-align:center;color:var(--muted);font-size:14px;margin-top:10px}}
.status{{margin-top:14px;padding:12px 14px;border-radius:12px;background:var(--soft);font-size:15px}}
[data-device="android"] .for-ios,[data-device="ios"] .for-android{{display:none}}
h2{{font-size:17px;margin:0 0 6px}}
ol{{margin:0;padding-inline-start:22px}} li{{margin:5px 0}}
.cols{{display:grid;gap:16px}}
.qr{{margin:18px auto 0;text-align:center;display:none}}
[data-device="other"] .qr{{display:block}}
.qr img{{display:block;margin:0 auto;border-radius:14px;border:1px solid var(--line);image-rendering:pixelated;background:#fff}}
.qr figcaption{{color:var(--muted);font-size:14px;margin-top:8px}}
.share-row{{display:flex;flex-wrap:wrap;align-items:center;justify-content:center;gap:10px;margin-top:18px}}
.share{{font:inherit;font-weight:600;color:var(--deep);background:var(--soft);border:1px solid var(--line);border-radius:999px;padding:9px 16px;cursor:pointer}}
code{{font:600 15px ui-monospace,Consolas,monospace;color:var(--deep)}}
.foot{{text-align:center;margin-top:22px;font-size:14.5px}}
.foot a{{color:var(--deep)}}
details{{margin-top:12px;font-size:13.5px;color:var(--muted)}} details code{{font-size:12px;overflow-wrap:anywhere;color:var(--muted)}}
</style></head><body><div class="rule"></div>
<main>
<a class="brand" href="../">{logo}<span>Cipher <b>Lacuna</b></span></a>
<section class="card">
<h1>Cipher Lacuna on your phone<span lang="ar" dir="rtl">Cipher Lacuna على هاتفك</span></h1>
<p>{ABOUT_EN}</p>
<p lang="ar" dir="rtl">{ABOUT_AR}</p>
<p class="inapp-note" role="note">{INAPP_EN}<br><span lang="ar" dir="rtl">{INAPP_AR}</span></p>
</section>
{android_sections(info, qr)}
<section class="card cols for-ios" id="iphone">
<p class="kicker">iPhone</p>
<p>No iPhone app yet. Add the website to your Home Screen: its icon opens Cipher Lacuna full screen, like an app.<br><span lang="ar" dir="rtl">لا يوجد تطبيق لـ iPhone بعد. أضف الموقع إلى الشاشة الرئيسية، فتفتح أيقونته Cipher Lacuna بملء الشاشة مثل التطبيق.</span></p>
<a class="btn2" href="../">Open the website · <span lang="ar">افتح الموقع</span></a>
<div><h2>Add to Home Screen</h2><ol>{steps(IOS_EN)}</ol></div>
<div lang="ar" dir="rtl"><h2>الإضافة إلى الشاشة الرئيسية</h2><ol>{steps(IOS_AR)}</ol></div>
</section>
<div class="share-row"><button class="share" id="share" type="button">Share this link · <span lang="ar">شارك الرابط</span></button><code>{SHOWN}</code></div>
<p class="foot"><a href="../">Open the website · <span lang="ar">افتح الموقع</span></a></p>
</main>
<script>
(() => {{
  const ua = navigator.userAgent || '', root = document.documentElement;
  // Opened from a Home Screen icon made from this page: go to the website itself.
  if (navigator.standalone === true || (window.matchMedia && matchMedia('(display-mode: standalone)').matches)) {{ location.replace('../'); return; }}
  const android = /Android/i.test(ua), ios = /iPhone|iPad|iPod/i.test(ua) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  // Another app's built-in browser (Instagram, Facebook, TikTok, Snapchat, LINE, Android WebViews) can neither install an APK nor add an icon.
  const inApp = /; wv\\)|Instagram|FBAN|FBAV|FB_IAB|FBIOS|musical_ly|BytedanceWebview|Snapchat|Line\\//i.test(ua);
  root.dataset.device = android ? 'android' : ios ? 'ios' : 'other';
  if (inApp) root.classList.add('inapp');
  const dl = document.getElementById('dl'), st = document.getElementById('st');
  if (android && !inApp && dl) {{
    // Start the download once per visit: a reload or a return to the page does not start another one.
    let done = false;
    try {{ done = sessionStorage.getItem('apk-started') === '1'; }} catch (e) {{}}
    if (history.state && history.state.apk) done = true;
    const mark = () => {{ try {{ sessionStorage.setItem('apk-started', '1'); }} catch (e) {{}} try {{ history.replaceState({{ apk: 1 }}, ''); }} catch (e) {{}} }};
    const t = done ? 0 : setTimeout(() => {{ mark(); st.hidden = false; location.href = dl.href; }}, 900);
    dl.addEventListener('click', () => {{ clearTimeout(t); mark(); st.hidden = false; }});
  }}
  const btn = document.getElementById('share'), url = '{URL}';
  btn.addEventListener('click', async () => {{
    if (navigator.share) {{ try {{ await navigator.share({{ title: '{title}', text: 'Cipher Lacuna · تطبيق Cipher Lacuna', url }}); }} catch (e) {{}} return; }}
    try {{ await navigator.clipboard.writeText(url); btn.textContent = 'Link copied · تم نسخ الرابط'; }} catch (e) {{ prompt('Copy the link', url); }}
  }});
}})();
</script>
</body></html>
'''


def build(out_dir, info, logo_uri='', icon_uri='', qr_uri=''):
    """Write <out_dir>/apk/index.html on every build: with the download for a checked APK, or, without one, a page that
    says the Android download is unavailable and keeps the iPhone steps (shared links and QR codes never break)."""
    target = Path(out_dir) / DIR
    target.mkdir(parents=True, exist_ok=True)
    page = target / 'index.html'
    page.write_text(render(info, logo_uri, icon_uri, qr_uri), encoding='utf-8', newline='\n')
    return page
