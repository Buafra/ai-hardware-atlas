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
  const DEFAULTS = {q:'',vendor:'',level:'',scope:'',sort:'level',dir:1,view:'cards',cmp:[],lang:'en',params:'',bits:'4',extra:'20',fit:false};
  const PARAMS = {q:'q',vendor:'vendor',level:'level',scope:'scope',sort:'sort',dir:'dir',view:'view',cmp:'cmp',lang:'lang',params:'p',bits:'bits',extra:'extra',fit:'fit'};
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
    return s;
  }
  if (typeof module !== 'undefined') module.exports = {select,dateNumber,dateRange,estimateGB,fitStatus,encodeState,decodeState};
  if (!root.document) return;

  const AR = {
    'NVIDIA + AMD / AI infrastructure':'NVIDIA + AMD / بنية الذكاء الاصطناعي التحتية','AI Hardware Atlas':'أطلس عتاد الذكاء الاصطناعي',
    'Compare GPUs, desktop systems, servers and racks.':'قارن معالجات الرسوميات والأجهزة المكتبية والخوادم والرفوف.',
    'One-page PDF':'ملف PDF من صفحة واحدة','Export CSV':'تصدير CSV','Copy link':'نسخ الرابط','Link copied':'تم نسخ الرابط','Print table':'طباعة الجدول',
    'Theme: Auto':'المظهر: تلقائي','Theme: Light':'المظهر: فاتح','Theme: Dark':'المظهر: داكن',
    'Content updated:':'آخر تحديث للمحتوى:','Source check:':'آخر فحص للمصادر:','Schedule:':'الجدولة:',
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
    '{n} of {m} products':'{n} من {m} منتج','No matches. Try another search or reset the filters.':'لا توجد نتائج. جرّب بحثًا آخر أو أعد ضبط الفلاتر.',
    'Availability / target':'التوفر / الهدف','Announced / launched':'الإعلان / الإطلاق','Power':'الطاقة','Bandwidth':'عرض النطاق','AI compute':'حوسبة الذكاء الاصطناعي',
    'Form factor':'الشكل','Cooling':'التبريد','Interconnect':'الربط','Content reviewed':'تاريخ مراجعة المحتوى','Notes and official sources':'ملاحظات ومصادر رسمية',
    'Not listed':'غير مذكور','Not documented in this edition':'غير موثق في هذه النسخة','Compare':'قارن','Model':'الطراز','Memory':'الذاكرة','Type':'النوع',
    'Architecture':'المعمارية','Best fit':'الاستخدام الأنسب','Official source':'المصدر الرسمي','Fit':'الملاءمة',
    'What can it run?':'ما النماذج التي يشغّلها؟','Model size (billions of parameters)':'حجم النموذج (مليار مُعامل)','Precision':'الدقة',
    '16-bit (FP16 / BF16)':'16 بت (FP16 / BF16)','8-bit (FP8 / INT8)':'8 بت (FP8 / INT8)','4-bit (quantized)':'4 بت (مضغوط)',
    'Extra for context and runtime (%)':'إضافة للسياق والتشغيل (%)','Only show hardware that fits':'اعرض العتاد الذي يتسع فقط',
    'Needs about {x} GB':'يحتاج تقريبًا {x} جيجابايت','Enter a model size to highlight hardware that fits.':'أدخل حجم النموذج لتمييز العتاد الذي يتسع له.',
    'Rough guide: weights at the chosen precision plus the extra you set. Long contexts, batching and training need much more. Shared memory also serves the operating system, and multi-GPU totals need software that splits the model.':'تقدير تقريبي: الأوزان بالدقة المختارة مع النسبة الإضافية المحددة. السياقات الطويلة والدفعات والتدريب تحتاج أكثر بكثير. الذاكرة المشتركة يستخدمها نظام التشغيل أيضًا، والإجماليات متعددة المعالجات تحتاج برمجيات تقسّم النموذج.',
    'Fits':'يتسع','Fits across GPUs':'يتسع عبر عدة معالجات','Too small':'لا يتسع',
    '{n} selected':'{n} محدد','Clear':'مسح','Close':'إغلاق','Compare up to 4 products':'يمكن مقارنة 4 منتجات كحد أقصى','Remove':'إزالة',
    'Side-by-side comparison':'مقارنة جنبًا إلى جنب','Memory scopes differ, so totals are not directly comparable.':'نطاقات الذاكرة مختلفة، لذا لا تُقارن الإجماليات مباشرة.',
    'Highlighted: highest value among products with the same memory scope.':'المميَّز: أعلى قيمة بين منتجات لها نطاق الذاكرة نفسه.',
    'Announced':'أُعلن','Today':'اليوم','No dated milestones for these products.':'لا توجد تواريخ لهذه المنتجات.',
    'Hollow circle: announcement. Solid mark: availability or vendor target. Bars show quarter, half-year or seasonal windows.':'الدائرة المفرغة: الإعلان. العلامة المصمتة: التوفر أو هدف الشركة. الأشرطة تمثل فترات ربع سنوية أو نصف سنوية أو موسمية.',
    '{n} filtered products have no dated milestone.':'{n} من المنتجات المعروضة بلا تاريخ محدد.',
    'Capacity is not speed':'السعة ليست السرعة','Memory capacity determines what can fit. Bandwidth, compute, precision and software influence how quickly it runs. Sorting by memory is not a performance ranking.':'سعة الذاكرة تحدد ما يمكن أن يتسع. أما سرعة التشغيل فتتأثر بعرض النطاق والحوسبة والدقة والبرمجيات. الترتيب حسب الذاكرة ليس ترتيبًا للأداء.',
    'Compare the same scope':'قارن النطاق نفسه','A single GPU, shared CPU/GPU system, and rack total are different measurements. Multiple GPUs do not automatically expose one shared VRAM pool.':'معالج رسوميات واحد، ونظام بذاكرة مشتركة، وإجمالي رف كامل هي قياسات مختلفة. تعدد معالجات الرسوميات لا يعني تلقائيًا ذاكرة واحدة مشتركة.',
    'Dates have different meanings':'للتواريخ معانٍ مختلفة','An announcement does not establish first shipment. Vendor targets remain labeled as targets until a release or availability statement is verified. Unknown values stay blank.':'الإعلان لا يعني بدء الشحن. تبقى أهداف الشركات موسومة كأهداف حتى يتم التحقق من الإصدار أو التوفر. القيم غير المعروفة تبقى فارغة.',
    'What changed':'ما الذي تغيّر','Official announcement watch':'رصد الإعلانات الرسمية','Air':'هوائي','Liquid':'سائل','Air or liquid':'هوائي أو سائل'
  };
  const $ = id => document.getElementById(id);
  const data = JSON.parse($('catalog-data').textContent);
  const byId = new Map(data.products.map(p => [p.id, p]));
  const cards = new Map([...document.querySelectorAll('[data-product]')].map(el => [el.dataset.product, el]));
  const store = {get(k){try{return localStorage.getItem(k)}catch(e){return null}},set(k,v){try{localStorage.setItem(k,v)}catch(e){}}};
  const state = decodeState(location.search);
  if (!new URLSearchParams(location.search).has('lang') && store.get('atlas-lang') === 'ar') state.lang = 'ar';
  state.cmp = state.cmp.filter(id => byId.has(id));
  let visible = data.products, theme = store.get('atlas-theme') || 'auto';
  const T = s => state.lang === 'ar' ? (AR[s] || s) : s;
  const F = (s, vars) => T(s).replace(/\{(\w+)\}/g, (_, k) => vars[k]);
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const fmt = n => Number(n).toLocaleString('en-US', {maximumFractionDigits: 3});
  const bw = p => p.bandwidth_tbs == null ? T('Not listed') : fmt(p.bandwidth_tbs) + ' TB/s';
  const watts = p => p.power_w == null ? T('Not listed') : fmt(p.power_w) + ' W';
  const price = p => p.msrp_usd == null ? T('Not listed') : '$' + fmt(p.msrp_usd);
  const orNA = v => v == null || v === '' ? T('Not listed') : T(v);
  const FIT = {fits:'Fits', multi:'Fits across GPUs', no:'Too small'};
  const SORTABLE = ['level','model','memory_gb','bandwidth_tbs','power_w','announcement','release','msrp_usd'];

  function need() { return estimateGB(state.params, state.bits, state.extra); }
  function readControls() {
    ['search:q','vendor','level','scope','params','bits','extra'].forEach(x => { const [id,k] = x.split(':'); state[k || id] = $(id).value; });
    state.fit = $('fit-only').checked;
  }
  function writeControls() {
    ['search:q','vendor','level','scope','params','bits','extra'].forEach(x => { const [id,k] = x.split(':'); $(id).value = state[k || id]; });
    ['vendor','level','scope'].forEach(id => { state[id] = $(id).value; });
    $('fit-only').checked = state.fit;
    if (!SORTABLE.includes(state.sort)) state.sort = 'level';
    $('sort').value = state.sort;
  }
  function applyLang() {
    document.documentElement.lang = state.lang;
    document.documentElement.dir = state.lang === 'ar' ? 'rtl' : 'ltr';
    document.querySelectorAll('[data-i18n]').forEach(el => { if (el.dataset.en == null) el.dataset.en = el.textContent; el.textContent = T(el.dataset.en); });
    document.querySelectorAll('[data-i18n-ph]').forEach(el => { el.placeholder = T(el.dataset.i18nPh); });
    document.querySelectorAll('[data-ar]').forEach(el => { if (el.dataset.en == null) el.dataset.en = el.textContent; el.textContent = state.lang === 'ar' && el.dataset.ar ? el.dataset.ar : el.dataset.en; });
    $('lang').textContent = state.lang === 'ar' ? 'English' : 'العربية';
    $('lang').lang = state.lang === 'ar' ? 'en' : 'ar';
    applyTheme();
  }
  function applyTheme() {
    if (theme === 'light' || theme === 'dark') document.documentElement.dataset.theme = theme;
    else { theme = 'auto'; delete document.documentElement.dataset.theme; }
    $('theme').textContent = T('Theme: ' + theme[0].toUpperCase() + theme.slice(1));
  }
  function syncUrl() {
    const qs = encodeState(state);
    try { history.replaceState(null, '', qs ? '?' + qs : location.pathname); } catch (e) {}
  }

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
    $('count').textContent = F('{n} of {m} products', {n: visible.length, m: data.products.length});
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
    syncUrl();
  }

  function renderTable(n) {
    const cols = [['model','Model'],['level','Level'],['memory_gb','Memory'],['bandwidth_tbs','Bandwidth'],['power_w','Power'],['announcement','Announced / launched'],['release','Availability / target'],['msrp_usd','Launch price']];
    const arrow = k => state.sort === k ? (state.dir === 1 ? ' ↑' : ' ↓') : '';
    const head = cols.map(([k,l]) => `<th scope="col" aria-sort="${state.sort === k ? (state.dir === 1 ? 'ascending' : 'descending') : 'none'}"><button type="button" data-sort="${k}">${esc(T(l))}${arrow(k)}</button></th>`).join('') + (n ? `<th scope="col">${esc(T('Fit'))}</th>` : '');
    const rows = visible.map(p => {
      const s = fitStatus(p, n);
      return `<tr><td><input type="checkbox" class="cmp-toggle" value="${esc(p.id)}" aria-label="${esc(T('Compare') + ' ' + p.model)}"${state.cmp.includes(p.id) ? ' checked' : ''}></td>
      <td class="t-model"><span class="dot ${p.vendor.toLowerCase()}" aria-hidden="true"></span><a href="${esc(p.sources[0].url)}" target="_blank" rel="noopener noreferrer">${esc(p.model)}</a><small>${esc(p.vendor)} · ${esc(p.architecture)}</small></td>
      <td>${esc(T(p.level))}<small>${esc(T(p.type))}</small></td><td class="num">${esc(p.memory)}<small>${esc(T(p.memory_scope))}</small></td>
      <td class="num">${esc(bw(p))}</td><td class="num">${esc(watts(p))}</td><td class="num">${esc(p.announcement || T('Not established'))}</td>
      <td class="num">${esc(p.release || T('Not established'))}<small>${esc(T(p.release_kind))}</small></td><td class="num">${esc(price(p))}</td>
      ${n ? `<td><span class="fit ${s}">${esc(T(FIT[s]))}</span></td>` : ''}</tr>`;
    }).join('');
    $('table-view').innerHTML = `<div class="tablewrap"><table><thead><tr><th scope="col"><span class="sr-only">${esc(T('Compare'))}</span></th>${head}</tr></thead><tbody>${rows}</tbody></table></div>`;
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
      const tip = `${p.model} · ${T('Announced')}: ${p.announcement || T('Not established')} · ${T('Availability / target')}: ${p.release || T('Not established')} (${T(p.release_kind)})`;
      svg += `<g class="row ${v}"><title>${esc(tip)}</title><rect class="hit" x="0" y="${cy - rowH / 2}" width="${W}" height="${rowH}"/>`;
      svg += `<text class="label" x="${L - 12}" y="${cy + 4}" text-anchor="end">${esc(p.model.length > 32 ? p.model.slice(0, 31) + '…' : p.model)}</text>`;
      if (a && r) svg += `<line class="conn" x1="${x(a[0])}" x2="${x(r[0])}" y1="${cy}" y2="${cy}"/>`;
      if (r) svg += r[0] === r[1] ? `<path class="rel" d="M${x(r[0])} ${cy - 6}l6 6-6 6-6-6z"/>` : `<rect class="rel" x="${x(r[0])}" y="${cy - 5}" width="${Math.max(6, x(r[1]) - x(r[0]))}" height="10" rx="5"/>`;
      if (a) svg += `<circle class="ann" cx="${x(a[0])}" cy="${cy}" r="5"/>`;
      svg += '</g>';
    });
    if (today >= min && today <= max) svg += `<line class="today" x1="${x(today)}" x2="${x(today)}" y1="${top - 8}" y2="${H - 6}"/><text class="today-label" x="${x(today)}" y="${H - 1}" text-anchor="middle">${esc(T('Today'))}</text>`;
    $('timeline-view').innerHTML = `<p class="tl-legend"><span class="key ann-key"></span>${esc(T('Announced'))}<span class="key rel-key"></span>${esc(T('Availability / target'))}<span class="key nv-key"></span>NVIDIA<span class="key amd-key"></span>AMD</p>
      <div class="tl-scroll" dir="ltr"><svg class="tl" viewBox="0 0 ${W} ${H + 6}" role="img" aria-label="${esc(T('Timeline'))}">${svg}</svg></div>
      <p class="tl-note">${esc(T('Hollow circle: announcement. Solid mark: availability or vendor target. Bars show quarter, half-year or seasonal windows.'))}${missing ? ' ' + esc(F('{n} filtered products have no dated milestone.', {n: missing})) : ''}</p>`;
  }

  function renderTray() {
    $('tray').hidden = state.cmp.length === 0;
    $('tray-count').textContent = F('{n} selected', {n: state.cmp.length});
    $('tray-items').innerHTML = state.cmp.map(id => `<button type="button" class="chip" data-remove="${esc(id)}" aria-label="${esc(T('Remove') + ' ' + byId.get(id).model)}">${esc(byId.get(id).model)} ×</button>`).join('');
    $('compare-open').disabled = state.cmp.length < 2;
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
    const rows = [
      ['Vendor', p => esc(p.vendor)], ['Level', p => esc(T(p.level)) + ' / ' + esc(T(p.type))], ['Architecture', p => esc(p.architecture)],
      ['Memory', p => `<span class="${p.memory_gb === bestMem ? 'best' : ''}">${esc(p.memory)}</span>`], ['Memory scope', p => esc(T(p.memory_scope))],
      ['Bandwidth', p => `<span class="${p.bandwidth_tbs != null && p.bandwidth_tbs === bestBw ? 'best' : ''}">${esc(bw(p))}</span>${p.bandwidth_note ? `<small>${esc(p.bandwidth_note)}</small>` : ''}`],
      ['AI compute', p => esc(orNA(p.ai_compute))], ['Power', p => esc(watts(p))],
      ['Announced / launched', p => esc(p.announcement || T('Not established'))],
      ['Availability / target', p => `${esc(p.release || T('Not established'))}<small>${esc(T(p.release_kind))}</small>`],
      ['Launch price', p => esc(price(p))], ['Form factor', p => esc(orNA(p.form_factor))], ['Cooling', p => esc(orNA(p.cooling))], ['Interconnect', p => esc(orNA(p.interconnect))],
      ['Best fit', p => esc(state.lang === 'ar' && p.use_ar ? p.use_ar : p.use)],
      ['Official source', p => p.sources.map(s => `<a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${esc(s.label)}</a>`).join('<br>')]
    ];
    $('compare-body').innerHTML = `<div class="tablewrap"><table class="cmp-table"><thead><tr><th scope="col"></th>${ps.map(p => `<th scope="col" class="${p.vendor.toLowerCase()}">${esc(p.model)}</th>`).join('')}</tr></thead>
      <tbody>${rows.map(([l, f]) => `<tr><th scope="row">${esc(T(l))}</th>${ps.map(p => `<td>${f(p)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>
      <p class="tl-note">${esc(T(sameScope ? 'Highlighted: highest value among products with the same memory scope.' : 'Memory scopes differ, so totals are not directly comparable.'))}</p>`;
    const dlg = $('compare-dlg');
    if (dlg.showModal) dlg.showModal(); else dlg.setAttribute('open', '');
  }

  ['search','params','extra'].forEach(id => $(id).addEventListener('input', () => { readControls(); render(); }));
  ['vendor','level','scope','bits','fit-only'].forEach(id => $(id).addEventListener('change', () => { readControls(); render(); }));
  $('sort').addEventListener('change', () => { state.sort = $('sort').value; render(); });
  $('direction').addEventListener('click', () => { state.dir *= -1; render(); });
  $('reset').addEventListener('click', () => { Object.assign(state, {...DEFAULTS, cmp: state.cmp, lang: state.lang, view: state.view}); writeControls(); render(); });
  ['cards','table','timeline'].forEach(v => $('view-' + v).addEventListener('click', () => { state.view = v; render(); }));
  document.querySelectorAll('[data-params]').forEach(b => b.addEventListener('click', () => { $('params').value = b.dataset.params; readControls(); render(); }));
  document.addEventListener('change', e => { if (e.target.classList.contains('cmp-toggle')) toggleCompare(e.target.value, e.target.checked, e.target); });
  document.addEventListener('click', e => {
    const s = e.target.closest('[data-sort]');
    if (s) { if (state.sort === s.dataset.sort) state.dir *= -1; else { state.sort = s.dataset.sort; state.dir = 1; } $('sort').value = state.sort; render(); }
    const r = e.target.closest('[data-remove]');
    if (r) toggleCompare(r.dataset.remove, false);
  });
  $('compare-open').addEventListener('click', openCompare);
  $('compare-clear').addEventListener('click', () => { state.cmp = []; render(); });
  $('compare-close').addEventListener('click', () => { const d = $('compare-dlg'); if (d.close) d.close(); else d.removeAttribute('open'); });
  $('lang').addEventListener('click', () => { state.lang = state.lang === 'ar' ? 'en' : 'ar'; store.set('atlas-lang', state.lang); applyLang(); render(); });
  $('theme').addEventListener('click', () => { theme = {auto:'light', light:'dark', dark:'auto'}[theme]; store.set('atlas-theme', theme); applyTheme(); });
  $('share').addEventListener('click', async () => {
    try { await navigator.clipboard.writeText(location.href); flash(T('Link copied')); }
    catch (e) { window.prompt(T('Copy link'), location.href); }
  });
  $('print').addEventListener('click', () => { state.view = 'table'; render(); window.print(); });
  $('csv').addEventListener('click', () => {
    const cols = ['vendor','model','level','type','architecture','memory','memory_gb','memory_scope','bandwidth_tbs','ai_compute','power_w','power_note','msrp_usd','form_factor','cooling','interconnect','announcement','release','release_kind','use','source_reviewed'];
    const cell = v => '"' + String(v ?? '').replaceAll('"', '""') + '"';
    const csv = [cols.join(','), ...visible.map(p => cols.map(k => cell(p[k])).join(','))].join('\r\n');
    const url = URL.createObjectURL(new Blob(['﻿' + csv], {type: 'text/csv;charset=utf-8'}));
    const a = document.createElement('a'); a.href = url; a.download = 'ai-hardware-atlas.csv'; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  writeControls();
  applyLang();
  render();
})(typeof window !== 'undefined' ? window : {});
