"""Cipher Lacuna's content policy for the UAE and the GCC states, and the region detection it relies on.

The owner approved this policy for everything shown on the website and in the Android app (which reads dist/app/*.json):
news headlines, excerpts and AI summaries as well as fixed content (UAE facts, Learn AI, About, hardware notes).

- mentions_region(*texts): True when any text names the UAE or a GCC state (Saudi Arabia, Qatar, Kuwait, Bahrain,
  Oman), one of their emirates, regions or cities, a ruling family or leader title, or a state-owned / state-linked
  entity. English and Arabic, case- and diacritic-insensitive, whole words only ("woman" is not Oman, the Gulf of
  Mexico is not the Gulf).
- regional_outlet(source): the UAE newsrooms (region "uae" in data/news-sources.json, which include the official Dubai
  Media Office feeds) and the GCC-based outlets marked "regional_outlet": true. may_cover_region(source): those plus
  any source marked "official_region": true (a UAE/GCC government source outside region "uae"). Only these may carry
  stories that mention the region (rule M1 in scripts/news.py). Global vendor newsrooms (kind "primary": NVIDIA, AMD,
  OpenAI ...) are not official sources of the region and may not.
- shown_ok(item): the display rule used by build.news_items() for the site and the app. A story that failed the check,
  or got an unusable answer (a refusal, bad output), is never shown; a story that mentions the region is shown only
  with a passing verdict at the current POLICY_VERSION for its current texts (policy_hash) (fail closed: no key, an
  API error or a refusal leaves it hidden).

POLICY is the text the AI check applies (scripts/news.py). When in doubt, leave it out; a failing story is dropped,
never rewritten to sound positive.
"""
import hashlib
import re
import unicodedata

# Bump when POLICY changes: stored verdicts from an older version no longer count, and those items are checked again
# (items that mention the region stay hidden until they are).
POLICY_VERSION = 1

POLICY = """Scope: the United Arab Emirates and the GCC states (Saudi Arabia, Qatar, Kuwait, Bahrain, Oman).

A story FAILS the policy if it does any of the following:
P1. Criticises, insults, mocks, blames or casts in a negative light the UAE or any GCC state, any emirate or region of them, their rulers and leaders (heads of state, crown princes, members of ruling families such as Al Nahyan, Al Maktoum, Al Qasimi, Al Nuaimi, Al Sharqi, Al Mualla, Al Saud, Al Thani, Al Sabah, Al Khalifa, Al Said, ministers, officials), their governments and institutions, armed forces, national symbols, or state-owned or state-linked entities (for example G42, MGX, Mubadala, ADNOC, ADQ, TII, Core42, Khazna, e&, PIF, HUMAIN, Aramco, NEOM, QIA, Ooredoo, KIA, Mumtalakat, Omantel).
P2. Covers those countries in a negative or controversial political frame: human-rights criticism, surveillance, spyware, security or espionage allegations, conflicts, wars and foreign-policy disputes, sanctions or export-control disputes that portray them as a risk, investigations or lawsuits against state bodies, allegations about officials, conflict damage or instability in those countries.
P3. Could harm national unity, public order or relations between states, or offends Islam or any religion.
P4. Spreads rumours or unverified claims about officials or institutions.

A story PASSES when it reports facts neutrally or positively and none of the above applies, for example product launches, investments, partnerships, research, events, education and official announcements.
When in doubt, the story fails."""

RULES = ('P1', 'P2', 'P3', 'P4')

# Fields of a news item the check reads and that the display rule looks at.
TEXT_FIELDS = ('title', 'title_ar', 'excerpt', 'summary_en', 'summary_ar')

# ---------- normalisation ----------

_AR_MARKS = re.compile('[ؐ-ًؚ-ٰٟۖ-ۭـ]')  # harakat, Quranic marks, tatweel
_AR_LETTERS = str.maketrans({'أ': 'ا', 'إ': 'ا', 'آ': 'ا', 'ٱ': 'ا', 'ى': 'ي', 'ة': 'ه', 'ک': 'ك', 'ی': 'ي', 'ؤ': 'و', 'ئ': 'ي'})
_DASHES = re.compile('[‐-―−_]')
_APOS = re.compile('[‘’ʼʻ`´]')
_INVISIBLE = re.compile('[​-‏‪-‮⁠-⁤﻿­]')
# "Amman" (Jordan) is written with a shadda: عمّان. Without marks it looks like Oman (عمان), so it is set aside first.
_AMMAN = re.compile('عم[ً-ٟ]*ّ[ً-ٟ]*ا[ً-ٟ]*ن')
# ... except after «سلطنة» (the Sultanate of Oman), whatever marks either word carries.
_M = '[ً-ٟـ]*'
_SULTANATE_OMAN = re.compile('س' + _M + 'ل' + _M + 'ط' + _M + 'ن' + _M + '[ةه]' + _M + r'\s+' + 'ع' + _M + 'م' + _M + 'ا' + _M + 'ن')
# Cyrillic and Greek letters that look like Latin ones ("Dubаi" with a Cyrillic а): matched as the Latin letter.
_CONFUSABLES = str.maketrans(
    '\u0410\u0412\u0415\u041a\u041c\u041d\u041e\u0420\u0421\u0422\u0425\u0423\u0405\u0406\u0408'
    '\u0430\u0435\u043e\u0440\u0441\u0445\u0443\u0455\u0456\u0458\u0501\u04bb'
    '\u0391\u0392\u0395\u0396\u0397\u0399\u039a\u039c\u039d\u039f\u03a1\u03a4\u03a5\u03a7\u03bf\u03b9\u03ba\u03bd',
    'ABEKMHOPCTXYSIJ' 'aeopcxysijdh' 'ABEZHIKMNOPTYXoikv')

def normalize(text):
    """Text for matching: Latin accents and Arabic diacritics removed, Arabic letter variants unified (أ/إ/آ -> ا,
    ى -> ي, ة -> ه), dashes and apostrophes unified, invisible characters removed. Case is kept (some acronyms such
    as KIA or PIF only count in capitals). Cyrillic and Greek look-alikes of Latin letters become Latin."""
    text = _INVISIBLE.sub('', str(text or ''))
    text = _AMMAN.sub(' AMMAN_JO ', _SULTANATE_OMAN.sub('سلطنه عمان', text))
    text = text.translate(_CONFUSABLES)
    text = ''.join(c for c in unicodedata.normalize('NFKD', text) if not (unicodedata.combining(c) and not '؀' <= c <= 'ۿ'))
    text = _AR_MARKS.sub('', text).translate(_AR_LETTERS)
    text = _DASHES.sub('-', _APOS.sub("'", text))
    return text

# ---------- region detection ----------

_SEP = r"[\s\-']+"  # "Al Nahyan", "Al-Nahyan", "Ras al-Khaimah" (never glued: "Alain" is not Al Ain)

def _en(*terms):
    return r'(?<![\w&])(?:' + '|'.join(terms) + r')(?![\w&])'

# Case-insensitive English names (whole words).
EN_TERMS = _en(
    # Countries, nationalities and the bloc
    r'U\.?A\.?E\.?', r'United' + _SEP + r'Arab' + _SEP + r'Emirates', r'Emirat(?:e|es|i|is)', r'Emirati[sz]ation',
    r'Saudis?', r'Saudi' + _SEP + r'Arabia', r'Qatar(?:i|is)?', r'Kuwait(?:i|is)?', r'Bahrain(?:i|is)?', r'Oman(?:i|is)?',
    r'Gulf' + _SEP + r'Cooperation' + _SEP + r'Council', r'Khaleeji',
    # "the Gulf", "Gulf states", "Arabian Gulf" - but not the Gulf of Mexico, Gulf Coast, Gulf Stream ...
    r"Gulf(?!" + _SEP + r"(?:of|Coast|Stream|Shores?|Islands?|Breeze|Port|South|Power|Oil" + r")(?![\w]))",
    # Emirates, regions and cities
    r"Abu[\s\-']*Dhabi", r'Dubai', r'Sharjah', r'Ajman', r'Ras' + _SEP + r'al' + _SEP + r'Khaimah?', r'Fujairah',
    r'Umm' + _SEP + r'al' + _SEP + r'Qu?aiwain', r'Umm' + _SEP + r'al' + _SEP + r'Quwain', r'Al' + _SEP + r'Ain', r'Khor' + _SEP + r'Fakkan',
    r'Riyadh?', r'Jedd?ah', r'Jiddah', r'Mecca', r'Makkah', r'Medina', r'Madinah', r'Dammam', r'Dhahran', r'Khobar', r'Tabuk', r'Al' + _SEP + r'Ula',
    r'Diriyah', r'NEOM', r'Doha', r'Lusail', r'Manama', r'Muscat', r'Salalah', r'Duqm', r'Masdar',
    r'Jebel' + _SEP + r'Ali', r'Yas', r'Saadiyat', r'Burj' + _SEP + r'Khalifa', r'Expo' + _SEP + r'City', r'Hub[\s\-]?71', r'Qiddiya',
    # Ruling families, leaders and titles
    r'Al' + _SEP + r'(?:Nahyan|Nahayan|Maktoum|Qasimi|Qassimi|Nuaimi|Sharqi|Mualla|Saud|Thani|Sabah|Khalifa|Said|Busaidi)',
    r'Nahyan', r'Maktoum', r'bin' + _SEP + r'(?:Zayed|Rashid|Salman|Tahnoun|Tahnoon|Hamad|Khalifa|Saqr|Humaid|Sultan' + _SEP + r'Al' + _SEP + r'Qasimi|Haitham|Tariq)',
    r'Sheikh(?:a)?', r'His' + _SEP + r'Highness', r'Crown' + _SEP + r'Prince', r'Custodian' + _SEP + r'of' + _SEP + r'the' + _SEP + r'Two' + _SEP + r'Holy' + _SEP + r'Mosques',
    r'King' + _SEP + r'(?:Salman|Hamad)', r'Emir' + _SEP + r'(?:Tamim|Mishal|Meshal)', r'Sultan' + _SEP + r'Haitham',
    # Leaders by first name or title alone ("Tahnoun", "Prince Mohammed", "the Emir"); over-matching is the safe side.
    r'Tahn(?:o|ou|oo)n', r'Hamdan', r'Tamim', r'Khalifa', r'Emirs?', r'Sultans?',
    r'Prince' + _SEP + r'(?:M[ou]h?am+[ae]d|Sultan|Abdul[\s\-]?aziz|Faisal|Turki|Khall?e?d|Bandar|Al[\s\-]?Waleed|Salman|Mishal|Nawaf|Nayef|Hamdan|Mansour)',
    # State-owned and state-linked entities
    r'G[\s\-]?42', r'Mubadala', r'ADNOC', r'Core[\s\-]?42', r'Khazna', r'Etisalat', r'Space[\s\-]?42', r'Presight', r'Inception' + _SEP + r'AI',
    r'Technology' + _SEP + r'Innovation' + _SEP + r'Institute', r'MBZUAI', r'Jais', r'Falcon' + _SEP + r'(?:LLM|H1R?|E|Arabic|Mamba|40B|180B|7B|2|3)',
    r'Public' + _SEP + r'Investment' + _SEP + r'Fund', r'HUMAIN', r'Aramco', r'SDAIA', r'KAUST', r'SABIC', r"Ma'?aden", r'Saudi' + _SEP + r'Telecom',
    r'Qatar' + _SEP + r'Investment' + _SEP + r'Authority', r'Ooredoo', r'Kuwait' + _SEP + r'Investment' + _SEP + r'Authority', r'Mumtalakat', r'Batelco',
    r'Omantel', r'ADIA', r'Etihad', r'DEWA', r'Emirates' + _SEP + r'NBD', r'e&',
    r'DP' + _SEP + r'World', r'Emaar', r'Aldar', r'TAQA', r'flydubai', r'Saudia',
)
# Acronyms that only count in capitals ("Kia" the car maker is not KIA, the Kuwait Investment Authority). MBS, MbS, MBZ
# and MBR count with a lower-case b too, but "MBs" (megabytes) does not.
EN_CASED = _en(r'KSA', r'GCC', r'MGX', r'ADQ', r'TII', r'PIF', r'QIA', r'KIA', r'M[bB][SZR]', r'RAK', r'UAQ', r'QCRI', r'WAM', r'STC')

# Arabic: an optional conjunction (و/ف), then a preposition and/or the article, then the word. Some names only count
# with the article (الرياض is also "gardens", الخليج without it is any gulf), others never take it.
_CONJ = r'(?<![\w])(?:[وف])?'
_POST = r'(?![\w])'
_ARTICLE = {'optional': r'(?:[بك]?ال|لل|[بلك])?', 'required': r'(?:[بك]?ال|لل)', 'none': r'(?:[بلك])?'}

def _ar(article, *stems):
    return _CONJ + _ARTICLE[article] + '(?:' + '|'.join(stems) + ')' + _POST

_NISBA = r'(?:ي|يه|يون|يين|يات)'  # إماراتي، إماراتية، إماراتيون ...
AR_TERMS = '|'.join((
    _ar('optional', r'امارات' + _NISBA + '?', r'سعود' + _NISBA, r'قطر' + _NISBA + '?', r'كويت' + _NISBA + '?', r'بحرين' + _NISBA + '?',
        r'عمان' + _NISBA + '?', r'خليج' + _NISBA, r'مملكه العربيه السعوديه', r'دوله الامارات', r'دوله قطر', r'دوله الكويت',
        r'مملكه البحرين', r'سلطنه عمان'),
    _ar('required', r'رياض', r'دمام', r'ظهران', r'دوحه', r'منامه', r'شارقه', r'فجيره', r'درعيه', r'علا', r'دقم', r'خليج',
        r'مدينه المنوره'),
    _ar('none', r'ابو ?ظبي', r'دبي', r'عجمان', r'راس الخيمه', r'ام القيوين', r'مكه(?: المكرمه)?', r'نيوم', r'لوسيل', r'صلاله', r'تبوك',
        r'مبادله', r'ادنوك', r'ارامكو', r'هيوماين', r'سدايا', r'كاوست', r'سابك', r'اوريدو', r'عمانتل', r'بتلكو', r'ممتلكات القابضه'),
    # Jeddah (جده) is also "grandmother" and «وجده» is "he found it": only after a preposition or «مدينة».
    r'(?<![\w])(?:في|من|الي|مدينه|بمدينه)\s+جده' + _POST, r'(?<![\w])[بل]جده' + _POST,
    _CONJ + _ARTICLE['none'] + r'مسقط(?!\s*را?س)' + _POST,  # Muscat, but not «مسقط رأس» (birthplace)
    # The bloc, ruling families, leaders and titles
    r'مجلس التعاون', r'التعاون الخليجي',
    r'(?<![\w])ال (?:نهيان|مكتوم|سعود|ثاني|صباح|خليفه|سعيد|قاسمي|نعيمي|شرقي|معلا|بوسعيدي)' + _POST,
    _CONJ + r'(?:ل|ب)?(?:نهيان|مكتوم)' + _POST,
    r'(?<![\w])ا?بن (?:زايد|راشد|سلمان|طحنون|حمد|خليفه|صقر|حميد|هيثم|طارق)' + _POST,
    # Leaders by first name, and titles followed by a name («الملك سلمان», «الأمير تميم», «السلطان هيثم», «الشيخ طحنون»).
    _CONJ + r'(?:[بل])?(?:طحنون|تميم|حمدان)' + _POST,
    r'(?<![\w])[وفبل]?(?:ال|لل)(?:امير|اميره|ملك|سلطان) \w+', r'(?<![\w])(?:امير|ملك|سلطان) (?:قطر|الكويت|البحرين|السعوديه|عمان)' + _POST,
    r'(?<![\w])(?:[وفبل]|لل)?(?:ال)?شيخ(?:ه)?' + _POST,
    r'(?<![\w])بن \w+ (?:القاسمي|النعيمي|الشرقي|المعلا|النهيان|المكتوم)' + _POST,
    r'(?<![\w])[وفبل]?(?:ال)?شيخ(?:ه)? \w+ بن' + _POST, r'(?<![\w])(?:صاحب ال)?سمو' + _POST, r'(?<![\w])[وبل]سمو' + _POST,
    r'ولي (?:ال)?عهد', r'خادم الحرمين', r'امير (?:دوله )?(?:قطر|الكويت)', r'ملك (?:البحرين|السعوديه)', r'سلطان عمان',
    r'صندوق الاستثمارات العامه', r'جهاز (?:قطر|ابوظبي|الكويت) لل?استثمار', r'معهد الابتكار التكنولوجي',
    r'(?<![\w])جي ?42', r'(?<![\w])كور ?42', r'خزنه (?:داتا|للبيانات)',
))

# The UAE alone (the UAE AI view): places, emirates, ruling families, leaders and state-linked entities of the UAE only.
# No generic titles ("Sheikh", "Crown Prince", "Emir") and no other GCC names, so a Saudi or Qatari story is not UAE news.
UAE_EN_TERMS = _en(
    r'U\.?A\.?E\.?', r'United' + _SEP + r'Arab' + _SEP + r'Emirates', r'Emirates', r'Emirati(?:s)?', r'Emirati[sz]ation',
    r"Abu[\s\-']*Dhabi", r'Dubai', r'Sharjah', r'Ajman', r'Ras' + _SEP + r'al' + _SEP + r'Khaimah?', r'Fujairah',
    r'Umm' + _SEP + r'al' + _SEP + r'Qu?aiwain', r'Umm' + _SEP + r'al' + _SEP + r'Quwain', r'Al' + _SEP + r'Ain', r'Khor' + _SEP + r'Fakkan',
    r'Masdar', r'Jebel' + _SEP + r'Ali', r'Saadiyat', r'Yas' + _SEP + r'(?:Island|Marina)', r'Burj' + _SEP + r'Khalifa', r'Expo' + _SEP + r'City', r'Hub[\s\-]?71',
    r'Al' + _SEP + r'(?:Nahyan|Nahayan|Maktoum|Qasimi|Qassimi|Nuaimi|Sharqi|Mualla)', r'Nahyan', r'Maktoum',
    r'bin' + _SEP + r'(?:Zayed|Rashid|Tahnoun|Tahnoon|Saqr|Humaid)', r'Tahn(?:o|ou|oo)n', r'Hamdan' + _SEP + r'bin' + _SEP + r'M[ou]h?am+[ae]d',
    r'G[\s\-]?42', r'Mubadala', r'ADNOC', r'Core[\s\-]?42', r'Khazna', r'Etisalat', r'Space[\s\-]?42', r'Presight',
    r'Technology' + _SEP + r'Innovation' + _SEP + r'Institute', r'MBZUAI', r'Jais', r'Falcon' + _SEP + r'(?:LLM|H1R?|E|Arabic|Mamba|40B|180B|7B|2|3)',
    r'ADIA', r'Etihad', r'DEWA', r'e&', r'DP' + _SEP + r'World', r'Emaar', r'Aldar', r'TAQA', r'flydubai',
)
UAE_EN_CASED = _en(r'MGX', r'ADQ', r'TII', r'RAK', r'UAQ', r'WAM', r'M[bB][ZR]')
UAE_AR_TERMS = '|'.join((
    _ar('optional', r'امارات' + _NISBA + '?', r'دوله الامارات'),
    _ar('required', r'شارقه', r'فجيره'),
    _ar('none', r'ابو ?ظبي', r'دبي', r'عجمان', r'راس الخيمه', r'ام القيوين', r'مبادله', r'ادنوك'),
    r'(?<![\w])ال (?:نهيان|مكتوم|قاسمي|نعيمي|شرقي|معلا)' + _POST, _CONJ + r'(?:ل|ب)?(?:نهيان|مكتوم)' + _POST,
    r'(?<![\w])ا?بن (?:زايد|راشد|طحنون|صقر|حميد)' + _POST, _CONJ + r'(?:[بل])?طحنون' + _POST, r'(?<![\w])[وبل]?حمدان بن محمد' + _POST,
    r'معهد الابتكار التكنولوجي', r'(?<![\w])جي ?42', r'(?<![\w])كور ?42', r'خزنه (?:داتا|للبيانات)',
))

_EN = re.compile(EN_TERMS, re.I)
_EN_CASED = re.compile(EN_CASED)
_AR = re.compile(AR_TERMS)

def region_terms(*texts):
    """The region names found in the texts (normalised spelling), in order; empty when none."""
    out = []
    for t in texts:
        n = normalize(t)
        for rx in (_EN, _EN_CASED, _AR):
            out += [m.group(0).strip() for m in rx.finditer(n)]
    return out

def mentions_region(*texts):
    """True when any of the texts mentions the UAE or a GCC state (see region_terms)."""
    for t in texts:
        if not t:
            continue
        n = normalize(t)
        if _EN.search(n) or _EN_CASED.search(n) or _AR.search(n):
            return True
    return False

_UAE = (re.compile(UAE_EN_TERMS, re.I), re.compile(UAE_EN_CASED), re.compile(UAE_AR_TERMS))

def mentions_uae(*texts, ignore=()):
    """True when any of the texts is about the UAE (UAE places, rulers or entities; see UAE_EN_TERMS/UAE_AR_TERMS).
    `ignore` lists names to blank out first - publishers' own names such as «الإمارات اليوم» or "Sharjah24", which name
    the outlet, not the story's subject."""
    names = sorted({normalize(x).casefold() for x in ignore if x}, key=len, reverse=True)
    for t in texts:
        if t:
            n = normalize(t)
            for name in names:
                n = re.sub(re.escape(name), ' ', n, flags=re.I)
            if any(rx.search(n) for rx in _UAE):
                return True
    return False

def item_texts(item):
    return [item.get(k) or '' for k in TEXT_FIELDS]

def item_mentions_region(item):
    return mentions_region(*item_texts(item))

def fingerprint(item):
    """Short hash of the texts the check read: when any of them changes, the verdict no longer applies."""
    return hashlib.sha1('\x1f'.join(item_texts(item)).encode('utf-8')).hexdigest()[:12]

# ---------- sources and verdicts ----------

def regional_outlet(source):
    """UAE newsrooms and GCC-based outlets: the only sources whose stories may mention the region."""
    return bool(source) and (source.get('region') == 'uae' or source.get('regional_outlet') is True)

def may_cover_region(source):
    """Rule M1: stories that mention the region come only from regional outlets and official sources of the region
    (the Dubai Media Office feeds are region "uae"; another official UAE/GCC source is marked "official_region": true).
    Global vendor newsrooms (kind "primary") are not official sources of the region."""
    return regional_outlet(source) or (bool(source) and source.get('official_region') is True)

def verified(item):
    """A passing verdict at the current policy version, given for the item's current texts (policy_hash): a verdict
    whose headline, translation, excerpt or summary changed since (a hand edit, a restore) does not count."""
    return (item.get('policy_ok') is True and (item.get('policy_version') or 0) >= POLICY_VERSION
            and item.get('policy_hash') == fingerprint(item))

def shown_ok(item, source=None):
    """May this item be shown? Never after a failing verdict or an unusable answer (policy_attempts); a story that
    mentions the region only from a regional outlet (when the source is given) and only with a passing verdict at the
    current version for its current texts."""
    if item.get('policy_ok') is False:
        return False
    if item.get('policy_attempts') and not verified(item):  # a refusal or unusable answer: when in doubt, leave it out
        return False
    if not item_mentions_region(item):
        return True
    if source is not None and not may_cover_region(source):
        return False
    return verified(item)
