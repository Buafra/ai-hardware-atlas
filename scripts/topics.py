"""Pick one topic for each news story, for its topic image (web/news-img/<topic>.svg) when it has no company image.

Deterministic keyword rules: no AI, no network, the same story always gets the same topic.

  1. UAE official source: a story from a UAE/GCC government source (region "uae" and kind "primary": WAM, the Dubai
     Media Office, Sharjah24; or any source marked "official_region") is always "uae". Their own photos are never used
     (they often show leaders), so their stories get the site's own UAE image.
  2. Arabic AI: the story is about an Arabic language model or Arabic NLP (English and Arabic phrases, any field).
  3. UAE AI: the story is UAE-tagged ("uae": true) and its headline names the UAE, an emirate or a UAE body. The flag
     alone is not enough: it is set on every item of a UAE outlet, so Gulf News' copy of a global OpenAI story would
     otherwise get the UAE image.
  4. Headline: the first topic in PRIORITY with a keyword in the original headline wins. Only when the original
     headline matches nothing is the AI translation (title_ar of an English item) read the same way: a translation
     adds words the publisher did not write ("Automating" became «أتمتة»).
  5. Body: the topic with the most keyword matches in the excerpt and the English and Arabic summaries wins (ties go to
     PRIORITY order). No match at all: "general".

English keywords match whole words, case-insensitively. An Arabic keyword may carry the clitics و ف ب ل ك and the
article ال before it and any suffix after it.
"""
import re

# topic id -> (English name, Arabic name): the alt text of the topic image.
TOPICS = {
    'models':    ('Models & releases', 'النماذج والإصدارات'),
    'hardware':  ('Hardware & chips', 'العتاد والرقائق'),
    'research':  ('Research', 'الأبحاث'),
    'business':  ('Business & investment', 'الأعمال والاستثمار'),
    'policy':    ('Policy & law', 'السياسات والتشريعات'),
    'security':  ('Safety & security', 'الأمان والأمن'),
    'agents':    ('Agents & automation', 'الوكلاء والأتمتة'),
    'apps':      ('Apps & devices', 'التطبيقات والأجهزة'),
    'cloud':     ('Cloud & data centres', 'السحابة ومراكز البيانات'),
    'health':    ('Health & science', 'الصحة والعلوم'),
    'education': ('Education & skills', 'التعليم والمهارات'),
    'robotics':  ('Robotics', 'الروبوتات'),
    'uae':       ('UAE AI', 'الذكاء الاصطناعي في الإمارات'),
    'arabic':    ('Arabic AI', 'الذكاء الاصطناعي العربي'),
    'general':   ('AI news', 'أخبار الذكاء الاصطناعي'),
}

# Order for the headline rule and for ties in the body rule: the most specific topics first.
PRIORITY = ['security', 'robotics', 'health', 'policy', 'education', 'cloud', 'hardware', 'agents', 'business',
            'research', 'models', 'apps']

ARABIC_AI = {
    'en': [r'arabic (?:large )?language models?', r'arabic llms?', r'arabic[- ]first (?:model|llm)', r'arabic nlp',
           r'jais', r'falcon arabic', r'arabic speech', r'arabic chatbot', r'arabic dialects?'],
    'ar': ['نموذج لغوي عربي', 'نماذج لغوية عربية', 'نموذج لغة عربي', 'جيس', 'فالكون العربي', 'اللهجات العربية',
           'معالجة اللغة العربية'],
}
UAE_NAMES = {
    'en': [r'uae', r'u\.a\.e\.?', r'emirates?', r'emirati', r'abu dhabi', r'dubai', r'sharjah', r'ajman',
           r'ras al khaimah', r'fujairah', r'umm al quwain', r'khalifa university', r'mbzuai', r'g42', r'tii',
           r'adnoc', r'adnec'],
    'ar': ['الإمارات', 'الامارات', 'إماراتي', 'اماراتي', 'أبوظبي', 'ابوظبي', 'أبو ظبي', 'دبي', 'الشارقة', 'عجمان',
           'رأس الخيمة', 'الفجيرة', 'أم القيوين', 'جامعة خليفة'],
}

KEYWORDS = {
    'security': {
        'en': [r'hack(?:s|ed|ers?|ing)?', r'breach(?:es|ed)?', r'cyber\w*', r'vulnerabilit(?:y|ies)', r'0-day',
               r'zero-day', r'exploit\w*', r'leak(?:s|ed)?', r'exposing', r'exposed', r'fraud\w*', r'scams?',
               r'deepfakes?', r'malware', r'phishing', r'compromis\w+', r'rogue', r'attack(?:s|ed|ing)?',
               r'unsecured', r'security(?! council)',
               # "safety" of AI, not a workplace's: "detects industrial safety risks" is a computer-vision product story.
               r'(?<!industrial )(?<!workplace )(?<!food )(?<!road )safety', r'misuse', r'infiltrat\w+', r'doomsday',
               r'fake', r'cheat\w*', r'collusion', r'guardrails?', r'posted .{0,20}images', r'crossed the line',
               ],
        'ar': ['اختراق', 'اخترق', 'هاكر', 'قراصنة', 'تسريب', 'ثغرة', 'ثغرات', 'احتيال', 'التزييف العميق', 'هجوم',
               'هجمات', 'الأمن السيبراني', 'مخاوف أمنية', 'المشاكل الأمنية', 'الأمنية', 'تجاوز القيود', 'على الملأ',
               # The OpenAI agents incident in Arabic outlets: «نشر 53 صورة لمستخدمين», «بنشر أدواتها صور مستخدمين».
               r'نشر (?:\d+ )?صور', r'صور(?:ة)? (?:ال)?مستخدمين', r'صور(?:ة)? لمستخدمين', 'وفاة'],
    },
    'policy': {
        'en': [r'regulat\w+', r'laws?', r'legislat\w+', r'lawsuits?', r'sues?', r'sued', r'suing', r'courts?',
               r'judge', r'ruling', r'rules', r'pentagon', r'government', r'ministry', r'minister', r'united nations',
               r'un', r'security council', r'white house', r'congress', r'senate', r'tariffs?', r'treaty',
               r'declaration', r'blacklist', r'supply-chain risk', r'policy', r'policies', r'trump', r'hotline',
               r'communication channel', r'oversight', r'standards', r'prosecution', r'justice', r'border',
               r'surveillance', r'cartel', r'antitrust', r'geopolitic\w*', r'ai race', r'third party assessments',
               r'copyright'],
        'ar': ['تنظيم', 'قانون', 'قوانين', 'تشريع', 'محكمة', 'دعوى', 'مجلس الأمن', 'الأمم المتحدة', 'حكومة', 'حكومي',
               'وزارة', 'قناة اتصال', 'السيادة', 'رسوم جمركية', 'البنتاغون'],
    },
    'health': {
        'en': [r'health\w*', r'mentalhealth\w*', r'medical', r'medicine', r'medicare', r'patients?', r'diseases?',
               r'diagnos\w+', r'hospitals?', r'clinical', r'mental', r'suicide', r'psychiatr\w+', r'pandemic',
               r'doctors?', r'drugs?', r'biolog\w+', r'scientists?', r'sclerosis', r'proteins?', r'enzymes?'],
        'ar': ['صحة', 'الصحي', 'طبي', 'طبية', 'مرض', 'أمراض', 'تشخيص', 'مستشفى', 'التصلب', 'علماء'],
    },
    'education': {
        'en': [r'education\w*', r'students?', r'schools?', r'universit(?:y|ies)', r'academy', r'learning paths?',
               r'skills', r'teach\w*', r'courses?', r'training initiative', r'hands-on', r'fellow', r'curricul\w+',
               r'humanist', r'careers?'],
        'ar': ['تعليم', 'التعليم', 'طلاب', 'الطلبة', 'مهارات', 'جامعة', 'مدرسة'],
    },
    'robotics': {
        'en': [r'robot\w*', r'humanoids?', r'optimus', r'isaac ros', r'physical ai', r'autonomous vehicles?',
               r'self-driving'],
        # «روبوت» but not «روبوت الدردشة» (a chatbot) or «روبوت زحف» (a web crawler).
        'ar': [r'روبوت(?!\S* (?:ال)?(?:دردشة|محادثة|زحف))'],
    },
    'hardware': {
        'en': [r'chips?', r'gpus?', r'semiconductors?', r'processors?', r'tpus?', r'npus?', r'nvidia', r'amd',
               r'silicon', r'copilot\+ pc', r'laptops?', r'geforce', r'hardware', r'wafer',
               r'memory chips?', r'designing chips'],
        'ar': ['رقائق', 'رقاقة', 'شرائح', 'معالجات', 'أشباه الموصلات', 'عتاد'],
    },
    'cloud': {
        'en': [r'data cent(?:er|re)s?', r'datacent(?:er|re)s?', r'cloud(?! gaming)', r'neoclouds?', r'compute',
               r'sagemaker', r'hyperpod', r'eks', r'efa', r'ai factor(?:y|ies)', r'cooling', r'power', r'turbines?',
               r'orbital', r'suncatcher', r'gas generators?', r'endpoints?', r'multi-region', r'throughput',
               r'server-side'],
        'ar': ['مراكز البيانات', 'مركز بيانات', 'السحابة', 'سحابية', 'الحوسبة'],
    },
    'business': {
        'en': [r'invest\w*', r'funding', r'financing', r'ipo', r'billion', r'\$[\d.]+[bm]', r'valuation',
               r'acqui\w+', r'deal', r'revenue', r'sales', r'profits?', r'economy', r'economic', r'exports?',
               r'jobs?', r'unemployment', r'workers?', r'workforce', r'ads', r'advertis\w+', r'market\w*',
               r'shopping', r'buying', r'commerce', r'cuts? costs?', r'brand reputation', r'voting control', r'hype',
               r'business\w*'],
        'ar': ['استثمار', 'استثمارات', 'صادرات', 'اقتصاد', 'مليار', 'وظائف', 'الأسواق', 'مديرك'],
    },
    'agents': {
        'en': [r'agents?', r'agentic', r'agentcore', r'agentforce', r'automation', r'automates', r'autonomous',
               r'swarms?', r'mcp', r'makes? calls', r'workflows?', r'triage', r'customer calls'],
        'ar': ['وكلاء', 'وكيل', 'الوكلاء', 'أتمتة', 'مؤتمت'],
    },
    'models': {
        'en': [r'models?', r'gpt-?\d[\w.]*', r'claude', r'opus', r'gemini', r'llms?', r'language models?',
               r'open[- ]weights?', r'text-to-speech', r'tts', r'multimodal', r'vision-language', r'moe',
               r'reinforcement learning', r'rl', r'fine-tun\w+', r'quants?', r'llama\.cpp', r'transformers',
               r'training', r'release[sd]?', r'launch(?:es|ed)?', r'introduc\w+', r'frontier', r'prompt caching',
               r'astra', r'sol and luna', r'deepseek', r'qwen\w*', r'whisperx?'],
        'ar': ['نموذج', 'نماذج', 'تطلقان', 'تطلق', 'ديب سيك', 'إطلاق'],
    },
    'research': {
        'en': [r'research\w*', r'study', r'studies', r'paper', r'benchmarks?', r'reproducib\w+', r'evaluat\w+',
               r'evals?', r'mit', r'open science', r'estimating', r'mathematics', r'turing', r'long-form video',
               r'video generation', r'map', r'visual ai', r'cities', r'lab',
               # Climate, energy and nature stories are research, not health.
               r'climate', r'clean energy', r'wildfires?', r'animals?'],
        'ar': ['أبحاث', 'دراسة', 'باحثون', 'الباحثين', 'بحث', 'العلماء', 'يفهم', 'المناخ', 'الحيوانات'],
    },
    'apps': {
        'en': [r'apps?', r'assistant', r'chatbots?', r'chatgpt', r'copilot', r'features?', r'youtube', r'glasses',
               r'ray-ban', r'phones?', r'pixel', r'keychain', r'avatar', r'video', r'games?', r'gaming',
               r'camera\w*', r'super app', r'tamagotchi', r'muse', r'office', r'googlebook',
               r'feeds?', r'fridges?', r'gadget', r'downloads', r'dating', r'music', r'suno', r'beam', r'filesystem',
               r'tools?', r'color grading', r'drafts?', r'analytics', r'speech', r'transcription', r'ai mode',
               r'smart glasses', r'consumer'],
        'ar': ['تطبيق', 'أداة', 'أدوات', 'تشات جي بي تي', 'أوفيس', 'ميوز', 'مساعد', 'هاتف', 'نظارات'],
    },
}

AR_LETTER = 'ء-ي'
AR_PREFIX = rf'(?<![{AR_LETTER}])(?:و|ف|ب|ل|ك)?(?:ال)?'

def _compile(words, whole_ar=False):
    """[(keyword, regex)] for a {'en': [...], 'ar': [...]} list."""
    out = []
    for k in words.get('en', []):
        out.append((k, re.compile(r'(?<![\w+])' + k + r'(?![\w+])', re.I)))
    for k in words.get('ar', []):
        base = k[2:] if k.startswith('ال') else k  # «الوكلاء» also matches «والوكلاء», «للوكلاء»
        tail = rf'(?![{AR_LETTER}])' if whole_ar else ''
        out.append((k, re.compile(AR_PREFIX + base + tail)))
    return out

RULES = {t: _compile(v) for t, v in KEYWORDS.items()}
ARABIC_RX = _compile(ARABIC_AI, whole_ar=True)
UAE_RX = _compile(UAE_NAMES)
assert set(RULES) == set(PRIORITY) and set(PRIORITY) | {'uae', 'arabic', 'general'} == set(TOPICS)

def _hits(rules, text):
    return [k for k, rx in rules if text and rx.search(text)]

def uae_official(source):
    """A UAE/GCC government source (WAM, the Dubai Media Office, Sharjah24 ...): region "uae" and kind "primary", or
    marked "official_region". Their stories always get the UAE topic image, never a photo of theirs."""
    return bool(source) and ((source.get('region') == 'uae' and source.get('kind') == 'primary') or source.get('official_region') is True)

def headlines(item):
    """(original headline, AI translation or ''): the publisher's own words first."""
    return item.get('title') or '', (item.get('title_ar') or '') if item.get('lang') == 'en' else ''

def classify(item, source=None):
    """(topic, matched keyword, rule) for one news item (a news.json item). `source`: its news-sources.json record."""
    if uae_official(source):
        return 'uae', '', 'uae-official'
    title, translation = headlines(item)
    body = [item.get('excerpt') or '', item.get('summary_en') or '', item.get('summary_ar') or '']
    both = ' \n '.join(x for x in (title, translation) if x)
    hit = _hits(ARABIC_RX, ' \n '.join([both] + body))
    if hit:
        return 'arabic', hit[0], 'arabic'
    if item.get('uae'):
        hit = _hits(UAE_RX, both)
        if hit:
            return 'uae', hit[0], 'uae-headline'
    for head, rule in ((title, 'headline'), (translation, 'translation')):
        if not head:
            continue
        for t in PRIORITY:
            hit = _hits(RULES[t], head)
            if hit:
                return t, hit[0], rule
    best, best_n, best_kw = 'general', 0, ''
    for t in PRIORITY:
        n, first = 0, ''
        for text in body:
            for k, rx in RULES[t]:
                found = len(rx.findall(text)) if text else 0
                if found and not first:
                    first = k
                n += found
        if n > best_n:
            best, best_n, best_kw = t, n, first
    return best, best_kw, ('body' if best_n else 'fallback')

def topic_of(item, source=None):
    """The topic id of one news item (a key of TOPICS). Deterministic."""
    return classify(item, source)[0]

def name(topic, lang):
    """The topic's name in 'en' or 'ar' (the topic image's alt text)."""
    en, ar = TOPICS.get(topic, TOPICS['general'])
    return ar if lang == 'ar' else en
