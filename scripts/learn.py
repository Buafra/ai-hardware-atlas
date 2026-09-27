"""Learn AI: validate data/learn/*.json and render the separate static page learn.html.

    python scripts/learn.py                      # writes dist/learn.html (and the brand PNGs beside it)
    python scripts/learn.py --out DIR --home X   # another folder; links back to the overview go to X

build(out_dir, home='index.html') is the entry point for scripts/build.py. The page shares the site's look: it inlines
web/style.css (header, footer, tokens) plus web/learn.css and web/learn.js, and reuses build.py's brand files and icons.
Every concept and stack is rendered in the HTML in both languages (CSS shows the one matching <html lang>), so the page
reads completely without JavaScript; learn.js adds the tabs, topic filter, search, deep links and the language and theme
buttons (same localStorage keys as the overview: atlas-lang, atlas-theme).
"""
import argparse
import ast
import html
import json
import re
import sys
import types
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data' / 'learn'
CATALOG = ROOT / 'data' / 'catalog.json'
UAE = ROOT / 'data' / 'uae.json'
OUT = ROOT / 'dist'
PAGE = 'learn.html'
SITE_URL = 'https://buafra.github.io/ai-hardware-atlas/'

class LearnDataError(ValueError):
    """The learn data breaks a rule; the message lists every problem found."""

# ---------- build.py helpers ----------

_SITE = None

def site_without_pdf():
    """build.py's top-level definitions without its reportlab imports (needed only for the PDF), for a Python that
    lacks reportlab, such as the one running the browser tests. Read-only: build.py itself is not changed."""
    path = ROOT / 'scripts' / 'build.py'
    tree = ast.parse(path.read_text(encoding='utf-8'), str(path))
    tree.body = [n for n in tree.body if not (isinstance(n, ast.ImportFrom) and (n.module or '').startswith('reportlab'))
                 and not (isinstance(n, ast.Import) and any(a.name.startswith('reportlab') for a in n.names))]
    mod = types.ModuleType('build')
    mod.__file__ = str(path)
    exec(compile(tree, str(path), 'exec'), mod.__dict__)
    return mod

def site():
    global _SITE
    if _SITE is None:
        if str(ROOT / 'scripts') not in sys.path:
            sys.path.insert(0, str(ROOT / 'scripts'))
        try:
            import build as mod
        except ModuleNotFoundError as e:
            if not str(e.name or '').startswith('reportlab'):
                raise
            mod = site_without_pdf()
        _SITE = mod
    return _SITE

# ---------- data ----------

def load(data_dir=DATA):
    read = lambda name: json.loads((Path(data_dir) / name).read_text(encoding='utf-8'))
    return read('concepts.json'), read('stacks.json')

LEVELS = {'beginner': ('Beginner', 'مبتدئ'), 'intermediate': ('Intermediate', 'متوسط'), 'advanced': ('Advanced', 'متقدم')}
KINDS = ('stack', 'foundation')
OPTION_COLUMNS = (('local', 'Local / open-source', 'محلي / مفتوح المصدر'),
                  ('cloud', 'Managed cloud', 'سحابة مُدارة'),
                  ('uae', 'UAE-hosted', 'مستضاف في الإمارات'))
SLUG = re.compile(r'^[a-z0-9][a-z0-9-]*$')
AS_OF = re.compile(r'^(\d{4})-(0[1-9]|1[0-2])$')
# Links into the overview page (index.html): its views and the routes app.js understands (parseRoute in web/app.js).
SITE_HREF = re.compile(r'^#(?:hardware(?:/.+)?|news(?:/(?:all|global|uae))?|uae(?:/f/[a-z0-9-]+)?|contact(?:/about)?|estimator)$')
HW_HREF = re.compile(r'^#hardware(?:/(p|level|vendor|run|table|cards|timeline|compare)(?:/(.+))?)?$')
UAE_FACT = re.compile(r'^#uae/f/([a-z0-9-]+)$')
# A chip named after the "What can it run?" estimator must open it (#hardware alone stops at the top of the catalog).
RUN_LABEL, RUN_HREFS = 'What can it run?', ('#hardware/run', '#estimator')
CONCEPT_TEXT = ('title', 'summary', 'body', 'example', 'practices', 'mistakes')
STACK_TEXT = ('title', 'summary', 'use_when', 'avoid_when', 'flow', 'hardware', 'arabic', 'practices', 'pitfalls', 'cost')
# Prose whose Arabic version must be mostly Arabic letters (labels and titles may legitimately be Latin product names).
CONCEPT_PROSE = ('summary', 'body', 'example', 'practices', 'mistakes')
STACK_PROSE = ('summary', 'use_when', 'avoid_when', 'hardware', 'arabic', 'practices', 'pitfalls', 'cost')
AR_LETTER, LATIN_LETTER = re.compile(r'[؀-ۿ]'), re.compile(r'[A-Za-z]')

def _filled(v):
    if isinstance(v, str):
        return bool(v.strip())
    if isinstance(v, list):
        return bool(v) and all(isinstance(x, str) and x.strip() for x in v)
    return False

def _https(url):
    u = urlparse(str(url or ''))
    return u.scheme == 'https' and bool(u.hostname)

def _walk(o, where, errs):
    """Every *_en has a non-empty *_ar twin (lists of the same length), every *_ar is filled, every url is https."""
    if isinstance(o, dict):
        for k, v in o.items():
            at = f'{where}.{k}'
            if k.endswith('_ar') and not _filled(v):
                errs.append(f'{at} is empty')
            if k.endswith('_en'):
                twin = o.get(k[:-3] + '_ar')
                if not _filled(v):
                    errs.append(f'{at} is empty')
                if twin is None:
                    errs.append(f'{at} has no Arabic version ({k[:-3]}_ar)')
                elif isinstance(v, list) and isinstance(twin, list) and len(v) != len(twin):
                    errs.append(f'{at} has {len(v)} items but {k[:-3]}_ar has {len(twin)}')
            if k == 'url' and not _https(v):
                errs.append(f'{at} must be an https URL: {v!r}')
            _walk(v, at, errs)
    elif isinstance(o, list):
        for i, v in enumerate(o):
            _walk(v, f'{where}[{i}]', errs)

def _ids(items, kind, errs):
    seen = set()
    for i, x in enumerate(items):
        xid = x.get('id') if isinstance(x, dict) else None
        if not isinstance(xid, str) or not SLUG.match(xid):
            errs.append(f'{kind}[{i}] has an invalid id {xid!r}')
        elif xid in seen:
            errs.append(f'duplicate {kind} id {xid!r}')
        seen.add(xid)
    return seen

def _mostly_arabic(v):
    text = ' '.join(v) if isinstance(v, list) else str(v or '')
    ar, lat = len(AR_LETTER.findall(text)), len(LATIN_LETTER.findall(text))
    return ar > lat

def _arabic_prose(x, keys, where, errs):
    for k in keys:
        v = x.get(k + '_ar')
        if _filled(v) and not _mostly_arabic(v):
            errs.append(f'{where}: {k}_ar is not Arabic text')
    if _filled(x.get('title_ar')) and not AR_LETTER.search(str(x['title_ar'])):
        errs.append(f'{where}: title_ar has no Arabic letters')

# ---------- content policy guard (owner-approved policy P1-P4, fixed content under M5) ----------
# Fixed content (Learn AI, and the other fixed pages: data/uae.json, data/about.json and the hardware notes in
# data/catalog.json) never pairs a UAE/GCC name with conflict, attack, damage, disruption, sanctions or export-control,
# blockade, crisis, criticism, accusation, crackdown, detention, spyware, surveillance, scandal or human-rights wording,
# so a sentence like "the UAE region has been disrupted after conflict damage", or any paraphrase of it, cannot come
# back. The check is per text field, in English and Arabic, on normalised text (diacritics, tatweel, letter variants and
# look-alike letters do not hide a word); it is deliberately broad ("when in doubt, leave it out"): reword the sentence
# neutrally or drop the country name.
if str(ROOT / 'scripts') not in sys.path:
    sys.path.insert(0, str(ROOT / 'scripts'))
import policy  # noqa: E402  (scripts/policy.py: the region detection and normalisation the news check uses)

_AR = 'ء-ي'  # Arabic letters (without diacritics)

def _ar_words(*words):
    """Arabic whole words, allowing a leading و/ف/ب/ل/ك and a nisba or plural ending (Arabic has no \\b)."""
    alts = '|'.join(policy.normalize(w) for w in words)
    return rf'(?<![{_AR}])[وفبلك]?(?:{alts})(?:ي|يه|يون|يين|يا|ا)?(?![{_AR}])'

def _ar_any(*phrases):
    """Arabic phrases matched anywhere (normalised spelling)."""
    return '|'.join(policy.normalize(x) for x in phrases)

GCC_NAMES = re.compile('|'.join((
    r'\b(?:U\.?A\.?E|Emirates|Emirati|Abu ?Dhabi|Dubai|Sharjah|Ajman|Fujairah|Ras Al[ -]Khaimah|Umm Al[ -]Quwain|Al Ain|'
    r'Saudi|KSA|Riyadh|Jeddah|Qatari?|Doha|Kuwaiti?|Bahraini?|Manama|Omani?|Muscat|GCC|Gulf|'
    r'Al Nahyan|Al Maktoum|Al Qasimi|Al Nuaimi|Al Sharqi|Al Mualla|Al Saud|Al Thani|Al Sabah|Al Khalifa|Al Said|'
    r'bin Zayed|bin Rashid|bin Salman|Sheikh|Sheikha|G42|MGX|Mubadala|ADNOC|ADQ|TII|Core42|Khazna|PIF|HUMAIN|Aramco|NEOM|QIA|'
    r'Ooredoo|KIA|Mumtalakat|Omantel|MBZUAI|SDAIA|QCRI|WAM|me-central-1|me-south-1)\b',
    r'(?<!\w)e&(?!\w)',
    _ar_any('الإمارات', 'إماراتي', 'أبوظبي', 'أبو ظبي', 'الشارقة', 'عجمان', 'الفجيرة', 'رأس الخيمة', 'أم القيوين', 'السعودي', 'سعودي',
            'الدوحة', 'الكويت', 'كويتي', 'البحرين', 'بحريني', 'المنامة', 'سلطنة عمان', 'العماني', 'الخليج', 'خليجي', 'مجلس التعاون',
            'آل نهيان', 'آل مكتوم', 'القاسمي', 'النعيمي', 'المعلا', 'آل سعود', 'آل ثاني', 'آل الصباح', 'آل خليفة', 'آل سعيد', 'بن زايد',
            'بن راشد', 'بن سلمان', 'أرامكو', 'هيوماين', 'مبادلة', 'أدنوك', 'نيوم', 'جهاز قطر', 'صندوق الاستثمارات العامة', 'أوريدو',
            'عمانتل', 'ممتلكات البحرين', 'خزنة', 'وكالة أنباء الإمارات'),
    _ar_words('دبي', 'قطر', 'القطر', 'الرياض', 'مسقط', 'الشيخ', 'الشيخة', 'وام', 'عمان'),
)), re.I)

RISK_TERMS = re.compile('|'.join((
    r'\b(?:conflicts?|wars?|warfare|war-?time|war-torn|hostilities|invasion|invaded|military (?:strikes?|action|operations?)|'
    r'strikes?|struck by|air ?strikes?|drones? (?:strikes?|attacks?)|attack(?:s|ed|ing)?|missiles?|bomb(?:s|ed|ing)?|shelling|'
    r'damaged?|damages|disrupt(?:ed|ion|ions|s)?|sanction(?:s|ed)?|embargo(?:es)?|export[- ]controls?|blockade[ds]?|'
    r'boycott(?:s|ed)?|crisis|crises|tensions?|instability|unrest|riots?|protests?|protesters|coup|terror\w*|militants?|'
    r'militias?|rebels?|Houthis?|criticis(?:e|ed|es|ing|m)|criticiz(?:e|ed|es|ing)|critics?|accus(?:e|ed|es|ing|ation|ations)|'
    r'allegations?|alleged(?:ly)?|crackdowns?|censor(?:s|ed|ship)?|detain(?:s|ed|ee|ees)?|detention|arrest(?:s|ed)?|jail(?:s|ed)?|'
    r'imprison(?:s|ed|ment)?|prisons?|dissidents?|activists?|scandals?|abuses?|torture|executions?|spyware|espionage|spying|'
    r'surveillance|(?:national )?security (?:concerns?|risks?|fears?|threats?)|human[- ]rights?|lawsuits?|sued|probes?|'
    r'investigations? into)\b',
    _ar_any('نزاع', 'صراع', 'الحرب', 'حروب', 'حربي', 'قصف', 'غارة', 'غارات', 'صاروخ', 'صواريخ', 'دمار', 'تدمير', 'أضرار', 'تضرر',
            'اجتياح', 'هجوم', 'هجمات', 'الهجمات', 'هجمة', 'ضربة', 'ضربات', 'مسيرات هجومية', 'اضطرابات',
            'برامج التجسس', 'برمجيات التجسس', 'تجسس', 'التجسس', 'حقوق الإنسان', 'المراقبة الجماعية', 'مراقبة جماعية',
            'عقوبات اقتصادية', 'عقوبات دولية', 'عقوبات أمريكية', 'عقوبات أميركية', 'عقوبات غربية', 'العقوبات المفروضة', 'للعقوبات',
            'لعقوبات', 'قيود التصدير', 'ضوابط التصدير', 'قيود على التصدير', 'حظر التصدير', 'حصار', 'مقاطعة', 'أزمة', 'الأزمة',
            'أزمات', 'توتر', 'توترات', 'عدم الاستقرار', 'احتجاج', 'احتجاجات', 'مظاهرات', 'انقلاب', 'إرهاب', 'ارهابي', 'الحوثي',
            'الحوثيين', 'انتقاد', 'انتقادات', 'ينتقد', 'منتقد', 'اتهام', 'اتهامات', 'متهم', 'مزاعم', 'ادعاءات', 'قمع', 'الرقابة على',
            'اعتقال', 'احتجاز', 'معتقل', 'سجن', 'السجن', 'معارضين', 'المعارضة السياسية', 'معارض سياسي', 'فضيحة', 'انتهاك', 'انتهاكات', 'تعذيب',
            'إعدام', 'مخاوف أمنية', 'تهديد أمني', 'دعوى قضائية', 'دعاوى قضائية'),
    r'عقوبات علي (?:شركه|شركات|كيان|كيانات|افراد|مسوول|مسوولين|مسؤول|مسؤولين|دوله|دول)',  # normalised: على -> علي
    _ar_words('حرب'),
)), re.I)

def policy_problems(o, where):
    """Every text field under `o` that names the UAE or a GCC state, leader or state entity together with risk wording
    (RISK_TERMS: P1-P4 of the owner's content policy)."""
    errs = []
    if isinstance(o, dict):
        for k, v in o.items():
            if k not in ('url', 'href', 'id', 'image', 'images', 'src', 'photo'):
                errs += policy_problems(v, f'{where}.{k}')
    elif isinstance(o, list):
        for i, v in enumerate(o):
            errs += policy_problems(v, f'{where}[{i}]')
    elif isinstance(o, str):
        text = policy.normalize(o)
        risk = RISK_TERMS.search(text)
        name = risk and region_name(text)
        if name:
            errs.append(f'{where} breaks the content policy: it pairs {name!r} with {risk.group(0).strip()!r}; '
                        'reword it neutrally or leave it out')
    return errs

def region_name(text):
    """The first UAE/GCC name in the text ('' when none): this module's list, then the fuller region detection of
    scripts/policy.py (the one the news check uses)."""
    m = GCC_NAMES.search(policy.normalize(text))
    if m:
        return m.group(0).strip()
    found = policy.region_terms(text)
    return found[0] if found else ''

ABOUT = ROOT / 'data' / 'about.json'
FIXED_CONTENT = (UAE, ABOUT, CATALOG)

def fixed_content_problems(paths=FIXED_CONTENT):
    """The policy guard over the other fixed pages (data/uae.json, data/about.json, and the hardware notes, use lines,
    price notes and other text of data/catalog.json); a missing file is skipped."""
    errs = []
    for p in paths:
        try:
            doc = json.loads(Path(p).read_text(encoding='utf-8'))
        except FileNotFoundError:
            continue
        errs += policy_problems(doc, Path(p).name)
    return errs

def uae_fact_ids(path=UAE):
    """The ids of data/uae.json's facts, which #uae/f/<id> links open on the overview (empty when the file is missing)."""
    try:
        return {f['id'] for f in json.loads(Path(path).read_text(encoding='utf-8')).get('facts', [])}
    except FileNotFoundError:
        return set()

def _link_problem(link, products, fact_ids, hardware_only=False):
    """Why a site or hardware chip would not open what its label says ('' when it is fine)."""
    if not isinstance(link, dict):
        return 'must be an object with labels and an href'
    href = str(link.get('href') or '')
    if hardware_only and not HW_HREF.match(href):
        return f'href {href!r} is not a hardware route'
    if not SITE_HREF.match(href):
        return f'href {href!r} is not a page of this site'
    if RUN_LABEL in str(link.get('label_en') or '') and href not in RUN_HREFS:
        return f'href {href!r} must open the estimator ({" or ".join(RUN_HREFS)}) because the label names it'
    m = HW_HREF.match(href)
    if href.startswith('#hardware') and not m:
        return f'href {href!r} is not a hardware route'
    if m:
        route, arg = m.group(1), m.group(2)
        if route in ('p', 'level', 'vendor') and not arg:
            return f'href {href!r} needs an id'
        if route == 'p' and arg not in {p['id'] for p in products}:
            return f'product {arg!r} is not in data/catalog.json'
        if route == 'level' and arg not in {p.get('level') for p in products}:
            return f'level {arg!r} is not a catalog level'
        if route == 'vendor' and arg not in {p.get('vendor') for p in products}:
            return f'vendor {arg!r} is not a catalog vendor'
        if route not in ('p', 'level', 'vendor') and arg:
            return f'href {href!r}: #hardware/{route} takes nothing after it'
    m = UAE_FACT.match(href)
    if m and m.group(1) not in fact_ids:
        return f'UAE fact {m.group(1)!r} is not in data/uae.json'
    return ''

def _sources(x, where, errs):
    src = x.get('sources')
    if not isinstance(src, list) or not src:
        errs.append(f'{where} has no sources')
        return
    for j, s in enumerate(src):
        if not (isinstance(s, dict) and _filled(s.get('label')) and _https(s.get('url'))):
            errs.append(f'{where}.sources[{j}] needs a label and an https url')

def validate(concepts_doc, stacks_doc, products, fact_ids=None, fixed_paths=FIXED_CONTENT):
    """Raise LearnDataError listing every problem: ids, bilingual text, cross references, links, hardware and UAE fact
    ids, and the content policy guard (policy_problems) over the Learn text and the fixed pages in fixed_paths.
    fact_ids defaults to the facts in data/uae.json."""
    errs = policy_problems(concepts_doc, 'concepts') + policy_problems(stacks_doc, 'stacks') + fixed_content_problems(fixed_paths)
    fact_ids = uae_fact_ids() if fact_ids is None else set(fact_ids)
    groups, concepts = concepts_doc.get('groups') or [], concepts_doc.get('concepts') or []
    stacks = stacks_doc.get('stacks') or []
    if not all(isinstance(x, dict) for x in groups + concepts + stacks):
        raise LearnDataError('problem(s) in data/learn:\n  every group, concept and stack must be an object')
    group_ids = _ids(groups, 'group', errs)
    concept_ids = _ids(concepts, 'concept', errs)
    stack_ids = _ids(stacks, 'stack', errs)
    if not concepts:
        errs.append('no concepts')
    if not stacks:
        errs.append('no stacks')
    _walk(concepts_doc, 'concepts', errs)
    _walk(stacks_doc, 'stacks', errs)
    for g in groups:
        for k in ('title', 'intro'):
            if not _filled(g.get(k + '_en')):
                errs.append(f'group {g.get("id")}: {k}_en missing')
        _arabic_prose(g, ('intro',), f'group {g.get("id")}', errs)
    for c in concepts:
        at = f'concept {c.get("id")}'
        _arabic_prose(c, CONCEPT_PROSE, at, errs)
        if c.get('group') not in group_ids:
            errs.append(f'{at}: unknown group {c.get("group")!r}')
        if c.get('level') not in LEVELS:
            errs.append(f'{at}: unknown level {c.get("level")!r}')
        for k in CONCEPT_TEXT:
            if not _filled(c.get(k + '_en')):
                errs.append(f'{at}: {k}_en missing')
        if c.get('as_of') is not None and not AS_OF.match(str(c['as_of'])):
            errs.append(f'{at}: as_of must be YYYY-MM or null')
        for r in c.get('related') or []:
            if r not in concept_ids or r == c.get('id'):
                errs.append(f'{at}: related concept {r!r} does not exist')
        for j, les in enumerate(c.get('related_lessons') or []):
            if not (isinstance(les, dict) and isinstance(les.get('lesson'), int) and les['lesson'] > 0 and _filled(les.get('title_en'))):
                errs.append(f'{at}: related_lessons[{j}] needs a lesson number and titles')
        for j, s in enumerate(c.get('site_links') or []):
            problem = _link_problem(s, products, fact_ids)
            if problem:
                errs.append(f'{at}: site_links[{j}] {problem}')
        _sources(c, at, errs)
    for s in stacks:
        at = f'stack {s.get("id")}'
        _arabic_prose(s, STACK_PROSE, at, errs)
        if s.get('kind') not in KINDS:
            errs.append(f'{at}: kind must be one of {KINDS}')
        for k in STACK_TEXT:
            if not _filled(s.get(k + '_en')):
                errs.append(f'{at}: {k}_en missing')
        if s.get('as_of') is not None and not AS_OF.match(str(s['as_of'])):
            errs.append(f'{at}: as_of must be YYYY-MM or null')
        for r in s.get('related_stacks') or []:
            if r not in stack_ids or r == s.get('id'):
                errs.append(f'{at}: related stack {r!r} does not exist')
        for r in s.get('related_concepts') or []:
            if r not in concept_ids:
                errs.append(f'{at}: related concept {r!r} does not exist')
        for j, h in enumerate(s.get('hardware_links') or []):
            problem = _link_problem(h, products, fact_ids, hardware_only=True)
            if problem:
                errs.append(f'{at}: hardware_links[{j}] {problem}')
        layers = s.get('layers')
        if not isinstance(layers, list) or not layers:
            errs.append(f'{at}: no layers')
            layers = []
        for j, layer in enumerate(layers):
            if not isinstance(layer, dict):
                errs.append(f'{at} layer {j}: must be an object')
                continue
            la = f'{at} layer {layer.get("id") or j}'
            for k in ('name', 'role'):
                if not _filled(layer.get(k + '_en')):
                    errs.append(f'{la}: {k}_en missing')
            opts = layer.get('options') or {}
            if not isinstance(opts, dict) or set(opts) - {c for c, _, _ in OPTION_COLUMNS}:
                errs.append(f'{la}: options must be grouped as local, cloud and uae')
                opts = {}
            for col, lst in opts.items():
                if not isinstance(lst, list):
                    errs.append(f'{la}: options.{col} must be a list')
                    continue
                for n, o in enumerate(lst):
                    if not (isinstance(o, dict) and _filled(o.get('name')) and _https(o.get('url'))
                            and _filled(o.get('note_en')) and _filled(o.get('note_ar'))):
                        errs.append(f'{la}: options.{col}[{n}] needs a name, an https url and notes')
            pick = layer.get('pick')
            if pick is not None and not (isinstance(pick, dict) and _filled(pick.get('name'))
                                         and _filled(pick.get('why_en')) and _filled(pick.get('why_ar'))):
                errs.append(f'{la}: pick needs a name and a reason')
        _sources(s, at, errs)
    if errs:
        raise LearnDataError(f'{len(errs)} problem(s) in data/learn:\n  ' + '\n  '.join(errs))

# ---------- markup helpers ----------

def esc(v):
    return html.escape(str(v if v is not None else ''), quote=True)

def L(en, ar):
    """Both language versions of inline text (already escaped); CSS shows the one matching <html lang>."""
    return f'<span data-lang="en">{en}</span><span data-lang="ar">{ar}</span>'

def T(o, key):
    return L(esc(o[key + '_en']), esc(o[key + '_ar']))

def B(tag, en, ar, cls=''):
    """A block in both languages: <tag data-lang="en"> … and <tag data-lang="ar"> … (content already built)."""
    c = f' class="{cls}"' if cls else ''
    return f'<{tag}{c} data-lang="en">{en}</{tag}><{tag}{c} data-lang="ar" lang="ar">{ar}</{tag}>'

def paras(o, key):
    return B('div', ''.join(f'<p>{esc(p)}</p>' for p in o[key + '_en']), ''.join(f'<p>{esc(p)}</p>' for p in o[key + '_ar']), 'it-text')

def bullets(o, key):
    return B('ul', ''.join(f'<li>{esc(x)}</li>' for x in o[key + '_en']), ''.join(f'<li>{esc(x)}</li>' for x in o[key + '_ar']), 'it-list')

def para(o, key, cls='it-p'):
    return B('p', esc(o[key + '_en']), esc(o[key + '_ar']), cls)

def sec(title_en, title_ar, body, cls=''):
    c = f' {cls}' if cls else ''
    return f'<section class="it-sec{c}"><h5>{L(title_en, title_ar)}</h5>{body}</section>'

EN_MONTHS_FULL = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
AR_MONTHS = ['يناير', 'فبراير', 'مارس', 'أبريل', 'مايو', 'يونيو', 'يوليو', 'أغسطس', 'سبتمبر', 'أكتوبر', 'نوفمبر', 'ديسمبر']

def month(value, lang):
    m = AS_OF.match(str(value or ''))
    if not m:
        return ''
    return f'{(AR_MONTHS if lang == "ar" else EN_MONTHS_FULL)[int(m.group(2)) - 1]} {m.group(1)}'

def as_of_tag(value):
    if not value:
        return ''
    return f'<span class="asof">{L("As of " + month(value, "en"), "وفق معلومات " + month(value, "ar"))}</span>'

NOUNS = {
    'concept': (('concept', 'concepts'), ('مفهوم واحد', 'مفهومان', 'مفاهيم', 'مفهوماً', 'مفهوم')),
    'stack': (('AI stack', 'AI stacks'), ('تركيبة واحدة', 'تركيبتان', 'تركيبات', 'تركيبة', 'تركيبة')),
    'foundation': (('foundation', 'foundations'), ('أساس واحد', 'أساسان', 'أسس', 'أساساً', 'أساس')),
}

def cnt(n, kind, lang):
    """Number + noun with English plurals and Arabic number agreement (the same rule as cnt() in build.py)."""
    en, ar = NOUNS[kind]
    if lang != 'ar':
        return f'{n} {en[0] if n == 1 else en[1]}'
    if n == 1:
        return ar[0]
    if n == 2:
        return ar[1]
    r = n % 100
    return f'{n} {ar[2]}' if 3 <= r <= 10 else f'{n} {ar[3]}' if 11 <= r <= 99 else f'{n} {ar[4]}'

OUT_LINK = 'target="_blank" rel="noopener noreferrer"'
# The series name in Arabic, kept on one line (otherwise «و» can end a line and «AI» start the next).
QAHWA_AR = '<span class="l-nw">قهوة و AI</span>'
BOOK = ('<svg viewBox="0 0 24 24" width="21" height="21" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
        'stroke-linejoin="round" aria-hidden="true"><path d="M12 6.5C10.5 5 8 4.5 4 4.5v13c4 0 6.5.5 8 2 1.5-1.5 4-2 8-2v-13c-4 0-6.5.5-8 2z"/>'
        '<path d="M12 6.5v13"/></svg>')

def sources(o):
    items = ''.join(f'<li><a href="{esc(s["url"])}" {OUT_LINK} lang="en" dir="ltr">{esc(s["label"])}</a></li>' for s in o['sources'])
    return sec('Sources', 'المصادر', f'<ul class="srcs">{items}</ul>', 'it-srcs')

def chips(links):
    return f'<div class="lchips">{"".join(links)}</div>' if links else ''

# ---------- concepts ----------

def lesson_title(t):
    return ' '.join(str(t).split())

def concept_item(c, by_id, home, instagram):
    lv_en, lv_ar = LEVELS[c['level']]
    related = [f'<a class="lchip rel" href="#concept/{esc(r)}">{T(by_id[r], "title")}</a>' for r in c.get('related') or []]
    lessons = [f'<a class="lchip lesson" href="{esc(instagram)}" {OUT_LINK}>'
               + L(f'Qahwa &amp; AI lesson {les["lesson"]:02d}: {esc(lesson_title(les["title_en"]))}',
                   f'{QAHWA_AR}، الدرس {les["lesson"]:02d}: {esc(lesson_title(les["title_ar"]))}') + '</a>'
               for les in c.get('related_lessons') or []]
    site_links = [f'<a class="lchip site" href="{esc(home + s["href"])}">{T(s, "label")}</a>' for s in c.get('site_links') or []]
    body = (sec('How it works', 'كيف يعمل', paras(c, 'body'))
            + sec('Example', 'مثال', para(c, 'example', 'it-p ex'))
            + '<div class="two">' + sec('Best practices', 'أفضل الممارسات', bullets(c, 'practices'), 'do')
            + sec('Common mistakes and myths', 'أخطاء وخرافات شائعة', bullets(c, 'mistakes'), 'dont') + '</div>'
            + (sec('Related concepts', 'مفاهيم مرتبطة', chips(related)) if related else '')
            + (sec('Qahwa &amp; AI lessons', f'دروس {QAHWA_AR}', chips(lessons)) if lessons else '')
            + (sec('On this site', 'في هذا الموقع', chips(site_links)) if site_links else '')
            + sources(c))
    return (f'<details class="l-item" id="concept/{esc(c["id"])}" data-group="{esc(c["group"])}">'
            f'<summary><span class="it-head"><h4 class="it-t">{T(c, "title")}</h4>'
            f'<span class="lv lv-{esc(c["level"])}">{L(lv_en, lv_ar)}</span>{as_of_tag(c.get("as_of"))}</span>'
            f'<span class="it-sum">{T(c, "summary")}</span></summary>'
            f'<div class="it-body">{body}</div></details>')

# ---------- stacks ----------

def flow(s):
    # The arrows between the steps are drawn by learn.css and point the reading direction (they flip in Arabic).
    step = lambda x: f'<li><span class="step">{esc(x)}</span></li>'
    return B('ol', ''.join(step(x) for x in s['flow_en']), ''.join(step(x) for x in s['flow_ar']), 'flow')

def options_table(s):
    head = ''.join(f'<th scope="col">{L(en, ar)}</th>' for _, en, ar in OPTION_COLUMNS)
    rows = ''
    for layer in s['layers']:
        cells = ''
        for col, en, ar in OPTION_COLUMNS:
            opts = (layer.get('options') or {}).get(col) or []
            if opts:
                lis = ''.join(f'<li><a href="{esc(o["url"])}" {OUT_LINK}><bdi lang="en">{esc(o["name"])}</bdi></a>'
                              f'<small>{T(o, "note")}</small></li>' for o in opts)
                inner = f'<ul class="opts">{lis}</ul>'
            else:
                inner = f'<p class="none">{L("None listed", "لا يوجد خيار مدرج")}</p>'
            cells += f'<td data-col="{col}"><span class="cell-h">{L(en, ar)}</span>{inner}</td>'
        pick = layer.get('pick')
        pick_row = (f'<tr class="pick-row"><td colspan="4"><p class="pick"><b>{L("Our starter pick:", "اختيارنا للبداية:")}</b> '
                    f'<bdi lang="en">{esc(pick["name"])}</bdi>. {T(pick, "why")}</p></td></tr>') if pick else ''
        rows += (f'<tbody class="layer"><tr><th scope="row"><b>{T(layer, "name")}</b><small>{T(layer, "role")}</small></th>{cells}</tr>'
                 f'{pick_row}</tbody>')
    return (f'<div class="opt-wrap"><table class="opt"><thead><tr><th scope="col">{L("Building block", "المكوّن")}</th>{head}</tr></thead>'
            f'{rows}</table></div>')

def stack_item(s, by_stack, by_concept, home):
    hw = [f'<a class="lchip hw" href="{esc(home + h["href"])}">{T(h, "label")}</a>' for h in s.get('hardware_links') or []]
    rel_s = [f'<a class="lchip rel" href="#stack/{esc(r)}">{T(by_stack[r], "title")}</a>' for r in s.get('related_stacks') or []]
    rel_c = [f'<a class="lchip rel" href="#concept/{esc(r)}">{T(by_concept[r], "title")}</a>' for r in s.get('related_concepts') or []]
    body = (sec('How it flows', 'مسار العمل', flow(s))
            + '<div class="two">' + sec('Use it when', 'استخدمه عندما', bullets(s, 'use_when'), 'do')
            + sec('Avoid it when', 'تجنّبه عندما', bullets(s, 'avoid_when'), 'dont') + '</div>'
            + sec('Building blocks', 'المكوّنات', options_table(s))
            + sec('Hardware', 'العتاد', para(s, 'hardware') + chips(hw))
            + sec('Arabic and Gulf notes', 'ملاحظات عربية وخليجية', para(s, 'arabic'))
            + '<div class="two">' + sec('Best practices', 'أفضل الممارسات', bullets(s, 'practices'), 'do')
            + sec('Pitfalls', 'مزالق', bullets(s, 'pitfalls'), 'dont') + '</div>'
            + sec('What drives cost', 'ما الذي يحدد التكلفة', para(s, 'cost'))
            + (sec('Related stacks', 'تركيبات مرتبطة', chips(rel_s)) if rel_s else '')
            + (sec('Related concepts', 'مفاهيم مرتبطة', chips(rel_c)) if rel_c else '')
            + sources(s))
    group = 'foundation' if s['kind'] == 'foundation' else 'core'
    icon = f'<span class="s-ic" aria-hidden="true">{esc(s["icon"])}</span>' if s.get('icon') else ''
    return (f'<details class="l-item l-stack" id="stack/{esc(s["id"])}" data-group="{group}">'
            f'<summary><span class="it-head"><span class="it-tl">{icon}<h4 class="it-t">{T(s, "title")}</h4></span>{as_of_tag(s.get("as_of"))}</span>'
            f'<span class="it-sum">{T(s, "summary")}</span></summary>'
            f'<div class="it-body">{body}</div></details>')

# ---------- page ----------

def filter_chip(value, label, n):
    return (f'<button type="button" class="fchip" data-filter="{esc(value)}" aria-pressed="{"true" if not value else "false"}">'
            f'{label} <span class="n">{n}</span></button>')

def filters(aria_en, aria_ar, chips_html):
    return (f'<div class="l-filter js-only" role="group" aria-label="{esc(aria_en)}" data-aria-ar="{esc(aria_ar)}">{chips_html}</div>')

def concepts_panel(groups, concepts, home, instagram):
    by_id = {c['id']: c for c in concepts}
    chip_row = filter_chip('', L('All topics', 'كل المواضيع'), len(concepts)) + ''.join(
        filter_chip(g['id'], T(g, 'title'), sum(c['group'] == g['id'] for c in concepts)) for g in groups)
    out = ''
    for g in groups:
        items = ''.join(concept_item(c, by_id, home, instagram) for c in concepts if c['group'] == g['id'])
        out += (f'<section class="l-group" id="group/{esc(g["id"])}" data-group="{esc(g["id"])}" aria-labelledby="h-{esc(g["id"])}">'
                f'<div class="g-head"><h3 id="h-{esc(g["id"])}">{T(g, "title")}</h3>{para(g, "intro", "g-intro")}</div>'
                f'<div class="l-items">{items}</div></section>')
    lead = L('Key AI ideas in plain language, grouped by topic. Each one has an example, best practices, common mistakes and its sources.',
             'أهم أفكار الذكاء الاصطناعي بلغة واضحة، مصنّفة حسب الموضوع، ولكل منها مثال وأفضل الممارسات والأخطاء الشائعة ومصادرها.')
    return (f'<section id="concepts" class="l-panel" data-panel="concepts" aria-labelledby="concepts-h">'
            f'<div class="p-intro"><h2 id="concepts-h">{L("Concepts", "المفاهيم")}</h2><p>{lead}</p></div>'
            f'{filters("Filter concepts by topic", "تصفية المفاهيم حسب الموضوع", chip_row)}{out}</section>')

def stacks_panel(stacks, concepts, home):
    by_stack, by_concept = {s['id']: s for s in stacks}, {c['id']: c for c in concepts}
    core = [s for s in stacks if s['kind'] != 'foundation']
    found = [s for s in stacks if s['kind'] == 'foundation']
    chip_row = (filter_chip('', L('All', 'الكل'), len(stacks)) + filter_chip('core', L('Core stacks', 'التركيبات الأساسية'), len(core))
                + filter_chip('foundation', L('Foundations', 'الأسس'), len(found)))
    item = lambda s: stack_item(s, by_stack, by_concept, home)
    lead = L('Recommended building blocks for common AI projects. Each stack shows how the parts connect, with local, managed-cloud and UAE-hosted options and our starter pick for each part.',
             'مكوّنات موصى بها لمشاريع الذكاء الاصطناعي الشائعة. تعرض كل تركيبة كيف تترابط أجزاؤها، مع خيارات محلية وسحابية مُدارة ومستضافة في الإمارات، واختيارنا للبداية لكل جزء.')
    return (f'<section id="stacks" class="l-panel" data-panel="stacks" aria-labelledby="stacks-h">'
            f'<div class="p-intro"><h2 id="stacks-h">{L("AI stacks", "التركيبات التقنية")}</h2><p>{lead}</p></div>'
            f'{filters("Filter stacks", "تصفية التركيبات", chip_row)}'
            f'<section class="l-group" id="group/core" data-group="core" aria-labelledby="h-core"><div class="g-head"><h3 id="h-core">{L("Core stacks", "التركيبات الأساسية")}</h3>'
            f'<p class="g-intro">{L("Pick the stack that matches what you want to build, then open it for the building blocks.", "اختر التركيبة التي تناسب ما تريد بناءه، ثم افتحها لترى مكوّناتها.")}</p></div>'
            f'<div class="l-items">{"".join(item(s) for s in core)}</div></section>'
            f'<section class="l-group" id="group/foundation" data-group="foundation" aria-labelledby="h-foundation"><div class="g-head"><h3 id="h-foundation">{L("Foundations: apply to every stack", "الأسس: تنطبق على كل تركيبة")}</h3>'
            f'<p class="g-intro">{L("Whatever you build, decide these three early: where it runs, how it handles Arabic, and how you test it.", "أياً كان ما تبنيه، حدّد هذه الثلاثة مبكراً: أين يعمل، وكيف يتعامل مع العربية، وكيف تختبره.")}</p></div>'
            f'<div class="l-items">{"".join(item(s) for s in found)}</div></section></section>')

TITLE = {'en': 'Learn AI · Cipher Lacuna', 'ar': 'تعلّم الذكاء الاصطناعي · Cipher Lacuna'}
TAGLINE = ('Decoding the gaps in AI knowledge', 'كشف المجهول في عالم الذكاء الاصطناعي')
# Before first paint: theme, language (same keys and ?lang= rule as the overview) and the open tab, so nothing flashes.
HEAD_SCRIPT = ("(function(d){d.classList.add('js');var t=null,l=null,q=null;try{t=localStorage.getItem('atlas-theme');l=localStorage.getItem('atlas-lang')}catch(e){}"
               "if(t==='light'||t==='dark')d.dataset.theme=t;try{q=new URLSearchParams(location.search).get('lang')}catch(e){}if(q)l=q;"
               "if(l==='ar'){d.lang='ar';d.dir='rtl'}d.dataset.ltab=/^#(stack|group[/](core|foundation)$)/.test(location.hash)?'stacks':'concepts'})(document.documentElement)")

def render(concepts_doc, stacks_doc, catalog=None, home='index.html', brand_dir=None):
    """Return the learn.html text. Pure: writes nothing. `home` is the overview page the links go back to."""
    s = site()
    icon = lambda k: s.ICON.get(k, '')
    instagram = s.INSTAGRAM
    logo, favicon = s.brand_assets(brand_dir) if brand_dir else s.brand_assets()
    groups, concepts = concepts_doc['groups'], concepts_doc['concepts']
    stacks = sorted(stacks_doc['stacks'], key=lambda x: x.get('order', 0))
    n_c, n_core = len(concepts), sum(x['kind'] != 'foundation' for x in stacks)
    n_found = len(stacks) - n_core
    latest = max((str(x.get('as_of')) for x in concepts + stacks if x.get('as_of')), default='')
    year = str((catalog or {}).get('updated_at') or latest or '')[:4]
    h = esc(home)
    arrow = icon('arrow')
    follow = (f'<a class="ig follow-btn" href="{esc(instagram)}" {OUT_LINK}>{icon("ig")}{L("Follow Qahwa &amp; AI", f"تابع {QAHWA_AR}")} '
              '<bdi class="handle" lang="en">@qahwa.w.ai</bdi></a>')
    learn_name = L('Learn AI', 'تعلّم الذكاء الاصطناعي')
    desc = (f'Learn AI with Cipher Lacuna: {n_c} key AI concepts in plain language with best practices, and {n_core} recommended AI stacks '
            f'with local, cloud and UAE-hosted options, plus {cnt(n_found, "foundation", "en")} that apply to every stack, in English and Arabic.')
    og_alt = 'Cipher Lacuna cube logo with the tagline Decoding the gaps in AI knowledge, in English and Arabic'
    head = (f'<!doctype html>\n<html lang="en" dir="ltr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<meta name="color-scheme" content="light dark"><meta name="theme-color" content="#6537d7"><title>{esc(TITLE["en"])}</title>'
            f'<meta name="description" content="{esc(desc)}"><meta name="author" content="Cipher Lacuna">'
            f'<link rel="icon" type="image/png" sizes="32x32" href="brand/icon-32.png"><link rel="icon" type="image/svg+xml" href="{favicon}">'
            f'<link rel="apple-touch-icon" href="brand/apple-touch-icon.png">\n'
            f'<meta property="og:type" content="website"><meta property="og:site_name" content="Cipher Lacuna"><meta property="og:title" content="{esc(TITLE["en"])}">'
            f'<meta property="og:description" content="{esc(desc)}"><meta property="og:url" content="{SITE_URL}{PAGE}">'
            f'<meta property="og:image" content="{SITE_URL}brand/og.png"><meta property="og:image:type" content="image/png"><meta property="og:image:width" content="1200">'
            f'<meta property="og:image:height" content="630"><meta property="og:image:alt" content="{esc(og_alt)}"><meta property="og:locale" content="en_US">'
            f'<meta property="og:locale:alternate" content="ar_AE">\n'
            f'<meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="{esc(TITLE["en"])}"><meta name="twitter:description" content="{esc(desc)}">'
            f'<meta name="twitter:image" content="{SITE_URL}brand/og.png"><meta name="twitter:image:alt" content="{esc(og_alt)}">\n'
            f'<script>{HEAD_SCRIPT}</script>\n<style>{_asset("style.css")}\n{_asset("learn.css")}</style></head>\n')
    lang_btn = ('<button type="button" class="btn-ghost js-only" id="lang"><span class="l-long"><span data-lang="en" lang="ar">العربية</span>'
                '<span data-lang="ar" lang="en">English</span></span><span class="l-short" aria-hidden="true"><span data-lang="en" lang="ar">عربي</span>'
                '<span data-lang="ar" lang="en">EN</span></span></button>')
    header = (f'<body><a class="skip" href="#main" id="skip">{L("Skip to content", "انتقل إلى المحتوى")}</a>\n'
              f'<header class="top"><div class="wrap top-in"><a class="brand" href="{h}">{logo}<span class="brand-text"><span class="wordmark" lang="en" dir="ltr">Cipher <span class="wm-2">Lacuna</span></span>'
              f'<span class="brand-sec" id="brand-sec">{learn_name}</span><span class="tagline">{L(*TAGLINE)}</span></span></a>\n'
              f'<nav class="nav" aria-label="Main sections" data-aria-ar="الأقسام الرئيسية"><a href="{h}" class="n-home">{icon("home")}<span class="nl">{L("Overview", "الرئيسية")}</span></a>'
              f'<a href="{h}#hardware" class="n-hw"><i class="dot" aria-hidden="true"></i><span>{L("Hardware", "العتاد")}</span></a>'
              f'<a href="{h}#news" class="n-news"><i class="dot" aria-hidden="true"></i><span class="nl-full">{L("AI news", "أخبار الذكاء الاصطناعي")}</span><span class="nl-short" aria-hidden="true">{L("News", "الأخبار")}</span></a>'
              f'<a href="{h}#uae" class="n-uae"><i class="dot" aria-hidden="true"></i><span class="nl-full">{L("UAE AI", "الذكاء الاصطناعي في الإمارات")}</span><span class="nl-short" aria-hidden="true">{L("UAE", "الإمارات")}</span></a>'
              f'<a href="{PAGE}" class="n-learn" aria-current="page"><i class="dot" aria-hidden="true"></i><span class="nl-full">{learn_name}</span><span class="nl-short" aria-hidden="true">{L("Learn", "تعلّم")}</span></a>'
              f'<a href="{h}#contact" class="n-contact">{icon("mail")}<span class="nl">{L("Contact", "تواصل معنا")}</span></a></nav>\n'
              f'<div class="ctrl"><a class="btn-ghost ig-mini" href="{esc(instagram)}" {OUT_LINK} aria-label="Instagram @qahwa.w.ai">{icon("ig")}<bdi lang="en">@qahwa.w.ai</bdi></a>'
              f'{lang_btn}<button type="button" class="btn-ghost js-only" id="theme" aria-label="Theme: Auto">{icon("theme")}<span class="theme-label" id="theme-label">{L("Auto", "تلقائي")}</span></button></div></div></header>\n')
    lead = L('Plain-language guides to the ideas behind today\'s AI, and recommended stacks for building with it: local, cloud and UAE-hosted options, each with its sources.',
             'شروح واضحة للأفكار التي يقوم عليها الذكاء الاصطناعي اليوم، وتركيبات تقنية موصى بها للبناء به: خيارات محلية وسحابية ومستضافة في الإمارات، ولكل منها مصادرها.')
    status = (f'<p class="statusbar"><span>{L(esc(cnt(n_c, "concept", "en")), cnt(n_c, "concept", "ar"))} · {L(esc(cnt(n_core, "stack", "en")), cnt(n_core, "stack", "ar"))} · '
              f'{L(esc(cnt(n_found, "foundation", "en")), cnt(n_found, "foundation", "ar"))}</span>'
              + (f'<span><b>{L("Content as of", "المحتوى وفق معلومات")}</b> {L(month(latest, "en"), month(latest, "ar"))}</span>' if latest else '') + '</p>')
    ihead = (f'<div class="ihead ih-learn"><nav class="crumbs" aria-label="Breadcrumb" data-aria-ar="مسار التنقل"><a href="{h}">{L("Overview", "الرئيسية")}</a>'
             f'<span aria-hidden="true">/</span><span aria-current="page">{learn_name}</span></nav>'
             f'<div class="ihead-row"><div><h1 id="learn-title" tabindex="-1">{learn_name}</h1><p class="lead">{lead}</p></div>'
             f'<div class="ihead-acts"><a class="back" href="{h}">{icon("back")}<span>{L("Back to overview", "العودة إلى الرئيسية")}</span></a>{follow}</div></div>{status}</div>')
    tools = (f'<div class="l-tools"><nav class="l-tabs" aria-label="Learn AI sections" data-aria-ar="أقسام تعلّم الذكاء الاصطناعي">'
             f'<a class="l-tab" href="#concepts" data-tab="concepts">{L("Concepts", "المفاهيم")} <span class="n" data-count="concepts">{n_c}</span></a>'
             f'<a class="l-tab" href="#stacks" data-tab="stacks">{L("AI stacks", "التركيبات التقنية")} <span class="n" data-count="stacks">{n_core}</span></a></nav>'
             f'<label class="l-search js-only"><span class="sr-only">{L("Search concepts and stacks", "ابحث في المفاهيم والتركيبات")}</span>'
             f'<input id="lq" class="inp" type="search" autocomplete="off" spellcheck="false" placeholder="Search concepts and stacks…" data-ph-ar="ابحث في المفاهيم والتركيبات…"></label></div>'
             f'<p class="l-count js-only" id="l-count" aria-live="polite"></p>'
             f'<p class="l-empty" id="l-empty" hidden>{L("No matches. Try another word or clear the search.", "لا توجد نتائج. جرّب كلمة أخرى أو امسح البحث.")}</p>')
    note = (f'<p class="muted l-note">{L("These guides are editorial summaries for learning. Products, services, prices and regional availability change, so check the linked sources before you decide. Qahwa &amp; AI lesson links open the @qahwa.w.ai Instagram account.", f"هذه الشروح ملخصات تحريرية لأغراض التعلّم. المنتجات والخدمات والأسعار والتوفّر حسب المنطقة تتغيّر، لذا راجع المصادر المرفقة قبل أن تتخذ قرارك. روابط دروس {QAHWA_AR} تفتح حساب ‎@qahwa.w.ai على إنستغرام.")}</p>')
    cards = (('hardware', '', icon('hw'), L('Hardware', 'العتاد'), L('NVIDIA and AMD GPUs, desktop systems, servers and racks, side by side.', 'معالجات رسوميات وأجهزة مكتبية وخوادم ورفوف من NVIDIA وAMD، جنباً إلى جنب.')),
             ('news', ' x-news', icon('news'), L('AI news', 'أخبار الذكاء الاصطناعي'), L('The latest AI headlines in English and Arabic, each linked to the original article.', 'أحدث عناوين الذكاء الاصطناعي بالعربية والإنجليزية، ولكل عنوان رابط إلى المقال الأصلي.')),
             ('uae', ' x-uae', icon('uae'), L('UAE AI', 'الذكاء الاصطناعي في الإمارات'), L('Latest UAE AI headlines, then key facts on strategy, compute and models, each with its source.', 'أحدث عناوين الذكاء الاصطناعي في الإمارات، ثم حقائق رئيسية عن الاستراتيجية والحوسبة والنماذج، ولكل منها مصدره.')))
    xnav = ('<nav class="xnav" aria-label="Other areas" data-aria-ar="الأقسام الأخرى">' + ''.join(
        f'<a class="xcard{cls}" href="{h}#{v}"><span class="p-icon" aria-hidden="true">{ic}</span><span><b>{name}</b><span class="x-sub">{sub}</span></span><span class="x-arr">{arrow}</span></a>'
        for v, cls, ic, name, sub in cards) + '</nav>')
    main = (f'<main id="main" tabindex="-1"><div class="wrap">\n{ihead}\n{tools}\n'
            f'{concepts_panel(groups, concepts, home, instagram)}\n{stacks_panel(stacks, concepts, home)}\n{note}\n{xnav}\n</div></main>\n')
    footer = (f'<footer class="foot"><div class="wrap foot-in"><div><p class="foot-brand"><a class="brand" href="{h}"><span class="wordmark" lang="en" dir="ltr">Cipher <span class="wm-2">Lacuna</span></span></a></p>'
              f'<p class="foot-tag">{L(*TAGLINE)}</p><p><bdi lang="en">© {esc(year)} Cipher Lacuna.</bdi> {L("All rights reserved.", "جميع الحقوق محفوظة.")}</p>'
              f'<p>{L("Product images © NVIDIA and AMD. Headlines and publisher excerpts © their publishers, with links to the original articles. AI summaries are machine-written and may contain mistakes.", "صور المنتجات © NVIDIA وAMD. العناوين ومقتطفات الناشرين © لناشريها، مع روابط إلى المقالات الأصلية. ملخصات الذكاء الاصطناعي مكتوبة آلياً وقد تحتوي على أخطاء.")}</p></div>\n'
              f'<div class="foot-side">{follow}<p>{L("AI lessons and news from Qahwa &amp; AI, in English and Arabic.", f"دروس وأخبار الذكاء الاصطناعي من {QAHWA_AR}، بالعربية والإنجليزية.")}</p>'
              f'<nav class="foot-links" aria-label="Footer" data-aria-ar="تذييل الصفحة"><a href="{h}">{L("Overview", "الرئيسية")}</a><a href="{h}#hardware">{L("Hardware", "العتاد")}</a>'
              f'<a href="{h}#news">{L("AI news", "أخبار الذكاء الاصطناعي")}</a><a href="{h}#uae">{L("UAE AI", "الذكاء الاصطناعي في الإمارات")}</a>'
              f'<a href="{PAGE}" aria-current="page">{learn_name}</a><a href="{h}#contact">{L("Contact", "تواصل معنا")}</a><a href="{h}#contact/about">{L("About", "عن الموقع")}</a></nav></div></div></footer>\n')
    return head + header + main + footer + f'<script>{_asset("learn.js")}</script></body></html>\n'

def landing_card(data_dir=DATA, href=PAGE):
    """The overview's link card to this page, in both languages, using the overview's own .xcard styles (put it inside
    an .xnav). Counts come from the data. style.css needs `.xcard.x-learn{--c:var(--learn);--ink:var(--learn-ink)}`."""
    concepts_doc, stacks_doc = load(data_dir)
    n_c = len(concepts_doc['concepts'])
    n_s = sum(x['kind'] != 'foundation' for x in stacks_doc['stacks'])
    sub = L(esc(f'{cnt(n_c, "concept", "en")} in plain language and {cnt(n_s, "stack", "en")} to build with, in English and Arabic'),
            f'{cnt(n_c, "concept", "ar")} بلغة واضحة و{cnt(n_s, "stack", "ar")} للبناء بها، بالعربية والإنجليزية')
    return (f'<a class="xcard x-learn" href="{esc(href)}"><span class="p-icon" aria-hidden="true">{BOOK}</span>'
            f'<span><b>{L("Learn AI", "تعلّم الذكاء الاصطناعي")}</b><span class="x-sub">{sub}</span></span>'
            f'<span class="x-arr">{site().ICON.get("arrow", "")}</span></a>')

def _asset(name):
    text = (ROOT / 'web' / name).read_text(encoding='utf-8')
    closing = '</script' if name.endswith('.js') else '</style'
    if closing in text.lower():
        raise LearnDataError(f'web/{name} contains {closing}, which would end the inline block early')
    return text

def build(out_dir=OUT, home='index.html', data_dir=DATA, catalog_path=CATALOG, uae_path=UAE):
    """Validate the learn data and write <out_dir>/learn.html plus the brand PNGs it links (brand/). Returns the page path."""
    concepts_doc, stacks_doc = load(data_dir)
    catalog = json.loads(Path(catalog_path).read_text(encoding='utf-8'))
    validate(concepts_doc, stacks_doc, catalog['products'], uae_fact_ids(uae_path))
    page = render(concepts_doc, stacks_doc, catalog, home=home)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / PAGE
    target.write_text(page, encoding='utf-8', newline='\n')
    site().copy_brand_images(out_dir / 'brand')
    return target

def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--out', type=Path, default=OUT, help='folder to write learn.html into (default: dist/)')
    parser.add_argument('--home', default='index.html', help='file name of the overview page beside it (default: index.html)')
    args = parser.parse_args()
    path = build(args.out, home=args.home)
    concepts_doc, stacks_doc = load()
    st = stacks_doc['stacks']
    core = sum(s['kind'] != 'foundation' for s in st)
    print(f'Built {path.name}: {len(concepts_doc["concepts"])} concepts in {len(concepts_doc["groups"])} groups, '
          f'{core} stacks + {len(st) - core} foundations, {path.stat().st_size / 1024:.0f} KB')

if __name__ == '__main__':
    main()
