/* Qahwa & AI library (qahwa.html), ported from the approved mock A. Inlined into the page by scripts/qahwa.py.
   Data: the <script type="application/json" id="qahwa-data"> block (data/qahwa.json, published posts only).
   Language and theme use the site's localStorage keys (atlas-lang, atlas-theme); ?lang=ar wins and saves nothing. */
(function () {
  'use strict';
  let DATA = {};
  try { DATA = JSON.parse(document.getElementById('qahwa-data').textContent || '{}'); } catch (e) { DATA = {}; }
  const PROFILE = 'https://www.instagram.com/qahwa.w.ai/';
  const HOME = DATA.home || 'index.html';
  const LEARN = DATA.learn || 'learn.html';
  const CONCEPTS = DATA.concepts || {};
  const BRAND = 'brand/qahwa/';
  const PAGE_SIZE = 24;
  const DRINKS = ['v60', 'cortado', 'iced-americano', 'cappuccino', 'latte', 'espresso', 'flat-white', 'mocha', 'macchiato', 'turkish-coffee'];

  // Topic names and dots exactly as the posts use them (generator/templates.mjs PILLARS).
  const PILLARS = {
    basics: { en: 'Basics', ar: 'أساسيات', dot: '#E0489A' },
    tools: { en: 'Tools', ar: 'أدوات', dot: '#2FA392' },
    life: { en: 'Real life', ar: 'في حياتك', dot: '#F8C24C' },
    hardware: { en: 'AI Hardware', ar: 'عتاد الذكاء الاصطناعي', dot: '#2FA392' },
    safety: { en: 'Safety', ar: 'الأمان', dot: '#E0443F' },
    challenge: { en: 'Challenge', ar: 'تحدٍّ', dot: '#F8C24C' },
    recap: { en: 'Week recap', ar: 'ملخص الأسبوع', dot: '#F59A45' },
    welcome: { en: 'Welcome', ar: 'أهلاً بك', dot: '#E0489A' },
    quiz: { en: 'Quiz', ar: 'اختبار', dot: '#2FA392' },
    news: { en: 'AI news', ar: 'أخبار الذكاء الاصطناعي', dot: '#F59A45' },
  };
  // Post kinds: plural for the Type filter, singular for the pill on a card.
  const KINDS = {
    lesson: { en: 'Lessons', ar: 'الدروس', one: { en: 'Lesson', ar: 'درس' }, dot: '#E0489A' },
    welcome: { en: 'Welcome', ar: 'الترحيب', one: { en: 'Welcome', ar: 'أهلاً بك' }, dot: '#E0489A' },
    reel: { en: 'Reels', ar: 'ريلز', one: { en: 'Try it', ar: 'جرّبها' }, dot: '#F8C24C' },
    story: { en: 'Stories', ar: 'ستوري', one: { en: 'Story', ar: 'ستوري' }, dot: '#E0489A' },
    challenge: { en: 'Challenges', ar: 'التحديات', one: { en: 'Challenge', ar: 'تحدٍّ' }, dot: '#2FA392' },
    recap: { en: 'Week recaps', ar: 'ملخصات الأسبوع', one: { en: 'Week recap', ar: 'ملخص الأسبوع' }, dot: '#F59A45' },
    news: { en: 'AI news', ar: 'أخبار الذكاء الاصطناعي', one: { en: 'AI news', ar: 'خبر' }, dot: '#F59A45' },
    other: { en: 'Other posts', ar: 'منشورات أخرى', one: { en: 'Post', ar: 'منشور' }, dot: '#CD7829' },
  };
  const KIND_ORDER = Object.keys(KINDS);
  const TOPIC_ORDER = ['basics', 'tools', 'life', 'hardware', 'safety'];

  const T = {
    en: {
      skip: 'Skip to the lessons', partOf: 'Part of <b>Cipher Lacuna</b>', theme: 'Dark mode',
      tagline: 'A free AI lesson <span class="hl">with your morning coffee</span>',
      steps: 'Learn · Try · Check', langs: 'Arabic & English', linksLabel: 'Links',
      follow: 'Follow on Instagram', website: 'Cipher Lacuna website', allPrompts: 'All prompts',
      showLabel: 'Show', tabLessons: 'Lessons', tabMore: 'More posts', tabPrompts: 'Prompts',
      searchLabel: 'Search lessons', searchPh: 'Search lessons, prompts and topics', clear: 'Clear search',
      week: 'Week', topic: 'Topic', type: 'Type', all: 'All', wk: (n) => `Week ${n}`,
      count: (n, total) => `Showing <b>${n}</b> of ${total}`,
      empty: 'Nothing matches that search. Try another word, or clear the filters.', resetAll: 'Clear filters',
      elsewhere: (n, tab) => `${n} ${n === 1 ? 'match' : 'matches'} in ${tab}`,
      earlyH: 'The first lessons are on their way',
      earlyP: 'New lessons arrive here as they are published on Instagram. Follow @qahwa.w.ai to see each one first.',
      soon: 'New lessons arrive here as they are published on Instagram.', soonFollow: 'Follow @qahwa.w.ai',
      showMore: (n) => `Show ${n} more`,
      lesson: (n) => `Lesson ${n}`, reel: (c) => (c ? `Reel ${c}` : 'Reel'), story: 'Story', tryIt: 'Try it now', code: 'Prompt code',
      copy: 'Copy', copied: 'Copied', copiedToast: 'Prompt copied. Paste it into your AI assistant.', copyFail: 'Copy did not work. Select the text and copy it.',
      read: 'Read the lesson', readPost: 'Read the post', view: 'View on Instagram', viewProfile: 'Open @qahwa.w.ai',
      guide: 'Related guide on Cipher Lacuna', guides: 'Related guides on Cipher Lacuna',
      postedOn: (d) => `Published ${d}`, close: 'Close', next: 'Next lesson', nextUp: 'Coming next',
      coffee: 'In coffee terms', mythfact: 'Myth or fact?', myth: 'Myth', fact: 'Fact',
      example: 'Example', openItem: (t) => `Open: ${t}`, listH: 'Published on Instagram',
      footer: 'Qahwa &amp; AI is a free bilingual AI series on Instagram, and part of <a data-home href="index.html">Cipher Lacuna</a>.',
      learnAI: 'Learn AI', home: 'Cipher Lacuna', title: 'Qahwa & AI Lessons · Cipher Lacuna',
      langBtn: 'العربية', langBtnLang: 'ar', langBtnLabel: 'اقرأ بالعربية',
    },
    ar: {
      skip: 'انتقل إلى الدروس', partOf: 'جزء من موقع <b>Cipher Lacuna</b>', theme: 'الوضع الداكن',
      tagline: 'درس مجاني في الذكاء الاصطناعي <span class="hl">مع قهوة الصباح</span>',
      steps: 'تعلّم · جرّب · تحقّق', langs: 'بالعربية والإنجليزية', linksLabel: 'روابط',
      follow: 'تابعنا على Instagram', website: 'موقع Cipher Lacuna', allPrompts: 'كل الأوامر',
      showLabel: 'اعرض', tabLessons: 'الدروس', tabMore: 'منشورات أخرى', tabPrompts: 'الأوامر',
      searchLabel: 'ابحث في الدروس', searchPh: 'ابحث في الدروس والأوامر والمواضيع', clear: 'امسح البحث',
      week: 'الأسبوع', topic: 'الموضوع', type: 'النوع', all: 'الكل', wk: (n) => `الأسبوع ${n}`,
      count: (n, total) => `المعروض: <b>${n}</b> من ${total}`,
      empty: 'لا توجد نتائج لهذا البحث. جرّب كلمة أخرى، أو امسح عوامل التصفية.', resetAll: 'امسح عوامل التصفية',
      elsewhere: (n, tab) => `النتائج في «${tab}»: ${n}`,
      earlyH: 'الدروس الأولى في الطريق',
      earlyP: 'تُضاف الدروس الجديدة هنا مع نشرها على Instagram. تابع ‎@qahwa.w.ai لتصلك أولاً بأول.',
      soon: 'تُضاف الدروس الجديدة هنا مع نشرها على Instagram.', soonFollow: 'تابع ‎@qahwa.w.ai',
      showMore: (n) => `اعرض المزيد (${n})`,
      lesson: (n) => `الدرس ${n}`, reel: (c) => (c ? `ريل ${c}` : 'ريل'), story: 'ستوري', tryIt: 'جرّبها الآن', code: 'رمز الأمر',
      copy: 'نسخ', copied: 'تم النسخ', copiedToast: 'تم نسخ الأمر. الصقه في المساعد الذكي الذي تستخدمه.', copyFail: 'تعذّر النسخ. حدّد النص وانسخه يدوياً.',
      read: 'اقرأ الدرس', readPost: 'اقرأ المنشور', view: 'شاهده على Instagram', viewProfile: 'افتح حساب ‎@qahwa.w.ai',
      guide: 'شرح أعمق على Cipher Lacuna', guides: 'شروح أعمق على Cipher Lacuna',
      postedOn: (d) => `نُشر في ${d}`, close: 'إغلاق', next: 'الدرس التالي', nextUp: 'التالي',
      coffee: 'بلغة القهوة', mythfact: 'خرافة أم حقيقة؟', myth: 'خرافة', fact: 'حقيقة',
      example: 'مثال', openItem: (t) => `افتح: ${t}`, listH: 'منشور على Instagram',
      footer: '<span class="l-nw">«قهوة و AI»</span> سلسلة مجانية بالعربية والإنجليزية على Instagram، وهي جزء من موقع <a data-home href="index.html">Cipher Lacuna</a>.',
      learnAI: 'تعلّم الذكاء الاصطناعي', home: 'Cipher Lacuna', title: 'دروس قهوة و AI · Cipher Lacuna',
      langBtn: 'English', langBtnLang: 'en', langBtnLabel: 'Read in English',
    },
  };

  const $ = (s, r = document) => r.querySelector(s);
  const html = document.documentElement;
  html.classList.add('js');
  const S = { lang: html.lang === 'ar' ? 'ar' : 'en', tab: 'lessons', q: '', week: 'all', topic: 'all', shown: PAGE_SIZE };
  const t = (k, ...a) => { const v = T[S.lang][k]; return typeof v === 'function' ? v(...a) : v; };
  const other = (l) => (l === 'ar' ? 'en' : 'ar');
  const dirOf = (l) => (l === 'ar' ? 'rtl' : 'ltr');

  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  const plain = (s) => String(s ?? '').replace(/==/g, '').replace(/\s*\n\s*/g, ' ');
  // ==highlight== → a sunset underline on small text (keeps contrast); gradient text only on large headings.
  const mark = (s) => esc(String(s ?? '').replace(/\s*\n\s*/g, ' ')).replace(/==(.+?)==/g, '<span class="mark">$1</span>');
  const multi = (s) => esc(plain(s));
  const txt = (o, l) => (o && typeof o === 'object' ? o[l] || o[other(l)] || '' : '');

  // Search: case-folded, Arabic diacritics/tatweel removed, letter variants merged, Arabic-Indic digits → Latin.
  function norm(s) {
    return String(s ?? '')
      .normalize('NFKD')
      .toLowerCase()
      .replace(/[̀-ͯ]/g, '')
      .replace(/[ً-ٰٟۖ-ۭـ]/g, '')
      .replace(/[أإآٱ]/g, 'ا').replace(/ى/g, 'ي').replace(/ة/g, 'ه').replace(/ؤ/g, 'و').replace(/ئ/g, 'ي')
      .replace(/[٠-٩]/g, (d) => String('٠١٢٣٤٥٦٧٨٩'.indexOf(d)))
      .replace(/[۰-۹]/g, (d) => String('۰۱۲۳۴۵۶۷۸۹'.indexOf(d)))
      .replace(/[=«»"“”‘’'.,:;!?؟،()[\]…·—–\-→←]/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
  }
  const pad2 = (n) => String(n).padStart(2, '0');
  const isIG = (u) => { try { const x = new URL(u); return x.protocol === 'https:' && /(^|\.)instagram\.com$/.test(x.hostname); } catch (e) { return false; } };

  // ---------- items ----------
  const ITEMS = (Array.isArray(DATA.posts) ? DATA.posts : []).filter((p) => p && p.id && p.title).map((p) => {
    const it = Object.assign({ slides: [], related_concepts: [] }, p);
    it.lesson = Number.isInteger(it.lesson) ? it.lesson : null;
    it.slug = it.kind === 'lesson' && it.lesson ? `lesson-${pad2(it.lesson)}` : `post-${it.id}`;
    // Stories expire on Instagram, so they always link to the profile; everything else to its own post.
    it.link = it.kind === 'story' || !isIG(it.permalink) ? PROFILE : it.permalink;
    it.related = (it.related_concepts || []).filter((id) => CONCEPTS[id]).map((id) => Object.assign({ id }, CONCEPTS[id]));
    it.pcode = (it.prompt && it.prompt.code) || it.code || '';
    it.time = Date.parse(it.published_at) || 0;
    return it;
  }).sort((a, b) => b.time - a.time || (b.lesson || 0) - (a.lesson || 0));

  function slideText(s) {
    const out = [];
    for (const l of ['ar', 'en']) {
      const x = s[l] || {};
      for (const v of Object.values(x)) {
        if (typeof v === 'string') out.push(v);
        else if (Array.isArray(v)) out.push(...v.filter((y) => typeof y === 'string'));
      }
      if (s.note) out.push(s.note[l]);
      if (s.next) out.push(s.next[l]);
    }
    return out.filter(Boolean).join(' ');
  }
  for (const it of ITEMS) {
    const p = PILLARS[it.topic] || {};
    const k = KINDS[it.kind] || {};
    const bits = [txt(it.title, 'ar'), txt(it.title, 'en'), txt(it.summary, 'ar'), txt(it.summary, 'en'), it.code, it.pcode,
      p.en, p.ar, k.en, k.ar, it.prompt && it.prompt.ar, it.prompt && it.prompt.en, ...(it.slides || []).map(slideText)];
    if (it.lesson) bits.push(`lesson ${pad2(it.lesson)}`, `lesson ${it.lesson}`, `الدرس ${pad2(it.lesson)}`, `درس ${it.lesson}`);
    for (const r of it.related) bits.push(r.en, r.ar);
    it._idx = norm(bits.filter(Boolean).join(' '));
  }
  const bySlug = (s) => ITEMS.find((i) => i.slug === s);

  // ---------- filtering ----------
  const TABS = [['lessons', 'tabLessons'], ['more', 'tabMore'], ['prompts', 'tabPrompts']];
  function inTab(it, tab) {
    if (tab === 'lessons') return it.kind === 'lesson';
    if (tab === 'more') return it.kind !== 'lesson';
    return !!(it.prompt && it.prompt.en && it.prompt.ar);
  }
  const topicOf = (it, tab) => (tab === 'lessons' ? it.topic : it.kind);
  function queryMatch(it) {
    if (!S.q.trim()) return true;
    const q = norm(S.q);
    // "lesson 5", "L05", "الدرس ٥" go straight to that lesson instead of matching every text with a 5 in it.
    const lm = q.match(/^(?:lesson|l|الدرس|درس)\s*0*(\d{1,3})$/);
    if (lm) return it.lesson === Number(lm[1]);
    return q.split(' ').filter(Boolean).every((w) => it._idx.includes(w));
  }
  function matches(it, tab = S.tab, useTopic = true) {
    if (!inTab(it, tab)) return false;
    if (S.week !== 'all' && it.week !== Number(S.week)) return false;
    if (useTopic && S.topic !== 'all' && topicOf(it, tab) !== S.topic) return false;
    return queryMatch(it);
  }
  function topicSet() {
    const present = new Set(ITEMS.filter((i) => inTab(i, S.tab)).map((i) => topicOf(i, S.tab)).filter(Boolean));
    if (S.tab === 'lessons') {
      const known = TOPIC_ORDER.filter((k) => present.has(k));
      const extra = [...present].filter((k) => !TOPIC_ORDER.includes(k)).sort();
      return [...known, ...extra].map((k) => [k, PILLARS[k] || { en: k, ar: k, dot: '#CD7829' }]);
    }
    return KIND_ORDER.filter((k) => present.has(k)).map((k) => [k, KINDS[k]]);
  }
  function weekSet() {
    return [...new Set(ITEMS.filter((i) => inTab(i, S.tab)).map((i) => i.week).filter((w) => Number.isInteger(w)))].sort((a, b) => a - b);
  }

  // ---------- small pieces ----------
  const ICON = {
    copy: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="8" y="8" width="12" height="12" rx="3"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/></svg>',
    check: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12.5 4.5 4.5L19 7.5"/></svg>',
    ig: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="5.2"/><circle cx="12" cy="12" r="4.1"/><circle cx="17.3" cy="6.7" r="1.1" class="fill"/></svg>',
    book: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v15H6.5A2.5 2.5 0 0 0 4 20.5z"/><path d="M4 20.5A2.5 2.5 0 0 0 6.5 23H20v-5"/></svg>',
    arrow: '<svg class="arr" viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6"/></svg>',
  };
  const CL_LOGO = (document.querySelector('.cl img') || {}).src || '';
  function withLang(href) {
    // Links to the rest of the site keep the language shown here (the overview and Learn AI read ?lang=, else the saved
    // choice): an Arabic visit always adds ?lang=ar, an English visit adds ?lang=en only while Arabic is the saved choice
    // (a ?lang= visit saves nothing). Same rule as app.js and learn.js.
    let saved = null;
    try { saved = localStorage.getItem('atlas-lang'); } catch (e) { /* private mode */ }
    const want = S.lang === 'ar' ? 'ar' : saved === 'ar' ? 'en' : '';
    if (!want) return href;
    const i = href.indexOf('#');
    const base = i < 0 ? href : href.slice(0, i), hash = i < 0 ? '' : href.slice(i);
    return `${base}${base.includes('?') ? '&' : '?'}lang=${want}${hash}`;
  }
  function dateFmt(ms) {
    if (!ms) return '';
    try {
      return new Intl.DateTimeFormat(S.lang === 'ar' ? 'ar-AE-u-nu-latn' : 'en-GB', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'Asia/Dubai' }).format(new Date(ms));
    } catch (e) { return new Date(ms).toISOString().slice(0, 10); }
  }
  function label(it) {
    if (it.kind === 'lesson' && it.lesson) return t('lesson', pad2(it.lesson));
    if (it.kind === 'reel') return t('reel', it.pcode);
    if (it.kind === 'story') return t('story');
    return '';
  }
  function pillOf(it) {
    if (it.kind === 'lesson') return PILLARS[it.topic] || KINDS.lesson;
    if (it.kind === 'story' && (it.slides || []).some((s) => s.type === 'myth')) return { en: T.en.mythfact, ar: T.ar.mythfact, dot: '#E0489A' };
    const k = KINDS[it.kind] || KINDS.other;
    return { en: k.one.en, ar: k.one.ar, dot: k.dot };
  }
  function pillHtml(it) {
    const p = pillOf(it);
    return `<span class="pill"><i style="background:${p.dot}"></i>${esc(p[S.lang])}</span>`;
  }
  function titles(it, big) {
    const L = S.lang, O = other(L);
    const Tag = big ? 'h2' : 'h3';
    const id = big ? ' id="dTitle"' : '';
    const main = big ? mark(txt(it.title, L)) : `<button type="button" data-open="${esc(it.slug)}">${mark(txt(it.title, L))}</button>`;
    const second = it.title[O] ? `<p class="t2" lang="${O}" dir="${dirOf(O)}">${multi(it.title[O])}</p>` : '';
    return `<${Tag} class="t1" lang="${L}" dir="${dirOf(L)}"${id}>${main}</${Tag}>${second}`;
  }
  const summaryOf = (it) => plain(txt(it.summary, S.lang));
  const statusHtml = (it) => (it.time ? `<span class="status">${esc(t('postedOn', dateFmt(it.time)))}</span>` : '');
  const promptText = (it) => String(txt(it.prompt, S.lang)).replace(/==/g, '');
  function promptHtml(it, head) {
    if (!it.prompt) return '';
    const L = S.lang;
    return `<div class="promptbox">
      <div class="pb-head"><img src="${BRAND}bot-badge.webp" alt="" width="28" height="28">
        <span class="pb-lbl">${esc(head || t('tryIt'))}</span>
        ${it.pcode ? `<span class="code" title="${esc(t('code'))}" aria-label="${esc(t('code'))} ${esc(it.pcode)}" dir="ltr">${esc(it.pcode)}</span>` : ''}
        <button class="copy" type="button" data-copy="${esc(it.slug)}">${ICON.copy}<span>${esc(t('copy'))}</span></button>
      </div>
      <p class="pb-text" lang="${L}" dir="${dirOf(L)}">${esc(promptText(it))}</p>
    </div>`;
  }
  function igHtml(it) {
    const lbl = it.kind === 'story' ? t('viewProfile') : t('view');
    return `<a class="act ig-link" href="${esc(it.link)}" rel="noopener">${ICON.ig}<span>${esc(lbl)}</span></a>`;
  }
  function guideHtml(r, single) {
    const L = S.lang;
    return `<a class="guide" href="${esc(withLang(`${LEARN}#concept/${encodeURIComponent(r.id)}`))}">
      ${CL_LOGO ? `<img src="${esc(CL_LOGO)}" alt="" width="20" height="20">` : ''}
      <span>${single ? `${esc(t('guide'))}: ` : ''}<b>${esc(r[L] || r.en)}</b></span>${ICON.arrow}</a>`;
  }
  function thumbImg(it, eager) {
    if (it.cover) return `<img src="${esc(it.cover)}" alt=""${eager ? '' : ' loading="lazy"'} width="480" height="600">`;
    return `<span class="ph"><img src="${BRAND}bot-badge.webp" alt="" width="96" height="96"></span>`;
  }

  function card(it) {
    const readLbl = it.kind === 'lesson' ? t('read') : t('readPost');
    const fmt = it.kind === 'reel' ? 'Reel' : it.kind === 'story' ? 'Story' : '';
    const name = plain(txt(it.title, S.lang));
    // A summary that only repeats the pill ("Myth or fact?") or the title adds nothing: it is left out.
    const sum = [name, pillOf(it)[S.lang], label(it)].some((x) => x && norm(x) === norm(summaryOf(it))) ? '' : summaryOf(it);
    return `<article class="card" data-kind="${esc(it.kind)}" data-slug="${esc(it.slug)}">
      <button class="thumb" type="button" data-open="${esc(it.slug)}" aria-label="${esc(t('openItem', `${label(it)} ${name}`.trim()))}">
        ${thumbImg(it)}${fmt ? `<span class="fmt" lang="en">${fmt}</span>` : ''}
      </button>
      <div class="c-main">
        <div class="meta">${pillHtml(it)}${label(it) ? `<span class="num">${esc(label(it))}</span>` : ''}</div>
        ${titles(it)}
        ${sum ? `<p class="sum">${esc(sum)}</p>` : ''}
        <div class="meta">${statusHtml(it)}</div>
      </div>
      ${it.prompt ? `<div class="full">${promptHtml(it)}</div>` : ''}
      <div class="full actions">
        <button class="act primary" type="button" data-open="${esc(it.slug)}">${ICON.book}<span>${esc(readLbl)}</span></button>
        ${igHtml(it)}
      </div>
      ${it.related.length ? `<div class="full">${guideHtml(it.related[0], true)}</div>` : ''}
    </article>`;
  }
  function promptCard(it) {
    const L = S.lang;
    return `<article class="pcard" data-slug="${esc(it.slug)}">
      <div class="meta">${pillHtml(it)}${label(it) ? `<span class="num">${esc(label(it))}</span>` : ''}</div>
      <h3 class="t1" lang="${L}" dir="${dirOf(L)}"><button type="button" data-open="${esc(it.slug)}">${mark(txt(it.title, L))}</button></h3>
      ${promptHtml(it)}
    </article>`;
  }

  // ---------- render ----------
  function applyStatic() {
    html.lang = S.lang; html.dir = dirOf(S.lang);
    document.querySelectorAll('[data-i18n]').forEach((el) => { el.textContent = t(el.dataset.i18n); });
    document.querySelectorAll('[data-i18n-html]').forEach((el) => { el.innerHTML = t(el.dataset.i18nHtml); });
    document.querySelectorAll('[data-i18n-ph]').forEach((el) => { el.placeholder = t(el.dataset.i18nPh); });
    document.querySelectorAll('[data-i18n-aria]').forEach((el) => { el.setAttribute('aria-label', t(el.dataset.i18nAria)); });
    document.querySelectorAll('[data-home]').forEach((el) => { el.setAttribute('href', withLang(HOME)); });
    document.querySelectorAll('[data-learn]').forEach((el) => { el.setAttribute('href', withLang(LEARN)); });
    const lb = $('#langBtn');
    lb.textContent = t('langBtn'); lb.lang = t('langBtnLang'); lb.setAttribute('aria-label', t('langBtnLabel'));
    document.title = t('title');
    syncThemeBtn();
  }
  function tabCount(tab) { return ITEMS.filter((i) => matches(i, tab, false)).length; }
  function renderTabs() {
    $('#tabs').innerHTML = TABS.map(([k, l]) =>
      `<button class="tab" type="button" data-tab="${k}" aria-pressed="${S.tab === k}">${esc(t(l))}<span class="n">${tabCount(k)}</span></button>`).join('');
  }
  function renderChips() {
    const weeks = weekSet();
    if (S.week !== 'all' && !weeks.includes(Number(S.week))) S.week = 'all';
    $('#weekRow').hidden = weeks.length < 2;
    $('#weekChips').innerHTML = [`<button class="chip" type="button" data-week="all" aria-pressed="${S.week === 'all'}">${esc(t('all'))}</button>`]
      .concat(weeks.map((w) => `<button class="chip" type="button" data-week="${w}" aria-pressed="${String(S.week) === String(w)}" aria-label="${esc(t('wk', w))}">${w}</button>`)).join('');
    const topics = topicSet();
    if (S.topic !== 'all' && !topics.some(([k]) => k === S.topic)) S.topic = 'all';
    $('#topicRow').hidden = topics.length < 2;
    $('#topicLbl').textContent = S.tab === 'lessons' ? t('topic') : t('type');
    $('#topicChips').innerHTML = `<button class="chip" type="button" data-topic="all" aria-pressed="${S.topic === 'all'}">${esc(t('all'))}</button>` +
      topics.map(([k, p]) => `<button class="chip" type="button" data-topic="${esc(k)}" aria-pressed="${S.topic === k}"><i style="background:${p.dot}" aria-hidden="true"></i>${esc(p[S.lang])}</button>`).join('');
    $('#filters').hidden = $('#weekRow').hidden && $('#topicRow').hidden;
  }
  function renderList() {
    const early = !ITEMS.length;
    $('#early').hidden = !early;
    $('#libTools').hidden = early;
    $('#listBlock').hidden = early;
    if (early) { $('#empty').hidden = true; return; }
    const list = ITEMS.filter((i) => matches(i));
    const visible = list.slice(0, S.shown);
    const fn = S.tab === 'prompts' ? promptCard : card;
    $('#grid').innerHTML = visible.map(fn).join('');
    $('#grid').classList.toggle('prompts', S.tab === 'prompts');
    // One card alone gets the full width (a wide card on desktop) instead of half an empty grid.
    $('#grid').classList.toggle('solo', visible.length === 1);
    $('#listH').textContent = t(TABS.find(([k]) => k === S.tab)[1]);
    const rest = list.length - visible.length;
    $('#moreWrap').hidden = rest <= 0;
    $('#moreBtn').textContent = t('showMore', Math.min(rest, PAGE_SIZE));
    $('#count').innerHTML = t('count', visible.length, list.length);
    const filtering = !!S.q.trim() || S.week !== 'all' || S.topic !== 'all';
    // Few lessons so far: say more are on the way (never when the reader is searching or filtering).
    const lessons = ITEMS.filter((i) => i.kind === 'lesson').length;
    $('#soon').hidden = filtering || S.tab !== 'lessons' || lessons >= 6;
    const empty = $('#empty');
    empty.hidden = !!list.length;
    if (!list.length) {
      let hint = '';
      if (S.q.trim()) {
        const alt = TABS.filter(([k]) => k !== S.tab).map(([k, l]) => [k, l, ITEMS.filter((i) => matches(i, k, false)).length]).find(([, , n]) => n > 0);
        if (alt) hint = `<button class="act" type="button" data-tab="${alt[0]}">${esc(t('elsewhere', alt[2], t(alt[1])))}</button>`;
      }
      empty.innerHTML = `${esc(filtering ? t('empty') : t('soon'))}<br>${hint}${filtering ? `<button class="act" type="button" data-reset>${esc(t('resetAll'))}</button>` : ''}`;
    }
    $('#clearQ').hidden = !S.q;
  }
  function renderAll() { applyStatic(); renderTabs(); renderChips(); renderList(); if (current) openDetail(current, false); }
  function refresh() { S.shown = PAGE_SIZE; renderTabs(); renderChips(); renderList(); }

  // ---------- reading view ----------
  let current = null, opener = null;
  function genericSlide(x) {
    const parts = [];
    if (x.title) parts.push(`<h3>${mark(x.title)}</h3>`);
    if (x.body) parts.push(`<p>${multi(x.body)}</p>`);
    if (Array.isArray(x.items) && x.items.length) parts.push(`<ul>${x.items.map((li) => `<li><span>${multi(li)}</span></li>`).join('')}</ul>`);
    return parts.length ? `<section class="slide">${parts.join('')}</section>` : '';
  }
  function slideHtml(s, it, i) {
    const L = S.lang, x = s[L] || s[other(L)] || {};
    switch (s.type) {
      case 'cover': {
        const same = plain(x.title) === plain(txt(it.title, L));
        return (!same && x.title ? `<section class="slide"><h3>${mark(x.title)}</h3></section>` : '') + (x.body ? `<p class="lead">${multi(x.body)}</p>` : '');
      }
      case 'text':
        return `<section class="slide"><h3>${mark(x.title)}</h3>${x.body ? `<p>${multi(x.body)}</p>` : ''}</section>`;
      case 'bullets':
        return `<section class="slide"><h3>${mark(x.title)}</h3><ul>${(x.items || []).map((li) => `<li><span>${multi(li)}</span></li>`).join('')}</ul>${s.note ? `<p class="note">${multi(txt(s.note, L))}</p>` : ''}</section>`;
      case 'predict':
        return `<section class="slide"><h3>${mark(x.title)}</h3>${x.body ? `<p>${multi(x.body)}</p>` : ''}
          ${x.prompt ? `<div class="ex" aria-label="${esc(t('example'))}">${esc(plain(x.prompt))}</div>` : ''}
          <div class="bars">${(s.options || []).map((o, k) => `<div class="bar${k === 0 ? ' top' : ''}"><span>${esc(txt(o, L))}</span><span class="track" aria-hidden="true"><span class="fill" style="width:${Math.max(0, Math.min(100, Number(o.pct) || 0))}%"></span></span><span class="pct">${esc(o.pct)}%</span></div>`).join('')}</div>
          ${s.note ? `<p class="note">${multi(txt(s.note, L))}</p>` : ''}</section>`;
      case 'coffee': {
        const drink = DRINKS.includes(s.drink) ? s.drink : DRINKS[((it.lesson || 1) - 1) % DRINKS.length];
        return `<section class="slide coffee"><img src="${BRAND}drink-${drink}.webp" alt="" width="76" height="76"><div><span class="hand">${esc(t('coffee'))}</span><h3>${mark(x.title)}</h3>${x.body ? `<p>${multi(x.body)}</p>` : ''}</div></section>`;
      }
      case 'mythfact':
        return `<section class="slide"><h3 class="mf-h">${esc(t('mythfact'))}</h3>
          <div class="mf myth"><b>${esc(t('myth'))}</b><p>${multi(x.myth)}</p></div>
          <div class="mf fact"><b>${esc(t('fact'))}</b><p>${multi(x.fact)}</p></div></section>`;
      case 'prompt':
        return promptHtml(it, x.title);
      case 'myth':
        // A story's poll claim. The poll itself and its answer lived on Instagram, so only the claim is shown,
        // and only once: when the claim is already the heading of the reading view, the slide adds nothing.
        if (norm(x.title) === norm(txt(it.title, L))) return '';
        return `<section class="slide"><h3 class="mf-h">${esc(t('mythfact'))}</h3><p>${multi(x.title)}</p></section>`;
      case 'reel-cover': {
        const chat = s.chat && (s.chat.user || (s.chat.bot || []).length)
          ? `<div class="chat" lang="ar" dir="rtl">${s.chat.user ? `<p class="u">${multi(s.chat.user)}</p>` : ''}${(s.chat.bot || []).length ? `<div class="b"><ul>${s.chat.bot.map((b) => `<li>${multi(b)}</li>`).join('')}</ul></div>` : ''}</div>` : '';
        return `<section class="slide">${s.duration ? `<span class="dur" dir="ltr">${esc(s.duration)}</span>` : ''}<h3>${mark(x.title)}</h3>${chat}</section>`;
      }
      case 'cta': {
        let out = x.title ? `<section class="slide"><p class="cta-t">${mark(x.title)}</p></section>` : '';
        if (s.next) {
          const nx = it.kind === 'lesson' && it.lesson ? bySlug(`lesson-${pad2(it.lesson + 1)}`) : null;
          const m = !nx && /^(?:Lesson|الدرس)\s*0*(\d{1,3})\s*[:：]/.exec(txt(s.next, 'en') || '');
          const target = nx || (m && bySlug(`lesson-${pad2(Number(m[1]))}`));
          const inner = `${ICON.arrow.replace('class="arr"', 'class="next-arr"')}<div><small>${esc(it.kind === 'lesson' ? t('next') : t('nextUp'))}</small><span>${multi(txt(s.next, L))}</span></div>`;
          out += target ? `<button class="next" type="button" data-open="${esc(target.slug)}">${inner}</button>` : `<div class="next">${inner}</div>`;
        }
        return out;
      }
      default:
        return genericSlide(x);
    }
  }
  function openDetail(it, push = true) {
    current = it;
    const L = S.lang;
    const d = $('#detail');
    $('#dCrumb').textContent = label(it) || (KINDS[it.kind] || KINDS.other).one[L];
    let body = `<div class="d-head">
        <div class="thumb">${thumbImg(it, true)}</div>
        <div><div class="meta">${pillHtml(it)}${statusHtml(it)}</div>${titles(it, true)}</div>
      </div>`;
    body += (it.slides || []).map((s, i) => slideHtml(s, it, i)).join('');
    if (it.prompt && !(it.slides || []).some((s) => s.type === 'prompt')) body += promptHtml(it);
    body += `<div class="actions">${igHtml(it)}</div>`;
    if (it.related.length) {
      body += `<div class="d-guides"><h3>${esc(it.related.length > 1 ? t('guides') : t('guide'))}</h3>${it.related.map((r) => guideHtml(r, false)).join('')}</div>`;
    }
    $('#dBody').innerHTML = body;
    d.setAttribute('lang', L);
    d.setAttribute('dir', dirOf(L));
    if (!d.open) { d.showModal(); $('#dClose').focus(); }
    d.scrollTop = 0;
    if (push && location.hash !== `#${it.slug}`) history.replaceState(null, '', `${location.pathname}${location.search}#${it.slug}`);
  }
  function closeDetail() { const d = $('#detail'); if (d.open) d.close(); }
  $('#detail').addEventListener('close', () => {
    current = null;
    if (location.hash) history.replaceState(null, '', location.pathname + location.search);
    if (opener && document.contains(opener)) opener.focus();
    opener = null;
  });
  $('#detail').addEventListener('click', (e) => { if (e.target.id === 'detail') closeDetail(); });
  $('#dClose').addEventListener('click', closeDetail);

  // ---------- copy ----------
  let toastTimer;
  function toast(msg) {
    const el = $('#toast');
    el.textContent = msg; el.classList.add('on');
    clearTimeout(toastTimer); toastTimer = setTimeout(() => el.classList.remove('on'), 2200);
  }
  async function copyText(text) {
    try { await navigator.clipboard.writeText(text); return true; } catch (e) {
      const ta = document.createElement('textarea');
      ta.value = text; ta.setAttribute('readonly', ''); ta.style.position = 'fixed'; ta.style.opacity = '0';
      (document.querySelector('dialog[open]') || document.body).appendChild(ta); ta.select();
      let ok = false; try { ok = document.execCommand('copy'); } catch (_) { ok = false; }
      ta.remove(); return ok;
    }
  }

  // ---------- events ----------
  document.addEventListener('click', async (e) => {
    const o = e.target.closest('[data-open]');
    if (o) { const it = bySlug(o.dataset.open); if (it) { if (!$('#detail').open) opener = o; openDetail(it); } return; }
    const c = e.target.closest('[data-copy]');
    if (c) {
      const it = bySlug(c.dataset.copy);
      if (!it) return;
      if (await copyText(promptText(it))) {
        c.classList.add('done'); c.innerHTML = `${ICON.check}<span>${esc(t('copied'))}</span>`;
        toast(t('copiedToast'));
        setTimeout(() => { c.classList.remove('done'); c.innerHTML = `${ICON.copy}<span>${esc(t('copy'))}</span>`; }, 1800);
      } else toast(t('copyFail'));
      return;
    }
    const tab = e.target.closest('[data-tab]');
    if (tab) { S.tab = tab.dataset.tab; S.topic = 'all'; refresh(); return; }
    const w = e.target.closest('[data-week]');
    if (w) { S.week = w.dataset.week; refresh(); return; }
    const tp = e.target.closest('[data-topic]');
    if (tp) { S.topic = tp.dataset.topic; refresh(); return; }
    if (e.target.closest('#moreBtn')) {
      const first = S.shown;
      S.shown += PAGE_SIZE; renderList();
      const next = $('#grid').children[first];
      const btn = next && next.querySelector('button');
      if (btn) btn.focus({ preventScroll: false });
      return;
    }
    if (e.target.closest('[data-reset]')) { S.q = ''; $('#q').value = ''; S.week = 'all'; S.topic = 'all'; refresh(); $('#q').focus(); }
  });
  $('#q').addEventListener('input', (e) => { S.q = e.target.value; S.shown = PAGE_SIZE; renderTabs(); renderList(); });
  $('#q').addEventListener('keydown', (e) => { if (e.key === 'Escape' && S.q) { e.preventDefault(); S.q = ''; e.target.value = ''; refresh(); } });
  $('#clearQ').addEventListener('click', () => { S.q = ''; $('#q').value = ''; refresh(); $('#q').focus(); });
  $('#promptsLink').addEventListener('click', (e) => {
    e.preventDefault(); S.tab = 'prompts'; S.topic = 'all'; refresh();
    $('#library').scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
    $('#library').focus({ preventScroll: true });
  });
  $('#langBtn').addEventListener('click', () => {
    S.lang = other(S.lang);
    try { localStorage.setItem('atlas-lang', S.lang); } catch (e) { /* private mode */ }
    // A ?lang= in the address would override the choice on reload, so it goes.
    if (/[?&]lang=/.test(location.search)) {
      const u = new URL(location.href); u.searchParams.delete('lang');
      history.replaceState(null, '', u.pathname + (u.search || '') + u.hash);
    }
    renderAll();
  });
  function isDark() {
    return html.dataset.theme ? html.dataset.theme === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches;
  }
  function syncThemeBtn() {
    const b = $('#themeBtn');
    b.setAttribute('aria-pressed', String(isDark()));
    b.querySelector('.vh').textContent = t('theme');
  }
  $('#themeBtn').addEventListener('click', () => {
    html.dataset.theme = isDark() ? 'light' : 'dark';
    try { localStorage.setItem('atlas-theme', html.dataset.theme); } catch (e) { /* private mode */ }
    syncThemeBtn();
  });
  matchMedia('(prefers-color-scheme: dark)').addEventListener('change', syncThemeBtn);
  document.addEventListener('keydown', (e) => {
    if (e.key === '/' && !/^(INPUT|TEXTAREA)$/.test(document.activeElement.tagName) && !$('#detail').open) { e.preventDefault(); $('#q').focus(); }
  });
  function fromHash() {
    let s = '';
    try { s = decodeURIComponent(location.hash.slice(1)); } catch (e) { s = ''; }
    const m = /^lesson-0*(\d{1,3})$/.exec(s);
    const it = s && (bySlug(s) || (m && bySlug(`lesson-${pad2(Number(m[1]))}`)));
    if (it) openDetail(it, false);
    else if (!s && $('#detail').open) closeDetail();
  }
  window.addEventListener('hashchange', fromHash);

  if (!ITEMS.some((i) => i.kind === 'lesson') && ITEMS.length) S.tab = 'more';
  renderAll();
  fromHash();
})();
