import json,re,sys,tempfile,unittest
from pathlib import Path
from urllib.parse import unquote,urlparse
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import build
ROOT=Path(__file__).resolve().parents[1]

class BrandSlotTests(unittest.TestCase):
    def test_sanitize_strips_active_content_and_external_refs(self):
        dirty=('<?xml version="1.0"?><!-- c --><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" onload="alert(1)">'
               '<script>alert(2)</script><defs><linearGradient id="g"><stop offset="0"/></linearGradient></defs>'
               '<rect width="64" height="64" fill="url(#g)" onclick=\'x()\'/><use href="#g"/><image href="https://evil.example/x.png"/>'
               '<a href="javascript:alert(3)"><circle r="4" style="fill:url(https://evil.example/f)"/></a>'
               '<foreignObject><div onmouseover="y()">hi</div></foreignObject></svg>')
        s=build.sanitize_svg(dirty)
        self.assertTrue(s.startswith('<svg') and s.endswith('</svg>'))
        for bad in ('script','onload','onclick','onmouseover','javascript:','evil.example','foreignObject','<a ','<?xml','<!--'):self.assertNotIn(bad,s)
        self.assertIn('id="logo-g"',s);self.assertIn('url(#logo-g)',s);self.assertIn('href="#logo-g"',s)
        self.assertEqual(build.sanitize_svg('<div>not svg</div>'),'')
    # The logo is an <img> of a data: URI: whatever slips past the regex sanitiser, an SVG image runs no script and loads nothing.
    INERT=re.compile(r'^<img class="brand-logo" src="data:image/svg\+xml,[^"<>]*" alt="">$')
    PAYLOADS={
        'slash_onload':'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"/onload="window.__hit=1"><rect width="10" height="10"/></svg>',
        'nospace_img':'<svg viewBox="0 0 10 10"><rect width="10" height="10"/><img src="nope.png"onerror="window.__hit=1"></svg>',
        'split_script':'<svg viewBox="0 0 10 10"><scr<script>ipt>window.__hit=1</script x><rect width="10" height="10"/></svg>',
        'unquoted_href':'<svg viewBox="0 0 10 10"><image href=https://example.com/unquoted.png width="10" height="10"/></svg>',
        'img_src':'<svg viewBox="0 0 10 10"><rect width="10" height="10"/><img src="https://example.com/breakout.png"></svg>',
        'image_set':"<svg viewBox=\"0 0 10 10\" style=\"background-image:image-set('https://example.com/imageset.png' 1x)\"><rect width=\"10\" height=\"10\"/></svg>",
    }
    def test_logo_bypass_payloads_stay_inside_an_image(self):
        data,feed,sources,uae,models=build.load_all()
        for name,svg in self.PAYLOADS.items():
            with tempfile.TemporaryDirectory() as d:
                (Path(d)/'logo.svg').write_text(svg,encoding='utf-8')
                logo,_=build.brand_assets(Path(d))
                page,_=build.render_page(data,feed,sources,uae,models,brand_dir=Path(d))
            self.assertRegex(logo,self.INERT,name)
            header=page[page.index('<header'):page.index('</header>')]
            self.assertIn(logo,header,name)
            for raw in ('__hit','example.com','onerror','onload','<script','<image','<img src="nope'):self.assertNotIn(raw,header.replace(logo,''),name)
    def test_no_logo_means_wordmark_only_and_neutral_favicon(self):
        with tempfile.TemporaryDirectory() as d:
            logo,icon=build.brand_assets(Path(d))
        self.assertEqual(logo,'')
        svg=unquote(icon.split(',',1)[1])
        self.assertTrue(icon.startswith('data:image/svg+xml,'))
        self.assertEqual(re.findall(r'<(\w+)',svg),['svg','defs','linearGradient','stop','stop','stop','rect'])  # a gradient square, no letter or symbol
    def test_owner_logo_and_favicon_are_used(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d)/'logo.svg').write_text('<svg viewBox="0 0 64 64" width="64" height="64"><circle cx="32" cy="32" r="30" onclick="x()"/></svg>',encoding='utf-8')
            (Path(d)/'favicon.svg').write_text('<svg viewBox="0 0 32 32"><rect width="32" height="32"/><script>x()</script></svg>',encoding='utf-8')
            logo,icon=build.brand_assets(Path(d))
        self.assertRegex(logo,self.INERT)
        svg=unquote(logo.split(',',1)[1].split('"')[0])
        self.assertTrue(svg.startswith('<svg') and 'xmlns="http://www.w3.org/2000/svg"' in svg and '<circle' in svg,svg)
        self.assertNotIn('onclick',svg)
        self.assertIn('<rect',unquote(icon));self.assertNotIn('script',unquote(icon));self.assertIn('xmlns=',unquote(icon))

class BrandTests(unittest.TestCase):
    """The owner's Cipher Lacuna brand files, the page head and the share preview."""
    @classmethod
    def setUpClass(cls):
        cls.html,_=build.render_page(*build.load_all())
        cls.head=cls.html[:cls.html.index('<style>')]
    def meta(self,attr,name):
        m=re.search(r'<meta %s="%s" content="([^"]*)">'%(attr,re.escape(name)),self.head)
        self.assertTrue(m,name);return m.group(1)
    def test_owner_logo_and_favicon_are_shipped(self):
        logo,icon=build.brand_assets()
        self.assertRegex(logo,BrandSlotTests.INERT)
        self.assertIn(logo,self.html[self.html.index('<header'):self.html.index('</header>')])
        self.assertIn('<path',unquote(icon));self.assertNotIn('<rect width="32"',unquote(icon))  # not the placeholder square
    def test_head_title_description_and_share_preview(self):
        self.assertIn('<title>Cipher Lacuna | AI hardware, AI news and UAE AI</title>',self.head)
        self.assertIn('Cipher Lacuna',self.meta('name','description'))
        self.assertIn('<link rel="apple-touch-icon" href="brand/apple-touch-icon.png">',self.head)
        # PNG tab icon for browsers without SVG favicons, listed before the SVG one so the others keep using the SVG.
        png_icon='<link rel="icon" type="image/png" sizes="32x32" href="brand/icon-32.png">'
        self.assertIn(png_icon+'<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,',self.head)
        url='https://buafra.github.io/ai-hardware-atlas/'
        want={'og:type':'website','og:url':url,'og:image':url+'brand/og.png','og:image:width':'1200','og:image:height':'630','og:locale':'en_US','og:locale:alternate':'ar_AE'}
        for k,v in want.items():self.assertEqual(self.meta('property',k),v,k)
        self.assertTrue(self.meta('property','og:title').startswith('Cipher Lacuna'));self.assertIn('Cipher Lacuna',self.meta('property','og:description'))
        self.assertEqual(self.meta('name','twitter:card'),'summary_large_image');self.assertEqual(self.meta('name','twitter:image'),url+'brand/og.png')
        png=(ROOT/'web/brand/og.png').read_bytes()
        self.assertEqual((png[1:4],png[12:16]),(b'PNG',b'IHDR'));self.assertEqual((int.from_bytes(png[16:20],'big'),int.from_bytes(png[20:24],'big')),(1200,630))
        for f in ('apple-touch-icon.png','icon-512.png','icon-32.png'):self.assertTrue((ROOT/'web/brand'/f).exists(),f)
    def test_brand_pngs_are_copied_next_to_the_page(self):
        with tempfile.TemporaryDirectory() as d:
            names=build.copy_brand_images(Path(d)/'brand')
            self.assertEqual(sorted(names),sorted(f.name for f in (Path(d)/'brand').iterdir()))
        self.assertTrue({'og.png','apple-touch-icon.png','icon-512.png','icon-32.png'}<=set(names))
    def test_old_name_is_gone_and_taglines_translate(self):
        for f in ('web/template.html','web/app.js','scripts/build.py','README.md','web/brand/README.md'):
            self.assertNotIn('Cipher AI Knowledge',(ROOT/f).read_text(encoding='utf-8'),f)
        js=(ROOT/'web/app.js').read_text(encoding='utf-8')
        self.assertIn("'Decoding the gaps in AI knowledge':'كشف المجهول في عالم الذكاء الاصطناعي'",js)

class SiteChoicesTests(unittest.TestCase):
    def setUp(self):
        self.data,self.feed,self.sources,self.uae,self.models=build.load_all()
        self.ps,self.facts=self.data['products'],self.uae['facts']
    def pick(self,content):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'site.json'
            if content is not None:p.write_text(content,encoding='utf-8')
            return build.load_site(self.ps,self.facts,p)
    def test_owner_choices_in_order(self):
        f,h=self.pick(json.dumps({'featured_products':['gb300-nvl72','h200'],'uae_highlights':['jais-arabic-llm']}))
        self.assertEqual([p['id'] for p in f][:2],['gb300-nvl72','h200']);self.assertEqual(len(f),3)
        self.assertEqual([x['id'] for x in h],['jais-arabic-llm'])  # the landing shows one key fact
    def test_fallbacks(self):
        for content in (None,'{not json','[]',json.dumps({'featured_products':['nope','nope'],'uae_highlights':'x'})):
            f,h=self.pick(content)
            self.assertEqual(len(f),3,content);self.assertEqual(len({p['id'] for p in f}),3);self.assertEqual(len(h),build.UAE_HIGHLIGHTS,content)
    def test_repository_site_json(self):
        site=json.loads((ROOT/'data/site.json').read_text(encoding='utf-8'))
        ids={p['id'] for p in self.ps};fids={f['id'] for f in self.facts}
        self.assertTrue(set(site['featured_products'])<=ids);self.assertTrue(set(site['uae_highlights'])<=fids)

class CountTests(unittest.TestCase):
    def test_counts_match_app_js_rules(self):
        self.assertEqual(build.cnt(1,'product','en'),'1 product');self.assertEqual(build.cnt(53,'product','en'),'53 products')
        self.assertEqual(build.cnt(2,'product','ar'),'منتجان');self.assertEqual(build.cnt(5,'product','ar'),'5 منتجات')
        self.assertEqual(build.cnt(53,'product','ar'),'53 منتجاً');self.assertEqual(build.cnt(100,'headline','ar'),'100 عنوان')
        self.assertEqual(build.ymd('2017-10','ar'),'أكتوبر 2017');self.assertEqual(build.ymd('2026-09-26T22:30:00+00:00','en'),'27 Sep 2026')
    def test_dates_for_people_match_app_js(self):
        # Same expectations as tests/test-sort.cjs for when() in app.js.
        cases={('2025-Q3','en'):'Q3 2025',('2025-Q3','ar'):'الربع الثالث 2025',('2026-H2','ar'):'النصف الثاني 2026',('2025-Summer','en'):'Summer 2025',
               ('2025-Summer','ar'):'صيف 2025',('2026-end','en'):'End of 2026',('2026-end','ar'):'نهاية 2026',('2025-03-05','en'):'5 Mar 2025',
               ('2025-03-05','ar'):'5 مارس 2025',('2023-07','en'):'Jul 2023',('2026-09-26T22:30:00+00:00','ar'):'27 سبتمبر 2026'}
        for (v,lang),want in cases.items():self.assertEqual(build.when(v,lang),want,(v,lang))
        self.assertEqual(build.change_text('GeForce RTX 5070: power_w changed from None to 250'),'GeForce RTX 5070: power changed from not listed to 250 W')
        self.assertEqual(build.change_text('Added X after review.'),'Added X after review.')

class ScheduleAndLinkTests(unittest.TestCase):
    def test_schedule_text_matches_publish_cron(self):
        # The page says when it updates (from data/catalog.json schedule); the workflow cron must say the same, in UTC.
        data=json.loads((ROOT/'data/catalog.json').read_text(encoding='utf-8'))
        cron=re.search(r"cron:\s*'([^']+)'",(ROOT/'.github/workflows/publish.yml').read_text(encoding='utf-8')).group(1).split()
        uae=sorted(f'{(int(h)+4)%24:02d}:{int(cron[0]):02d}' for h in cron[1].split(','))
        self.assertEqual(sorted(build.schedule_times(data)),uae)
        # The page says how often, not at what times (no run statistics in public).
        self.assertEqual(build.schedule_phrase(data,'en'),'twice a day')
        self.assertEqual(build.schedule_phrase(data,'ar'),'مرتين يومياً')
        line=build.fresh_line({'updated_at':'2026-09-26T13:09:30+00:00'},data)
        self.assertEqual(line,build.L('Updated 26 Sep 2026 · twice a day','آخر تحديث 26 سبتمبر 2026 · مرتين يومياً'))
    def test_links_must_be_https(self):
        with self.assertRaises(AssertionError):build.validate_links([{'id':'x','homepage':'javascript:alert(1)'}],None)
        with self.assertRaises(AssertionError):build.validate_links([],{'facts':[{'id':'f','sources':[{'url':'http://x.example/'}]}]})
        items=build.news_items({'items':[{'source':'s','url':'javascript:x','published':'2026-01-01T00:00:00+00:00'},{'source':'s','url':'https://a.example/','published':'2026-01-01T00:00:00+00:00'}]},[{'id':'s'}])
        self.assertEqual([i['url'] for i in items],['https://a.example/'])

class PageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        data,feed,sources,uae,models=build.load_all()
        cls.data,cls.feed,cls.uae,cls.sources=data,feed,uae,sources
        with tempfile.TemporaryDirectory() as d:
            cls.html,cls.public=build.render_page(data,feed,sources,uae,models,brand_dir=Path(d))
    def test_every_view_rendered_and_visible_without_js(self):
        for v in ('home','hardware','news','uae','contact'):
            m=re.search(r'<(?:div|section) id="%s" [^>]*data-view="%s"[^>]*>'%(v,v),self.html)
            self.assertTrue(m,v);self.assertNotIn('hidden',m.group(0))
        self.assertEqual(self.html.count('class="product '),len(self.data['products']))
    def test_one_h1_per_view(self):
        main=self.html[self.html.index('<main'):self.html.index('</main>')]
        views=re.split(r'<(?:div|section) id="\w+" class="view',main)[1:]
        self.assertEqual(len(views),5)
        for chunk in views:self.assertEqual(chunk.count('<h1'),1,chunk[:20])
    def test_site_rules(self):
        self.assertNotIn('buafra@gmail.com',self.html)
        self.assertNotIn('announcements',self.public);self.assertNotIn('"announcements"',self.html)
        for tag in re.findall(r'<a\b[^>]*target="_blank"[^>]*>',self.html):self.assertIn('rel="noopener noreferrer"',tag)
        self.assertIsNone(re.search(r'<script[^>]+src=|<link[^>]+stylesheet|<img[^>]+src="(?:https?:)?//|url\((?:["\'])?(?:https?:)?//|@import',self.html))
        self.assertIsNone(re.search(r'__[A-Z][A-Z0-9_]*__',self.html))
        self.assertNotIn('brand-logo',self.html.split('<style>')[0]+self.html.split('</style>')[1])
        self.assertIn('<span class="wordmark" lang="en" dir="ltr">Cipher <span class="wm-2">Lacuna</span></span>',self.html)
        self.assertIn('<span class="tagline" data-i18n>Decoding the gaps in AI knowledge</span>',self.html)
        # On phones the header has no room for the tagline, so the hero repeats it under the name (CSS shows it there only).
        self.assertIn('</h1><p class="hero-tag" data-i18n>Decoding the gaps in AI knowledge</p>',self.html)
    def test_release_without_a_date(self):
        # A product with no availability date shows "Not established" plus its kind when the kind explains something (for
        # example "Not on NVIDIA's current roadmap"), never "Not established" twice and never a leftover "Expected"; every
        # kind used in the catalog has an Arabic translation in app.js.
        js=(ROOT/'web/app.js').read_text(encoding='utf-8')
        for kind in {p['release_kind'] for p in self.data['products']}:
            self.assertTrue(f"'{kind}':" in js or f'"{kind}":' in js,kind)
        for p in self.data['products']:
            if p['release'] is None:
                card=re.search(r'<article class="product [^"]*" id="p-%s".*?</article>'%re.escape(p['id']),self.html,re.S).group(0)
                cell=card[card.index('Availability / target'):card.index('Announced / launched')]
                self.assertIn('<span data-i18n>Not established</span>',cell,p['id'])
                if p['release_kind'] in (None,'','Not established'):
                    self.assertEqual(cell.count('Not established'),1,p['id']);self.assertNotIn('<small>',cell,p['id'])
                else:
                    self.assertIn(f"<small>{build.T(p['release_kind'])}</small>",cell,p['id'])
                self.assertNotIn('>Expected<',cell,p['id'])
        self.assertEqual(build.release_kind('Not established'),'');self.assertEqual(build.release_kind(None),'')
        self.assertEqual(build.release_kind('Released'),'<small><span data-i18n>Released</span></small>')
    def test_counts_are_honest(self):
        # UAE headlines in total plus the lists a reader can open in each language. The news link card gives the headline
        # count only: the pillar and #news already say how many sources are followed (see ReviewRoundTests).
        items=build.news_items(self.feed,self.sources)
        uae_items=[i for i in items if i.get('uae')]
        n_en,n_ar=sum(build.in_lang(i,'en') for i in uae_items),sum(build.in_lang(i,'ar') for i in uae_items)
        self.assertIn(f'<dt data-i18n>UAE headlines</dt><dd><bdi>{len(uae_items)}</bdi>',self.html)
        self.assertIn(f'<dt data-i18n>English · Arabic</dt><dd><bdi>{build.L(f"{n_en} · {n_ar}",f"{n_ar} · {n_en}")}</bdi>',self.html)
        self.assertIn(f'<dl class="side-stats">{build.stat(len(uae_items),"headlines")}{build.stat(n_en,"English")}{build.stat(n_ar,"Arabic")}</dl>',self.html)
        self.assertIn(f'{build.cnt(len(items),"headline","en")} in English and Arabic',self.html)
    def test_stats_and_featured_come_from_data(self):
        ps=self.data['products']
        self.assertIn(f'<dt data-i18n>products</dt><dd><bdi>{len(ps)}</bdi>',self.html)
        self.assertIn(f'<dt data-i18n>with approx. price</dt><dd><bdi>{sum(1 for p in ps if p["price_view"])}</bdi>',self.html)
        self.assertIn(f'<dt data-i18n>key facts</dt><dd><bdi>{len(self.uae["facts"])}</bdi>',self.html)
        for pid in json.loads((ROOT/'data/site.json').read_text(encoding='utf-8'))['featured_products']:self.assertIn(f'data-route="hardware/p/{pid}"',self.html)
    def test_no_content_hard_coded_in_template_or_script(self):
        shell=(ROOT/'web/template.html').read_text(encoding='utf-8')+(ROOT/'web/app.js').read_text(encoding='utf-8')
        for p in self.data['products']:self.assertNotIn(p['model'],shell)
        for f in self.uae['facts']:self.assertNotIn(f['title_en'],shell)
        for i in self.feed['items'][:40]:self.assertNotIn(i['title'],shell)

class NewsCardTests(unittest.TestCase):
    """Headline cards: title as text, a summary with who wrote it, then a small link to the original article and the date."""
    SRC={'s':{'id':'s','name':'Pub News','name_ar':'أخبار الناشر','homepage':'https://pub.example/','region':'global','lang':'en'},
         'a':{'id':'a','name':'Arabic Pub','name_ar':'ناشر عربي','homepage':'https://ar.example/','region':'uae','lang':'ar'}}
    BASE={'source':'s','lang':'en','published':'2026-09-26T12:00:00+00:00','uae':False}
    def card(self,lang,**kw):
        return build.news_card({**self.BASE,'id':'x','title':'NVIDIA ships a new chip','url':'https://pub.example/2026/chip',**kw},lang,self.SRC)
    def test_ai_summary_in_each_language(self):
        kw=dict(title_ar='إنفيديا تشحن شريحة جديدة',excerpt='Publisher text.',summary_en='NVIDIA began shipping the chip. It has <b>288 GB</b>.',summary_ar='بدأت NVIDIA شحن الشريحة.',summary_source='ai')
        en,ar=self.card('en',**kw),self.card('ar',**kw)
        self.assertIn('<h4 class="n-title" lang="en" dir="ltr">NVIDIA ships a new chip</h4><p class="n-sum" lang="en" dir="ltr">NVIDIA began shipping the chip. It has &lt;b&gt;288 GB&lt;/b&gt;.</p><p class="n-by">AI summary</p>',en)
        self.assertIn('<h4 class="n-title" lang="ar" dir="rtl">إنفيديا تشحن شريحة جديدة</h4><p class="n-sum" lang="ar" dir="rtl">بدأت NVIDIA شحن الشريحة.</p><p class="n-by">ملخص بالذكاء الاصطناعي</p>',ar)
        self.assertIn('<span class="mt">ترجمة بالذكاء الاصطناعي</span>',ar);self.assertNotIn('Publisher text.',en+ar)
        self.assertNotIn('class="mt"',en)  # the English page shows English headlines only, never a translation
    def test_source_link_goes_to_the_article(self):
        en,ar=self.card('en'),self.card('ar',title_ar='عنوان')
        self.assertIn('<p class="n-meta"><a class="n-src" href="https://pub.example/2026/chip" target="_blank" rel="noopener noreferrer">Source: Pub News <span class="n-ext" aria-hidden="true">↗</span></a>'
                      '<time datetime="2026-09-26T12:00:00+00:00">26 Sep, <bdi>16:00</bdi></time>',en)
        self.assertIn('>المصدر: أخبار الناشر <span class="n-ext" aria-hidden="true">↗</span></a><time datetime="2026-09-26T12:00:00+00:00">26 سبتمبر، <bdi>16:00</bdi></time>',ar)
        for c in (en,ar):
            self.assertNotIn('https://pub.example/"',c)  # never the publisher's homepage
            self.assertEqual(c.count('<a '),1);self.assertLess(c.index('</h4>'),c.index('<a '))  # the headline itself is not a link
    def test_publisher_excerpt_only_in_its_own_language(self):
        en=self.card('en',excerpt='The company said shipments start today.',title_ar='عنوان')
        self.assertIn('<p class="n-sum" lang="en" dir="ltr">The company said shipments start today.</p><p class="n-by">From the publisher</p>',en)
        self.assertNotIn('n-sum',self.card('ar',excerpt='The company said shipments start today.',title_ar='عنوان'))
        ar=build.news_card({**self.BASE,'source':'a','lang':'ar','id':'y','title':'عنوان عربي','url':'https://ar.example/1','excerpt':'نص من الناشر.'},'ar',self.SRC)
        self.assertIn('<p class="n-sum" lang="ar" dir="rtl">نص من الناشر.</p><p class="n-by">من الناشر</p>',ar)
        self.assertEqual(build.summary_of({'lang':'ar','excerpt':'نص'},'en'),(None,None))
    def test_no_summary_means_headline_and_link_only(self):
        c=self.card('en')
        self.assertNotIn('n-sum',c);self.assertNotIn('n-by',c)
        self.assertTrue(c.startswith('<h4 class="n-title"'));self.assertIn('class="n-src"',c)
        # A summary that isn't marked as the AI's own is not shown as one.
        self.assertNotIn('n-sum',self.card('en',summary_en='Unlabelled text.'))

class OwnerRequestTests(unittest.TestCase):
    """The owner's September 2026 requests: summaries, no public source list or run statistics, contact card, clearer
    estimator wording and the Qahwa & AI follow button on every page (the UAE flag of that round was later removed again)."""
    @classmethod
    def setUpClass(cls):
        data,feed,sources,uae,models=build.load_all()
        cls.feed,cls.sources=feed,sources
        with tempfile.TemporaryDirectory() as d:
            cls.html,_=build.render_page(data,feed,sources,uae,models,brand_dir=Path(d))
        cls.main=cls.html[cls.html.index('<main'):cls.html.index('</main>')]
        cls.views={v:cls.main[cls.main.index(f'data-view="{v}"'):] for v in ('home','hardware','news','uae','contact')}
        for v,nxt in (('home','hardware'),('hardware','news'),('news','uae'),('uae','contact')):
            cls.views[v]=cls.views[v][:cls.views[v].index(f'data-view="{nxt}"')]
    def test_headlines_have_summaries_and_article_links(self):
        items={i['url']:i for i in self.feed['items']}
        homes={s['homepage'] for s in self.sources}
        cards=re.findall(r'<h4 class="n-title".*?</p>(?=</li>)',self.main,re.S)
        self.assertGreater(len(cards),0)
        for c in cards:
            self.assertNotIn('<a',c[:c.index('</h4>')])  # the headline itself is plain text
            href=build.html.unescape(re.search(r'<a class="n-src" href="([^"]+)"',c).group(1))
            self.assertIn(href,items);self.assertNotIn(href,homes)
        # Every card in the #news lists shows exactly the summary the display rules pick for its language.
        news=self.views['news']
        pool=build.news_items(self.feed,self.sources)
        for lang,end in (('en','<div class="nlist" data-lang="ar">'),('ar','<div class="more-row')):
            start=news.index(f'<div class="nlist" data-lang="{lang}">')
            chunk=news[start:news.index(end,start)]
            want=[build.summary_of(i,lang) for i in pool if build.in_lang(i,lang)]
            self.assertEqual(chunk.count('class="n-sum"'),sum(1 for text,_ in want if text),lang)
            for kind in ('ai','publisher'):
                self.assertEqual(chunk.count(f'<p class="n-by">{build.SUMMARY_LABEL[kind][lang]}</p>'),sum(1 for _,k in want if k==kind),(lang,kind))
    # The site's own markup and labels for the source lists, fetch statistics and schedule that were removed. Headlines,
    # publisher excerpts and AI summaries are free text and may use any word ("reached 1 billion users", «استجابة»),
    # so the page is rendered from a fixed feed that uses such words, and only the site's own phrases are checked.
    REMOVED=('srcs-grid','class="panel srcs"','feeds responded','sources responded','responded in the latest run','sources reached',
             'data-i18n>News sources','مصادر الأخبار','nr-list','data-i18n>UAE newsrooms<','Checked at 07:15','Schedule:','Source check:',
             'Asia/Dubai','Configured in GitHub Actions','"check_health"','"automation_status"','"schedule"','"last_attempt_at"','الجدولة:','آخر فحص للمصادر')
    def test_no_public_source_list_or_run_statistics(self):
        data,_,sources,uae,models=build.load_all()
        by_region={r:next(s for s in sources if s['region']==r and s['lang']==l) for r,l in (('global','en'),('uae','ar'))}
        feed={'updated_at':'2026-09-26T13:09:30+00:00','items':[
            {'id':'f1','title':'ChatGPT has reached 1 billion weekly users','url':'https://'+build.urlparse(by_region['global']['homepage']).hostname+'/f1','source':by_region['global']['id'],'lang':'en','uae':False,
             'published':'2026-09-26T10:00:00+00:00','excerpt':'The company responded within a day; the schedule was checked at noon and the target was reached.'},
            {'id':'f2','title':'استجابة سريعة من الإمارات للذكاء الاصطناعي','url':'https://'+build.urlparse(by_region['uae']['homepage']).hostname+'/f2','source':by_region['uae']['id'],'lang':'ar','uae':True,
             'published':'2026-09-26T09:00:00+00:00','excerpt':'تم الوصول إلى اتفاق واستجاب المشاركون للدعوة بسرعة كبيرة.'}]}
        with tempfile.TemporaryDirectory() as d:
            html,public=build.render_page(data,feed,sources,uae,models,brand_dir=Path(d))
        self.assertIn('ChatGPT has reached 1 billion weekly users',html);self.assertIn('استجابة سريعة',html)  # free text is shown as is
        # Only the page rendered from the fixed feed: a live headline may say anything, even "Schedule:".
        for bad in self.REMOVED:self.assertNotIn(bad,html,bad)
        for k in ('check_health','automation_status','schedule','last_attempt_at','announcements'):self.assertNotIn(k,public)
        js=(ROOT/'web/app.js').read_text(encoding='utf-8')
        for bad in ("'feeds responded'","'Schedule:'","'Source check:'","'UAE newsrooms'",'GitHub Actions'):self.assertNotIn(bad,js)
        self.assertRegex(self.html,r'Updated \d{1,2} [A-Z][a-z]{2} \d{4} · twice a day</span>')
        # The hardware header says when the content and the prices were last updated, nothing about the checks themselves.
        bar=re.search(r'<p class="statusbar">(.*?)</p>',self.views['hardware']).group(1)
        self.assertEqual(re.findall(r'<b data-i18n>([^<]+)</b>',bar),['Content updated:','Prices checked:'])
        self.assertTrue((ROOT/'data/news-sources.json').exists())
    def test_trust_strip_wording(self):
        self.assertIn('<h3 data-i18n>Every headline sourced</h3><p><span data-i18n>Each summary says whether AI or the publisher wrote it, and every headline has a source link to the original article.</span></p>',self.views['home'])
        self.assertIn("'Each summary says whether AI or the publisher wrote it, and every headline has a source link to the original article.':'يوضح كل ملخص إن كان من كتابة الذكاء الاصطناعي أو من الناشر، ولكل عنوان رابط إلى المقال الأصلي.'",(ROOT/'web/app.js').read_text(encoding='utf-8'))
        self.assertIn('machine-written from the article or the publisher\'s description',build.NEWS_NOTE)
    def test_uae_generic_icon_restored(self):
        # The owner asked for the UAE flag to go and the earlier generic icon and markers to come back.
        self.assertFalse(hasattr(build,'UAE_FLAG'));self.assertNotIn('flag',build.ICON)
        icon=build.ICON['uae']
        self.assertIn('<path d="M5 21V4"/><path d="M5 4h14v10H5"/><path d="M9 4v10"/>',icon)
        for bad in ('class="flag"','#EF3340','#009739','p-flag','ih-flag','j-flag'):self.assertNotIn(bad,self.html,bad)
        css=(ROOT/'web/style.css').read_text(encoding='utf-8')
        for bad in ('.flag{','.flag ','p-flag','ih-flag','j-flag'):self.assertNotIn(bad,css,bad)
        self.assertIn('.j-uae{background:#5eead4}',css)
        header=self.html[self.html.index('<header'):self.html.index('</header>')]
        self.assertIn('<a href="#uae" data-nav="uae" class="n-uae"><i class="dot" aria-hidden="true"></i><span class="nl-full" data-i18n>UAE AI</span>',header)
        self.assertIn(f'<span class="p-icon" aria-hidden="true">{icon}</span><span>03</span>',self.views['home'])
        self.assertIn('<a href="#uae"><i class="j-uae" aria-hidden="true"></i><b data-i18n>UAE</b>',self.views['home'])
        self.assertIn('<h1 id="uae-title" tabindex="-1"><span data-i18n>UAE AI</span></h1>',self.views['uae'])
        for v in ('news','contact'):self.assertIn(f'<span class="p-icon" aria-hidden="true">{icon}</span><span><b data-i18n>UAE AI</b>',self.views[v])
    def test_contact_card_without_form(self):
        c=self.views['contact']
        for bad in ('<form','<textarea','contact-form','c-subject'):self.assertNotIn(bad,c)
        self.assertIn('<h2 data-i18n>Email us</h2><p><a id="c-mail" href="#contact" lang="en" dir="ltr">buafra [at] gmail [dot] com</a></p>',c)
        self.assertIn(build.follow_btn(),c)
        self.assertNotIn('buafra@gmail.com',self.html)
        js=(ROOT/'web/app.js').read_text(encoding='utf-8')
        self.assertIn("['buafra', 'gmail.com'].join('@')",js);self.assertNotIn('contact-form',js)
        self.assertIn("'Email us':'راسلنا عبر البريد الإلكتروني'",js)
        self.assertIn('<a href="#contact" data-nav="contact"',self.html)
    def test_estimator_wording(self):
        h=self.views['hardware']
        # A short label that fits on one line beside the others ("(%)" never on a line of its own); the help text under it explains.
        self.assertIn('<span class="fl" data-i18n>Extra memory&nbsp;(%)</span><input id="extra" class="inp" type="number" min="0" max="500" step="5" value="20" aria-describedby="extra-hint">',h)
        self.assertIn('<p class="hint est-hint" id="extra-hint" data-i18n>Besides the model itself, memory is needed for the conversation it holds and the software running it. 20% suits a normal chat; long documents need more.</p>',h)
        self.assertNotIn('Extra for context and runtime',self.html)
        js=(ROOT/'web/app.js').read_text(encoding='utf-8')
        self.assertIn("'Extra memory\\u00a0(%)':'ذاكرة إضافية\\u00a0(%)'",js)
        self.assertIn("'إلى جانب النموذج نفسه، يلزم قدرٌ إضافي من الذاكرة للمحادثة التي يحتفظ بها وللبرمجيات التي تشغّله. نسبة 20% تناسب محادثة عادية، أما المستندات الطويلة فتحتاج أكثر.'",js)
        self.assertIn("extra:'extra'",js.replace(' ',''))  # URL parameter unchanged
    def test_follow_button_everywhere(self):
        btn=build.follow_btn()
        self.assertIn('href="https://www.instagram.com/qahwa.w.ai/" target="_blank" rel="noopener noreferrer"',btn)
        self.assertIn('<span data-i18n>Follow Qahwa &amp; AI</span> <bdi class="handle" lang="en">@qahwa.w.ai</bdi>',btn)
        for v,chunk in self.views.items():self.assertIn(btn,chunk,v)
        self.assertIn(btn,self.html[self.html.index('<footer'):])
        for v in ('hardware','news','uae'):self.assertIn(f'<div class="ihead-acts"><a class="back" href="#home">',self.views[v])
        self.assertIn('class="btn-ghost ig-mini" href="https://www.instagram.com/qahwa.w.ai/"',self.html)
        self.assertNotIn('.ig-mini{display:none}',self.html.replace(' ',''))
        self.assertIn("'Follow Qahwa & AI':'تابع قهوة و AI'",(ROOT/'web/app.js').read_text(encoding='utf-8'))

class OwnerRequestTests2(unittest.TestCase):
    """The owner's second round of September 2026 requests: the freshness line once, the AI translation label, full
    summaries in the lists, only items mainly about AI, and the UAE view with the latest headlines before the key facts."""
    @classmethod
    def setUpClass(cls):
        cls.data,cls.feed,cls.sources,cls.uae,cls.models=build.load_all()
        cls.html,cls.views=cls.render(cls.feed)
    @classmethod
    def render(cls,feed):
        with tempfile.TemporaryDirectory() as d:
            html,_=build.render_page(cls.data,feed,cls.sources,cls.uae,cls.models,brand_dir=Path(d))
        main=html[html.index('<main'):html.index('</main>')]
        views={v:main[main.index(f'data-view="{v}"'):] for v in ('home','hardware','news','uae','contact')}
        for v,nxt in (('home','hardware'),('hardware','news'),('news','uae'),('uae','contact')):
            views[v]=views[v][:views[v].index(f'data-view="{nxt}"')]
        return html,views
    def fixed_feed(self,*extra):
        src=next(s for s in self.sources if s['region']=='global' and s['lang']=='en')
        host='https://'+build.urlparse(src['homepage']).hostname
        items=[{'id':'g1','title':'Lab releases a new open model','url':host+'/g1','source':src['id'],'lang':'en','uae':False,'published':'2026-09-26T10:00:00+00:00',
                'summary_en':'The lab released an open model. It runs on one GPU.','summary_ar':'أصدر المختبر نموذجاً مفتوحاً.','summary_source':'ai','summary_version':2,'ai_focus':True}]
        return {'updated_at':'2026-09-26T13:09:30+00:00','items':items+[{**i,'source':src['id'],'url':host+'/'+i['id']} for i in extra]}
    def test_freshness_line_only_once(self):
        # "Updated <date> · twice a day" (both languages) only at the top of the AI news view.
        page=self.html.split('<style>')[0]+self.html.split('</style>')[1].split('<script type="application/json"')[0]
        en=re.findall(r'Updated \d{1,2} [A-Z][a-z]{2} \d{4} · twice a day',page)
        ar=re.findall(r'آخر تحديث \d{1,2} \S+ \d{4} · مرتين يومياً',page)
        self.assertEqual((len(en),len(ar)),(1,1))
        self.assertRegex(self.views['news'],r'<p class="ifresh"><span class="pulse" aria-hidden="true"></span><span><span data-lang="en">Updated \d')
        for v in ('home','hardware','uae','contact'):
            self.assertNotIn('Updated ',self.views[v],v);self.assertNotIn('آخر تحديث',self.views[v],v);self.assertNotIn('ifresh',self.views[v],v)
        for bad in ('class="fresh"','class="live"'):self.assertNotIn(bad,self.html)
        # No other "twice a day" either (site text only: rendered from a fixed feed, the inline script checked separately).
        html,views=self.render(self.fixed_feed())
        own=html.split('<style>')[0]+html.split('</style>')[1].split('<script type="application/json"')[0]
        self.assertEqual(len(re.findall(r'twice a day',own,re.I)),1);self.assertEqual(own.count('مرتين يومياً'),1)
        js=(ROOT/'web/app.js').read_text(encoding='utf-8')
        for bad in ('twice a day','Twice a day','مرتين'):self.assertNotIn(bad,js)
        # The hardware status bar: when content and prices were last updated, no schedule line.
        self.assertNotIn('Schedule',self.views['hardware']);self.assertNotIn('GitHub Actions',self.views['hardware'])
    def test_ai_translation_label(self):
        for f in ('scripts/build.py','web/app.js','web/template.html','README.md'):self.assertNotIn('ترجمة آلية',(ROOT/f).read_text(encoding='utf-8'),f)
        self.assertNotIn('ترجمة آلية',self.html)
        self.assertEqual(build.MT_LABEL,{'en':'AI translation','ar':'ترجمة بالذكاء الاصطناعي'})
        self.assertIn('«ترجمة بالذكاء الاصطناعي»',build.NEWS_NOTE)
        if any(i['lang']=='en' and i.get('title_ar') for i in build.news_items(self.feed,self.sources)):
            self.assertIn('<span class="mt">ترجمة بالذكاء الاصطناعي</span>',self.views['news'])
    def test_full_summaries_in_lists_clamped_on_the_landing(self):
        css=(ROOT/'web/style.css').read_text(encoding='utf-8')
        clamped=[sel.strip() for sel,body in re.findall(r'([^{}]+)\{([^{}]*)\}',css) if 'line-clamp' in body and 'n-sum' in sel]
        self.assertEqual(clamped,['.heads .n-sum'])  # only the landing pillars clamp the summary
        self.assertIn('.heads .n-sum{display:-webkit-box;-webkit-line-clamp:3;',css)
        long='The lab released an open model that runs on one GPU. '*12
        html,views=self.render(self.fixed_feed({'id':'g2','title':'A second AI story','lang':'en','uae':False,'published':'2026-09-26T09:00:00+00:00',
                                                'summary_en':long.strip(),'summary_ar':'ملخص.','summary_source':'ai','summary_version':2,'ai_focus':True}))
        self.assertIn(f'<p class="n-sum" lang="en" dir="ltr">{long.strip()}</p><p class="n-by">AI summary</p>',views['news'])  # not cut
    def test_items_not_mainly_about_ai_are_hidden(self):
        feed=self.fixed_feed({'id':'w1','title':'Weekend reads: gardens, jobs and AI','lang':'en','uae':True,'published':'2026-09-26T08:00:00+00:00',
                              'summary_en':'A digest of weekend stories. It mentions AI once.','summary_ar':'مجموعة من قصص نهاية الأسبوع.','summary_source':'ai','summary_version':2,'ai_focus':False},
                             {'id':'k1','title':'AI chip exports rise','lang':'en','uae':False,'published':'2026-09-26T07:00:00+00:00','excerpt':'Exports of AI chips rose again this month.'})
        items=build.news_items(feed,self.sources)
        self.assertEqual([i['id'] for i in items],['g1','k1'])  # no verdict (k1): the collection keyword rule stands
        html,views=self.render(feed)
        self.assertNotIn('Weekend reads',html)
        for v in ('home','news','uae'):self.assertNotIn('/w1"',views[v],v)
        self.assertIn('<dt data-i18n>UAE headlines</dt><dd><bdi>0</bdi>',views['home'])  # counts leave it out too
        self.assertIn(build.L(build.cnt(2,'headline','en'),build.cnt(0,'headline','ar')),views['news'])
    def test_uae_view_latest_headlines_before_key_facts(self):
        u=self.views['uae']
        heads,facts=u.index('<h2 id="uae-news-h" data-i18n>Latest UAE AI news</h2>'),u.index('<h2 id="uae-facts-h" data-i18n>Key facts</h2>')
        self.assertLess(heads,facts)
        self.assertLess(u.index('<div class="split-layout uae-heads">'),u.index('<section class="uae-facts"'))
        if 'class="nitem"' in u:self.assertLess(u.index('class="nitem"'),u.index('class="fact"'))
        self.assertLess(facts,u.index('class="fact"'))
        self.assertEqual(u.count('class="f-date"'),len(self.uae['facts']));self.assertEqual(u.count('As of '),len(self.uae['facts']))  # each keeps its date
        js=(ROOT/'web/app.js').read_text(encoding='utf-8')
        self.assertIn("'Latest UAE AI news':'أحدث أخبار الذكاء الاصطناعي في الإمارات'",js);self.assertIn("'Key facts':'حقائق رئيسية'",js)
        # The landing's UAE pillar: latest UAE headlines, then one highlighted fact.
        home=self.views['home'];pillar=home[home.index('<article class="pillar p-uae"'):home.index('</article>',home.index('<article class="pillar p-uae"'))]
        self.assertLess(pillar.index('<span data-i18n>Latest UAE headlines</span>'),pillar.index('<span data-i18n>Key fact</span>'))
        self.assertEqual(pillar.count('class="fmini"'),1)
        self.assertLess(pillar.index('<dt data-i18n>UAE headlines</dt>'),pillar.index('<dt data-i18n>key facts</dt>'))  # stats too
        n=len(self.uae['facts'])
        self.assertIn(build.L(build.E(f'UAE headlines and {build.cnt(n,"fact","en")}'),f'عناوين إماراتية و{build.cnt(n,"fact","ar")}'),self.views['news'])
        site=json.loads((ROOT/'data/site.json').read_text(encoding='utf-8'))
        self.assertIn(f'href="#fact-{site["uae_highlights"][0]}"',pillar)
        self.assertIn("'Key fact':'حقيقة رئيسية'",js)

class LearnIntegrationTests(unittest.TestCase):
    """Learn AI (learn.html, rendered by scripts/learn.py) wired into the overview: the build writes it, the header and
    footer link to it, and the landing has a fourth pillar with counts from data/learn."""
    @classmethod
    def setUpClass(cls):
        cls.html,_=build.render_page(*build.load_all())
        main=cls.html[cls.html.index('<main'):cls.html.index('</main>')]
        cls.home=main[main.index('data-view="home"'):main.index('data-view="hardware"')]
        start=cls.home.index('<article class="pillar p-learn"')
        cls.pillar=cls.home[start:cls.home.index('</article>',start)]
        cls.header=cls.html[cls.html.index('<header'):cls.html.index('</header>')]
        cls.foot=cls.html[cls.html.index('<footer'):cls.html.index('</footer>')]
        cls.concepts,cls.stacks=build.learn.load()
    NAV_LINK=('<a href="learn.html" class="n-learn"><i class="dot" aria-hidden="true"></i><span class="nl-full" data-i18n>Learn AI</span>'
              '<span class="nl-short" aria-hidden="true" data-i18n>Learn</span></a>')
    def test_header_and_footer_link_to_learn_page(self):
        # Between UAE AI and Contact; no data-nav, since it is a separate page and not one of app.js's views.
        nav=self.header[self.header.index('<nav class="nav"'):]
        self.assertEqual(re.findall(r'<a href="([^"]+)"',nav[:nav.index('</nav>')]),['#home','#hardware','#news','#uae','learn.html','#contact'])
        self.assertIn(self.NAV_LINK,self.header)
        self.assertIn('<a href="#uae" data-i18n>UAE AI</a><a href="learn.html" data-i18n>Learn AI</a><a href="#contact" data-i18n>Contact</a>',self.foot)
    def test_fourth_pillar(self):
        self.assertEqual(self.home.count('<article class="pillar '),4)
        self.assertIn('<section class="pillars" aria-label="The four areas of the site" data-i18n-aria="The four areas of the site">',self.home)
        self.assertIn('<h2 id="p4-title"><a href="learn.html" data-i18n>Learn AI</a></h2>',self.pillar)
        self.assertIn('<a class="cta" href="learn.html"><span data-i18n>Open Learn AI</span>',self.pillar)
        st=self.stacks['stacks'];core=sum(s['kind']!='foundation' for s in st)
        self.assertEqual((len(self.concepts['concepts']),core,len(st)-core),(39,12,3))
        for n,label in ((len(self.concepts['concepts']),'concepts'),(core,'AI stacks'),(len(st)-core,'foundations')):
            self.assertIn(f'<dt data-i18n>{label}</dt><dd><bdi>{n}</bdi></dd>',self.pillar)
        # Picks and topics come from the data in both languages, and every deep link has its target on learn.html.
        first=next(c for c in self.concepts['concepts'] if c['level']=='beginner')
        self.assertIn(build.L(build.E(first['title_en']),build.E(first['title_ar'])),self.pillar)
        for g in self.concepts['groups']:self.assertIn(f'href="learn.html#group/{g["id"]}">{build.L(build.E(g["title_en"]),build.E(g["title_ar"]))}',self.pillar)
        hrefs=re.findall(r'href="learn\.html#([^"]+)"',self.pillar)
        self.assertEqual({h.split('/')[0] for h in hrefs},{'concept','stack','group'})
        page=build.learn.render(self.concepts,self.stacks)
        for h in hrefs:self.assertIn(f'id="{h}"',page,h)
    def test_arabic_for_every_new_label(self):
        js=(ROOT/'web/app.js').read_text(encoding='utf-8')
        labels=set(re.findall(r'data-i18n>([^<]+)<',self.pillar+self.NAV_LINK))|{'The four areas of the site'}
        self.assertTrue({'Learn AI','Learn','Open Learn AI','concepts','AI stacks','foundations'}<=labels)
        for t in labels:self.assertTrue(f"'{t}':" in js or f'"{t}":' in js,t)
        self.assertIn("'Learn AI':'تعلّم الذكاء الاصطناعي','Learn':'تعلّم'",js)
    def test_styles(self):
        css=(ROOT/'web/style.css').read_text(encoding='utf-8')
        self.assertIn('.pillars{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));',css)  # two by two, no lone fourth card
        self.assertIn('.p-learn{--c:var(--learn);--ink:var(--learn-ink);--soft:var(--learn-soft)}',css)
        self.assertEqual(css.count('--learn:#3b7be6;'),2)  # both dark-mode blocks
        self.assertIn('.n-learn{--c:var(--learn)}',css)
        # The six-item header lives in style.css only (learn.html inlines style.css before learn.css).
        self.assertIn('@media (max-width:459px){.nav{gap:0;justify-content:space-between}',css)
        learn_css=(ROOT/'web/learn.css').read_text(encoding='utf-8')
        for dup in ('--learn:#','.n-learn{','@media (max-width:459px){.nav'):self.assertNotIn(dup,learn_css)
    def test_build_writes_learn_page_beside_both_copies(self):
        from unittest import mock
        with tempfile.TemporaryDirectory() as d:
            out,target=Path(d)/'dist',Path(d)/'site'/'Atlas.html'
            target.parent.mkdir()
            fake_pdf=lambda data:(out/'AI_Hardware_Atlas_2026_One_Page.pdf').write_bytes(b'%PDF-1.4\n')
            with mock.patch.object(build,'OUT',out),mock.patch.object(build,'pdf',fake_pdf),mock.patch.object(sys,'argv',['build.py','--standalone',str(target)]),mock.patch('builtins.print'):
                build.main()
            self.assertIn('href="learn.html"',(out/'index.html').read_text(encoding='utf-8'))
            self.assertIn('<a href="index.html" class="n-home">',(out/'learn.html').read_text(encoding='utf-8'))
            # Beside the standalone copy, learn.html links back to that file's name.
            self.assertIn('<a href="Atlas.html" class="n-home">',(target.parent/'learn.html').read_text(encoding='utf-8'))
            self.assertTrue((target.parent/'brand'/'og.png').exists())

class ReviewRoundTests(unittest.TestCase):
    """Review of 26 Sep 2026: one source count on the site, the hero's quick links without a count, a "Show more" step in
    the UAE list, three headlines on the news pillar, Learn data checked before anything is written, links to learn.html
    keeping the language, and a hardware status label that doesn't echo the news freshness line."""
    @classmethod
    def setUpClass(cls):
        data,cls.feed,cls.sources,uae,models=build.load_all()
        cls.html,_=build.render_page(data,cls.feed,cls.sources,uae,models)
        main=cls.html[cls.html.index('<main'):cls.html.index('</main>')]
        cls.home=main[main.index('data-view="home"'):main.index('data-view="hardware"')]
        cls.uae=main[main.index('data-view="uae"'):main.index('data-view="contact"')]
        cls.js=(ROOT/'web/app.js').read_text(encoding='utf-8')
    def test_news_card_gives_no_second_source_count(self):
        n=len(build.news_items(self.feed,self.sources))
        cards=re.findall(r'<a class="xcard x-news" href="#news">.*?</a>',self.html)
        self.assertEqual(len(cards),3)  # #hardware, #uae and #contact
        want=build.L(build.E(f'{build.cnt(n,"headline","en")} in English and Arabic'),f'{build.cnt(n,"headline","ar")} بالعربية والإنجليزية')
        for card in cards:
            self.assertIn(want,card)
            self.assertIsNone(re.search(r'from \d+ sources?|من \d+ مصدر',card),card)
    def test_hero_quick_links_state_no_count(self):
        self.assertIn('<nav class="jump" aria-label="Quick links" data-i18n-aria="Quick links">',self.home)
        # Only the old label: headlines and summaries on the page may use the words freely.
        self.assertIsNone(re.search(r'aria-label="[^"]*three areas',self.html))
        self.assertIn("'Quick links':'روابط سريعة'",self.js);self.assertNotIn('The three areas',self.js)
    def test_uae_list_has_a_show_more_step(self):
        btn='<div class="more-row js-only"><button type="button" class="btn" id="uae-more" hidden data-i18n>Show more</button></div>'
        self.assertIn(btn,self.uae)
        self.assertLess(self.uae.index(btn),self.uae.index('<section class="uae-facts"'))
        if 'class="nitem"' in self.uae:self.assertLess(self.uae.rindex('class="nitem"'),self.uae.index(btn))
        self.assertIn('const UAE_STEP = 8;',self.js);self.assertIn("$('uae-more').addEventListener('click'",self.js)
        self.assertIn('renderUae();',self.js[self.js.index('function render()'):self.js.index('function renderNews()')])
    def test_news_pillar_shows_three_headlines(self):
        self.assertEqual(build.NEWS_PICKS,3)
        start=self.home.index('<article class="pillar p-news"');pillar=self.home[start:self.home.index('</article>',start)]
        for lang in ('en','ar'):
            m=re.search(rf'<ol class="heads" data-lang="{lang}">(.*?)</ol>',pillar)
            if m:self.assertLessEqual(m.group(1).count('<li>'),3,lang)
    def test_bad_learn_data_fails_before_anything_is_written(self):
        from unittest import mock
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'dist'
            err=build.learn.LearnDataError('1 problem(s) in data/learn')
            with mock.patch.object(build,'OUT',out),mock.patch.object(build.learn,'validate',side_effect=err),\
                 mock.patch.object(sys,'argv',['build.py']),mock.patch.object(build,'pdf') as pdf,mock.patch('builtins.print'):
                with self.assertRaises(build.learn.LearnDataError):build.main()
            self.assertFalse(out.exists() and any(out.iterdir()))
            pdf.assert_not_called()
    def test_links_to_learn_page_carry_the_language(self):
        # A ?lang=ar visit saves nothing; the links to learn.html carry ?lang= (before any #fragment) instead.
        self.assertIn('a[href^="learn.html"]',self.js);self.assertIn("path + '?lang=' + want + frag",self.js)
        self.assertIn('learnLinks();',self.js[self.js.index('function applyLang()'):self.js.index('function learnLinks()')])
        self.assertTrue(re.findall(r'href="learn\.html#',self.home))  # the pillar's deep links go through it too
    def test_hardware_status_label_does_not_echo_the_news_freshness_line(self):
        self.assertIn("'Content updated:':'تاريخ المحتوى:'",self.js)
        self.assertNotIn('آخر تحديث للمحتوى',self.js)

if __name__=='__main__':unittest.main()
