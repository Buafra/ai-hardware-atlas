(function (root) {
  'use strict';
  const levels = ['Personal', 'Workstation', 'Enterprise', 'Data center', 'Rack scale'];
  // Vendor windows become [first day, last day] ranges so sorting and the timeline agree.
  const WINDOWS = {Q1:[0,3],Q2:[3,3],Q3:[6,3],Q4:[9,3],H1:[0,6],H2:[6,6],Summer:[5,3],end:[9,3]};
  function dateRange(value) {
    if (!value) return null;
    const s = String(value);
    let m = /^(\d{4})-(Q[1-4]|H[12]|Summer|end)$/.exec(s);
    if (m) { const [start,len] = WINDOWS[m[2]]; return [Date.UTC(+m[1],start,1), Date.UTC(+m[1],start+len,0)]; }
    m = /^(\d{4})-(\d{2})$/.exec(s);
    if (m) return [Date.UTC(+m[1],+m[2]-1,1), Date.UTC(+m[1],+m[2],0)];
    m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s);
    if (m) { const t = Date.UTC(+m[1],+m[2]-1,+m[3]); return [t,t]; }
    return null;
  }
  function dateNumber(value) { const r = dateRange(value); return r ? r[0] : null; }
  // Weights only, plus a user-set allowance for context and runtime. A rough guide, not a guarantee.
  function estimateGB(paramsB, bits, extraPct) {
    const p = Number(paramsB), b = Number(bits), x = Number(extraPct);
    if (!(p > 0) || !(b > 0)) return null;
    return p * b / 8 * (1 + (x > 0 ? x : 0) / 100);
  }
  function fitStatus(p, need) {
    if (!need) return null;
    if (!(p.memory_gb >= need)) return 'no';
    return p.memory_scope === 'System total' || p.memory_scope === 'Rack total' ? 'multi' : 'fits';
  }
  // UAE and Gulf models from official model cards (data/models-extra.json, merged by scripts/build.py) also carry the
  // maker (mk), the country (co), runnable (r: false means chat only, no downloadable weights), the card link (u), the
  // license (l) and, when the card says so, Arabic (ar). Only open, runnable models with a published size are ever
  // fitted to hardware: closed, chat-only and unsized models are listed but never fitted.
  const fittable = m => !!(m && m.o && Number(m.b) > 0 && m.r !== false);
  // The estimator's "Arabic models" chip: the models whose official card lists Arabic.
  function arabicModels(models) { return (models || []).filter(m => m && m.ar === true); }
  // "My hardware": the fittable models whose estimate (weights at `bits` plus `extra`%) fits in `memoryGb` (the same
  // rule as fitStatus), largest first.
  function modelsThatFit(models, memoryGb, bits, extra) {
    const mem = Number(memoryGb);
    if (!(mem > 0)) return [];
    return (models || []).filter(fittable).filter(m => { const need = estimateGB(m.b, bits, extra); return need != null && need <= mem; })
      .sort((a, b) => b.b - a.b || String(a.n).localeCompare(String(b.n)));
  }
  function select(products, filters, key, direction) {
    const q = (filters.q || '').trim().toLowerCase();
    const result = products.filter(p => (!filters.vendor || p.vendor === filters.vendor) && (!filters.level || p.level === filters.level) && (!filters.scope || p.memory_scope === filters.scope) && (!filters.fitOnly || !filters.need || fitStatus(p, filters.need) !== 'no') && (!q || [p.model,p.vendor,p.maker,p.level,p.type,p.architecture,p.memory,p.use,p.use_ar,p.notes,p.release,p.announcement,p.interconnect,p.form_factor,p.ai_compute].join(' ').toLowerCase().includes(q)));
    const get = p => key === 'level' ? levels.indexOf(p.level) : key === 'release' || key === 'announcement' ? dateNumber(p[key]) : p[key];
    return result.sort((a,b) => {
      const av = get(a), bv = get(b);
      // Unknown values stay last in either direction.
      if (av == null && bv == null) return a.model.localeCompare(b.model);
      if (av == null) return 1;
      if (bv == null) return -1;
      const n = typeof av === 'number' ? av-bv : String(av).localeCompare(String(bv), undefined, {numeric:true});
      return n * direction || a.model.localeCompare(b.model);
    });
  }
  // News search (#news and #uae): the same rules as the Android app's NewsSearch.norm, so keep the two in step. The shared
  // cases are in tests/test-sort.cjs and in the app's NewsSearchTest.kt.
  // Case, accents, Arabic diacritics, tatweel and invisible marks are ignored; ٱ أ إ آ count as ا, ة as ه, ى and ی as ي,
  // ؤ as و, ئ as ي, ک and گ as ك, ڤ as ف, پ as ب, چ as ج; Arabic-Indic and Persian digits as 0-9; anything that is
  // not a letter or a digit is a space. A search starts at 2 characters, and the field takes 100 at most.
  const SEARCH_MIN = 2, SEARCH_MAX = 100;
  const FOLD = {'\u0671': '\u0627', '\u0649': '\u064A', '\u06CC': '\u064A', '\u0629': '\u0647', '\u06A9': '\u0643', '\u06AF': '\u0643', '\u06A4': '\u0641', '\u067E': '\u0628', '\u0686': '\u062C'};
  function normText(s) {
    return String(s ?? '').normalize('NFKD').toLowerCase()
      .replace(/[\p{M}\p{Cf}\u0640]/gu, '')  // accents, harakat, hamza marks (أ إ آ ؤ ئ fold here), tatweel, bidi and zero-width marks
      .replace(/[\u0671\u0649\u06CC\u0629\u06A9\u06AF\u06A4\u067E\u0686]/g, c => FOLD[c])
      .replace(/[\u0660-\u0669]/g, d => String(d.charCodeAt(0) - 0x0660))
      .replace(/[\u06F0-\u06F9]/g, d => String(d.charCodeAt(0) - 0x06F0))
      .replace(/[^\p{L}\p{N}]+/gu, ' ').trim();
  }
  // The words of a query, or none below SEARCH_MIN characters (the list then shows in full).
  function searchWords(q) { const n = normText(String(q ?? '').slice(0, SEARCH_MAX)); return n.length < SEARCH_MIN ? [] : n.split(' '); }
  // Every word must appear in `text` (normText output), inside a longer word too ("ذكاء" finds "الذكاء"). `compact` is the
  // same text without spaces, so "gpt5" finds "GPT-5" and "2000" finds "2,000".
  function matchesWords(text, words, compact) {
    const t = String(text ?? ''), c = compact ?? t.replace(/ /g, '');
    return words.every(w => t.includes(w) || c.includes(w));
  }
  // nq and uq are the searches of AI news and UAE AI, one each (the UAE list is a part of the news, with its own context).
  // nt is the topic chosen in AI news (a topic id of scripts/topics.py, as the cards' data-topic); arabic: the estimator's
  // "Arabic models" chip (?arabic=1).
  const DEFAULTS = {q:'',vendor:'',level:'',scope:'',sort:'level',dir:1,view:'cards',cmp:[],lang:'en',params:'',bits:'4',extra:'20',fit:false,model:'',arabic:false,region:'',nq:'',uq:'',nt:''};
  const PARAMS = {q:'q',vendor:'vendor',level:'level',scope:'scope',sort:'sort',dir:'dir',view:'view',cmp:'cmp',lang:'lang',params:'p',bits:'bits',extra:'extra',fit:'fit',model:'m',arabic:'arabic',region:'region',nq:'nq',uq:'uq',nt:'nt'};
  const NEWS_QUERIES = ['nq', 'uq'], FLAGS = ['fit', 'arabic'];
  function encodeState(state) {
    const qs = new URLSearchParams();
    Object.keys(PARAMS).forEach(k => {
      const v = k === 'cmp' ? (state.cmp || []).join(',') : k === 'dir' ? (state.dir === -1 ? 'desc' : '') : FLAGS.includes(k) ? (state[k] ? '1' : '') : NEWS_QUERIES.includes(k) ? String(state[k] ?? '').trim() : String(state[k] ?? '');
      if (v && (typeof DEFAULTS[k] !== 'string' || v !== DEFAULTS[k])) qs.set(PARAMS[k], v);
    });
    return qs.toString();
  }
  function decodeState(search) {
    const qs = new URLSearchParams(search), s = {...DEFAULTS, cmp: []};
    Object.keys(PARAMS).forEach(k => {
      const v = qs.get(PARAMS[k]);
      if (v == null) return;
      if (k === 'cmp') s.cmp = [...new Set(v.split(',').filter(Boolean))].slice(0, 4);
      else if (k === 'dir') s.dir = v === 'desc' ? -1 : 1;
      else if (FLAGS.includes(k)) s[k] = v === '1';
      else if (NEWS_QUERIES.includes(k)) s[k] = v.trim().slice(0, SEARCH_MAX);
      else s[k] = v;
    });
    if (!['cards','table','timeline'].includes(s.view)) s.view = 'cards';
    if (!['en','ar'].includes(s.lang)) s.lang = 'en';
    if (!['global','uae'].includes(s.region)) s.region = '';
    if (!/^[a-z]{2,20}$/.test(s.nt)) s.nt = '';
    return s;
  }
  // Views live in the hash (#home, #hardware, #news, #uae, #contact); filters stay in the query string.
  // Deep links such as #hardware/level/Personal, #contact/about or #contact/android are applied once, then the hash is reduced to the view.
  // A product or a key fact (#hardware/p/<id>, #uae/f/<id>) keeps its deep link in the address, so the address can be shared.
  const VIEWS = ['home','hardware','news','uae','contact'];
  const SUBS = {hardware: ['cards','table','timeline','compare','run','level','vendor','p'], news: ['all','global','uae'], uae: ['f'], contact: ['about', 'android']};
  const WITH_ARG = ['level','vendor','p','f'];
  // Links shared before the views existed carry only a query string (?q=4090, ?cmp=…): they belong to the hardware atlas.
  // The head script in template.html repeats this list so the first paint already shows the right view.
  const HW_KEYS = ['q','vendor','level','scope','sort','dir','view','cmp','p','bits','extra','fit','m','arabic'];
  function impliedView(search) {
    let qs;
    try { qs = new URLSearchParams(search || ''); } catch (e) { return 'home'; }
    if (HW_KEYS.some(k => qs.has(k))) return 'hardware';
    // Without a hash, a region, a topic or a news search opens AI news and a UAE search opens UAE AI (the head script agrees).
    if (qs.has('region') || qs.has('nq') || qs.has('nt')) return 'news';
    return qs.has('uq') ? 'uae' : 'home';
  }
  function parseRoute(hash, search) {
    let h = String(hash || '').replace(/^#/, '');
    try { h = decodeURIComponent(h); } catch (e) {}
    // Plain element ids used as no-JavaScript fallbacks (#p-<product>, #fact-<id>, #estimator, #about, #android) map onto their view.
    let m = /^p-(.+)$/.exec(h);
    if (m) return {view: 'hardware', sub: 'p', arg: m[1]};
    m = /^fact-(.+)$/.exec(h);
    if (m) return {view: 'uae', sub: 'f', arg: m[1]};
    if (h === 'estimator') return {view: 'hardware', sub: 'run', arg: ''};
    if (h === 'about' || h === 'android') return {view: 'contact', sub: h, arg: ''};
    const parts = h.split('/');
    if (!VIEWS.includes(parts[0])) return {view: impliedView(search), sub: '', arg: ''};
    const view = parts[0], sub = (SUBS[view] || []).includes(parts[1]) ? parts[1] : '';
    const arg = WITH_ARG.includes(sub) ? parts.slice(2).join('/') : '';
    if (WITH_ARG.includes(sub) && !arg) return {view, sub: '', arg: ''};
    return {view, sub, arg};
  }
  function routePatch(route, known) {
    // A deep link becomes a state change, an optional element to bring into view, and the canonical hash (the view alone).
    const out = {patch: {}, hash: route.view, focus: null};
    const clear = {q: '', vendor: '', level: '', scope: '', fit: false};
    const has = (list, v) => (list || []).includes(v);
    if (route.view === 'hardware') {
      if (['cards','table','timeline'].includes(route.sub)) out.patch = {view: route.sub};
      else if (route.sub === 'level' && has(known.levels, route.arg)) out.patch = {...clear, level: route.arg};
      else if (route.sub === 'vendor' && has(known.vendors, route.arg)) out.patch = {...clear, vendor: route.arg};
      else if (route.sub === 'p' && has(known.products, route.arg)) { out.patch = {...clear, view: 'cards'}; out.focus = 'p-' + route.arg; out.hash = 'hardware/p/' + route.arg; }
      else if (route.sub === 'run') out.focus = 'estimator';
      else if (route.sub === 'compare') out.focus = 'compare';
    } else if (route.view === 'news' && route.sub) {
      out.patch = {region: route.sub === 'all' ? '' : route.sub};
    } else if (route.view === 'uae' && route.sub === 'f' && has(known.facts, route.arg)) {
      out.focus = 'fact-' + route.arg;
      out.hash = 'uae/f/' + route.arg;
    } else if (route.view === 'contact' && (route.sub === 'about' || route.sub === 'android')) {
      out.focus = route.sub;
    }
    return out;
  }
  // An empty view keeps the URL without a hash.
  function pageUrl(path, qs, view) { return (path || '') + (qs ? '?' + qs : '') + (view ? '#' + view : ''); }
  const NOUNS = {
    product: {en: ['product', 'products'], ar: ['منتج واحد', 'منتجان', 'منتجات', 'منتجاً', 'منتج']},
    headline: {en: ['headline', 'headlines'], ar: ['عنوان واحد', 'عنوانان', 'عناوين', 'عنواناً', 'عنوان']},
    token: {en: ['token', 'tokens'], ar: ['رمز واحد', 'رمزان', 'رموز', 'رمزاً', 'رمز']}
  };
  // Number + noun: English plural, Arabic number agreement (1, 2, 3-10, 11-99, 100+). Same rules as cnt() in build.py.
  // `show` formats the number for display (for example 131,072) without changing the agreement.
  function countLabel(n, kind, lang, show) {
    const f = NOUNS[kind][lang === 'ar' ? 'ar' : 'en'], num = show ? show(n) : n;
    if (lang !== 'ar') return num + ' ' + (n === 1 ? f[0] : f[1]);
    if (n === 1) return f[0];
    if (n === 2) return f[1];
    const r = n % 100;
    return num + ' ' + (r >= 3 && r <= 10 ? f[2] : r >= 11 && r <= 99 ? f[3] : f[4]);
  }
  // Dates for people: '2025-03-18' -> '18 Mar 2025' / '18 مارس 2025', '2025-Q3' -> 'Q3 2025' / 'الربع الثالث 2025'.
  // Same output as when() in build.py; timestamps are shown as the UAE date. Sorting always uses the raw value.
  const MONTHS = {en: ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'], ar: ['يناير','فبراير','مارس','أبريل','مايو','يونيو','يوليو','أغسطس','سبتمبر','أكتوبر','نوفمبر','ديسمبر']};
  const WINDOW_NAMES = {
    en: {Q1:'Q1',Q2:'Q2',Q3:'Q3',Q4:'Q4',H1:'H1',H2:'H2',Summer:'Summer',end:'End of'},
    ar: {Q1:'الربع الأول',Q2:'الربع الثاني',Q3:'الربع الثالث',Q4:'الربع الرابع',H1:'النصف الأول',H2:'النصف الثاني',Summer:'صيف',end:'نهاية'}
  };
  function when(value, lang) {
    let s = String(value ?? '');
    const L = lang === 'ar' ? 'ar' : 'en';
    let m = /^(\d{4})-(Q[1-4]|H[12]|Summer|end)$/.exec(s);
    if (m) return WINDOW_NAMES[L][m[2]] + ' ' + m[1];
    if (/^\d{4}-\d{2}-\d{2}T/.test(s) && !isNaN(Date.parse(s))) s = new Date(Date.parse(s) + 4 * 3600e3).toISOString().slice(0, 10);
    m = /^(\d{4})-(\d{2})(?:-(\d{2}))?$/.exec(s);
    if (m && +m[2] >= 1 && +m[2] <= 12) return (m[3] ? +m[3] + ' ' : '') + MONTHS[L][+m[2] - 1] + ' ' + m[1];
    return s;
  }
  // The kind under an availability date, or '' when it would only repeat "Not established" (same rule as release_kind in build.py).
  const releaseKind = k => k && k !== 'Not established' ? k : '';
  // AI models named in the hardware search (the Android app's EstimatorText.search, same rules and ranking).
  // A word is letters and digits with optional dotted versions; each word splits into letter and number parts:
  // "qwen2.5" -> [qwen, 2.5], "32b" -> [32, b], "o3" -> [o, 3]. Numbers match whole ("5" finds 5 and 5.1, never 3.5 or 50);
  // letters match whole, except the last part of a query word, which may be the start of a longer word ("qwe" finds qwen).
  const WORD = /[\p{L}\p{Nd}]+(?:\.\p{Nd}+)*/gu, PART = /\p{L}+|\p{Nd}+(?:\.\p{Nd}+)*/gu;
  const isDigit = s => /^\p{Nd}/u.test(s);
  function words(text) { return (String(text || '').toLowerCase().match(WORD) || []).map(w => w.match(PART)); }
  function partMatches(q, s, last) {
    if (isDigit(q)) return isDigit(s) && (s === q || s.startsWith(q + '.'));
    if (isDigit(s)) return false;
    return last ? s.startsWith(q) : s === q;
  }
  function wordMatches(qParts, parts) {
    for (let i = 0; i + qParts.length <= parts.length; i++) {
      if (qParts.every((q, j) => partMatches(q, parts[i + j], j === qParts.length - 1))) return true;
    }
    return false;
  }
  function searchModels(models, query) {
    const list = models || [];
    if (!String(query || '').trim()) return list.slice();
    const q = words(query);
    if (!q.length) return [];
    const parts = m => words(m.n + ' ' + (m.hf || '')).flat();
    let hits = list.filter(m => { const p = parts(m); return q.every(w => wordMatches(w, p)); });
    if (!hits.length) {
      // Nothing matched word by word: a query word of letters only may also sit inside a longer word ("seek" -> DeepSeek).
      hits = list.filter(m => {
        const p = parts(m), joined = p.join('');
        return q.every(w => wordMatches(w, p) || (w.length === 1 && !isDigit(w[0]) && joined.includes(w[0])));
      });
    }
    const flat = q.flat(), first = q[0].join('');
    const rank = m => {
      const i = m.n.indexOf(': '), bare = words(i < 0 ? m.n : m.n.slice(i + 2)).flat();
      if (bare.length >= flat.length && flat.every((x, j) => partMatches(x, bare[j], j === flat.length - 1))) return 0;
      if (q.every(w => wordMatches(w, bare))) return 1;
      // The maker is the "Org" of "Org: Name"; a name without that prefix has none (as in the app).
      const maker = i < 0 ? '' : words(m.n.slice(0, i)).flat().join('');
      if (maker && maker.startsWith(first)) return 2;
      return 3;
    };
    // Stable: list order within each rank.
    return hits.map((m, i) => ({m, i, r: rank(m)})).sort((a, b) => a.r - b.r || a.i - b.i).map(x => x.m);
  }
  // What the hardware search offers: nothing below two characters.
  function modelSuggestions(models, query) { return String(query || '').trim().length < 2 ? [] : searchModels(models, query); }
  // Share buttons: a story shares "<headline> — via cipherlacuna.ae" with the original article's link; a product or a key
  // fact shares its own deep link. `copy` is what goes to the clipboard where the browser has no share sheet.
  const VIA = {en: '{t} — via cipherlacuna.ae', ar: '{t} — عبر cipherlacuna.ae'};
  function sharePayload(kind, title, url, lang) {
    const t = String(title ?? '').replace(/\s+/g, ' ').trim(), u = String(url ?? '');
    if (kind === 'story') { const text = VIA[lang === 'ar' ? 'ar' : 'en'].replace('{t}', () => t); return {title: t, text, url: u, copy: text + ' ' + u}; }
    return {title: t, url: u, copy: u};
  }
  // The deep link of a product or a key fact: the page address (/ or /ar/, which says the language) and the route.
  function deepLink(base, route) { return pageUrl(base, '', route); }
  // Older stories (the news archive, dist/news-archive/): what a card shows in one language, as the site's own cards do
  // (build.py headline_text and summary_of): the AI translation of an English headline in Arabic, the AI summary in that
  // language, else the publisher's excerpt when the story is in that language.
  function olderView(item, lang, sources) {
    const src = (sources || {})[item.source] || {}, ar = lang === 'ar';
    const title = ar && item.lang === 'en' && item.title_ar ? item.title_ar : item.title;
    const ai = item['summary_' + lang], summary = ai || (item.excerpt && item.lang === lang ? item.excerpt : '');
    return {title, summary, kind: ai ? 'ai' : summary ? 'publisher' : '', mt: ar && item.lang === 'en',
            publisher: (ar ? src.name_ar : src.name) || src.name || item.source || ''};
  }
  // The older stories one view lists for a search: in the page language's list, UAE stories only in UAE AI, the region
  // and topic chosen in AI news, every search word in the headline, summary or publisher shown (the same matcher as the
  // current list). Newest first, as the archive files are.
  function olderMatches(items, sources, o) {
    const terms = o.terms || [];
    if (!terms.length) return [];
    return (items || []).filter(i => {
      if (!(o.lang === 'ar' ? i.lang === 'ar' || !!i.title_ar : i.lang === 'en')) return false;
      if (o.view === 'uae' && !i.uae) return false;
      if (o.view === 'news') {
        const region = ((sources || {})[i.source] || {}).region, regions = (region === 'global' ? ['global'] : []).concat(i.uae ? ['uae'] : []);
        if (o.region && !(regions.length ? regions : ['global']).includes(o.region)) return false;
        if (o.topic && i.topic !== o.topic) return false;
      }
      const v = olderView(i, o.lang, sources), norm = normText([v.title, v.summary, v.publisher].join(' '));
      return matchesWords(norm, terms, norm.replace(/ /g, ''));
    });
  }
  if (typeof module !== 'undefined') module.exports = {select,dateNumber,dateRange,estimateGB,fitStatus,encodeState,decodeState,parseRoute,routePatch,pageUrl,countLabel,when,releaseKind,HW_KEYS,searchModels,modelSuggestions,normText,searchWords,matchesWords,sharePayload,deepLink,olderView,olderMatches,fittable,arabicModels,modelsThatFit};
  if (!root.document) return;

  const AR = {
    'NVIDIA + AMD / AI infrastructure':'NVIDIA + AMD / بنية الذكاء الاصطناعي التحتية','AI Hardware Atlas':'أطلس عتاد الذكاء الاصطناعي',
    'Compare GPUs, desktop systems, servers and racks.':'قارن معالجات الرسوميات والأجهزة المكتبية والخوادم والرفوف.',
    'One-page PDF':'ملف PDF من صفحة واحدة','Export CSV':'تصدير CSV','Copy link':'نسخ الرابط','Link copied':'تم نسخ الرابط','Print table':'طباعة الجدول',
    'Theme: Auto':'المظهر: تلقائي','Theme: Light':'المظهر: فاتح','Theme: Dark':'المظهر: داكن','Auto':'تلقائي','Light':'فاتح','Dark':'داكن',
    'Content updated:':'تاريخ المحتوى:','Prices checked:':'آخر تحقق من الأسعار:',
    'Search':'بحث','Vendor':'الشركة','Level':'المستوى','Memory scope':'نطاق الذاكرة','Model, memory, architecture…':'الطراز، الذاكرة، المعمارية…',
    'All levels':'كل المستويات','All memory scopes':'كل نطاقات الذاكرة',
    'Personal':'شخصي','Workstation':'محطة عمل','Enterprise':'مؤسسات','Data center':'مراكز البيانات','Rack scale':'على مستوى الرف',
    'Per GPU':'لكل معالج رسوميات','Shared CPU + GPU':'مشتركة بين المعالج والرسوميات','System total':'إجمالي النظام','Rack total':'إجمالي الرف',
    'GPU':'معالج رسوميات','System':'نظام','Platform':'منصة','Server class':'فئة خادم','Rack':'رف','Reference design':'تصميم مرجعي','Laptop':'حاسوب محمول','Built by':'من صنع',
    'Expected':'متوقع','Generally available':'متاح للجميع','Not established':'غير محدد','Orders opened':'فُتح باب الطلب','Partner rollout':'طرح عبر الشركاء',
    'Partner rollout expected':'طرح متوقع عبر الشركاء','Released':'صدر','Standalone cards':'بطاقات منفصلة','Vendor availability window':'فترة توفر معلنة',
    'Vendor distribution window':'فترة توزيع معلنة','Vendor target (summer 2025)':'هدف الشركة (صيف 2025)','Volume expected':'إنتاج كمي متوقع',
    "Not on NVIDIA's current roadmap":'ليس ضمن خارطة طريق NVIDIA الحالية',
    'Sort by':'ترتيب حسب','Hardware level':'مستوى العتاد','Model name':'اسم الطراز','Memory capacity':'سعة الذاكرة','Memory bandwidth':'عرض نطاق الذاكرة',
    'Launch price':'سعر الإطلاق','Availability date':'تاريخ التوفر','Announcement date':'تاريخ الإعلان','Power rating':'استهلاك الطاقة',
    'Ascending ↑':'تصاعدي ↑','Descending ↓':'تنازلي ↓','Reset':'إعادة ضبط','Cards':'بطاقات','Table':'جدول','Timeline':'خط زمني','View':'العرض',
    '{n} of {m}':'{n} من أصل {m}','No matches. Try another search or reset the filters.':'لا توجد نتائج. جرّب بحثاً آخر أو أعد ضبط الفلاتر.',
    'All products are visible. Enable JavaScript to search, sort, compare and export CSV.':'كل المنتجات ظاهرة. فعّل JavaScript للبحث والترتيب والمقارنة وتصدير CSV.',
    // AI models named in the hardware search
    'AI models ({n})':'نماذج الذكاء الاصطناعي ({n})','The atlas lists hardware. Pick a model to see which hardware can run it.':'الأطلس يعرض العتاد. اختر نموذجاً لترى العتاد القادر على تشغيله.',
    'Show all {n} models':'عرض كل النماذج ({n})','Show fewer':'عرض أقل','Show models':'عرض النماذج','Hide models':'إخفاء النماذج',
    'No hardware matches this search.':'لا يوجد عتاد مطابق لهذا البحث.',
    'No hardware matches this search with these filters. Reset the filters to see more.':'لا يوجد عتاد يطابق هذا البحث مع هذه الفلاتر. أعد ضبط الفلاتر لترى المزيد.',
    'Availability / target':'التوفر / الهدف','Announced / launched':'الإعلان / الإطلاق','Power':'الطاقة','Bandwidth':'عرض النطاق','AI compute':'حوسبة الذكاء الاصطناعي',
    'Form factor':'الشكل','Cooling':'التبريد','Interconnect':'الربط','Content reviewed':'تاريخ مراجعة المحتوى','Notes and official sources':'ملاحظات ومصادر رسمية',
    'Not listed':'غير مذكور','Not documented in this edition':'غير موثق في هذه النسخة','Compare':'قارن','Model':'الطراز','Memory':'الذاكرة','Type':'النوع',
    'Architecture':'المعمارية','Best fit':'الاستخدام الأنسب','Official source':'المصدر الرسمي','Fit':'الملاءمة',
    'What can it run?':'ما النماذج التي يشغّلها؟','Model size (billions of parameters)':'حجم النموذج (مليار مُعامل)','Precision':'الدقة',
    '16-bit (FP16 / BF16)':'16 بت (FP16 / BF16)','8-bit (FP8 / INT8)':'8 بت (FP8 / INT8)','4-bit (quantized)':'4 بت (مضغوط)',
    'Extra memory\u00a0(%)':'ذاكرة إضافية\u00a0(%)',
    'Besides the model itself, memory is needed for the conversation it holds and the software running it. 20% suits a normal chat; long documents need more.':'إلى جانب النموذج نفسه، يلزم قدرٌ إضافي من الذاكرة للمحادثة التي يحتفظ بها وللبرمجيات التي تشغّله. نسبة 20% تناسب محادثة عادية، أما المستندات الطويلة فتحتاج أكثر.','Only show hardware that fits':'اعرض العتاد الذي يتسع فقط','Presets':'قيم جاهزة',
    'Needs about {x} GB':'يحتاج تقريباً {x} جيجابايت','Enter a model size to highlight hardware that fits.':'أدخل حجم النموذج لتمييز العتاد الذي يتسع له.',
    'Rough guide: weights at the chosen precision plus the extra you set. Long contexts, batching and training need much more. Shared memory also serves the operating system, and multi-GPU totals need software that splits the model.':'تقدير تقريبي: الأوزان بالدقة المختارة مع النسبة الإضافية المحددة. السياقات الطويلة والدفعات والتدريب تحتاج أكثر بكثير. الذاكرة المشتركة يستخدمها نظام التشغيل أيضاً، والإجماليات متعددة المعالجات تحتاج برمجيات تقسّم النموذج.',
    'Fits':'يتسع','Fits across GPUs':'يتسع عبر عدة معالجات','Too small':'لا يتسع',
    '{n} selected':'المحدد: {n}','Clear':'مسح','Close':'إغلاق','Compare up to 4 products':'يمكن مقارنة 4 منتجات كحد أقصى','Remove':'إزالة',
    'Tick "Compare" on 2 to 4 products to compare them side by side.':'اختر «قارن» في منتجين إلى 4 منتجات لمقارنتها جنباً إلى جنب.',
    'Side-by-side comparison':'مقارنة جنباً إلى جنب','Memory scopes differ, so totals are not directly comparable.':'نطاقات الذاكرة مختلفة، لذا لا تُقارن الإجماليات مباشرة.',
    'Highlighted: highest value among products with the same memory scope.':'المميَّز: أعلى قيمة بين منتجات لها نطاق الذاكرة نفسه.',
    'Announced':'أُعلن','Today':'اليوم','No dated milestones for these products.':'لا توجد تواريخ لهذه المنتجات.',
    'Hollow circle: announcement. Solid mark: availability or vendor target. Bars show quarter, half-year or seasonal windows.':'الدائرة المفرغة: الإعلان. العلامة المصمتة: التوفر أو هدف الشركة. الأشرطة تمثل فترات ربع سنوية أو نصف سنوية أو موسمية.',
    'Without a dated milestone: {p}.':'بلا تاريخ محدد: {p}.',
    'How to read this':'كيف تقرأ هذه البيانات','Products':'المنتجات','Hardware catalog':'كتالوج العتاد','Filter hardware':'تصفية العتاد','Download and share':'التنزيل والمشاركة',
    'Capacity is not speed':'السعة ليست السرعة','Memory capacity determines what can fit. Bandwidth, compute, precision and software influence how quickly it runs. Sorting by memory is not a performance ranking.':'سعة الذاكرة تحدد ما يمكن أن يتسع. أما سرعة التشغيل فتتأثر بعرض النطاق والحوسبة والدقة والبرمجيات. الترتيب حسب الذاكرة ليس ترتيباً للأداء.',
    'Compare the same scope':'قارن النطاق نفسه','A single GPU, shared CPU/GPU system, and rack total are different measurements. Multiple GPUs do not automatically expose one shared VRAM pool.':'معالج رسوميات واحد، ونظام بذاكرة مشتركة، وإجمالي رف كامل هي قياسات مختلفة. تعدد معالجات الرسوميات لا يعني تلقائياً ذاكرة واحدة مشتركة.',
    'Dates have different meanings':'للتواريخ معانٍ مختلفة','An announcement does not establish first shipment. Vendor targets remain labeled as targets until a release or availability statement is verified. Unknown values stay blank.':'الإعلان لا يعني بدء الشحن. تبقى أهداف الشركات موسومة كأهداف حتى يتم التحقق من الإصدار أو التوفر. القيم غير المعروفة تبقى فارغة.',
    'What changed':'ما الذي تغيّر','Contact':'تواصل معنا','Questions, corrections or partnership ideas? Email us.':'أسئلة أو تصحيحات أو أفكار للتعاون؟ راسلنا عبر البريد الإلكتروني.',
    'Email us':'راسلنا عبر البريد الإلكتروني',
    'All rights reserved.':'جميع الحقوق محفوظة.',
    'Product images © NVIDIA and AMD. Headlines and publisher excerpts © their publishers, with links to the original articles. AI summaries are machine-written and may contain mistakes.':'صور المنتجات © NVIDIA وAMD. العناوين ومقتطفات الناشرين © لناشريها، مع روابط إلى المقالات الأصلية. ملخصات الذكاء الاصطناعي مكتوبة آلياً وقد تحتوي على أخطاء.','Pick a model':'اختر نموذجاً','size not published':'الحجم غير منشور','closed · cloud only':'مغلق · سحابي فقط',
    // UAE and Gulf models from official model cards (data/models-extra.json) and the "Arabic models" chip
    'Arabic models':'نماذج عربية','Chat only — no download':'محادثة فقط — لا تنزيل','Qatar':'قطر','Saudi Arabia':'السعودية',
    '{name} is chat only: its maker offers it in an online chat and has not published weights to download, so no hardware on this page can run it.':'{name} للمحادثة فقط: تتيحه الجهة المطوّرة عبر محادثة على الإنترنت ولم تنشر أوزانه للتنزيل، لذا لا يمكن لأي عتاد في هذه الصفحة تشغيله.',
    'size from the official model card':'الحجم من بطاقة النموذج الرسمية','Made by {maker} · {country}':'من تطوير {maker} · {country}','Supports Arabic':'يدعم العربية',
    'License: {l}':'الترخيص: {l}','Model card':'بطاقة النموذج','Official page':'الصفحة الرسمية',
    'Choose from {n} models listed on OpenRouter (list updated {d}) and {x} UAE and Gulf models from their official model cards, or enter a size below.':'اختر من {n} نموذجاً مدرجاً على OpenRouter (آخر تحديث للقائمة {d}) و{x} نموذجاً من الإمارات ودول الخليج من بطاقاتها الرسمية، أو أدخل الحجم أدناه.',
    'Arabic models only: {n} whose official model card lists Arabic. Choose one, or enter a size below.':'النماذج العربية فقط: {n} نموذجاً تذكر بطاقاتها الرسمية اللغة العربية. اختر واحداً منها أو أدخل الحجم أدناه.',
    // My hardware (kept in this browser only)
    'My hardware':'عتادي','None selected':'لم تختر بعد','Saved as My hardware':'حُفظ كعتادك','My hardware cleared':'أُزيل اختيار عتادك',
    'Choose the GPU or system you have to see which AI models fit it. It is saved in this browser only.':'اختر معالج الرسوميات أو الجهاز الذي لديك لترى نماذج الذكاء الاصطناعي التي تتسع له. يُحفظ اختيارك في هذا المتصفح فقط.',
    'With {hw}: {fit}':'مع {hw}: {fit}',
    '{n} of {m} models fit {hw} at this precision, largest first:':'{n} من أصل {m} نموذجاً تتسع لـ {hw} بهذه الدقة، الأكبر أولاً:',
    'No model with a published size fits {hw} at this precision. Try a lower precision.':'لا يتسع أي نموذج منشور الحجم لـ {hw} بهذه الدقة. جرّب دقة أقل.',
    'This memory is a total across several GPUs: the model has to be split across them.':'هذه الذاكرة إجمالي عدة معالجات رسوميات: يجب تقسيم النموذج عليها.',
    // Official MLPerf results (links only)
    'Official benchmarks (MLPerf)':'اختبارات الأداء الرسمية (MLPerf)','Open a round to find this hardware in the results MLCommons publishes.':'افتح الجولة للعثور على هذا العتاد في النتائج التي تنشرها MLCommons.',
    "{name} is a closed model: its weights are not public, so it runs only in the provider's cloud (for example through OpenRouter). No hardware on this page can run it locally.":'{name} نموذج مغلق: أوزانه غير منشورة، لذا يعمل فقط في سحابة المزوّد (مثلاً عبر OpenRouter). لا يمكن لأي عتاد في هذه الصفحة تشغيله محلياً.',
    '{name} is open-weight, but its size is not published in a form we can verify. Enter the size manually.':'{name} مفتوح الأوزان، لكن حجمه غير منشور بصيغة يمكننا التحقق منها. أدخل الحجم يدوياً.',
    '{name}: {b} billion parameters':'{name}: {b} مليار مُعامل','size taken from the model name':'الحجم مأخوذ من اسم النموذج','counted from Hugging Face weights':'محسوب من أوزان Hugging Face',
    'mixture-of-experts: all experts must fit in memory':'نموذج خبراء متعددين (MoE): يجب أن تتسع الذاكرة لكل الخبراء','context up to {c}':'سياق حتى {c}',
    'Choose from {n} models listed on OpenRouter (list updated {d}), or enter a size below.':'اختر من {n} نموذجاً مدرجاً على OpenRouter (آخر تحديث للقائمة {d})، أو أدخل الحجم أدناه.','Hardware':'العتاد','AI news':'أخبار الذكاء الاصطناعي','UAE AI':'الذكاء الاصطناعي في الإمارات',
    'Latest UAE AI news':'أحدث أخبار الذكاء الاصطناعي في الإمارات','As of':'بتاريخ','Headlines appear after the first scheduled update.':'تظهر العناوين بعد أول تحديث مجدول.',
    'Image:':'الصورة:','Approx. price':'السعر التقريبي','checked':'تم التحقق في','Not publicly priced':'لا يوجد سعر معلن',
    'US retail':'متاجر أمريكية','US used market':'سوق المستعمل الأمريكي','UAE used market':'سوق المستعمل في الإمارات','Ada Lovelace':'Ada Lovelace','UAE retail':'متاجر الإمارات','Reported estimate':'تقدير منشور','Converted from USD at 3.6725':'محوّل من الدولار بسعر 3.6725','Approx. USD':'تقريبي بالدولار','Approx. AED':'تقريبي بالدرهم','Air':'هوائي','Liquid':'سائل','Air or liquid':'هوائي أو سائل',
    'Reference total graphics power':'الطاقة الإجمالية المرجعية للرسوميات','Official specification, checked automatically':'مواصفة رسمية يُتحقق منها تلقائياً','Accelerator rating; excludes host':'تصنيف المسرّع، دون النظام المضيف','Total board power':'إجمالي طاقة البطاقة','Workstation Edition maximum':'الحد الأقصى لإصدار محطة العمل',
    // Site shell and the four-pillar hub
    'Skip to content':'انتقل إلى المحتوى','Main sections':'الأقسام الرئيسية','Overview':'الرئيسية','News':'الأخبار','UAE':'الإمارات',
    'Breadcrumb':'مسار التنقل','Back to overview':'العودة إلى الرئيسية','Other areas':'الأقسام الأخرى','Footer':'تذييل الصفحة','About':'عن الموقع','Android app':'تطبيق Android',
    'AI hardware, AI news and UAE AI':'عتاد الذكاء الاصطناعي وأخباره وحضوره في الإمارات','Decoding the gaps in AI knowledge':'كشف المجهول في عالم الذكاء الاصطناعي',
    'Follow Qahwa & AI':'تابع قهوة و AI','AI lessons and news from Qahwa & AI, in English and Arabic.':'دروس وأخبار الذكاء الاصطناعي من قهوة و AI، بالعربية والإنجليزية.',
    'Quick links':'روابط سريعة','The four areas of the site':'أقسام الموقع الأربعة',
    'NVIDIA and AMD GPUs, desktop systems, servers and racks, side by side.':'معالجات رسوميات وأجهزة مكتبية وخوادم ورفوف من NVIDIA وAMD، جنباً إلى جنب.',
    'products':'المنتجات','levels':'المستويات','with approx. price':'بسعر تقريبي','Featured':'مختارات','Prices approximate':'الأسعار تقريبية',
    'Browse by level':'تصفّح حسب المستوى','Browse':'تصفّح','Approx.':'حوالي','Open hardware':'افتح قسم العتاد',
    'headlines':'العناوين','English · Arabic':'إنجليزي · عربي','sources':'المصادر','Latest headlines':'أحدث العناوين','Times in UAE time':'الأوقات بتوقيت الإمارات',
    'Global':'عالمي','Open AI news':'افتح قسم الأخبار',
    'What the UAE is building in AI: strategy, compute and models, each fact with its source.':'ما تبنيه الإمارات في الذكاء الاصطناعي: الاستراتيجية والحوسبة والنماذج، ولكل معلومة مصدرها.',
    'key facts':'الحقائق الرئيسية','UAE headlines':'عناوين الإمارات','Key fact':'حقيقة رئيسية',
    'Latest UAE headlines':'أحدث عناوين الإمارات','Open UAE AI':'افتح قسم الإمارات',
    // Learn AI: its nav item and the fourth pillar (the page itself, learn.html, carries both languages in its HTML)
    'Learn AI':'تعلّم الذكاء الاصطناعي','Learn':'تعلّم','Open Learn AI':'افتح صفحة تعلّم الذكاء الاصطناعي',
    // Qahwa & AI lessons (qahwa.html, a separate page): the footer and About links
    'Qahwa & AI lessons':'دروس قهوة و AI',
    "Plain-language guides to the ideas behind today's AI, and recommended stacks for building with it.":'شروح واضحة للأفكار التي يقوم عليها الذكاء الاصطناعي اليوم، وتركيبات تقنية موصى بها للبناء به.',
    'concepts':'المفاهيم','AI stacks':'التركيبات التقنية','foundations':'الأسس','Start here':'ابدأ من هنا','Beginner concepts':'مفاهيم للمبتدئين',
    'Local, cloud and UAE-hosted options':'خيارات محلية وسحابية ومستضافة في الإمارات','Browse by topic':'تصفّح حسب الموضوع',
    'Why trust this':'لماذا تثق بهذه البيانات؟','Official sources':'مصادر رسمية','Dated prices':'أسعار مؤرّخة',
    'Prices are approximate, labelled by kind, with the date they were checked.':'الأسعار تقريبية، ويظهر مع كل سعر نوعه وتاريخ التحقق منه.',
    'Every headline sourced':'لكل عنوان مصدره','Official sources checked':'فحص المصادر الرسمية','Hardware sources are checked automatically.':'تُفحص مصادر العتاد تلقائياً.',
    'Each summary says whether AI or the publisher wrote it, and every headline has a source link to the original article.':'يوضح كل ملخص إن كان من كتابة الذكاء الاصطناعي أو من الناشر، ولكل عنوان رابط إلى المقال الأصلي.',
    'Headlines at a glance':'العناوين في لمحة','Region':'النطاق','All':'الكل','English':'الإنجليزية','Arabic':'العربية',
    'Headlines':'العناوين','Show more':'عرض المزيد','Showing {n} of {m}':'المعروض {n} من أصل {m}',
    // News search (#news and #uae; the Android app uses the same pairs)
    'Search news…':'ابحث في الأخبار…','Clear search':'مسح البحث','Results: {m}':'النتائج: {m}','Results: {m} · showing {n}':'النتائج: {m} · المعروض منها {n}',
    'No results':'لا توجد نتائج','No matches. Try another word or clear the search.':'لا توجد نتائج. جرّب كلمة أخرى أو امسح البحث.',
    'No headlines in this region match this search. Choose All to search every region.':'لا توجد عناوين في هذا النطاق تطابق هذا البحث. اختر «الكل» للبحث في كل النطاقات.',
    // Topic chips, older stories (the news archive) and share buttons
    'Topic':'الموضوع','No headlines match these filters. Choose All to see every headline.':'لا توجد عناوين تطابق هذه الفلاتر. اختر «الكل» لعرض كل العناوين.',
    'No headlines match this search with these filters. Choose All to search every headline.':'لا توجد عناوين تطابق هذا البحث مع هذه الفلاتر. اختر «الكل» للبحث في كل العناوين.',
    'Search older stories':'ابحث في الأخبار الأقدم','Search earlier months':'ابحث في الأشهر السابقة','Older stories: {m}':'الأخبار الأقدم: {m}',
    'No older stories match this search.':'لا توجد أخبار أقدم تطابق هذا البحث.','Loading older stories…':'جارٍ تحميل الأخبار الأقدم…',
    'Older stories could not be loaded. Try again later.':'تعذّر تحميل الأخبار الأقدم. حاول مرة أخرى لاحقاً.',
    'Share this product':'مشاركة المنتج','Share this key fact':'مشاركة الحقيقة الرئيسية','Share this story':'مشاركة الخبر',
    'Key facts':'حقائق رئيسية','Newest first. Hardware tags open the matching products.':'الأحدث أولاً. وسوم العتاد تفتح المنتجات المطابقة.','Sources':'المصادر',
    'Each product links to its evidence. Uses are editorial guidance. Power figures apply to the listed component or edition, not the whole server. Launch prices are vendor MSRPs at launch, not current street prices. Timing and stock vary by manufacturer and region. Approximate prices are dated snapshots of retail listings or reported estimates, not offers; UAE retail prices normally include 5% VAT. Product images belong to NVIDIA and AMD and link to their source pages.':'كل منتج مرتبط بمصدره. الاستخدامات المقترحة إرشاد تحريري. أرقام الطاقة تخص المكوّن أو الإصدار المذكور، لا الخادم كاملاً. أسعار الإطلاق هي الأسعار المقترحة من الشركة عند الإطلاق، وليست أسعار السوق الحالية. المواعيد والتوفر يختلفان حسب الشركة المصنّعة والمنطقة. الأسعار التقريبية لقطات مؤرّخة من قوائم المتاجر أو تقديرات منشورة، وليست عروض بيع، وأسعار متاجر الإمارات تشمل عادةً ضريبة القيمة المضافة 5%. صور المنتجات مملوكة لـ NVIDIA وAMD وترتبط بصفحات مصادرها.',
    'Llama, Qwen, DeepSeek, gpt-oss…':'مثل Llama وQwen وDeepSeek وgpt-oss…','Specification':'المواصفة','Selected for comparison':'المنتجات المختارة للمقارنة'
  };
  const $ = id => document.getElementById(id);
  const data = JSON.parse($('catalog-data').textContent);
  const byId = new Map(data.products.map(p => [p.id, p]));
  const cards = new Map([...document.querySelectorAll('[data-product]')].map(el => [el.dataset.product, el]));
  const store = {get(k){try{return localStorage.getItem(k)}catch(e){return null}},set(k,v){try{localStorage.setItem(k,v)}catch(e){}},del(k){try{localStorage.removeItem(k)}catch(e){}}};
  const state = decodeState(location.search);
  // The page's own language: index.html is English, ar/index.html Arabic (scripts/lang_pages.py). The head script has
  // already sent a ?lang= of the other language, or Arabic saved on the English page, to the other page.
  const PAGE_LANG = document.documentElement.getAttribute('lang') === 'ar' ? 'ar' : 'en';
  state.lang = PAGE_LANG;
  // The Arabic page sits one folder down and reuses the site's files: their paths in the data get this prefix.
  const ROOT = document.documentElement.getAttribute('data-root') || '';
  // The language link (#lang) leads to the other language's copy of this page (ar/index.html, or ../index.html from it);
  // over http(s) without the final index.html, so the address is /ar/ or /.
  const langLink = $('lang'), langHref = langLink.getAttribute('href') || '';
  const langBase = location.protocol === 'file:' ? langHref : langHref.replace(/(^|\/)index\.html$/, '$1');
  state.cmp = state.cmp.filter(id => byId.has(id));
  let visible = data.products, theme = store.get('atlas-theme') || 'auto', currentView = 'home', lastHref = '', routeSeq = 0;
  // The part of a product or key-fact deep link that stays in the address ('p/<id>', 'f/<id>'), so it can be shared; it
  // goes with the next navigation, or when the product leaves the cards (another filter, the table or the timeline).
  let currentDeep = '';
  const hashNow = () => currentDeep ? currentView + '/' + currentDeep : currentView;
  // Until the load event the address is left exactly as opened (see syncUrl).
  let booted = document.readyState === 'complete';
  const T = s => state.lang === 'ar' ? (AR[s] || s) : s;
  const F = (s, vars) => T(s).replace(/\{(\w+)\}/g, (_, k) => vars[k]);
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  // HTML version of F: the sentence is escaped, the values are markup (for example an isolated model name).
  const FH = (s, vars) => esc(T(s)).replace(/\{(\w+)\}/g, (_, k) => vars[k]);
  const en = v => `<span lang="en">${esc(v)}</span>`;
  const day = v => when(v, state.lang);
  const fmt = n => Number(n).toLocaleString('en-US', {maximumFractionDigits: 3});
  const bw = p => p.bandwidth_tbs == null ? T('Not listed') : fmt(p.bandwidth_tbs) + ' TB/s';
  const watts = p => p.power_w == null ? T('Not listed') : fmt(p.power_w) + ' W';
  const price = p => p.msrp_usd == null ? T('Not listed') : '$' + fmt(p.msrp_usd);
  const orNA = v => v == null || v === '' ? T('Not listed') : T(v);
  const kindSmall = p => releaseKind(p.release_kind) ? `<small>${esc(T(p.release_kind))}</small>` : '';
  const FIT = {fits:'Fits', multi:'Fits across GPUs', no:'Too small'};
  const SORTABLE = ['level','model','memory_gb','bandwidth_tbs','power_w','announcement','release','msrp_usd','price_usd'];
  const pv = (p, k) => p.price_view && p.price_view[k] ? p.price_view[k] : null;
  const VIEW_NAME = {home: 'Overview', hardware: 'Hardware', news: 'AI news', uae: 'UAE AI', contact: 'Contact'};
  const VIEW_TITLE = {hardware: 'AI Hardware Atlas', news: 'AI news', uae: 'UAE AI', contact: 'Contact'};
  const known = {levels, vendors: ['NVIDIA', 'AMD'], products: [...byId.keys()], facts: [...document.querySelectorAll('[data-fact]')].map(el => el.dataset.fact)};
  const NEWS_STEP = 30;
  let newsLimit = NEWS_STEP;
  // The UAE view lists its headlines before the key facts: a first few, then "Show more", so the facts stay near on a phone.
  const UAE_STEP = 8;
  let uaeLimit = UAE_STEP;
  // The count lines as the build wrote them (both languages), read before anything changes them: the UAE line comes back
  // when its search is cleared, and either one when the page language has no headlines.
  const countEl = view => $(view === 'news' ? 'news-count' : 'uae-count');
  const builtCount = {news: countEl('news') ? countEl('news').innerHTML : '', uae: countEl('uae') ? countEl('uae').innerHTML : ''};

  const MODELS = (() => { try { return JSON.parse($('models-data').textContent); } catch (e) { return {models: []}; } })();
  const modelByName = new Map(MODELS.models.map(m => [m.n.toLowerCase(), m]));
  const findModel = name => modelByName.get(String(name || '').trim().toLowerCase());
  // A link that names an open model but no size (?m=… without p) takes the model's published size.
  function sizeFromModel(s) {
    const m = findModel(s.model);
    if (fittable(m) && !s.params) s.params = String(m.b);
  }
  const sizeLabel = m => m.r === false ? T('Chat only — no download') : m.o ? (m.b ? fmt(m.b) + ' B' : T('size not published')) : T('closed · cloud only');
  // In the picker's list a card model also names its country.
  const modelLabel = m => sizeLabel(m) + (m.co ? ' · ' + T(m.co) : '');
  const N_ARABIC = arabicModels(MODELS.models).length;
  let listKey = '';
  function fillModelList() {
    // The "Arabic models" chip narrows the picker to the models whose official card lists Arabic.
    const list = state.arabic ? arabicModels(MODELS.models) : MODELS.models;
    $('model-list').innerHTML = list.map(m => `<option value="${esc(m.n)}">${esc(modelLabel(m))}</option>`).join('');
    listKey = state.lang + (state.arabic ? '1' : '0');
  }
  function renderArabicChip() {
    const chip = $('model-ar');
    chip.hidden = !N_ARABIC;
    chip.setAttribute('aria-pressed', String(!!state.arabic));
    $('model-ar-n').textContent = String(N_ARABIC);
    if (listKey !== state.lang + (state.arabic ? '1' : '0')) fillModelList();
  }
  // AI models matching the hardware search: a card above the products. Open with the first 3 when no hardware matches,
  // a title line with "Show models" when hardware matches too. The count is announced through #mh-live, which stays in
  // the page (a live region inside the hidden card would not be heard when the card appears).
  const MH_FIRST = 3;
  const mh = {q: null, hits: [], open: false, all: false, key: '', live: ''};
  function renderModelHits() {
    if (mh.q !== state.q) { mh.q = state.q; mh.hits = modelSuggestions(MODELS.models, state.q); }
    const hits = mh.hits, n = hits.length, title = n ? F('AI models ({n})', {n}) : '';
    if (title !== mh.live) { $('mh-live').textContent = title; mh.live = title; }
    $('model-hits').hidden = !n;
    if (!n) { mh.open = mh.all = false; return hits; }
    const none = visible.length === 0, open = none || mh.open, toggle = $('mh-toggle');
    $('mh-title').textContent = title;
    toggle.hidden = none;
    toggle.textContent = T(open ? 'Hide models' : 'Show models');
    toggle.setAttribute('aria-expanded', String(open));
    $('model-hits').classList.toggle('open', open);
    $('mh-body').hidden = !open;
    if (!open) return hits;
    const shown = mh.all ? hits : hits.slice(0, MH_FIRST), key = state.lang + '\n' + shown.map(m => m.n).join('\n');
    // Rebuilt only when the rows change, so typing doesn't replace buttons for nothing.
    if (key !== mh.key) {
      $('mh-list').innerHTML = shown.map(m => `<li><button type="button" class="mh-pick" data-pick="${esc(m.n)}"><bdi class="mh-name" lang="en">${esc(m.n)}</bdi><span class="sr-only">, </span><span class="mh-size">${esc(modelLabel(m))}</span></button></li>`).join('');
      mh.key = key;
    }
    const more = $('mh-more');
    more.hidden = n <= MH_FIRST;
    more.textContent = mh.all ? T('Show fewer') : F('Show all {n} models', {n});
    more.setAttribute('aria-expanded', String(mh.all));
    return hits;
  }
  function modelNote() {
    // The note follows the page direction; the Latin model name is isolated so it can't reorder an Arabic sentence.
    const note = $('model-note'), m = findModel(state.model);
    note.classList.toggle('closed', !!(m && (!m.o || m.r === false)));
    if (!m) {
      const x = MODELS.models.filter(v => v.co).length, n = MODELS.models.length - x, d = `<bdi>${esc(day(MODELS.updated_at))}</bdi>`;
      if (state.arabic && N_ARABIC) note.innerHTML = FH('Arabic models only: {n} whose official model card lists Arabic. Choose one, or enter a size below.', {n: esc(fmt(N_ARABIC))});
      else if (!MODELS.models.length) note.innerHTML = '';
      else if (x) note.innerHTML = FH('Choose from {n} models listed on OpenRouter (list updated {d}) and {x} UAE and Gulf models from their official model cards, or enter a size below.', {n: esc(fmt(n)), d, x: esc(fmt(x))});
      else note.innerHTML = FH('Choose from {n} models listed on OpenRouter (list updated {d}), or enter a size below.', {n: esc(fmt(n)), d});
      return;
    }
    const name = `<bdi lang="en">${esc(m.n)}</bdi>`;
    // A card model: who made it, where, Arabic when its card says so, its license, and its official page.
    const who = m.co ? FH('Made by {maker} · {country}', {maker: `<bdi lang="en">${esc(m.mk)}</bdi>`, country: esc(T(m.co))}) + (m.ar ? ' · ' + esc(T('Supports Arabic')) : '') : '';
    const link = (href, label) => /^https:\/\//.test(href || '') ? ` · <a href="${esc(href)}" target="_blank" rel="noopener noreferrer">${label}</a>` : '';
    if (m.r === false) {
      note.innerHTML = FH('{name} is chat only: its maker offers it in an online chat and has not published weights to download, so no hardware on this page can run it.', {name})
        + (who ? ' ' + who : '') + link(m.u, esc(T('Official page')));
      return;
    }
    if (!m.o) { note.innerHTML = FH("{name} is a closed model: its weights are not public, so it runs only in the provider's cloud (for example through OpenRouter). No hardware on this page can run it locally.", {name}); return; }
    if (!m.b) { note.innerHTML = FH('{name} is open-weight, but its size is not published in a form we can verify. Enter the size manually.', {name}); return; }
    const parts = [FH('{name}: {b} billion parameters', {name, b: esc(fmt(m.b))}), esc(T(m.s === 'name' ? 'size taken from the model name' : m.s === 'card' ? 'size from the official model card' : 'counted from Hugging Face weights'))];
    if (m.moe) parts.push(esc(T('mixture-of-experts: all experts must fit in memory')));
    if (m.c) parts.push(FH('context up to {c}', {c: esc(countLabel(m.c, 'token', state.lang, fmt))}));
    if (who) parts.push(who);
    if (m.l) parts.push(FH('License: {l}', {l: `<bdi lang="en">${esc(m.l)}</bdi>`}));
    const hfUrl = /^[\w.-]+\/[\w.-]+$/.test(m.hf || '') ? 'https://huggingface.co/' + m.hf : '';
    const hf = hfUrl ? ` · <a href="${esc(hfUrl)}" target="_blank" rel="noopener noreferrer" lang="en">Hugging Face</a>` : '';
    note.innerHTML = parts.join(' · ') + hf + (m.u && m.u !== hfUrl ? link(m.u, esc(T('Model card'))) : '');
  }
  // ---------- My hardware: one product a visitor owns, kept in this browser only (localStorage atlas-myhw) ----------
  // The page works the same without it (private windows, blocked storage). The estimator lists the models that fit it.
  const MYHW_KEY = 'atlas-myhw', MYHW_FIRST = 6;
  let myhw = byId.has(store.get(MYHW_KEY)) ? store.get(MYHW_KEY) : '', myhwAll = false, myhwKey = '';
  function setMyHw(id, announce) {
    myhw = byId.has(id) ? id : '';
    myhwAll = false;
    if (myhw) store.set(MYHW_KEY, myhw); else store.del(MYHW_KEY);
    render();
    if (announce) flash(T(myhw ? 'Saved as My hardware' : 'My hardware cleared'));
  }
  function fillMyHwSelect() {
    // Every product, grouped by level, with its memory, in the page language (the names are the vendors' own, in Latin).
    const sel = $('myhw-sel');
    sel.innerHTML = `<option value="">${esc(T('None selected'))}</option>` + levels.map(l => {
      const ps = data.products.filter(p => p.level === l);
      return ps.length ? `<optgroup label="${esc(T(l))}">${ps.map(p => `<option value="${esc(p.id)}">${esc(p.model)} · ${esc(p.memory)}</option>`).join('')}</optgroup>` : '';
    }).join('');
    sel.value = myhw;
  }
  function renderMyHw(n) {
    const p = byId.get(myhw), sel = $('myhw-sel'), note = $('myhw-note'), list = $('myhw-list'), more = $('myhw-more');
    if (sel.value !== myhw) sel.value = myhw;
    $('myhw-clear').hidden = !p;
    cards.forEach((el, id) => {
      const mine = id === myhw;
      el.classList.toggle('mine', mine);
      el.querySelector('.myhw-tag').hidden = !mine;
      el.querySelector('.myhw-btn').setAttribute('aria-pressed', String(mine));
    });
    if (!p) {
      setHtml(note, esc(T('Choose the GPU or system you have to see which AI models fit it. It is saved in this browser only.')));
      list.hidden = more.hidden = true;
      myhwKey = '';
      return;
    }
    const hw = `<bdi lang="en">${esc(p.model)}</bdi>`;
    // The same pool as the picker: every fittable model, or the Arabic ones while that chip is on.
    const pool = (state.arabic ? arabicModels(MODELS.models) : MODELS.models).filter(fittable);
    const fits = modelsThatFit(pool, p.memory_gb, state.bits, state.extra), s = fitStatus(p, n), parts = [];
    if (s) parts.push(FH('With {hw}: {fit}', {hw, fit: `<span class="fit ${s}">${esc(T(FIT[s]))}</span>`}));
    parts.push(fits.length ? FH('{n} of {m} models fit {hw} at this precision, largest first:', {n: esc(fmt(fits.length)), m: esc(fmt(pool.length)), hw})
      : FH('No model with a published size fits {hw} at this precision. Try a lower precision.', {hw}));
    if (p.memory_scope === 'System total' || p.memory_scope === 'Rack total') parts.push(esc(T('This memory is a total across several GPUs: the model has to be split across them.')));
    setHtml(note, parts.join(' '));
    const shown = myhwAll ? fits : fits.slice(0, MYHW_FIRST), key = state.lang + '\n' + shown.map(m => m.n).join('\n');
    list.hidden = !fits.length;
    // Rebuilt only when the rows change, so typing elsewhere doesn't replace the buttons.
    if (key !== myhwKey) {
      list.innerHTML = shown.map(m => `<li><button type="button" class="mh-pick" data-pick="${esc(m.n)}"><bdi class="mh-name" lang="en">${esc(m.n)}</bdi><span class="sr-only">, </span><span class="mh-size">${esc(modelLabel(m))}</span></button></li>`).join('');
      myhwKey = key;
    }
    more.hidden = fits.length <= MYHW_FIRST;
    more.textContent = myhwAll ? T('Show fewer') : F('Show all {n} models', {n: fits.length});
    more.setAttribute('aria-expanded', String(myhwAll));
  }
  function need() { return estimateGB(state.params, state.bits, state.extra); }
  function readControls() {
    ['search:q','vendor','level','scope','params','bits','extra'].forEach(x => { const [id,k] = x.split(':'); state[k || id] = $(id).value; });
    state.fit = $('fit-only').checked;
  }
  function writeControls() {
    ['search:q','vendor','level','scope','params','bits','extra'].forEach(x => { const [id,k] = x.split(':'); $(id).value = state[k || id]; });
    ['vendor','level','scope'].forEach(id => { state[id] = $(id).value; });
    $('fit-only').checked = state.fit;
    $('model').value = state.model || '';
    if (!SORTABLE.includes(state.sort)) state.sort = 'level';
    $('sort').value = state.sort;
    // The news searches (the fields exist only when the build has headlines). A field that differs only by spaces is left
    // as typed.
    [['news-q', 'nq'], ['uae-q', 'uq']].forEach(([id, k]) => { const f = $(id); if (f && f.value.trim() !== state[k].trim()) f.value = state[k]; });
  }
  function applyLang() {
    document.documentElement.lang = state.lang;
    document.documentElement.dir = state.lang === 'ar' ? 'rtl' : 'ltr';
    document.querySelectorAll('[data-i18n]').forEach(el => { if (el.dataset.en == null) el.dataset.en = el.textContent; el.textContent = T(el.dataset.en); });
    document.querySelectorAll('[data-i18n-ph]').forEach(el => { el.placeholder = T(el.dataset.i18nPh); });
    document.querySelectorAll('[data-i18n-aria]').forEach(el => { el.setAttribute('aria-label', T(el.dataset.i18nAria)); });
    document.querySelectorAll('[data-ar]').forEach(el => { if (el.dataset.en == null) el.dataset.en = el.textContent; el.textContent = state.lang === 'ar' && el.dataset.ar ? el.dataset.ar : el.dataset.en; });
    const lb = $('lang');
    lb.querySelector('.l-long').textContent = state.lang === 'ar' ? 'English' : 'العربية';
    lb.querySelector('.l-short').textContent = state.lang === 'ar' ? 'EN' : 'عربي';
    lb.lang = state.lang === 'ar' ? 'en' : 'ar';
    learnLinks();
    applyTheme();
    setTitle();
    document.documentElement.classList.remove('i18n-wait');
  }
  function learnLinks() {
    // learn.html and qahwa.html are separate pages, each in English and in Arabic (ar/learn.html beside ar/index.html), so
    // their links already lead to this page's language. Only an English visit while Arabic is the saved choice (opened
    // with ?lang=en, which saves nothing) says so, or those pages would go to their Arabic copies.
    const want = PAGE_LANG === 'en' && store.get('atlas-lang') === 'ar' ? 'en' : '';
    document.querySelectorAll('a[href^="learn.html"], a[href^="qahwa.html"]').forEach(a => {
      if (a.dataset.baseHref == null) a.dataset.baseHref = a.getAttribute('href');
      const h = a.dataset.baseHref, i = h.indexOf('#'), path = i < 0 ? h : h.slice(0, i), frag = i < 0 ? '' : h.slice(i);
      a.setAttribute('href', want ? path + '?lang=' + want + frag : h);
    });
  }
  function applyTheme() {
    if (theme === 'light' || theme === 'dark') document.documentElement.dataset.theme = theme;
    else { theme = 'auto'; delete document.documentElement.dataset.theme; }
    const name = theme[0].toUpperCase() + theme.slice(1);
    $('theme-label').textContent = T(name);
    $('theme').setAttribute('aria-label', T('Theme: ' + name));
  }
  function setTitle() {
    document.title = currentView === 'home' ? 'Cipher Lacuna | ' + T('AI hardware, AI news and UAE AI') : T(VIEW_TITLE[currentView]) + ' · Cipher Lacuna';
    $('brand-sec').textContent = currentView === 'home' ? '' : T(VIEW_NAME[currentView]);
  }
  function syncUrl() {
    // Query string = filters and settings, hash = the open view.
    // A URL opened without a hash keeps none while it still opens the same view: writing one (#home) would move the
    // browser's Tab starting point into the page. Before the load event nothing is rewritten, because the browser scrolls
    // to the element named by the hash at load: shortening #hardware/p/<id> to #hardware earlier sends it to the top.
    if (booted) {
      const hash = !location.hash && !currentDeep && impliedView(urlQuery()) === currentView ? '' : hashNow();
      try { history.replaceState(null, '', pageUrl(location.pathname, urlQuery(), hash)); } catch (e) {}
    }
    // A product or key-fact deep link goes along, so the other language opens the same card.
    langLink.setAttribute('href', pageUrl(langBase, urlQuery(), hashNow()));
    lastHref = location.href;
  }
  // The address says the language by its path (/ or /ar/), so the query string never repeats it.
  function urlQuery() { return encodeState({...state, lang: DEFAULTS.lang}); }
  function shareUrl() { return pageUrl(location.href.split(/[?#]/)[0], urlQuery(), hashNow()); }

  function render() {
    const n = need();
    visible = select(data.products, {q:state.q, vendor:state.vendor, level:state.level, scope:state.scope, need:n, fitOnly:state.fit}, state.sort, state.dir);
    const ids = new Set(visible.map(p => p.id));
    if (currentDeep.startsWith('p/') && (state.view !== 'cards' || !ids.has(currentDeep.slice(2)))) currentDeep = '';
    cards.forEach((el, id) => {
      el.hidden = !ids.has(id);
      const fit = el.querySelector('.fit'), s = fitStatus(byId.get(id), n);
      fit.hidden = !s;
      if (s) { fit.className = 'fit ' + s; fit.textContent = T(FIT[s]); }
      el.querySelector('.cmp-toggle').checked = state.cmp.includes(id);
    });
    visible.forEach(p => $('products').appendChild(cards.get(p.id)));
    $('count').textContent = F('{n} of {m}', {n: visible.length, m: countLabel(data.products.length, 'product', state.lang)});
    const models = renderModelHits().length > 0, filtered = !!(state.vendor || state.level || state.scope || (state.fit && n));
    $('empty').hidden = visible.length !== 0;
    $('empty').classList.toggle('slim', models);
    $('empty').textContent = T(!models ? 'No matches. Try another search or reset the filters.' : filtered ? 'No hardware matches this search with these filters. Reset the filters to see more.' : 'No hardware matches this search.');
    $('direction').textContent = T(state.dir === 1 ? 'Ascending ↑' : 'Descending ↓');
    $('need').textContent = n ? F('Needs about {x} GB', {x: fmt(Math.round(n * 10) / 10)}) : T('Enter a model size to highlight hardware that fits.');
    ['cards','table','timeline'].forEach(v => $('view-' + v).setAttribute('aria-pressed', String(state.view === v)));
    $('products').hidden = state.view !== 'cards';
    $('table-view').hidden = state.view !== 'table';
    $('timeline-view').hidden = state.view !== 'timeline';
    if (state.view === 'table') renderTable(n);
    if (state.view === 'timeline') renderTimeline();
    renderTray();
    renderArabicChip();
    modelNote();
    renderMyHw(n);
    renderNews();
    renderUae();
    syncUrl();
  }

  function renderNews() {
    // Filters the server-rendered list for the current language by the search, the region and the topic; "Show more"
    // reveals the matches in steps. The region chips count the matches of the search and the topic in each region, the
    // topic chips the matches of the search and the region in each topic.
    const view = $('news');
    if (!view) return;
    // A topic the page language has no headline in (the other language's, or one from an older shared link) is no choice.
    const tchips = [...view.querySelectorAll('[data-topic-chip]')];
    tchips.forEach(b => { b.hidden = !!b.dataset.topicChip && !(b.dataset.langs || '').split(' ').includes(state.lang); });
    if (state.nt && !tchips.some(b => b.dataset.topicChip === state.nt && !b.hidden)) state.nt = '';
    view.querySelectorAll('[data-region-chip]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.regionChip === state.region)));
    tchips.forEach(b => b.setAttribute('aria-pressed', String(b.dataset.topicChip === state.nt)));
    const list = view.querySelector(`.nlist[data-lang="${state.lang}"]`), more = $('news-more'), terms = searchWords(state.nq);
    if (!list) { if (more) more.hidden = true; searchUi('news', terms, 0, 0, null, false); renderOlder('news'); return; }
    const counts = {'': 0, global: 0, uae: 0}, topicCounts = {'': 0};
    let total = 0, shown = 0, hits = 0;
    list.querySelectorAll('li[data-region]').forEach(li => {
      const regions = li.dataset.region.split(' '), topic = li.dataset.topic || '', hit = !terms.length || newsHit(li, terms);
      const inRegion = !state.region || regions.includes(state.region), inTopic = !state.nt || topic === state.nt;
      if (hit) hits++;
      if (hit && inTopic) { counts['']++; regions.forEach(r => { if (r in counts) counts[r]++; }); }
      if (hit && inRegion) { topicCounts['']++; topicCounts[topic] = (topicCounts[topic] || 0) + 1; }
      const match = hit && inRegion && inTopic;
      if (match) total++;
      li.hidden = !(match && shown < newsLimit);
      if (!li.hidden) shown++;
    });
    list.querySelectorAll('.nday').forEach(d => { d.hidden = !d.querySelector('li:not([hidden])'); });
    const setCount = (b, v) => { const n = b.querySelector(`.n [data-lang="${state.lang}"]`); if (n && n.textContent !== v) n.textContent = v; };
    view.querySelectorAll('[data-region-chip]').forEach(b => setCount(b, String(counts[b.dataset.regionChip] ?? 0)));
    tchips.forEach(b => setCount(b, String(topicCounts[b.dataset.topicChip] ?? 0)));
    if (more) more.hidden = shown >= total;
    searchUi('news', terms, total, shown, counts, true, {filtered: !!(state.region || state.nt), hits});
    renderOlder('news');
  }

  function renderUae() {
    // The UAE headlines matching its search, a first few, then "Show more". The key facts below are never filtered.
    const view = $('uae'), more = $('uae-more');
    if (!view || !more) return;
    const list = view.querySelector(`.nlist[data-lang="${state.lang}"]`), items = list ? [...list.querySelectorAll('li.nitem')] : [], terms = searchWords(state.uq);
    let total = 0, shown = 0;
    items.forEach(li => {
      const hit = !terms.length || newsHit(li, terms);
      if (hit) total++;
      li.hidden = !(hit && shown < uaeLimit);
      if (!li.hidden) shown++;
    });
    if (list) list.querySelectorAll('.nday').forEach(d => { d.hidden = !d.querySelector('li:not([hidden])'); });
    more.hidden = shown >= total;
    searchUi('uae', terms, total, shown, null, !!list);
    renderOlder('uae');
  }

  // ---------- news search ----------
  // What a search reads on a card, in the language of its list: the headline, the summary shown and the publisher's name
  // (the first text of the source link without "Source:"). Never the labels, dates, region tags or image credits. Each
  // language has its own list elements, so the cache is per language.
  const cardText = new WeakMap();
  function newsText(li) {
    let t = cardText.get(li);
    if (!t) {
      const text = el => el ? el.textContent : '', src = li.querySelector('a.n-src'), first = src && src.firstChild;
      const publisher = first && first.nodeType === 3 ? first.nodeValue.replace(/^[^:]*:\s*/, '') : '';
      const norm = normText([text(li.querySelector('.n-title')), text(li.querySelector('.n-sum')), publisher].join(' '));
      t = {norm, compact: norm.replace(/ /g, '')};
      cardText.set(li, t);
    }
    return t;
  }
  const newsHit = (li, terms) => { const t = newsText(li); return matchesWords(t.norm, terms, t.compact); };
  const setText = (el, v) => { if (el && el.textContent !== v) el.textContent = v; };
  const setHtml = (el, v) => { if (el && el.innerHTML !== v) el.innerHTML = v; };
  // The search controls of one view: the (x) while the field has text, the count line (written only when it changes, so
  // the live region isn't repeated) and, when a search matches nothing, the message with "Clear search". The message never
  // repeats the query: a link can set it (?nq=, ?uq=).
  // As in the app (CountOrNoMatch), the message takes the count line's place: "No results" never sits right above a
  // message that starts with the same words («لا توجد نتائج»), and "Times in UAE time" is hidden with it. The count stays
  // the one live region and holds the message (kept for screen readers only), so it is announced once; the box under the
  // list shows it on screen (aria-hidden, so it isn't read twice) with "Clear search". "No results" is left only for a
  // search where the page language has no headlines at all, above that language's own message (as in the app).
  // `f` (AI news): whether a region or a topic is chosen, and how many headlines match the search alone. A choice of chips
  // with no headline says so too (with no "Clear search" button when nothing is searched).
  function searchUi(view, terms, total, shown, counts, hasList, f) {
    const input = $(view + '-q'), searching = terms.length > 0, filtered = !!(f && f.filtered), none = hasList && (searching || filtered) && total === 0;
    if (input) $(view + '-q-clear').hidden = !input.value;
    const count = countEl(view), m = countLabel(total, 'headline', state.lang);
    const msg = !none ? '' : T(!searching ? 'No headlines match these filters. Choose All to see every headline.'
      : view === 'news' && state.region && !state.nt && counts && counts[''] > 0 ? 'No headlines in this region match this search. Choose All to search every region.'
      : view === 'news' && filtered && f.hits > 0 ? 'No headlines match this search with these filters. Choose All to search every headline.'
      : 'No matches. Try another word or clear the search.');
    if (none) setText(count, msg);
    else if (!hasList) { if (searching) setText(count, T('No results')); else setHtml(count, builtCount[view]); }
    else if (searching) setText(count, shown < total ? F('Results: {m} · showing {n}', {m, n: shown}) : F('Results: {m}', {m}));
    else if (view === 'news') setText(count, F('Showing {n} of {m}', {n: shown, m}));
    else setHtml(count, builtCount.uae);
    if (count) {
      count.classList.toggle('sr-only', none);
      if (view === 'news' && count.nextElementSibling) count.nextElementSibling.hidden = none;  // "Times in UAE time"
    }
    const empty = $(view + '-empty');
    if (!empty) return;
    empty.hidden = !none;
    const clear = empty.querySelector('[data-clear-search]');
    if (clear) clear.hidden = !searching;
    if (none) setText($(view + '-empty-msg'), msg);
  }

  // ---------- older stories (the news archive) ----------
  // While a search is active, AI news and UAE AI offer "Search older stories": a press loads the archive's index and its
  // newest month files (dist/news-archive/, same origin, written by build.py; OLDER_MONTHS at a time, "Search earlier
  // months" for more) and lists the matches under the current results, with the same matcher (olderMatches). Loaded
  // once per page and shared by both views. The list follows the search, the language, and in AI news the region and topic.
  const OLDER_STEP = 20, OLDER_MONTHS = 3, MONTH_FILE = /^\d{4}-(0[1-9]|1[0-2])\.json$/;
  const archive = {index: null, items: [], loaded: 0, loading: null, failed: false};
  const older = {news: {open: false, limit: OLDER_STEP, key: ''}, uae: {open: false, limit: OLDER_STEP, key: ''}};
  function loadArchive(view, more) {
    if (archive.loading) return archive.loading;
    const box = $(view + '-older'), base = new URL(ROOT + (box ? box.dataset.archive : 'news-archive/index.json'), location.href);  // ROOT: from ar/, one folder up
    archive.loading = (async () => {
      try {
        if (!archive.index) {
          const r = await fetch(base.href, {credentials: 'same-origin'});
          if (!r.ok) throw new Error('index ' + r.status);
          archive.index = await r.json();
        }
        const months = (archive.index.months || []).filter(m => MONTH_FILE.test(m.file || ''));
        if (archive.loaded === 0 || more) {
          for (const m of months.slice(archive.loaded, archive.loaded + OLDER_MONTHS)) {
            const r = await fetch(new URL(m.file, base).href, {credentials: 'same-origin'});
            if (!r.ok) throw new Error('month ' + r.status);
            const doc = await r.json();
            archive.items.push(...(Array.isArray(doc.items) ? doc.items : []));
            archive.loaded++;
          }
        }
        archive.failed = false;
      } catch (e) { archive.failed = true; }
      archive.loading = null;
      older.news.key = older.uae.key = '';
    })();
    return archive.loading;
  }
  const SUMMARY_BY = {ai: {en: 'AI summary', ar: 'ملخص بالذكاء الاصطناعي'}, publisher: {en: 'From the publisher', ar: 'من الناشر'}};
  function olderCard(i) {
    // The same card as the server's (build.py news_card), without an image; text only, escaped.
    const lang = state.lang, ar = lang === 'ar', v = olderView(i, lang, archive.index && archive.index.sources), dir = `lang="${lang}" dir="${ar ? 'rtl' : 'ltr'}"`;
    const url = /^https:\/\//.test(String(i.url || '')) ? i.url : '';
    const sum = v.summary ? `<p class="n-sum" ${dir}>${esc(v.summary)}</p><p class="n-by">${esc(SUMMARY_BY[v.kind][lang])}</p>` : '';
    const link = url ? `<a class="n-src" href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(ar ? 'المصدر' : 'Source')}: ${esc(v.publisher)} <span class="n-ext" aria-hidden="true">↗</span></a>` : '';
    const icon = (document.querySelector('.share-btn svg') || {}).outerHTML || '', label = esc(T('Share this story'));
    const share = url ? `<button type="button" class="share-btn n-share" data-share="story" aria-label="${label}" title="${label}">${icon}</button>` : '';
    return `<li class="nitem older-item" data-topic="${esc(i.topic || '')}"><h4 class="n-title" ${dir}>${esc(v.title)}</h4>${sum}`
      + `<p class="n-meta">${link}<time datetime="${esc(i.published)}">${esc(day(i.published))}</time>${v.mt ? '<span class="mt">ترجمة بالذكاء الاصطناعي</span>' : ''}${share}</p></li>`;
  }
  function renderOlder(view) {
    const box = $(view + '-older');
    if (!box) return;
    const o = older[view], terms = searchWords(state[view === 'news' ? 'nq' : 'uq']);
    const btn = $(view + '-older-btn'), list = $(view + '-older-list'), count = $(view + '-older-count'), more = $(view + '-older-more'), back = $(view + '-older-back');
    box.hidden = !terms.length;
    if (!terms.length) { o.open = false; o.limit = OLDER_STEP; }
    btn.hidden = o.open;
    btn.setAttribute('aria-expanded', String(o.open));
    if (!o.open || archive.loading || archive.failed || !archive.index) {
      if (o.key) { list.innerHTML = ''; o.key = ''; }
      more.hidden = back.hidden = true;
      setText(count, !o.open ? '' : archive.failed ? T('Older stories could not be loaded. Try again later.') : T('Loading older stories…'));
      if (o.open && archive.failed) btn.hidden = false;  // a press tries again
      return;
    }
    const hits = olderMatches(archive.items, archive.index.sources, {lang: state.lang, terms, view, region: state.region, topic: state.nt});
    const shown = hits.slice(0, o.limit), key = [state.lang, terms.join(' '), state.region, state.nt, o.limit, archive.items.length].join('|');
    if (key !== o.key) { list.innerHTML = shown.map(olderCard).join(''); o.key = key; }
    setText(count, hits.length ? F('Older stories: {m}', {m: countLabel(hits.length, 'headline', state.lang)}) : T('No older stories match this search.'));
    more.hidden = shown.length >= hits.length;
    back.hidden = archive.loaded >= (archive.index.months || []).length;
  }
  async function openOlder(view, more) {
    const o = older[view];
    o.open = true;
    if (!more) o.limit = OLDER_STEP;
    const loading = loadArchive(view, more);
    renderOlder(view);
    await loading;
    renderOlder(view);
    const count = $(view + '-older-count');
    if (count && !more) { count.tabIndex = -1; count.focus({preventScroll: true}); }
  }

  // ---------- share buttons ----------
  // The phone's share sheet where the browser has one (navigator.share), else the text is copied, with a toast.
  async function shareFrom(btn) {
    // The page address without a final index.html over http(s), as the language link: /ar/#hardware/p/<id>, not /ar/index.html#….
    const kind = btn.dataset.share, here = location.href.split(/[?#]/)[0];
    const base = location.protocol === 'file:' ? here : here.replace(/(^|\/)index\.html$/, '$1');
    let title = '', url = '';
    if (kind === 'story') {
      const li = btn.closest('li'), a = li && li.querySelector('a.n-src'), h = li && li.querySelector('.n-title');
      if (!a || !h) return;
      title = h.textContent; url = a.href;
    } else if (kind === 'product') {
      const card = btn.closest('[data-product]'), p = card && byId.get(card.dataset.product);
      if (!p) return;
      title = p.model + ' · Cipher Lacuna'; url = deepLink(base, 'hardware/p/' + p.id);
    } else if (kind === 'fact') {
      const card = btn.closest('[data-fact]'), h = card && (card.querySelector(`h3 [data-lang="${state.lang}"]`) || card.querySelector('h3'));
      if (!h) return;
      title = h.textContent + ' · Cipher Lacuna'; url = deepLink(base, 'uae/f/' + card.dataset.fact);
    } else return;
    const s = sharePayload(kind, title, url, state.lang);
    if (navigator.share) {
      try { await navigator.share(kind === 'story' ? {title: s.title, text: s.text, url: s.url} : {title: s.title, url: s.url}); return; }
      catch (e) { if (e && e.name === 'AbortError') return; }  // closed by the visitor; any other failure falls back to copying
    }
    try { await navigator.clipboard.writeText(s.copy); flash(T('Link copied')); }
    catch (e) { window.prompt(T('Copy link'), s.copy); }
  }
  function searchInput(view, value) {
    const key = view === 'news' ? 'nq' : 'uq', before = searchWords(state[key]).join(' ');
    state[key] = String(value ?? '').slice(0, SEARCH_MAX);  // as typed: a trailing space is kept while typing
    const changed = searchWords(state[key]).join(' ') !== before;
    if (changed) { if (view === 'news') newsLimit = NEWS_STEP; else uaeLimit = UAE_STEP; }
    if (view === 'news') renderNews(); else renderUae();
    syncUrl();
    // With the side panel sticky (wide screens), the field stays in view while the list is scrolled: new results start
    // at the top of the list, not somewhere above the window.
    const col = changed && document.querySelector(`#${view} .main-col`), bar = document.querySelector('.top');
    if (col && bar && col.getBoundingClientRect().top < bar.getBoundingClientRect().bottom) col.scrollIntoView({block: 'start'});
  }
  // Empties a view's search. focus 'field' then puts the focus in the field; 'list' on the list's heading (after a tap on
  // "Clear search", whose box disappears: the on-screen keyboard stays closed and a screen reader keeps its place instead
  // of starting again at the top of the page); none leaves it where it is (Escape, typed in the field).
  function clearSearch(view, focus) {
    const input = $(view + '-q');
    if (!input) return;
    input.value = '';
    searchInput(view, '');
    if (focus === 'field') input.focus();
    else if (focus === 'list') {
      const h = view === 'news' ? document.querySelector('#news .main-col > h2') : $('uae-news-h');
      if (h) { h.tabIndex = -1; h.focus({preventScroll: true}); }
    }
  }

  function renderTable(n) {
    const cols = [['model','Model'],['level','Level'],['memory_gb','Memory'],['bandwidth_tbs','Bandwidth'],['power_w','Power'],['announcement','Announced / launched'],['release','Availability / target'],['price_usd','Approx. USD'],['price_usd','Approx. AED']];
    const arrow = k => state.sort === k ? (state.dir === 1 ? ' ↑' : ' ↓') : '';
    const head = cols.map(([k,l]) => `<th scope="col" aria-sort="${state.sort === k ? (state.dir === 1 ? 'ascending' : 'descending') : 'none'}"><button type="button" data-sort="${k}">${esc(T(l))}${arrow(k)}</button></th>`).join('') + (n ? `<th scope="col">${esc(T('Fit'))}</th>` : '');
    const rows = visible.map(p => {
      const s = fitStatus(p, n);
      return `<tr><td><input type="checkbox" class="cmp-toggle" value="${esc(p.id)}" aria-label="${esc(T('Compare') + ' ' + p.model)}"${state.cmp.includes(p.id) ? ' checked' : ''}></td>
      <td class="t-model"><span class="dot ${p.vendor.toLowerCase()}" aria-hidden="true"></span><a href="${esc(p.sources[0].url)}" target="_blank" rel="noopener noreferrer" lang="en">${esc(p.model)}</a><small lang="en">${esc(p.vendor)} · ${esc(p.architecture)}</small></td>
      <td>${esc(T(p.level))}<small>${esc(T(p.type))}</small></td><td class="num">${en(p.memory)}<small>${esc(T(p.memory_scope))}</small></td>
      <td class="num">${esc(bw(p))}</td><td class="num">${esc(watts(p))}</td><td class="num">${esc(p.announcement ? day(p.announcement) : T('Not established'))}</td>
      <td class="num">${esc(p.release ? day(p.release) : T('Not established'))}${kindSmall(p)}</td><td class="num">${esc(pv(p,'usd') || T('Not listed'))}<small>${esc(T(pv(p,'usd_kind') || ''))}</small></td><td class="num">${esc(pv(p,'aed') || T('Not listed'))}<small>${esc(T(pv(p,'aed_kind') || ''))}</small></td>
      ${n ? `<td><span class="fit ${s}">${esc(T(FIT[s]))}</span></td>` : ''}</tr>`;
    }).join('');
    // Focusable so the sideways scroll works from the keyboard.
    $('table-view').innerHTML = `<div class="tablewrap" tabindex="0" role="region" aria-label="${esc(T('Table'))}"><table><thead><tr><th scope="col"><span class="sr-only">${esc(T('Compare'))}</span></th>${head}</tr></thead><tbody>${rows}</tbody></table></div>`;
  }

  function renderTimeline() {
    const rows = visible.map(p => ({p, a: dateRange(p.announcement), r: dateRange(p.release)})).filter(x => x.a || x.r)
      .sort((x, y) => (x.a || x.r)[0] - (y.a || y.r)[0] || x.p.model.localeCompare(y.p.model));
    const missing = visible.length - rows.length;
    if (!rows.length) { $('timeline-view').innerHTML = `<p class="note">${esc(T('No dated milestones for these products.'))}</p>`; return; }
    const today = Date.now(), all = rows.flatMap(x => [...(x.a || []), ...(x.r || [])]);
    const y0 = new Date(Math.min(...all)).getUTCFullYear(), y1 = new Date(Math.max(...all, today)).getUTCFullYear() + 1;
    const min = Date.UTC(y0, 0, 1), max = Date.UTC(y1, 0, 1), W = 1000, L = 235, R = 16, top = 30, rowH = 26, H = top + rows.length * rowH + 12;
    const x = t => (L + (t - min) / (max - min) * (W - L - R)).toFixed(1);
    let svg = '';
    for (let y = y0; y <= y1; y++) {
      for (let q = 0; q < 4 && (y < y1 || q === 0); q++) {
        const t = Date.UTC(y, q * 3, 1);
        svg += `<line class="${q ? 'grid-q' : 'grid'}" x1="${x(t)}" x2="${x(t)}" y1="${top - 8}" y2="${H - 6}"/>`;
      }
      svg += `<text class="axis" x="${x(Date.UTC(y, 0, 1))}" y="16" text-anchor="middle">${y}</text>`;
    }
    rows.forEach(({p, a, r}, i) => {
      const cy = top + i * rowH + rowH / 2, v = p.vendor.toLowerCase();
      // Tooltips are plain text: in Arabic the Latin model name is isolated (U+2068 … U+2069) so the sentence stays right to left.
      const name = state.lang === 'ar' ? '\u2068' + p.model + '\u2069' : p.model;
      const tip = `${name} · ${T('Announced')}: ${p.announcement ? day(p.announcement) : T('Not established')} · ${T('Availability / target')}: ${p.release ? day(p.release) : T('Not established')}${releaseKind(p.release_kind) ? ` (${T(p.release_kind)})` : ''}`;
      svg += `<g class="row ${v}"><title>${esc(tip)}</title><rect class="hit" x="0" y="${cy - rowH / 2}" width="${W}" height="${rowH}"/>`;
      svg += `<text class="label" x="${L - 12}" y="${cy + 4}" text-anchor="end">${esc(p.model.length > 32 ? p.model.slice(0, 31) + '…' : p.model)}</text>`;
      if (a && r) svg += `<line class="conn" x1="${x(a[0])}" x2="${x(r[0])}" y1="${cy}" y2="${cy}"/>`;
      if (r) svg += r[0] === r[1] ? `<path class="rel" d="M${x(r[0])} ${cy - 6}l6 6-6 6-6-6z"/>` : `<rect class="rel" x="${x(r[0])}" y="${cy - 5}" width="${Math.max(6, x(r[1]) - x(r[0]))}" height="10" rx="5"/>`;
      if (a) svg += `<circle class="ann" cx="${x(a[0])}" cy="${cy}" r="5"/>`;
      svg += '</g>';
    });
    if (today >= min && today <= max) svg += `<line class="today" x1="${x(today)}" x2="${x(today)}" y1="${top - 8}" y2="${H - 6}"/><text class="today-label" x="${x(today)}" y="${H - 1}" text-anchor="middle">${esc(T('Today'))}</text>`;
    $('timeline-view').innerHTML = `<p class="tl-legend"><span class="key ann-key"></span>${esc(T('Announced'))}<span class="key rel-key"></span>${esc(T('Availability / target'))}<span class="key nv-key"></span>NVIDIA<span class="key amd-key"></span>AMD</p>
      <div class="tl-scroll" dir="ltr" tabindex="0" role="region" aria-label="${esc(T('Timeline'))}"><svg class="tl" viewBox="0 0 ${W} ${H + 6}" role="img" aria-label="${esc(T('Timeline'))}">${svg}</svg></div>
      <p class="tl-note">${esc(T('Hollow circle: announcement. Solid mark: availability or vendor target. Bars show quarter, half-year or seasonal windows.'))}${missing ? ' ' + esc(F('Without a dated milestone: {p}.', {p: countLabel(missing, 'product', state.lang)})) : ''}</p>`;
  }

  function renderTray() {
    $('tray').hidden = state.cmp.length === 0;
    $('tray-count').textContent = F('{n} selected', {n: state.cmp.length});
    $('tray-items').innerHTML = state.cmp.map(id => `<button type="button" class="chip" data-remove="${esc(id)}" aria-label="${esc(T('Remove') + ' ' + byId.get(id).model)}">${esc(byId.get(id).model)} ×</button>`).join('');
    $('compare-open').disabled = state.cmp.length < 2;
    trayRoom();
  }
  function trayRoom() {
    // Keyboard focus and scrolled-to targets stop above the fixed tray (scroll-padding-bottom in style.css).
    const h = $('tray').getBoundingClientRect().height;
    document.documentElement.style.setProperty('--tray-h', h ? Math.ceil(h + 14) + 'px' : '0px');
  }
  function toggleCompare(id, on, box) {
    if (on && !state.cmp.includes(id)) {
      if (state.cmp.length >= 4) { if (box) box.checked = false; flash(T('Compare up to 4 products')); return; }
      state.cmp.push(id);
    }
    if (!on) state.cmp = state.cmp.filter(x => x !== id);
    render();
  }
  function flash(text) {
    const el = $('toast'); el.textContent = text; el.hidden = false;
    clearTimeout(flash.t); flash.t = setTimeout(() => { el.hidden = true; }, 2600);
  }
  function openCompare() {
    const ps = state.cmp.map(id => byId.get(id));
    const sameScope = new Set(ps.map(p => p.memory_scope)).size === 1;
    const best = k => { const vals = ps.map(p => p[k]).filter(v => v != null); return sameScope && vals.length > 1 ? Math.max(...vals) : null; };
    const bestMem = best('memory_gb'), bestBw = best('bandwidth_tbs');
    // English-only data values carry lang="en" so screen readers don't read them with Arabic pronunciation.
    const value = v => v == null || v === '' ? esc(T('Not listed')) : en(v);
    const rows = [
      ['Vendor', p => esc(p.vendor) + (p.maker ? `<small>${esc(T('Built by'))} <span lang="en">${esc(p.maker)}</span></small>` : '')], ['Level', p => esc(T(p.level)) + ' / ' + esc(T(p.type))], ['Architecture', p => en(p.architecture)],
      ['Memory', p => `<span class="${p.memory_gb === bestMem ? 'best' : ''}" lang="en">${esc(p.memory)}</span>`], ['Memory scope', p => esc(T(p.memory_scope))],
      ['Bandwidth', p => `<span class="${p.bandwidth_tbs != null && p.bandwidth_tbs === bestBw ? 'best' : ''}">${esc(bw(p))}</span>${p.bandwidth_note ? `<small lang="en">${esc(p.bandwidth_note)}</small>` : ''}`],
      ['AI compute', p => value(p.ai_compute)], ['Power', p => esc(watts(p))],
      ['Announced / launched', p => esc(p.announcement ? day(p.announcement) : T('Not established'))],
      ['Availability / target', p => `${esc(p.release ? day(p.release) : T('Not established'))}${kindSmall(p)}`],
      ['Launch price', p => esc(price(p))],
      ['Approx. price', p => p.price_view ? `${esc(pv(p,'usd') || T('Not listed'))}<small>${esc(T(pv(p,'usd_kind') || ''))}</small>${esc(pv(p,'aed') || T('Not listed'))}<small>${esc(T(pv(p,'aed_kind') || ''))} · ${esc(T('checked'))} ${esc(day(pv(p,'checked') || ''))}</small>` : esc(T('Not publicly priced'))], ['Form factor', p => value(p.form_factor)], ['Cooling', p => esc(orNA(p.cooling))], ['Interconnect', p => value(p.interconnect)],
      ['Best fit', p => esc(state.lang === 'ar' && p.use_ar ? p.use_ar : p.use)],
      ['Official source', p => p.sources.map(s => `<a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer" lang="en">${esc(s.label)}</a>`).join('<br>')]
    ];
    $('compare-body').innerHTML = `<div class="tablewrap" tabindex="0" role="region" aria-label="${esc(T('Side-by-side comparison'))}"><table class="cmp-table"><thead><tr><th scope="col"><span class="sr-only">${esc(T('Specification'))}</span></th>${ps.map(p => `<th scope="col" class="${p.vendor.toLowerCase()}">${p.image && p.image.file ? `<img src="${esc(ROOT + p.image.file)}" alt="" loading="lazy">` : ''}<span lang="en">${esc(p.model)}</span></th>`).join('')}</tr></thead>
      <tbody>${rows.map(([l, f]) => `<tr><th scope="row">${esc(T(l))}</th>${ps.map(p => `<td>${f(p)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>
      <p class="tl-note">${esc(T(sameScope ? 'Highlighted: highest value among products with the same memory scope.' : 'Memory scopes differ, so totals are not directly comparable.'))}</p>`;
    const dlg = $('compare-dlg');
    if (dlg.open) return;
    if (dlg.showModal) dlg.showModal(); else dlg.setAttribute('open', '');
  }
  function closeCompare() { const d = $('compare-dlg'); if (d.close) d.close(); else d.removeAttribute('open'); }

  // ---------- views ----------
  function show(view) {
    currentView = view;
    document.documentElement.dataset.route = view;
    document.querySelectorAll('[data-view]').forEach(el => { el.hidden = el.dataset.view !== view; });
    document.querySelectorAll('[data-nav]').forEach(a => { if (a.dataset.nav === view) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current'); });
    setTitle();
  }
  function syncFromUrl() {
    // Back/forward can land on an entry with different filters: the URL wins, except the language, which is a preference.
    const s = decodeState(location.search);
    s.lang = state.lang;
    // The compare selection is a basket: an entry without cmp (for example #home) doesn't empty it.
    s.cmp = new URLSearchParams(location.search).has('cmp') ? s.cmp.filter(id => byId.has(id)) : state.cmp;
    if (s.model && !findModel(s.model)) s.model = '';
    sizeFromModel(s);
    if (encodeState(s) === encodeState(state)) return;
    if (s.region !== state.region || s.nt !== state.nt) newsLimit = NEWS_STEP;
    // Paging restarts only when the search words change, not when another parameter does.
    const same = k => searchWords(s[k]).join(' ') === searchWords(state[k]).join(' ');
    if (!same('nq')) newsLimit = NEWS_STEP;
    if (!same('uq')) uaeLimit = UAE_STEP;
    Object.assign(state, s);
    writeControls();
  }
  function highlight(el) {
    document.querySelectorAll('.flash').forEach(x => x.classList.remove('flash'));
    el.classList.add('flash');
    clearTimeout(highlight.t); highlight.t = setTimeout(() => el.classList.remove('flash'), 3000);
  }
  function route(first) {
    syncFromUrl();
    const r = parseRoute(location.hash, location.search), {patch, focus, hash} = routePatch(r, known);
    currentDeep = hash.includes('/') ? hash.slice(hash.indexOf('/') + 1) : '';
    if (Object.keys(patch).length) {
      if ('region' in patch && patch.region !== state.region) newsLimit = NEWS_STEP;
      Object.assign(state, patch);
      writeControls();
    }
    // Back while the comparison is open (the usual way to dismiss it on a phone) closes it with the view change.
    if ($('compare-dlg').open && focus !== 'compare') closeCompare();
    show(r.view);
    render();
    const seq = ++routeSeq;
    afterBrowser(() => { if (seq === routeSeq) land(r.view, focus, first); });
  }
  function afterBrowser(fn) {
    // Scrolling and focus wait for the browser's own fragment handling, which would otherwise undo them: on a fresh page
    // it scrolls to the hash target at the load event; in the app it focuses and scrolls to section#<view> after popstate.
    const run = () => requestAnimationFrame(() => setTimeout(fn, 0));
    if (document.readyState === 'complete') run(); else window.addEventListener('load', run, {once: true});
  }
  function land(view, focus, first) {
    if (focus === 'compare') {
      window.scrollTo(0, 0);
      if (state.cmp.length >= 2) openCompare();
      else flash(T('Tick "Compare" on 2 to 4 products to compare them side by side.'));
      return;
    }
    const target = focus ? $(focus) : null;
    if (target) {
      // Top of the card (image, vendor, title) just below the sticky header: scroll-padding-top in style.css.
      target.scrollIntoView({block: 'start'});
      if (focus === 'estimator') $('model').focus({preventScroll: true});
      else { highlight(target); target.setAttribute('tabindex', '-1'); target.focus({preventScroll: true}); }
      return;
    }
    if (first) return;  // a fresh page keeps the browser's position (the top, or where a reload left it)
    window.scrollTo(0, 0);
    const h = document.querySelector(`[data-view="${view}"] h1`);
    if (h) h.focus({preventScroll: true});
  }
  function onNavigate() { if (location.href !== lastHref) route(false); }

  ['search','params','extra'].forEach(id => $(id).addEventListener('input', () => { readControls(); render(); }));
  function modelInput() {
    const value = $('model').value.trim(), m = findModel(value);
    if (!value) { state.model = ''; render(); return; }
    if (!m) return;  // still typing
    state.model = m.n;
    // Closed, chat-only or unsized models must not leave an earlier model's size (and fit badges) behind.
    $('params').value = fittable(m) ? String(m.b) : '';
    readControls();
    render();
  }
  $('model').addEventListener('input', modelInput);
  // A model picked from the search card: the search is cleared (the products come back) and the estimator takes the
  // model exactly as if it had been chosen in its own field, then comes into view with the field focused.
  function pickModel(name) {
    const m = findModel(name);
    if (!m) return;
    state.q = '';
    $('search').value = '';
    mh.open = mh.all = false;
    $('model').value = m.n;
    modelInput();
    land(currentView, 'estimator');
    highlight($('estimator'));
  }
  ['mh-list', 'myhw-list'].forEach(id => $(id).addEventListener('click', e => { const b = e.target.closest('[data-pick]'); if (b) pickModel(b.dataset.pick); }));
  $('model-ar').addEventListener('click', () => { state.arabic = !state.arabic; render(); });
  $('myhw-sel').addEventListener('change', () => setMyHw($('myhw-sel').value));
  $('myhw-clear').addEventListener('click', () => { setMyHw('', true); $('myhw-sel').focus(); });
  $('myhw-more').addEventListener('click', () => { myhwAll = !myhwAll; renderMyHw(need()); });
  $('mh-toggle').addEventListener('click', () => { mh.open = !mh.open; renderModelHits(); });
  $('mh-more').addEventListener('click', () => { mh.all = !mh.all; renderModelHits(); });
  $('params').addEventListener('input', () => {
    // A hand-typed size no longer describes the picked model.
    const m = findModel(state.model);
    if (m && Number($('params').value) !== m.b) { state.model = ''; $('model').value = ''; render(); }
  });
  ['vendor','level','scope','bits','fit-only'].forEach(id => $(id).addEventListener('change', () => { readControls(); render(); }));
  $('sort').addEventListener('change', () => { state.sort = $('sort').value; render(); });
  $('direction').addEventListener('click', () => { state.dir *= -1; render(); });
  $('reset').addEventListener('click', () => { Object.assign(state, {...DEFAULTS, cmp: state.cmp, lang: state.lang, view: state.view, region: state.region, nq: state.nq, uq: state.uq, nt: state.nt}); writeControls(); render(); });
  ['cards','table','timeline'].forEach(v => $('view-' + v).addEventListener('click', () => { state.view = v; render(); }));
  document.querySelectorAll('[data-params]').forEach(b => b.addEventListener('click', () => { $('params').value = b.dataset.params; readControls(); render(); }));
  document.addEventListener('change', e => { if (e.target.classList.contains('cmp-toggle')) toggleCompare(e.target.value, e.target.checked, e.target); });
  document.addEventListener('click', e => {
    const s = e.target.closest('[data-sort]');
    if (s) { if (state.sort === s.dataset.sort) state.dir *= -1; else { state.sort = s.dataset.sort; state.dir = 1; } $('sort').value = state.sort; render(); }
    // Hardware tags on UAE facts: filter first (and record it in the URL), then the link opens #hardware.
    const chip = e.target.closest('[data-q]');
    if (chip) { Object.assign(state, {q: chip.dataset.q, vendor: '', level: '', scope: '', fit: false, view: 'cards'}); writeControls(); syncUrl(); }
    const r = e.target.closest('[data-remove]');
    if (r) toggleCompare(r.dataset.remove, false);
    // "My hardware" on a product card: pressing it again clears it.
    const mb = e.target.closest('[data-myhw]');
    if (mb) setMyHw(mb.dataset.myhw === myhw ? '' : mb.dataset.myhw, true);
    const rc = e.target.closest('[data-region-chip]');
    if (rc) { state.region = rc.dataset.regionChip; newsLimit = NEWS_STEP; render(); }
    const tc = e.target.closest('[data-topic-chip]');
    if (tc) { state.nt = tc.dataset.topicChip; newsLimit = NEWS_STEP; render(); }
    const sh = e.target.closest('[data-share]');
    if (sh) shareFrom(sh);
    const ob = e.target.closest('[data-older]');
    if (ob) openOlder(ob.dataset.older);
    // The (x) in a news search field and the "Clear search" button under a search without results. The (x) keeps the
    // focus in the field (pressing it never takes the focus, see below; from the keyboard it gives it back). The button
    // gives the focus to the field from the keyboard or a mouse (e.detail 0 is a keyboard click); after a tap it goes to
    // the list's heading, since focusing the field would open the on-screen keyboard over the list that just came back.
    const cs = e.target.closest('[data-clear-search]');
    if (cs) clearSearch(cs.dataset.clearSearch, cs.classList.contains('q-clear') || e.detail === 0 || matchMedia('(pointer: fine)').matches ? 'field' : 'list');
  });
  $('news-more') && $('news-more').addEventListener('click', () => { newsLimit += NEWS_STEP; renderNews(); });
  $('uae-more') && $('uae-more').addEventListener('click', () => { uaeLimit += UAE_STEP; renderUae(); });
  ['news', 'uae'].forEach(view => {
    const more = $(view + '-older-more'), back = $(view + '-older-back');
    if (more) more.addEventListener('click', () => { older[view].limit += OLDER_STEP; renderOlder(view); });
    if (back) back.addEventListener('click', () => openOlder(view, true));
  });
  ['news', 'uae'].forEach(view => {
    const input = $(view + '-q');
    if (!input) return;
    input.addEventListener('input', () => searchInput(view, input.value));
    // Pressing the (x) with a mouse, a finger or a pen doesn't move the focus out of the field, so a phone keyboard
    // doesn't close and reopen and a screen reader doesn't announce the field again; its click then empties the field.
    ['pointerdown', 'mousedown'].forEach(t => $(view + '-q-clear').addEventListener(t, e => e.preventDefault()));
    input.addEventListener('keydown', e => {
      // Escape empties a field that has text and keeps the focus; Enter only closes the on-screen keyboard (results are live).
      if (e.key === 'Escape' && input.value) { e.preventDefault(); clearSearch(view); }
      else if (e.key === 'Enter') { e.preventDefault(); if (matchMedia('(pointer: coarse)').matches) input.blur(); }
    });
  });
  $('skip').addEventListener('click', e => {
    e.preventDefault();
    const h = document.querySelector(`[data-view="${currentView}"] h1`);
    if (h) h.focus();
  });
  $('compare-open').addEventListener('click', openCompare);
  $('compare-clear').addEventListener('click', () => { state.cmp = []; render(); });
  $('compare-close').addEventListener('click', closeCompare);
  // The language link opens the same view with the same filters on the other language's page (syncUrl keeps its href);
  // the choice is saved, so the English page sends a later visit to the Arabic one and back.
  langLink.addEventListener('click', () => store.set('atlas-lang', PAGE_LANG === 'ar' ? 'en' : 'ar'));
  $('theme').addEventListener('click', () => { theme = {auto:'light', light:'dark', dark:'auto'}[theme]; store.set('atlas-theme', theme); applyTheme(); });
  $('share').addEventListener('click', async () => {
    // The shared link always names the view, even when the address bar has no hash.
    syncUrl();
    const link = shareUrl();
    try { await navigator.clipboard.writeText(link); flash(T('Link copied')); }
    catch (e) { window.prompt(T('Copy link'), link); }
  });
  $('print').addEventListener('click', () => { state.view = 'table'; render(); window.print(); });
  // Contact: the address is assembled here so it isn't sitting in the page source for scrapers
  // (without JavaScript the page shows "buafra [at] gmail [dot] com").
  const contactAddress = ['buafra', 'gmail.com'].join('@');
  $('c-mail').href = 'mailto:' + contactAddress;
  $('c-mail').textContent = contactAddress;
  $('csv').addEventListener('click', () => {
    const cols = ['vendor','maker','model','level','type','architecture','memory','memory_gb','memory_scope','bandwidth_tbs','ai_compute','power_w','power_note','msrp_usd','price_usd_range','price_aed_range','price_checked','form_factor','cooling','interconnect','announcement','release','release_kind','use','source_reviewed'];
    const cell = v => '"' + String(v ?? '').replaceAll('"', '""') + '"';
    const csv = [cols.join(','), ...visible.map(p => cols.map(k => cell(k === 'price_usd_range' ? pv(p,'usd') : k === 'price_aed_range' ? pv(p,'aed') : k === 'price_checked' ? pv(p,'checked') : p[k])).join(','))].join('\r\n');
    const url = URL.createObjectURL(new Blob(['﻿' + csv], {type: 'text/csv;charset=utf-8'}));
    const a = document.createElement('a'); a.href = url; a.download = 'ai-hardware-atlas.csv'; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  // Deep links only with JavaScript: without it these stay plain in-page anchors (#hardware, #p-<id>, #fact-<id>).
  document.querySelectorAll('a[data-route]').forEach(a => a.setAttribute('href', '#' + a.dataset.route));
  window.addEventListener('hashchange', onNavigate);
  window.addEventListener('popstate', onNavigate);
  window.addEventListener('resize', trayRoom);
  // After the load event (and the browser's scroll to the hash), the address can take its canonical form.
  if (!booted) window.addEventListener('load', () => requestAnimationFrame(() => setTimeout(() => { booted = true; syncUrl(); }, 0)), {once: true});
  if (state.model && !findModel(state.model)) state.model = '';
  sizeFromModel(state);
  writeControls();
  applyLang();
  fillModelList();
  fillMyHwSelect();
  route(true);
})(typeof window !== 'undefined' ? window : {});
