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
  function select(products, filters, key, direction) {
    const q = (filters.q || '').trim().toLowerCase();
    const result = products.filter(p => (!filters.vendor || p.vendor === filters.vendor) && (!filters.level || p.level === filters.level) && (!filters.scope || p.memory_scope === filters.scope) && (!filters.fitOnly || !filters.need || fitStatus(p, filters.need) !== 'no') && (!q || [p.model,p.vendor,p.level,p.type,p.architecture,p.memory,p.use,p.use_ar,p.notes,p.release,p.announcement,p.interconnect,p.form_factor,p.ai_compute].join(' ').toLowerCase().includes(q)));
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
  const DEFAULTS = {q:'',vendor:'',level:'',scope:'',sort:'level',dir:1,view:'cards',cmp:[],lang:'en',params:'',bits:'4',extra:'20',fit:false,model:'',region:''};
  const PARAMS = {q:'q',vendor:'vendor',level:'level',scope:'scope',sort:'sort',dir:'dir',view:'view',cmp:'cmp',lang:'lang',params:'p',bits:'bits',extra:'extra',fit:'fit',model:'m',region:'region'};
  function encodeState(state) {
    const qs = new URLSearchParams();
    Object.keys(PARAMS).forEach(k => {
      const v = k === 'cmp' ? (state.cmp || []).join(',') : k === 'dir' ? (state.dir === -1 ? 'desc' : '') : k === 'fit' ? (state.fit ? '1' : '') : String(state[k] ?? '');
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
      else if (k === 'fit') s.fit = v === '1';
      else s[k] = v;
    });
    if (!['cards','table','timeline'].includes(s.view)) s.view = 'cards';
    if (!['en','ar'].includes(s.lang)) s.lang = 'en';
    if (!['global','uae'].includes(s.region)) s.region = '';
    return s;
  }
  // Views live in the hash (#home, #hardware, #news, #uae, #contact); filters stay in the query string.
  // Deep links such as #hardware/level/Personal or #uae/f/<id> are applied once, then the hash is reduced to the view.
  const VIEWS = ['home','hardware','news','uae','contact'];
  const SUBS = {hardware: ['cards','table','timeline','compare','run','level','vendor','p'], news: ['all','global','uae'], uae: ['f']};
  const WITH_ARG = ['level','vendor','p','f'];
  // Links shared before the views existed carry only a query string (?q=4090, ?cmp=…): they belong to the hardware atlas.
  // The head script in template.html repeats this list so the first paint already shows the right view.
  const HW_KEYS = ['q','vendor','level','scope','sort','dir','view','cmp','p','bits','extra','fit','m'];
  function impliedView(search) {
    let qs;
    try { qs = new URLSearchParams(search || ''); } catch (e) { return 'home'; }
    if (HW_KEYS.some(k => qs.has(k))) return 'hardware';
    return qs.has('region') ? 'news' : 'home';
  }
  function parseRoute(hash, search) {
    let h = String(hash || '').replace(/^#/, '');
    try { h = decodeURIComponent(h); } catch (e) {}
    // Plain element ids used as no-JavaScript fallbacks (#p-<product>, #fact-<id>, #estimator) map onto their view.
    let m = /^p-(.+)$/.exec(h);
    if (m) return {view: 'hardware', sub: 'p', arg: m[1]};
    m = /^fact-(.+)$/.exec(h);
    if (m) return {view: 'uae', sub: 'f', arg: m[1]};
    if (h === 'estimator') return {view: 'hardware', sub: 'run', arg: ''};
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
      else if (route.sub === 'p' && has(known.products, route.arg)) { out.patch = {...clear, view: 'cards'}; out.focus = 'p-' + route.arg; }
      else if (route.sub === 'run') out.focus = 'estimator';
      else if (route.sub === 'compare') out.focus = 'compare';
    } else if (route.view === 'news' && route.sub) {
      out.patch = {region: route.sub === 'all' ? '' : route.sub};
    } else if (route.view === 'uae' && route.sub === 'f' && has(known.facts, route.arg)) {
      out.focus = 'fact-' + route.arg;
    }
    return out;
  }
  // An empty view keeps the URL without a hash.
  function pageUrl(path, qs, view) { return (path || '') + (qs ? '?' + qs : '') + (view ? '#' + view : ''); }
  const NOUNS = {
    product: {en: ['product', 'products'], ar: ['منتج واحد', 'منتجان', 'منتجات', 'منتجًا', 'منتج']},
    headline: {en: ['headline', 'headlines'], ar: ['عنوان واحد', 'عنوانان', 'عناوين', 'عنوانًا', 'عنوان']},
    token: {en: ['token', 'tokens'], ar: ['رمز واحد', 'رمزان', 'رموز', 'رمزًا', 'رمز']}
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
  if (typeof module !== 'undefined') module.exports = {select,dateNumber,dateRange,estimateGB,fitStatus,encodeState,decodeState,parseRoute,routePatch,pageUrl,countLabel,when,HW_KEYS};
  if (!root.document) return;

  const AR = {
    'NVIDIA + AMD / AI infrastructure':'NVIDIA + AMD / بنية الذكاء الاصطناعي التحتية','AI Hardware Atlas':'أطلس عتاد الذكاء الاصطناعي',
    'Compare GPUs, desktop systems, servers and racks.':'قارن معالجات الرسوميات والأجهزة المكتبية والخوادم والرفوف.',
    'One-page PDF':'ملف PDF من صفحة واحدة','Export CSV':'تصدير CSV','Copy link':'نسخ الرابط','Link copied':'تم نسخ الرابط','Print table':'طباعة الجدول',
    'Theme: Auto':'المظهر: تلقائي','Theme: Light':'المظهر: فاتح','Theme: Dark':'المظهر: داكن','Auto':'تلقائي','Light':'فاتح','Dark':'داكن',
    'Content updated:':'آخر تحديث للمحتوى:','Source check:':'آخر فحص للمصادر:','Schedule:':'الجدولة:','Prices checked:':'آخر تحقق من الأسعار:','Not run yet':'لم يُشغَّل بعد',
    '07:15 and 19:15 Asia/Dubai':'7:15 و19:15 بتوقيت الإمارات','Configured in GitHub Actions':'مُجدولة عبر GitHub Actions',
    'Search':'بحث','Vendor':'الشركة','Level':'المستوى','Memory scope':'نطاق الذاكرة','Model, memory, architecture…':'الطراز، الذاكرة، المعمارية…',
    'All levels':'كل المستويات','All memory scopes':'كل نطاقات الذاكرة',
    'Personal':'شخصي','Workstation':'محطة عمل','Enterprise':'مؤسسات','Data center':'مراكز البيانات','Rack scale':'على مستوى الرف',
    'Per GPU':'لكل معالج رسوميات','Shared CPU + GPU':'مشتركة بين المعالج والرسوميات','System total':'إجمالي النظام','Rack total':'إجمالي الرف',
    'GPU':'معالج رسوميات','System':'نظام','Platform':'منصة','Server class':'فئة خادم','Rack':'رف','Reference design':'تصميم مرجعي',
    'Expected':'متوقع','Generally available':'متاح للجميع','Not established':'غير محدد','Orders opened':'فُتح باب الطلب','Partner rollout':'طرح عبر الشركاء',
    'Partner rollout expected':'طرح متوقع عبر الشركاء','Released':'صدر','Standalone cards':'بطاقات منفصلة','Vendor availability window':'فترة توفر معلنة',
    'Vendor distribution window':'فترة توزيع معلنة','Vendor target (summer 2025)':'هدف الشركة (صيف 2025)','Volume expected':'إنتاج كمي متوقع',
    'Sort by':'ترتيب حسب','Hardware level':'مستوى العتاد','Model name':'اسم الطراز','Memory capacity':'سعة الذاكرة','Memory bandwidth':'عرض نطاق الذاكرة',
    'Launch price':'سعر الإطلاق','Availability date':'تاريخ التوفر','Announcement date':'تاريخ الإعلان','Power rating':'استهلاك الطاقة',
    'Ascending ↑':'تصاعدي ↑','Descending ↓':'تنازلي ↓','Reset':'إعادة ضبط','Cards':'بطاقات','Table':'جدول','Timeline':'خط زمني','View':'العرض',
    '{n} of {m}':'{n} من أصل {m}','No matches. Try another search or reset the filters.':'لا توجد نتائج. جرّب بحثًا آخر أو أعد ضبط الفلاتر.',
    'Availability / target':'التوفر / الهدف','Announced / launched':'الإعلان / الإطلاق','Power':'الطاقة','Bandwidth':'عرض النطاق','AI compute':'حوسبة الذكاء الاصطناعي',
    'Form factor':'الشكل','Cooling':'التبريد','Interconnect':'الربط','Content reviewed':'تاريخ مراجعة المحتوى','Notes and official sources':'ملاحظات ومصادر رسمية',
    'Not listed':'غير مذكور','Not documented in this edition':'غير موثق في هذه النسخة','Compare':'قارن','Model':'الطراز','Memory':'الذاكرة','Type':'النوع',
    'Architecture':'المعمارية','Best fit':'الاستخدام الأنسب','Official source':'المصدر الرسمي','Fit':'الملاءمة',
    'What can it run?':'ما النماذج التي يشغّلها؟','Model size (billions of parameters)':'حجم النموذج (مليار مُعامل)','Precision':'الدقة',
    '16-bit (FP16 / BF16)':'16 بت (FP16 / BF16)','8-bit (FP8 / INT8)':'8 بت (FP8 / INT8)','4-bit (quantized)':'4 بت (مضغوط)',
    'Extra for context and runtime (%)':'إضافة للسياق والتشغيل (%)','Only show hardware that fits':'اعرض العتاد الذي يتسع فقط','Presets':'قيم جاهزة',
    'Needs about {x} GB':'يحتاج تقريبًا {x} جيجابايت','Enter a model size to highlight hardware that fits.':'أدخل حجم النموذج لتمييز العتاد الذي يتسع له.',
    'Rough guide: weights at the chosen precision plus the extra you set. Long contexts, batching and training need much more. Shared memory also serves the operating system, and multi-GPU totals need software that splits the model.':'تقدير تقريبي: الأوزان بالدقة المختارة مع النسبة الإضافية المحددة. السياقات الطويلة والدفعات والتدريب تحتاج أكثر بكثير. الذاكرة المشتركة يستخدمها نظام التشغيل أيضًا، والإجماليات متعددة المعالجات تحتاج برمجيات تقسّم النموذج.',
    'Fits':'يتسع','Fits across GPUs':'يتسع عبر عدة معالجات','Too small':'لا يتسع',
    '{n} selected':'المحدد: {n}','Clear':'مسح','Close':'إغلاق','Compare up to 4 products':'يمكن مقارنة 4 منتجات كحد أقصى','Remove':'إزالة',
    'Tick "Compare" on 2 to 4 products to compare them side by side.':'اختر «قارن» في منتجين إلى 4 منتجات لمقارنتها جنبًا إلى جنب.',
    'Side-by-side comparison':'مقارنة جنبًا إلى جنب','Memory scopes differ, so totals are not directly comparable.':'نطاقات الذاكرة مختلفة، لذا لا تُقارن الإجماليات مباشرة.',
    'Highlighted: highest value among products with the same memory scope.':'المميَّز: أعلى قيمة بين منتجات لها نطاق الذاكرة نفسه.',
    'Announced':'أُعلن','Today':'اليوم','No dated milestones for these products.':'لا توجد تواريخ لهذه المنتجات.',
    'Hollow circle: announcement. Solid mark: availability or vendor target. Bars show quarter, half-year or seasonal windows.':'الدائرة المفرغة: الإعلان. العلامة المصمتة: التوفر أو هدف الشركة. الأشرطة تمثل فترات ربع سنوية أو نصف سنوية أو موسمية.',
    'Without a dated milestone: {p}.':'بلا تاريخ محدد: {p}.',
    'How to read this':'كيف تقرأ هذه البيانات','Products':'المنتجات','Hardware catalog':'كتالوج العتاد','Filter hardware':'تصفية العتاد','Download and share':'التنزيل والمشاركة',
    'Capacity is not speed':'السعة ليست السرعة','Memory capacity determines what can fit. Bandwidth, compute, precision and software influence how quickly it runs. Sorting by memory is not a performance ranking.':'سعة الذاكرة تحدد ما يمكن أن يتسع. أما سرعة التشغيل فتتأثر بعرض النطاق والحوسبة والدقة والبرمجيات. الترتيب حسب الذاكرة ليس ترتيبًا للأداء.',
    'Compare the same scope':'قارن النطاق نفسه','A single GPU, shared CPU/GPU system, and rack total are different measurements. Multiple GPUs do not automatically expose one shared VRAM pool.':'معالج رسوميات واحد، ونظام بذاكرة مشتركة، وإجمالي رف كامل هي قياسات مختلفة. تعدد معالجات الرسوميات لا يعني تلقائيًا ذاكرة واحدة مشتركة.',
    'Dates have different meanings':'للتواريخ معانٍ مختلفة','An announcement does not establish first shipment. Vendor targets remain labeled as targets until a release or availability statement is verified. Unknown values stay blank.':'الإعلان لا يعني بدء الشحن. تبقى أهداف الشركات موسومة كأهداف حتى يتم التحقق من الإصدار أو التوفر. القيم غير المعروفة تبقى فارغة.',
    'What changed':'ما الذي تغيّر','Contact':'تواصل معنا','Questions, corrections or partnership ideas? Send a message.':'أسئلة أو تصحيحات أو أفكار للتعاون؟ أرسل رسالة.',
    'Your name (optional)':'اسمك (اختياري)','Your email (optional)':'بريدك الإلكتروني (اختياري)','Subject':'الموضوع','Message':'الرسالة','Send message':'إرسال الرسالة',
    'Opens your email app with the message ready to send, or write to':'يفتح تطبيق البريد لديك والرسالة جاهزة للإرسال، أو راسلنا على',
    'Please add a subject and a message.':'يرجى إضافة الموضوع والرسالة.','Opening your email app…':'جارٍ فتح تطبيق البريد…',
    'All rights reserved.':'جميع الحقوق محفوظة.','Product images © NVIDIA and AMD. Headlines © their publishers and link to the original articles.':'صور المنتجات © NVIDIA وAMD. العناوين © لناشريها وترتبط بالمقالات الأصلية.','Pick a model from OpenRouter':'اختر نموذجًا من OpenRouter','size not published':'الحجم غير منشور','closed · cloud only':'مغلق · سحابي فقط',
    "{name} is a closed model: its weights are not public, so it runs only in the provider's cloud (for example through OpenRouter). No hardware on this page can run it locally.":'{name} نموذج مغلق: أوزانه غير منشورة، لذا يعمل فقط في سحابة المزوّد (مثلًا عبر OpenRouter). لا يمكن لأي عتاد في هذه الصفحة تشغيله محليًا.',
    '{name} is open-weight, but its size is not published in a form we can verify. Enter the size manually.':'{name} مفتوح الأوزان، لكن حجمه غير منشور بصيغة يمكننا التحقق منها. أدخل الحجم يدويًا.',
    '{name}: {b} billion parameters':'{name}: {b} مليار مُعامل','size taken from the model name':'الحجم مأخوذ من اسم النموذج','counted from Hugging Face weights':'محسوب من أوزان Hugging Face',
    'mixture-of-experts: all experts must fit in memory':'نموذج خبراء متعددين (MoE): يجب أن تتسع الذاكرة لكل الخبراء','context up to {c}':'سياق حتى {c}',
    'Choose from {n} models listed on OpenRouter (list updated {d}), or enter a size below.':'اختر من {n} نموذجًا مدرجًا على OpenRouter (آخر تحديث للقائمة {d})، أو أدخل الحجم أدناه.','Hardware':'العتاد','AI news':'أخبار الذكاء الاصطناعي','UAE AI':'الذكاء الاصطناعي في الإمارات','News sources':'مصادر الأخبار',
    'UAE AI headlines':'عناوين الذكاء الاصطناعي في الإمارات','As of':'بتاريخ','Headlines appear after the first scheduled update.':'تظهر العناوين بعد أول تحديث مجدول.',
    'Follow Qahwa & AI on Instagram':'تابع قهوة و AI على إنستغرام','Image:':'الصورة:','Approx. price':'السعر التقريبي','checked':'تم التحقق في','Not publicly priced':'لا يوجد سعر معلن',
    'US retail':'متاجر أمريكية','US used market':'سوق المستعمل الأمريكي','UAE used market':'سوق المستعمل في الإمارات','Ada Lovelace':'Ada Lovelace','UAE retail':'متاجر الإمارات','Reported estimate':'تقدير منشور','Converted from USD at 3.6725':'محوّل من الدولار بسعر 3.6725','Approx. USD':'تقريبي بالدولار','Approx. AED':'تقريبي بالدرهم','Air':'هوائي','Liquid':'سائل','Air or liquid':'هوائي أو سائل',
    'Reference total graphics power':'الطاقة الإجمالية المرجعية للرسوميات','Official specification, checked automatically':'مواصفة رسمية يُتحقق منها تلقائيًا','Accelerator rating; excludes host':'تصنيف المسرّع، دون النظام المضيف','Total board power':'إجمالي طاقة البطاقة','Workstation Edition maximum':'الحد الأقصى لإصدار محطة العمل',
    // Site shell and the three-pillar hub
    'Skip to content':'انتقل إلى المحتوى','Main sections':'الأقسام الرئيسية','Overview':'الرئيسية','News':'الأخبار','UAE':'الإمارات',
    'Breadcrumb':'مسار التنقل','Back to overview':'العودة إلى الرئيسية','Other areas':'الأقسام الأخرى','Footer':'تذييل الصفحة',
    'AI Hardware Atlas, AI news and UAE AI':'عتاد الذكاء الاصطناعي وأخباره وحضوره في الإمارات',
    'Compare NVIDIA and AMD AI hardware, catch up on the latest AI news, and follow what the UAE is building — with sources and dates shown throughout.':'قارن عتاد الذكاء الاصطناعي من NVIDIA وAMD، وتابع آخر أخبار الذكاء الاصطناعي، واطّلع على ما تبنيه الإمارات، مع ذكر المصادر والتواريخ في كل قسم.',
    'Follow Qahwa & AI':'تابع قهوة و AI','AI lessons and news from Qahwa & AI, in English and Arabic.':'دروس وأخبار الذكاء الاصطناعي من قهوة و AI، بالعربية والإنجليزية.',
    'The three areas':'الأقسام الثلاثة','The three areas of the site':'أقسام الموقع الثلاثة',
    'NVIDIA and AMD GPUs, desktop systems, servers and racks, side by side.':'معالجات رسوميات وأجهزة مكتبية وخوادم ورفوف من NVIDIA وAMD، جنبًا إلى جنب.',
    'products':'المنتجات','levels':'المستويات','with approx. price':'بسعر تقريبي','Featured':'مختارات','Prices approximate':'الأسعار تقريبية',
    'Browse by level':'تصفّح حسب المستوى','Browse':'تصفّح','Approx.':'حوالي','Open hardware':'افتح قسم العتاد',
    'headlines':'العناوين','English · Arabic':'إنجليزي · عربي','sources':'المصادر','Latest headlines':'أحدث العناوين','Times in UAE time':'الأوقات بتوقيت الإمارات',
    'Global':'عالمي','Open AI news':'افتح قسم الأخبار',
    'What the UAE is building in AI: strategy, compute and models, each fact with its source.':'ما تبنيه الإمارات في الذكاء الاصطناعي: الاستراتيجية والحوسبة والنماذج، ولكل معلومة مصدرها.',
    'key facts':'المعلومات الرئيسية','UAE headlines':'عناوين الإمارات','UAE newsrooms':'غرف الأخبار الإماراتية','Highlights':'أبرز المعلومات',
    'Latest UAE headlines':'أحدث عناوين الإمارات','Twice a day':'مرتين يوميًا','Open UAE AI':'افتح قسم الإمارات',
    'Why trust this':'لماذا تثق بهذه البيانات؟','Official sources':'مصادر رسمية','Dated prices':'أسعار مؤرّخة',
    'Prices are approximate, labelled by kind, with the date they were checked.':'الأسعار تقريبية، ويظهر مع كل سعر نوعه وتاريخ التحقق منه.',
    'News twice a day':'الأخبار مرتين يوميًا','Official sources checked':'فحص المصادر الرسمية','Hardware sources are checked twice a day.':'تُفحص مصادر العتاد مرتين يوميًا.',
    'Every headline links to its publisher.':'كل عنوان يقود إلى ناشره الأصلي.',
    'Headlines at a glance':'العناوين في لمحة','Region':'النطاق','All':'الكل','English':'الإنجليزية','Arabic':'العربية','feeds responded':'مصادر استجابت',
    'Headlines':'العناوين','Show more':'عرض المزيد','Showing {n} of {m}':'المعروض {n} من أصل {m}',
    'Key facts':'معلومات رئيسية','Newest first. Hardware tags open the matching products.':'الأحدث أولًا. وسوم العتاد تفتح المنتجات المطابقة.','Sources':'المصادر',
    'Each product links to its evidence. Uses are editorial guidance. Power figures apply to the listed component or edition, not the whole server. Launch prices are vendor MSRPs at launch, not current street prices. Timing and stock vary by manufacturer and region. Approximate prices are dated snapshots of retail listings or reported estimates, not offers; UAE retail prices normally include 5% VAT. Product images belong to NVIDIA and AMD and link to their source pages.':'كل منتج مرتبط بمصدره. الاستخدامات المقترحة إرشاد تحريري. أرقام الطاقة تخص المكوّن أو الإصدار المذكور، لا الخادم كاملًا. أسعار الإطلاق هي الأسعار المقترحة من الشركة عند الإطلاق، وليست أسعار السوق الحالية. المواعيد والتوفر يختلفان حسب الشركة المصنّعة والمنطقة. الأسعار التقريبية لقطات مؤرّخة من قوائم المتاجر أو تقديرات منشورة، وليست عروض بيع، وأسعار متاجر الإمارات تشمل عادةً ضريبة القيمة المضافة 5%. صور المنتجات مملوكة لـ NVIDIA وAMD وترتبط بصفحات مصادرها.',
    'Llama, Qwen, DeepSeek, gpt-oss…':'مثل Llama وQwen وDeepSeek وgpt-oss…','Specification':'المواصفة','Selected for comparison':'المنتجات المختارة للمقارنة'
  };
  const $ = id => document.getElementById(id);
  const data = JSON.parse($('catalog-data').textContent);
  const byId = new Map(data.products.map(p => [p.id, p]));
  const cards = new Map([...document.querySelectorAll('[data-product]')].map(el => [el.dataset.product, el]));
  const store = {get(k){try{return localStorage.getItem(k)}catch(e){return null}},set(k,v){try{localStorage.setItem(k,v)}catch(e){}}};
  const state = decodeState(location.search);
  if (!new URLSearchParams(location.search).has('lang') && store.get('atlas-lang') === 'ar') state.lang = 'ar';
  state.cmp = state.cmp.filter(id => byId.has(id));
  let visible = data.products, theme = store.get('atlas-theme') || 'auto', currentView = 'home', lastHref = '', routeSeq = 0;
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
  const FIT = {fits:'Fits', multi:'Fits across GPUs', no:'Too small'};
  const SORTABLE = ['level','model','memory_gb','bandwidth_tbs','power_w','announcement','release','msrp_usd','price_usd'];
  const pv = (p, k) => p.price_view && p.price_view[k] ? p.price_view[k] : null;
  const VIEW_NAME = {home: 'Overview', hardware: 'Hardware', news: 'AI news', uae: 'UAE AI', contact: 'Contact'};
  const VIEW_TITLE = {hardware: 'AI Hardware Atlas', news: 'AI news', uae: 'UAE AI', contact: 'Contact'};
  const known = {levels, vendors: ['NVIDIA', 'AMD'], products: [...byId.keys()], facts: [...document.querySelectorAll('[data-fact]')].map(el => el.dataset.fact)};
  const NEWS_STEP = 30;
  let newsLimit = NEWS_STEP;

  const MODELS = (() => { try { return JSON.parse($('models-data').textContent); } catch (e) { return {models: []}; } })();
  const modelByName = new Map(MODELS.models.map(m => [m.n.toLowerCase(), m]));
  const findModel = name => modelByName.get(String(name || '').trim().toLowerCase());
  // A link that names an open model but no size (?m=… without p) takes the model's published size.
  function sizeFromModel(s) {
    const m = findModel(s.model);
    if (m && m.o && m.b && !s.params) s.params = String(m.b);
  }
  function fillModelList() {
    $('model-list').innerHTML = MODELS.models.map(m => `<option value="${esc(m.n)}">${esc(m.o ? (m.b ? fmt(m.b) + ' B' : T('size not published')) : T('closed · cloud only'))}</option>`).join('');
  }
  function modelNote() {
    // The note follows the page direction; the Latin model name is isolated so it can't reorder an Arabic sentence.
    const note = $('model-note'), m = findModel(state.model);
    note.classList.toggle('closed', !!(m && !m.o));
    if (!m) { note.innerHTML = MODELS.models.length ? FH('Choose from {n} models listed on OpenRouter (list updated {d}), or enter a size below.', {n: esc(fmt(MODELS.models.length)), d: `<bdi>${esc(day(MODELS.updated_at))}</bdi>`}) : ''; return; }
    const name = `<bdi lang="en">${esc(m.n)}</bdi>`;
    if (!m.o) { note.innerHTML = FH("{name} is a closed model: its weights are not public, so it runs only in the provider's cloud (for example through OpenRouter). No hardware on this page can run it locally.", {name}); return; }
    if (!m.b) { note.innerHTML = FH('{name} is open-weight, but its size is not published in a form we can verify. Enter the size manually.', {name}); return; }
    const parts = [FH('{name}: {b} billion parameters', {name, b: esc(fmt(m.b))}), esc(T(m.s === 'name' ? 'size taken from the model name' : 'counted from Hugging Face weights'))];
    if (m.moe) parts.push(esc(T('mixture-of-experts: all experts must fit in memory')));
    if (m.c) parts.push(FH('context up to {c}', {c: esc(countLabel(m.c, 'token', state.lang, fmt))}));
    const hf = /^[\w.-]+\/[\w.-]+$/.test(m.hf || '') ? ` · <a href="https://huggingface.co/${esc(m.hf)}" target="_blank" rel="noopener noreferrer" lang="en">Hugging Face</a>` : '';
    note.innerHTML = parts.join(' · ') + hf;
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
    applyTheme();
    setTitle();
    document.documentElement.classList.remove('i18n-wait');
  }
  function applyTheme() {
    if (theme === 'light' || theme === 'dark') document.documentElement.dataset.theme = theme;
    else { theme = 'auto'; delete document.documentElement.dataset.theme; }
    const name = theme[0].toUpperCase() + theme.slice(1);
    $('theme-label').textContent = T(name);
    $('theme').setAttribute('aria-label', T('Theme: ' + name));
  }
  function setTitle() {
    document.title = currentView === 'home' ? 'Cipher AI Knowledge | ' + T('AI Hardware Atlas, AI news and UAE AI') : T(VIEW_TITLE[currentView]) + ' · Cipher AI Knowledge';
    $('brand-sec').textContent = currentView === 'home' ? '' : T(VIEW_NAME[currentView]);
  }
  function syncUrl() {
    // Query string = filters and settings, hash = the open view.
    // A URL opened without a hash keeps none while it still opens the same view: writing one (#home) would move the
    // browser's Tab starting point into the page. Before the load event nothing is rewritten, because the browser scrolls
    // to the element named by the hash at load: shortening #hardware/p/<id> to #hardware earlier sends it to the top.
    if (booted) {
      const hash = !location.hash && impliedView(encodeState(state)) === currentView ? '' : currentView;
      try { history.replaceState(null, '', pageUrl(location.pathname, encodeState(state), hash)); } catch (e) {}
    }
    lastHref = location.href;
  }
  function shareUrl() { return pageUrl(location.href.split(/[?#]/)[0], encodeState(state), currentView); }

  function render() {
    const n = need();
    visible = select(data.products, {q:state.q, vendor:state.vendor, level:state.level, scope:state.scope, need:n, fitOnly:state.fit}, state.sort, state.dir);
    const ids = new Set(visible.map(p => p.id));
    cards.forEach((el, id) => {
      el.hidden = !ids.has(id);
      const fit = el.querySelector('.fit'), s = fitStatus(byId.get(id), n);
      fit.hidden = !s;
      if (s) { fit.className = 'fit ' + s; fit.textContent = T(FIT[s]); }
      el.querySelector('.cmp-toggle').checked = state.cmp.includes(id);
    });
    visible.forEach(p => $('products').appendChild(cards.get(p.id)));
    $('count').textContent = F('{n} of {m}', {n: visible.length, m: countLabel(data.products.length, 'product', state.lang)});
    $('empty').hidden = visible.length !== 0;
    $('direction').textContent = T(state.dir === 1 ? 'Ascending ↑' : 'Descending ↓');
    $('need').textContent = n ? F('Needs about {x} GB', {x: fmt(Math.round(n * 10) / 10)}) : T('Enter a model size to highlight hardware that fits.');
    ['cards','table','timeline'].forEach(v => $('view-' + v).setAttribute('aria-pressed', String(state.view === v)));
    $('products').hidden = state.view !== 'cards';
    $('table-view').hidden = state.view !== 'table';
    $('timeline-view').hidden = state.view !== 'timeline';
    if (state.view === 'table') renderTable(n);
    if (state.view === 'timeline') renderTimeline();
    renderTray();
    modelNote();
    renderNews();
    syncUrl();
  }

  function renderNews() {
    // Filters the server-rendered list for the current language; "Show more" reveals it in steps.
    const view = $('news');
    if (!view) return;
    view.querySelectorAll('[data-region-chip]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.regionChip === state.region)));
    const list = view.querySelector(`.nlist[data-lang="${state.lang}"]`), more = $('news-more');
    if (!list) { if (more) more.hidden = true; return; }
    let total = 0, shown = 0;
    list.querySelectorAll('li[data-region]').forEach(li => {
      const match = !state.region || li.dataset.region.split(' ').includes(state.region);
      if (match) total++;
      li.hidden = !(match && shown < newsLimit);
      if (!li.hidden) shown++;
    });
    list.querySelectorAll('.nday').forEach(d => { d.hidden = !d.querySelector('li:not([hidden])'); });
    $('news-count').textContent = F('Showing {n} of {m}', {n: shown, m: countLabel(total, 'headline', state.lang)});
    if (more) more.hidden = shown >= total;
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
      <td class="num">${esc(p.release ? day(p.release) : T('Not established'))}<small>${esc(T(p.release_kind))}</small></td><td class="num">${esc(pv(p,'usd') || T('Not listed'))}<small>${esc(T(pv(p,'usd_kind') || ''))}</small></td><td class="num">${esc(pv(p,'aed') || T('Not listed'))}<small>${esc(T(pv(p,'aed_kind') || ''))}</small></td>
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
      const tip = `${name} · ${T('Announced')}: ${p.announcement ? day(p.announcement) : T('Not established')} · ${T('Availability / target')}: ${p.release ? day(p.release) : T('Not established')} (${T(p.release_kind)})`;
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
      ['Vendor', p => esc(p.vendor)], ['Level', p => esc(T(p.level)) + ' / ' + esc(T(p.type))], ['Architecture', p => en(p.architecture)],
      ['Memory', p => `<span class="${p.memory_gb === bestMem ? 'best' : ''}" lang="en">${esc(p.memory)}</span>`], ['Memory scope', p => esc(T(p.memory_scope))],
      ['Bandwidth', p => `<span class="${p.bandwidth_tbs != null && p.bandwidth_tbs === bestBw ? 'best' : ''}">${esc(bw(p))}</span>${p.bandwidth_note ? `<small lang="en">${esc(p.bandwidth_note)}</small>` : ''}`],
      ['AI compute', p => value(p.ai_compute)], ['Power', p => esc(watts(p))],
      ['Announced / launched', p => esc(p.announcement ? day(p.announcement) : T('Not established'))],
      ['Availability / target', p => `${esc(p.release ? day(p.release) : T('Not established'))}<small>${esc(T(p.release_kind))}</small>`],
      ['Launch price', p => esc(price(p))],
      ['Approx. price', p => p.price_view ? `${esc(pv(p,'usd') || T('Not listed'))}<small>${esc(T(pv(p,'usd_kind') || ''))}</small>${esc(pv(p,'aed') || T('Not listed'))}<small>${esc(T(pv(p,'aed_kind') || ''))} · ${esc(T('checked'))} ${esc(day(pv(p,'checked') || ''))}</small>` : esc(T('Not publicly priced'))], ['Form factor', p => value(p.form_factor)], ['Cooling', p => esc(orNA(p.cooling))], ['Interconnect', p => value(p.interconnect)],
      ['Best fit', p => esc(state.lang === 'ar' && p.use_ar ? p.use_ar : p.use)],
      ['Official source', p => p.sources.map(s => `<a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer" lang="en">${esc(s.label)}</a>`).join('<br>')]
    ];
    $('compare-body').innerHTML = `<div class="tablewrap" tabindex="0" role="region" aria-label="${esc(T('Side-by-side comparison'))}"><table class="cmp-table"><thead><tr><th scope="col"><span class="sr-only">${esc(T('Specification'))}</span></th>${ps.map(p => `<th scope="col" class="${p.vendor.toLowerCase()}">${p.image && p.image.file ? `<img src="${esc(p.image.file)}" alt="" loading="lazy">` : ''}<span lang="en">${esc(p.model)}</span></th>`).join('')}</tr></thead>
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
    if (s.region !== state.region) newsLimit = NEWS_STEP;
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
    const r = parseRoute(location.hash, location.search), {patch, focus} = routePatch(r, known);
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
  $('model').addEventListener('input', () => {
    const value = $('model').value.trim(), m = findModel(value);
    if (!value) { state.model = ''; render(); return; }
    if (!m) return;  // still typing
    state.model = m.n;
    // Closed or unsized models must not leave an earlier model's size (and fit badges) behind.
    $('params').value = m.o && m.b ? String(m.b) : '';
    readControls();
    render();
  });
  $('params').addEventListener('input', () => {
    // A hand-typed size no longer describes the picked model.
    const m = findModel(state.model);
    if (m && Number($('params').value) !== m.b) { state.model = ''; $('model').value = ''; render(); }
  });
  ['vendor','level','scope','bits','fit-only'].forEach(id => $(id).addEventListener('change', () => { readControls(); render(); }));
  $('sort').addEventListener('change', () => { state.sort = $('sort').value; render(); });
  $('direction').addEventListener('click', () => { state.dir *= -1; render(); });
  $('reset').addEventListener('click', () => { Object.assign(state, {...DEFAULTS, cmp: state.cmp, lang: state.lang, view: state.view, region: state.region}); writeControls(); render(); });
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
    const rc = e.target.closest('[data-region-chip]');
    if (rc) { state.region = rc.dataset.regionChip; newsLimit = NEWS_STEP; render(); }
  });
  $('news-more') && $('news-more').addEventListener('click', () => { newsLimit += NEWS_STEP; renderNews(); });
  $('skip').addEventListener('click', e => {
    e.preventDefault();
    const h = document.querySelector(`[data-view="${currentView}"] h1`);
    if (h) h.focus();
  });
  $('compare-open').addEventListener('click', openCompare);
  $('compare-clear').addEventListener('click', () => { state.cmp = []; render(); });
  $('compare-close').addEventListener('click', closeCompare);
  $('lang').addEventListener('click', () => { state.lang = state.lang === 'ar' ? 'en' : 'ar'; store.set('atlas-lang', state.lang); applyLang(); fillModelList(); render(); });
  $('theme').addEventListener('click', () => { theme = {auto:'light', light:'dark', dark:'auto'}[theme]; store.set('atlas-theme', theme); applyTheme(); });
  $('share').addEventListener('click', async () => {
    // The shared link always names the view, even when the address bar has no hash.
    syncUrl();
    const link = shareUrl();
    try { await navigator.clipboard.writeText(link); flash(T('Link copied')); }
    catch (e) { window.prompt(T('Copy link'), link); }
  });
  $('print').addEventListener('click', () => { state.view = 'table'; render(); window.print(); });
  // Contact: the address is assembled here so it isn't sitting in the page source for scrapers.
  const contactAddress = ['buafra', 'gmail.com'].join('@');
  $('c-mail').href = 'mailto:' + contactAddress;
  $('c-mail').textContent = contactAddress;
  $('contact-form').addEventListener('submit', e => {
    e.preventDefault();
    const v = id => $(id).value.trim(), required = ['c-subject', 'c-message'], empty = required.filter(id => !v(id));
    required.forEach(id => { if (empty.includes(id)) $(id).setAttribute('aria-invalid', 'true'); else $(id).removeAttribute('aria-invalid'); });
    if (empty.length) { $('c-error').textContent = T('Please add a subject and a message.'); $('c-error').hidden = false; $(empty[0]).focus(); return; }
    $('c-error').hidden = true;
    $('c-error').textContent = '';
    const from = [v('c-name'), v('c-email')].filter(Boolean).join(' · ');
    const body = (from ? from + '\n\n' : '') + v('c-message') + '\n\n— ' + location.href;
    flash(T('Opening your email app…'));
    location.href = `mailto:${contactAddress}?subject=${encodeURIComponent('[Cipher AI Knowledge] ' + v('c-subject'))}&body=${encodeURIComponent(body)}`;
  });
  $('csv').addEventListener('click', () => {
    const cols = ['vendor','model','level','type','architecture','memory','memory_gb','memory_scope','bandwidth_tbs','ai_compute','power_w','power_note','msrp_usd','price_usd_range','price_aed_range','price_checked','form_factor','cooling','interconnect','announcement','release','release_kind','use','source_reviewed'];
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
  route(true);
})(typeof window !== 'undefined' ? window : {});
