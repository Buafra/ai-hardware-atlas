(function () {
  'use strict';
  // Learn AI page. Everything is already in the HTML in both languages; this adds the tabs, topic filters, search,
  // deep links (#concept/<id>, #stack/<id>, #group/<id>, #concepts, #stacks) and the language and theme buttons, which share their
  // localStorage keys with the overview page (atlas-lang, atlas-theme).
  const d = document.documentElement;
  const $ = id => document.getElementById(id);
  const store = {get(k){try{return localStorage.getItem(k)}catch(e){return null}}, set(k,v){try{localStorage.setItem(k,v)}catch(e){}}};
  const TXT = {
    en: {title: 'Learn AI · Cipher Lacuna', auto: 'Auto', light: 'Light', dark: 'Dark', theme: 'Theme: '},
    ar: {title: 'تعلّم الذكاء الاصطناعي · Cipher Lacuna', auto: 'تلقائي', light: 'فاتح', dark: 'داكن', theme: 'المظهر: '}
  };
  const NOUN = {
    concepts: {en: ['concept', 'concepts'], ar: ['مفهوم واحد', 'مفهومان', 'مفاهيم', 'مفهوماً', 'مفهوم']},
    stacks: {en: ['AI stack', 'AI stacks'], ar: ['تركيبة واحدة', 'تركيبتان', 'تركيبات', 'تركيبة', 'تركيبة']},
    foundations: {en: ['foundation', 'foundations'], ar: ['أساس واحد', 'أساسان', 'أسس', 'أساساً', 'أساس']}
  };
  // Number + noun with English plurals and Arabic number agreement (same rule as cnt() in scripts/learn.py).
  function count(n, kind) {
    const f = NOUN[kind][lang];
    if (lang !== 'ar') return n + ' ' + (n === 1 ? f[0] : f[1]);
    if (n === 1) return f[0];
    if (n === 2) return f[1];
    const r = n % 100;
    return n + ' ' + (r >= 3 && r <= 10 ? f[2] : r >= 11 && r <= 99 ? f[3] : f[4]);
  }
  let lang = d.lang === 'ar' ? 'ar' : 'en';
  let theme = store.get('atlas-theme') || 'auto';
  let tab = d.dataset.ltab === 'stacks' ? 'stacks' : 'concepts';
  const filter = {concepts: '', stacks: ''};
  const panels = {concepts: $('concepts'), stacks: $('stacks')};
  const items = {concepts: [...panels.concepts.querySelectorAll('.l-item')], stacks: [...panels.stacks.querySelectorAll('.l-item')]};
  const search = $('lq');
  const empty = $('l-empty');
  // The stacks tab holds the AI stacks (data-group="core") and the foundations; its badge counts the AI stacks, as the
  // status bar and the overview do ("12 AI stacks · 3 foundations"), while its All chip counts both.
  const inBadge = (p, el) => p !== 'stacks' || el.dataset.group === 'core';
  const ofTotal = p => {
    if (p !== 'stacks') return count(items[p].length, p);
    const core = items.stacks.filter(el => el.dataset.group === 'core').length;
    return count(core, 'stacks') + (lang === 'ar' ? ' و' : ' and ') + count(items.stacks.length - core, 'foundations');
  };

  // Search ignores case, Latin accents and Arabic diacritics, tatweel and letter variants (أ إ آ ٱ ا, ة ه, ى ي).
  const norm = s => String(s || '').normalize('NFKD').toLowerCase()
    .replace(/[\u0300-\u036f\u064b-\u065f\u0670\u0640]/g, '').replace(/\u0671/g, 'ا').replace(/ة/g, 'ه').replace(/ى/g, 'ي')
    .replace(/[’‘`]/g, "'").replace(/[“”]/g, '"');
  const cache = {en: new Map(), ar: new Map()};
  function textOf(el) {
    // The item's words in the current language (the other language's copy is skipped); built once per item and language.
    if (!cache[lang].has(el)) {
      const walk = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
      let out = '', n;
      while ((n = walk.nextNode())) {
        const holder = n.parentElement.closest('[data-lang]');
        if (!holder || !el.contains(holder) || holder.dataset.lang === lang) out += ' ' + n.nodeValue;
      }
      cache[lang].set(el, norm(out));
    }
    return cache[lang].get(el);
  }

  function setTab(t) {
    tab = t === 'stacks' ? 'stacks' : 'concepts';
    d.dataset.ltab = tab;
    document.querySelectorAll('.l-tab').forEach(a => { if (a.dataset.tab === tab) a.setAttribute('aria-current', 'true'); else a.removeAttribute('aria-current'); });
    apply();
  }
  function apply() {
    const words = norm(search.value).trim().split(/\s+/).filter(Boolean);
    const found = el => !words.length || words.every(w => textOf(el).includes(w));
    const shown = {};
    for (const p of ['concepts', 'stacks']) {
      let n = 0, matches = 0;
      const hits = {'': 0};
      for (const el of items[p]) {
        const hit = found(el), ok = hit && (!filter[p] || el.dataset.group === filter[p]);
        el.hidden = !ok;
        if (ok) n++;
        if (hit) {
          hits[''] += 1;
          hits[el.dataset.group] = (hits[el.dataset.group] || 0) + 1;
          if (inBadge(p, el)) matches++;
        }
      }
      panels[p].querySelectorAll('.l-group').forEach(g => { g.hidden = !g.querySelector('.l-item:not([hidden])'); });
      // Each chip counts what it would show with the current search (the full counts while nothing is typed).
      panels[p].querySelectorAll('.fchip').forEach(b => {
        b.setAttribute('aria-pressed', String(b.dataset.filter === filter[p]));
        const c = b.querySelector('.n');
        if (c) c.textContent = String(hits[b.dataset.filter] || 0);
      });
      shown[p] = n;
      // The tab badges count search matches in each tab, so a hit in the other tab is visible.
      const badge = document.querySelector(`.l-tab [data-count="${p}"]`);
      if (badge) badge.textContent = String(matches);
    }
    const total = items[tab].length, n = shown[tab];
    const narrowed = n !== total;
    // Only while a search or topic filter narrows the list (the tab badge already shows the total).
    $('l-count').textContent = !narrowed ? ''
      : lang === 'ar' ? `عدد النتائج ${n} من أصل ${ofTotal(tab)}` : `Showing ${n} of ${ofTotal(tab)}`;
    // "No matches" sits where the items would be: under the open tab's topic chips.
    const chips = panels[tab].querySelector('.l-filter');
    if (chips && chips.nextElementSibling !== empty) chips.after(empty);
    empty.hidden = n > 0;
  }

  // Links back to the overview (the brand link's page: index.html, or the standalone file's name) and their original hrefs.
  const brand = document.querySelector('.top a.brand');
  const home = brand ? brand.getAttribute('href') || '' : '';
  const homeLinks = !home || home[0] === '#' ? [] : [...document.querySelectorAll('a[href]')]
    .filter(a => { const h = a.getAttribute('href'); return h === home || h.startsWith(home + '#'); })
    .map(a => [a, a.getAttribute('href')]);
  function langLinks() {
    // The overview takes its language from ?lang= or the saved choice. A ?lang=ar visit saves nothing, so while the
    // language shown here differs from the saved one, the links back carry it (app.js does the same for learn.html links).
    const want = lang !== (store.get('atlas-lang') === 'ar' ? 'ar' : 'en') ? lang : '';
    homeLinks.forEach(([a, h]) => {
      const i = h.indexOf('#');
      a.setAttribute('href', want ? (i < 0 ? h : h.slice(0, i)) + '?lang=' + want + (i < 0 ? '' : h.slice(i)) : h);
    });
  }

  function applyLang() {
    d.lang = lang;
    d.dir = lang === 'ar' ? 'rtl' : 'ltr';
    document.title = TXT[lang].title;
    document.querySelectorAll('[data-ph-ar]').forEach(el => { if (el.dataset.phEn == null) el.dataset.phEn = el.placeholder; el.placeholder = lang === 'ar' ? el.dataset.phAr : el.dataset.phEn; });
    document.querySelectorAll('[data-aria-ar]').forEach(el => { if (el.dataset.ariaEn == null) el.dataset.ariaEn = el.getAttribute('aria-label') || ''; el.setAttribute('aria-label', lang === 'ar' ? el.dataset.ariaAr : el.dataset.ariaEn); });
    langLinks();
    applyTheme();
  }
  function applyTheme() {
    if (theme === 'light' || theme === 'dark') d.dataset.theme = theme;
    else { theme = 'auto'; delete d.dataset.theme; }
    $('theme-label').textContent = TXT[lang][theme];
    $('theme').setAttribute('aria-label', TXT[lang].theme + TXT[lang][theme]);
  }

  let flashTimer = 0;
  function go(hash, userAction) {
    let h = String(hash || '').replace(/^#/, '');
    try { h = decodeURIComponent(h); } catch (e) {}
    if (h === 'concepts' || h === 'stacks') {
      setTab(h);
      if (userAction) panels[h].scrollIntoView({block: 'start'});
      return true;
    }
    // #group/<id>: a topic (or the core stacks, or the foundations) opens with its chip pressed.
    const g = /^group\/([a-z0-9-]+)$/.exec(h) && document.getElementById(h);
    if (g && g.classList.contains('l-group')) {
      const p = g.closest('[data-panel]').dataset.panel;
      filter[p] = g.dataset.group;
      search.value = '';
      setTab(p);
      g.scrollIntoView({block: 'start'});
      return true;
    }
    const m = /^(concept|stack)\/([a-z0-9-]+)$/.exec(h);
    const el = m && document.getElementById(h);
    if (!el || !el.classList.contains('l-item')) return false;
    const p = m[1] === 'concept' ? 'concepts' : 'stacks';
    setTab(p);
    if (el.hidden) { filter[p] = ''; search.value = ''; apply(); }
    el.open = true;
    el.scrollIntoView({block: 'start'});
    el.querySelector('summary').focus({preventScroll: true});
    document.querySelectorAll('.flash-item').forEach(x => x.classList.remove('flash-item'));
    el.classList.add('flash-item');
    clearTimeout(flashTimer);
    flashTimer = setTimeout(() => el.classList.remove('flash-item'), 1600);
    return true;
  }

  document.addEventListener('click', e => {
    const chip = e.target.closest('.fchip');
    if (chip) {
      const p = chip.closest('[data-panel]').dataset.panel;
      filter[p] = chip.dataset.filter;
      apply();
      return;
    }
    const a = e.target.closest('a[href^="#"]');
    if (!a || e.defaultPrevented || e.button || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    const href = a.getAttribute('href');
    if (!/^#(concepts|stacks|concept\/|stack\/|group\/)/.test(href)) return;
    e.preventDefault();
    if (location.hash !== href) { try { history.pushState(null, '', href); } catch (err) { location.hash = href; return; } }
    go(href, true);
  });
  // Opening an item puts its address in the bar, so the link can be copied and shared.
  document.querySelectorAll('.l-item').forEach(el => el.addEventListener('toggle', () => {
    if (el.open && location.hash !== '#' + el.id) { try { history.replaceState(null, '', '#' + el.id); } catch (e) {} }
  }));
  // The saved language can change in another tab, or on the overview before Back returns here from the page cache.
  window.addEventListener('storage', e => { if (e.key === 'atlas-lang' || e.key === null) langLinks(); });
  window.addEventListener('pageshow', langLinks);
  window.addEventListener('popstate', () => go(location.hash));
  window.addEventListener('hashchange', () => go(location.hash));
  search.addEventListener('input', apply);
  search.addEventListener('keydown', e => { if (e.key === 'Escape' && search.value) { search.value = ''; apply(); } });
  $('lang').addEventListener('click', () => {
    lang = lang === 'ar' ? 'en' : 'ar';
    store.set('atlas-lang', lang);
    // A ?lang= in the address (a shared link) would otherwise win again on reload.
    try {
      const u = new URL(location.href);
      if (u.searchParams.has('lang')) { u.searchParams.set('lang', lang); history.replaceState(null, '', u.href); }
    } catch (e) {}
    applyLang();
    apply();
  });
  $('theme').addEventListener('click', () => { theme = {auto: 'light', light: 'dark', dark: 'auto'}[theme] || 'auto'; store.set('atlas-theme', theme); applyTheme(); });
  $('skip').addEventListener('click', e => { e.preventDefault(); $('learn-title').focus(); });

  applyLang();
  setTab(tab);
  if (location.hash) go(location.hash);
})();
