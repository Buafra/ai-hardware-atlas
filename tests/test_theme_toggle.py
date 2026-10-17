"""The light/dark switch of the small stand-alone pages (scripts/theme_toggle.py): the weekly pages, /apk/ and 404.html
follow the overview's saved choice (atlas-theme: auto, light or dark) and can change it."""
import re
import sys
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import apk_page  # noqa: E402
import seo  # noqa: E402
import theme_toggle  # noqa: E402
import weekly  # noqa: E402

SOURCES = [{'id': 'g', 'name': 'Global Pub', 'name_ar': 'ناشر عالمي', 'homepage': 'https://g.example/', 'region': 'global', 'lang': 'en'}]
STORY = {'id': 's1', 'source': 'g', 'lang': 'en', 'uae': False, 'published': '2026-10-16T09:00:00+00:00',
         'title': 'NVIDIA ships a new GPU', 'url': 'https://g.example/1'}


def pages():
    """Every page with the switch: the weekly pages in both languages, the app share page and the 404 page."""
    out, _ = weekly.pages([STORY], [], SOURCES, datetime(2026, 10, 17, 8, tzinfo=timezone.utc), logo='', since=date(2026, 10, 12))
    out = {path: (page, 'ar' if path.startswith('ar/') else 'en') for path, page in out.items()}
    out['apk/index.html'] = (apk_page.render(None), 'both')
    out['404.html'] = (seo.page_404(), 'both')
    return out


class ThemeToggleTests(unittest.TestCase):
    def test_same_key_and_icon_as_the_overview(self):
        self.assertIn(f"localStorage.getItem('{theme_toggle.KEY}')", (ROOT / 'web' / 'template.html').read_text(encoding='utf-8'))
        self.assertIn(f"store.set('{theme_toggle.KEY}', theme)", (ROOT / 'web' / 'app.js').read_text(encoding='utf-8'))
        build = (ROOT / 'scripts' / 'build.py').read_text(encoding='utf-8')
        self.assertIn('M12 3.5a8.5 8.5 0 0 1 0 17z', build)  # the overview's theme icon

    def test_every_page_has_the_switch(self):
        for path, (page, lang) in pages().items():
            head = page[:page.index('</head>')]
            self.assertEqual(page.count(theme_toggle.HEAD), 1, path)
            self.assertIn(theme_toggle.HEAD, head, path)  # a saved choice applies before the first paint
            self.assertEqual(page.count('id="theme"'), 1, path)
            self.assertEqual(page.count(theme_toggle.script(lang)), 1, path)
            self.assertLess(page.index('id="theme"'), page.index(theme_toggle.script(lang)), path)  # the script finds the button
            self.assertIn('<button type="button" class="theme-btn" id="theme"', page, path)

    def test_labels(self):
        self.assertIn('aria-label="Theme: Auto"><svg', theme_toggle.button('en'))
        self.assertIn('<span id="theme-label">تلقائي</span>', theme_toggle.button('ar'))
        self.assertIn('aria-label="المظهر: تلقائي"', theme_toggle.button('ar'))
        self.assertIn('<span id="theme-label">Auto · تلقائي</span>', theme_toggle.button('both'))
        js = theme_toggle.script('en')
        self.assertIn("auto:['Auto','Theme: Auto'],light:['Light','Theme: Light'],dark:['Dark','Theme: Dark']", js)
        self.assertIn("{auto:'light',light:'dark',dark:'auto'}[t]", js)  # the overview's order
        self.assertIn(f"localStorage.setItem('{theme_toggle.KEY}',t)", js)
        self.assertEqual(js.count('try{'), 2)  # storage that throws (private windows, blocked site data) breaks nothing

    def test_dark_colours_follow_the_choice(self):
        css = theme_toggle.dark_css('--bg:#000')
        self.assertEqual(css, '@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#000}}:root[data-theme="dark"]{--bg:#000}')
        weekly_css = (ROOT / 'web' / 'weekly.css').read_text(encoding='utf-8')
        for page in (weekly_css, apk_page.render(None), seo.page_404()):
            self.assertIn('@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){', page)
            self.assertIn(':root[data-theme="dark"]{', page)
            self.assertNotRegex(page, r'@media \(prefers-color-scheme:dark\)\{:root\{')  # no dark block that ignores the choice
            self.assertIn('.theme-btn{', page)
        # The two dark blocks of the weekly pages hold the same colours.
        blocks = re.findall(r':root(?::not\(\[data-theme="light"\]\)|\[data-theme="dark"\])\{([^}]*)\}', weekly_css)
        self.assertEqual(len(blocks), 2)
        self.assertEqual(blocks[0], blocks[1])

    def test_scripts_allowed_by_the_share_page_policy(self):
        page = apk_page.render(None)
        self.assertIn("script-src 'unsafe-inline'", page)


if __name__ == '__main__':
    unittest.main()
