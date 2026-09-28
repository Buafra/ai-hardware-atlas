"""The topic classifier (scripts/topics.py) behind the site's own topic images, on real headlines from data/news.json
(September 2026), English and Arabic."""
import json, re, sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import topics

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {s['id']: s for s in json.loads((ROOT / 'data/news-sources.json').read_text(encoding='utf-8'))}

def item(title, source, lang='en', uae=False, title_ar=None, **kw):
    return {'id': 'x', 'title': title, 'title_ar': title_ar, 'lang': lang, 'source': source, 'uae': uae, **kw}

# (headline, source, lang, uae flag, AI translation, expected topic)
REAL = [
    ('Introducing GPT-6 Sol and Luna', 'openai-news', 'en', False, None, 'models'),
    ('Tesla workers balk at training Optimus humanoid robots as replacements', 'ars-ai', 'en', False, 'عمال Tesla يمانعون تدريب روبوتات Optimus البشرية الشكل لتحل محلهم', 'robotics'),
    ('Crusoe abandons $1.25B plan to use Boom turbines at AI data centers', 'techcrunch-ai', 'en', False, None, 'cloud'),
    ('Estimating suicide risk from text', 'mit-news-ai', 'en', False, 'تقدير مخاطر الانتحار انطلاقاً من النصوص', 'health'),
    ('Two years of OpenAI Academy', 'openai-news', 'en', False, None, 'education'),
    ('Build a multi-account AI agent with AgentCore Gateway and MCP', 'aws-ml', 'en', False, 'بناء وكيل ذكاء اصطناعي متعدد الحسابات باستخدام AgentCore Gateway وMCP', 'agents'),
    ('Court rules Pentagon can blacklist Anthropic for refusing to enable Claude features', 'ars-ai', 'en', False, None, 'policy'),
    ('How UK AISI and EvalEval Are Making Benchmark Results Reproducible', 'huggingface', 'en', False, None, 'research'),
    ('Meta puts its AI assistant on a keychain', 'ars-ai', 'en', False, 'Meta تضع مساعدها للذكاء الاصطناعي في سلسلة مفاتيح', 'apps'),
    ('Google tests buying from Walmart-owned Flipkart through Gemini and AI Mode in India', 'techcrunch-ai', 'en', False, None, 'business'),
    ('Anthropic to pay Akamai $11.6 billion over seven years in cloud deal', 'techcrunch-ai', 'en', False, None, 'cloud'),
    ('UAE Ministry of Justice unveils Agentic AI to slash pre-trial case review from 18 days to 2 hours', 'gn-uae', 'en', True, None, 'uae'),
    ('Generative AI adds a new dimension to brand reputation in the UAE', 'gulfnews-tech', 'en', True, None, 'uae'),
    # UAE-tagged (a UAE outlet) but about the world: the flag alone does not make it UAE news.
    ('China and US agree to tariff cuts on $30 billion in goods and AI dialogue', 'thenational', 'en', True,
     'الصين والولايات المتحدة تتفقان على خفض الرسوم الجمركية على سلع بقيمة 30 مليار دولار وعلى حوار بشأن الذكاء الاصطناعي', 'policy'),
    ('صادرات الذكاء الاصطناعي تقود اقتصاد هونغ كونغ لتحقيق نمو يلامس 4%', 'alittihad-feed', 'ar', True, None, 'business'),
    ('"صنع في مصر".. الكشف عن أول روبوت اصطناعي محلي', 'skynews-ar-tech', 'ar', False, None, 'robotics'),
    ('"علي بابا" تكشف عن تكنولوجيات جديدة لرقائق الذكاء الاصطناعي', 'skynews-ar-tech', 'ar', False, None, 'hardware'),
    ('عشرات الآلاف من الحوادث.. وكلاء الذكاء الاصطناعي يثيرون مخاوف أمنية كُبرى', 'aitnews', 'ar', False, None, 'security'),
    ('"قناة اتصال" بين الولايات المتحدة والصين لمعالجة حوادث الذكاء الاصطناعي', 'skynews-ar-tech', 'ar', False, None, 'policy'),
    ('أنثروبيك و OpenAI تطلقان نماذج ذكاء اصطناعي أقوى وأقل تكلفة', 'skynews-ar-tech', 'ar', False, None, 'models'),
    # Climate, energy and nature stories are research (the red-team saw them land on the health image).
    ('هل يفهم الذكاء الاصطناعي لغة الحيوانات؟', 'skynews-ar-tech', 'ar', False, None, 'research'),
    ('Jensen Huang talks about AI and climate change like a supervillain', 'verge-ai', 'en', False, None, 'research'),
    ('XPRIZE Wildfire winners spotted fires within 10 min—but couldn’t stop them', 'ars-ai', 'en', False, None, 'research'),
    ('5 Companies Using AI for Clean Energy', 'nvidia-news', 'en', False, None, 'research'),
]

# The prototype's known misses (hand check of 30 stories), each fixed here.
FIXED = [
    # The AI translation («أتمتة») used to outrank the publisher's own headline.
    ('Automating coherent long-form video generation', 'google-research', 'en', False, 'أتمتة توليد مقاطع فيديو طويلة ومترابطة', 'research'),
    # An incident story, not a policy one.
    ("OpenAI's AI agents crossed the line on US government websites. Here's what happened", 'gulfnews-tech', 'en', True,
     'وكلاء الذكاء الاصطناعي التابعون لـOpenAI تجاوزوا الحدود على مواقع حكومية أمريكية... إليك ما حدث', 'security'),
    # The OpenAI agents incident in Arabic: a number between «نشر» and «صورة», and «صور مستخدمين».
    ('«أوبن إيه آي»: وكلاء ذكاء اصطناعي تسبّبوا في نشر 53 صورة لمستخدمين', 'alittihad-feed', 'ar', True, None, 'security'),
    ('"أوبن أي آي" تقر بنشر أدواتها صور مستخدمين لـ"تشات جي بي تي"', 'indy-ar-new', 'ar', False, None, 'security'),
]

class TopicTests(unittest.TestCase):
    def check(self, rows):
        for title, source, lang, uae, title_ar, want in rows:
            with self.subTest(title=title):
                i = item(title, source, lang, uae, title_ar)
                self.assertEqual(topics.topic_of(i, SOURCES[source]), want, topics.classify(i, SOURCES[source]))

    def test_real_headlines(self):
        self.check(REAL)

    def test_known_misses_fixed(self):
        self.check(FIXED)

    def test_industrial_safety_is_not_ai_safety(self):
        # A known miss too: "industrial safety" is a computer-vision product story, not AI safety. With no other headline
        # keyword the excerpt decides (the real one: cameras, SageMaker, Kinesis).
        title = 'How Tata Elxsi detects industrial safety risks in seconds on AWS'
        self.assertNotEqual(topics.topic_of(item(title, 'aws-ml'), SOURCES['aws-ml']), 'security')
        i = item(title, 'aws-ml', excerpt='Learn how Tata Elxsi built IRIS, a real-time industrial safety platform on AWS. IRIS filters camera '
                 'video at the edge, streams metadata through Amazon Kinesis, runs computer vision on Amazon SageMaker AI, and correlates detections.')
        got = topics.classify(i, SOURCES['aws-ml'])
        self.assertEqual(got[2], 'body'); self.assertIn(got[0], ('cloud', 'apps'))
        self.assertEqual(topics.topic_of(item('New guardrails improve AI safety', 'openai-news')), 'security')

    def test_uae_official_sources_always_get_the_uae_topic(self):
        for sid in ('wam-en', 'wam-ar', 'mediaoffice-en2', 'mediaoffice-ar2', 'sharjah24-en', 'sharjah24-ar'):
            s = SOURCES[sid]
            self.assertTrue(topics.uae_official(s), sid)
            # Even a story that would otherwise be about a chip or an Arabic model.
            self.assertEqual(topics.topic_of(item('New Arabic LLM Jais runs on NVIDIA GPUs', sid, s['lang'], True), s), 'uae', sid)
        self.assertTrue(topics.uae_official({'region': 'global', 'kind': 'news', 'official_region': True}))
        for sid in ('openai-news', 'gulfnews-tech', 'thenational', 'alittihad-feed'):
            self.assertFalse(topics.uae_official(SOURCES[sid]), sid)

    def test_arabic_ai_rule(self):
        self.assertEqual(topics.topic_of(item('A new Arabic large language model tops the leaderboard', 'huggingface')), 'arabic')
        self.assertEqual(topics.topic_of(item('إطلاق نموذج لغوي عربي جديد', 'aitnews', 'ar')), 'arabic')
        # «جيس» only as a whole word.
        self.assertNotEqual(topics.topic_of(item('جيسون يتحدث عن الروبوتات', 'aitnews', 'ar')), 'arabic')

    def test_fallback_and_determinism(self):
        self.assertEqual(topics.topic_of(item('A quiet week', 'verge-ai')), 'general')
        rows = [item(t, s, l, u, a) for t, s, l, u, a, _ in REAL + FIXED]
        first = [topics.classify(i, SOURCES[i['source']]) for i in rows]
        self.assertEqual(first, [topics.classify(dict(i), SOURCES[i['source']]) for i in reversed(rows)][::-1])

    def test_every_topic_has_an_image_and_names(self):
        img = ROOT / 'web' / 'news-img'
        self.assertEqual(sorted(f.stem for f in img.glob('*.svg')), sorted(topics.TOPICS))
        for t, (en, ar) in topics.TOPICS.items():
            self.assertTrue(en and re.search(r'[؀-ۿ]', ar), t)
            self.assertEqual(topics.name(t, 'en'), en); self.assertEqual(topics.name(t, 'ar'), ar)
            svg = (img / f'{t}.svg').read_text(encoding='utf-8')
            self.assertLess(len(svg.encode('utf-8')), 4096, t)  # small
            self.assertTrue(svg.startswith('<svg') and 'viewBox="0 0 640 360"' in svg, t)
            # Nothing loaded from anywhere: no links, images, web fonts or scripts; the only URL is the SVG namespace. (The
            # Arabic AI image draws one letter in the reader's own system font.)
            rest = svg.replace('xmlns="http://www.w3.org/2000/svg"', '')
            for bad in ('http', 'href', '<image', '<script', '@import', '@font-face', 'url(data', 'on'):
                if bad == 'on':
                    self.assertIsNone(re.search(r'\son\w+=', rest), t)
                else:
                    self.assertNotIn(bad, rest, t)
        self.assertEqual(topics.name('nope', 'en'), 'AI news')

    def test_whole_words_only(self):
        # "un" is the United Nations, not the start of "unveils"; "rl" and "tii" are words, not letters in a word.
        self.assertNotEqual(topics.topic_of(item('Startup unveils a friendly keyboard', 'verge-ai')), 'policy')
        self.assertEqual(topics.topic_of(item('Leaders meet at the UN on AI', 'verge-ai')), 'policy')

if __name__ == '__main__':
    unittest.main()
