const assert=require('node:assert/strict');
const {select,dateNumber,dateRange,estimateGB,fitStatus,encodeState,decodeState}=require('../web/app.js');
const data=require('../data/catalog.json');
let rows=select(data.products,{},'memory_gb',1);
assert.equal(rows[0].memory_gb,Math.min(...data.products.map(p=>p.memory_gb)));
assert.ok(rows.findIndex(x=>x.memory_gb===128)<rows.findIndex(x=>x.memory_gb===1440));
rows=select(data.products,{vendor:'AMD',q:'R9700'},'model',1);
assert.equal(rows.length,1);assert.equal(rows[0].vendor,'AMD');
assert.equal(select(data.products,{q:'unmatched-query'},'model',1).length,0);
rows=select(data.products,{},'power_w',-1);assert.equal(rows.at(-1).power_w,null);
assert.ok(dateNumber('2025-Q1')<dateNumber('2025-10-15'));
assert.ok(dateNumber('2026-H2')<dateNumber('2026-end'));
assert.equal(dateNumber(null),null);
assert.equal(data.products.find(x=>x.id==='dgx-spark-gb10').release,'2025-10-15');
// Rubin CPX has no availability date any more: it sorts with the other undated products, last in both directions.
const cpx=data.products.find(x=>x.id==='vera-rubin-nvl144-cpx');assert.equal(cpx.release,null);assert.equal(cpx.release_kind,"Not on NVIDIA's current roadmap");
const {releaseKind}=require('../web/app.js');assert.equal(releaseKind('Not established'),'');assert.equal(releaseKind(null),'');assert.equal(releaseKind(cpx.release_kind),cpx.release_kind);
for(const dir of [1,-1]){const r=select(data.products,{},'release',dir),i=r.findIndex(x=>x.release==null);assert.ok(i>0&&r.slice(i).every(x=>x.release==null)&&r.slice(i).includes(cpx),'release sort '+dir);}
const [q3s,q3e]=dateRange('2025-Q3');assert.equal(new Date(q3s).toISOString().slice(0,10),'2025-07-01');assert.equal(new Date(q3e).toISOString().slice(0,10),'2025-09-30');
assert.equal(new Date(dateRange('2025-Summer')[1]).toISOString().slice(0,10),'2025-08-31');assert.equal(dateRange('soon'),null);
assert.equal(estimateGB(70,4,20),42);assert.equal(estimateGB('',4,20),null);assert.equal(estimateGB(8,16,0),16);
assert.equal(fitStatus({memory_gb:48,memory_scope:'Per GPU'},42),'fits');assert.equal(fitStatus({memory_gb:768,memory_scope:'System total'},42),'multi');assert.equal(fitStatus({memory_gb:32,memory_scope:'Per GPU'},42),'no');assert.equal(fitStatus({memory_gb:32},null),null);
rows=select(data.products,{need:42,fitOnly:true},'memory_gb',1);assert.ok(rows.length>0&&rows.every(p=>p.memory_gb>=42));
const st={...decodeState(''),q:'mi3',vendor:'AMD',sort:'memory_gb',dir:-1,view:'table',cmp:['h200','b200-blackwell'],lang:'ar',params:'70',fit:true};
const back=decodeState(encodeState(st));for(const k of Object.keys(st))assert.deepEqual(back[k],st[k],k);
assert.equal(encodeState(decodeState('')),'');assert.equal(decodeState('?view=evil&lang=xx').view,'cards');assert.equal(decodeState('?cmp=a,b,c,d,e,a').cmp.length,4);
// The renamed "Extra memory for chat length and software" field keeps its behaviour, default and URL parameter.
assert.equal(decodeState('').extra,'20');assert.equal(decodeState('?extra=35').extra,'35');
assert.equal(encodeState({...decodeState(''),extra:'35'}),'extra=35');assert.equal(encodeState({...decodeState(''),extra:'20'}),'');
console.log('PASS: sort, date windows, nulls, undated CPX, filters, Spark date, estimator, fit, URL state');
// Hash routes: views in the hash, deep links applied once, unknown hashes fall back to #home.
const {parseRoute,routePatch,pageUrl,countLabel}=require('../web/app.js');
const home={view:'home',sub:'',arg:''};
for(const h of ['','#','#nope','#main','#hardwarez','#%E0%A4%A'])assert.deepEqual(parseRoute(h),home,h);
for(const v of ['home','hardware','news','uae','contact'])assert.deepEqual(parseRoute('#'+v),{view:v,sub:'',arg:''},v);
assert.deepEqual(parseRoute('#hardware/level/Rack%20scale'),{view:'hardware',sub:'level',arg:'Rack scale'});
assert.deepEqual(parseRoute('hardware/timeline'),{view:'hardware',sub:'timeline',arg:''});
assert.deepEqual(parseRoute('#hardware/level'),{view:'hardware',sub:'',arg:''});
assert.deepEqual(parseRoute('#hardware/bogus/x'),{view:'hardware',sub:'',arg:''});
assert.deepEqual(parseRoute('#news/uae'),{view:'news',sub:'uae',arg:''});
assert.deepEqual(parseRoute('#uae/f/stargate-uae-announcement'),{view:'uae',sub:'f',arg:'stargate-uae-announcement'});
assert.deepEqual(parseRoute('#contact/level/Personal'),{view:'contact',sub:'',arg:''});
// No-JavaScript anchors (#p-<id>, #fact-<id>, #estimator) open the right view when JavaScript is on.
assert.deepEqual(parseRoute('#p-h200'),{view:'hardware',sub:'p',arg:'h200'});
assert.deepEqual(parseRoute('#fact-jais-arabic-llm'),{view:'uae',sub:'f',arg:'jais-arabic-llm'});
assert.deepEqual(parseRoute('#estimator'),{view:'hardware',sub:'run',arg:''});
const known={levels:['Personal','Rack scale'],vendors:['NVIDIA','AMD'],products:data.products.map(p=>p.id),facts:['jais-arabic-llm']};
let rp=routePatch(parseRoute('#hardware/level/Personal'),known);
assert.deepEqual(rp,{patch:{q:'',vendor:'',level:'Personal',scope:'',fit:false},hash:'hardware',focus:null});
assert.deepEqual(routePatch(parseRoute('#hardware/level/Evil'),known),{patch:{},hash:'hardware',focus:null});
assert.equal(routePatch(parseRoute('#hardware/vendor/AMD'),known).patch.vendor,'AMD');
// A product or a key fact keeps its deep link in the address (shareable); other deep links are reduced to the view.
rp=routePatch(parseRoute('#p-h200'),known);assert.equal(rp.focus,'p-h200');assert.equal(rp.patch.view,'cards');assert.equal(rp.hash,'hardware/p/h200');
assert.equal(routePatch(parseRoute('#hardware/p/h200'),known).hash,'hardware/p/h200');assert.equal(routePatch(parseRoute('#hardware/p/unknown'),known).hash,'hardware');
assert.equal(routePatch(parseRoute('#hardware/p/unknown'),known).focus,null);
assert.deepEqual(routePatch(parseRoute('#hardware/timeline'),known).patch,{view:'timeline'});
assert.equal(routePatch(parseRoute('#hardware/run'),known).focus,'estimator');
assert.equal(routePatch(parseRoute('#hardware/compare'),known).focus,'compare');
assert.deepEqual(routePatch(parseRoute('#news/all'),known).patch,{region:''});
assert.deepEqual(routePatch(parseRoute('#news/global'),known).patch,{region:'global'});
assert.equal(routePatch(parseRoute('#uae/f/jais-arabic-llm'),known).focus,'fact-jais-arabic-llm');
assert.equal(routePatch(parseRoute('#uae/f/jais-arabic-llm'),known).hash,'uae/f/jais-arabic-llm');assert.equal(routePatch(parseRoute('#fact-jais-arabic-llm'),known).hash,'uae/f/jais-arabic-llm');
assert.equal(routePatch(parseRoute('#uae/f/nope'),known).focus,null);assert.equal(routePatch(parseRoute('#uae/f/nope'),known).hash,'uae');
assert.equal(routePatch(parseRoute('#hardware/run'),known).hash,'hardware');assert.equal(routePatch(parseRoute('#hardware/level/Personal'),known).hash,'hardware');
assert.equal(routePatch(parseRoute('#nope'),known).hash,'home');
// About Cipher Lacuna: #contact/about (and the plain #about anchor used without JavaScript) opens #contact at the section.
assert.deepEqual(parseRoute('#contact/about'),{view:'contact',sub:'about',arg:''});
assert.deepEqual(parseRoute('#about'),{view:'contact',sub:'about',arg:''});
assert.deepEqual(parseRoute('#contact/about','?q=4090'),{view:'contact',sub:'about',arg:''});
assert.deepEqual(parseRoute('#contact/nope'),{view:'contact',sub:'',arg:''});
assert.deepEqual(routePatch(parseRoute('#contact/about'),known),{patch:{},hash:'contact',focus:'about'});
assert.deepEqual(routePatch(parseRoute('#about'),known),{patch:{},hash:'contact',focus:'about'});
assert.deepEqual(routePatch(parseRoute('#contact'),known),{patch:{},hash:'contact',focus:null});
assert.equal(routePatch(parseRoute('#news/about'),known).focus,null);
// Copy link = path + query-string state + view hash.
assert.equal(pageUrl('/ai-hardware-atlas/','q=mi3&view=table','hardware'),'/ai-hardware-atlas/?q=mi3&view=table#hardware');
assert.equal(pageUrl('/','','home'),'/#home');
const st2={...decodeState('?q=gb300&view=timeline&lang=ar'),region:'uae'};
assert.equal(pageUrl('/',encodeState(st2),'news'),'/?q=gb300&view=timeline&lang=ar&region=uae#news');
assert.equal(decodeState('?region=uae').region,'uae');assert.equal(decodeState('?region=mars').region,'');
assert.deepEqual(decodeState(encodeState(st2)),{...st2});
// Counts: English plural, Arabic number agreement.
assert.equal(countLabel(1,'product','en'),'1 product');assert.equal(countLabel(53,'product','en'),'53 products');
assert.equal(countLabel(1,'headline','ar'),'عنوان واحد');assert.equal(countLabel(2,'product','ar'),'منتجان');
assert.equal(countLabel(5,'product','ar'),'5 منتجات');assert.equal(countLabel(53,'product','ar'),'53 منتجاً');
assert.equal(countLabel(100,'headline','ar'),'100 عنوان');assert.equal(countLabel(103,'headline','ar'),'103 عناوين');assert.equal(countLabel(0,'headline','ar'),'0 عنوان');
// Legacy links (query string, no hash) open the hardware atlas; a lone region opens the news; lang alone stays home.
const {when,HW_KEYS}=require('../web/app.js');
for(const q of ['?q=4090','?cmp=h200,b200-blackwell','?view=table&sort=memory_gb&dir=desc','?vendor=AMD&lang=ar','?p=70&bits=8','?m=OpenAI%3A+gpt-oss-120b','?fit=1','?extra=30','?level=Personal','?scope=Per+GPU'])
  assert.deepEqual(parseRoute('',q),{view:'hardware',sub:'',arg:''},q);
assert.equal(parseRoute('','?region=uae').view,'news');assert.equal(parseRoute('#nope','?region=uae&lang=ar').view,'news');
assert.equal(parseRoute('','?lang=ar').view,'home');assert.equal(parseRoute('','').view,'home');
assert.equal(parseRoute('#news','?q=4090').view,'news');assert.equal(parseRoute('#home','?q=4090').view,'home');
assert.equal(parseRoute('#nope','?q=4090').view,'hardware');
// The head script in template.html must use the same keys, so the first paint shows the same view.
const tpl=require('node:fs').readFileSync(require('node:path').join(__dirname,'../web/template.html'),'utf8');
const keys=/\[\?&\]\(([a-z|]+)\)\(=\|&\|\$\)/.exec(tpl);assert.ok(keys,'head script key list');
assert.deepEqual(keys[1].split('|').sort(),[...HW_KEYS].sort());
assert.ok(tpl.includes("h==='about'||h==='android'?'contact'"),'head script maps #about and #android to the contact view');
// The Android app card: #android (no-JavaScript anchor) and #contact/android open the contact view and bring the card into view.
for(const h of ['#android','#contact/android']){const r=parseRoute(h,'');assert.deepEqual(r,{view:'contact',sub:'android',arg:''},h);assert.deepEqual(routePatch(r,known),{patch:{},hash:'contact',focus:'android'},h);}
assert.equal(routePatch(parseRoute('#contact/about',''),known).focus,'about');
assert.equal(pageUrl('/','q=4090',''),'/?q=4090');assert.equal(pageUrl('/','',''),'/');
// Arabic agreement with formatted numbers; dates for people (same cases as tests/test_build.py).
assert.equal(countLabel(131072,'token','ar',n=>n.toLocaleString('en-US')),'131,072 رمزاً');assert.equal(countLabel(8192,'token','en',n=>n.toLocaleString('en-US')),'8,192 tokens');
assert.equal(countLabel(100,'token','ar'),'100 رمز');
const cases={'2025-Q3|en':'Q3 2025','2025-Q3|ar':'الربع الثالث 2025','2026-H2|ar':'النصف الثاني 2026','2025-Summer|en':'Summer 2025','2025-Summer|ar':'صيف 2025',
  '2026-end|en':'End of 2026','2026-end|ar':'نهاية 2026','2025-03-05|en':'5 Mar 2025','2025-03-05|ar':'5 مارس 2025','2023-07|en':'Jul 2023','2026-09-26T22:30:00+00:00|ar':'27 سبتمبر 2026'};
for(const [k,want] of Object.entries(cases)){const [v,lang]=k.split('|');assert.equal(when(v,lang),want,k);}
assert.equal(when('soon','en'),'soon');
console.log('PASS: hash routes, legacy query links, deep links, canonical URL, region state, count labels, dates');
// AI models in the hardware search: the Android app's EstimatorText.search rules, on a small sample and on the real list.
const {searchModels,modelSuggestions}=require('../web/app.js');
const names=list=>list.map(m=>m.n);
const sample=[{n:'OpenAI: GPT-3.5 Turbo',hf:null},{n:'OpenAI: GPT-5.1',hf:null},{n:'OpenAI: GPT-5',hf:null},{n:'OpenAI: gpt-oss-120b',hf:'openai/gpt-oss-120b'},
  {n:'OpenAI: o3 Mini',hf:null},{n:'OpenAI: GPT-4o',hf:null},{n:'Qwen2.5 72B Instruct',hf:'Qwen/Qwen2.5-72B-Instruct'},{n:'Qwen: Qwen3 32B',hf:'Qwen/Qwen3-32B'},
  {n:'DeepSeek: DeepSeek V3',hf:'deepseek-ai/DeepSeek-V3'},{n:'NVIDIA: Nemotron 3 Super',hf:'nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-FP8'},{n:'Auto Router',hf:null}];
assert.deepEqual(names(searchModels(sample,'')),names(sample));assert.deepEqual(names(searchModels(sample,'   ')),names(sample));  // blank: everything, in list order
assert.deepEqual(searchModels(sample,'-- ..'),[]);  // no words
assert.deepEqual(names(searchModels(sample,'gpt 5')),['OpenAI: GPT-5.1','OpenAI: GPT-5']);  // numbers whole: 5 and 5.1, never 3.5
assert.deepEqual(names(searchModels(sample,'gpt-5')),['OpenAI: GPT-5.1','OpenAI: GPT-5']);
assert.deepEqual(names(searchModels(sample,'o3')),['OpenAI: o3 Mini']);  // "o" then 3, not GPT-4o
assert.deepEqual(names(searchModels(sample,'qwen2.5')),['Qwen2.5 72B Instruct']);assert.deepEqual(names(searchModels(sample,'qwen3')),['Qwen: Qwen3 32B']);
assert.deepEqual(names(searchModels(sample,'qwe')),['Qwen2.5 72B Instruct','Qwen: Qwen3 32B']);  // the last letters may start a word
assert.deepEqual(names(searchModels(sample,'72b')),['Qwen2.5 72B Instruct']);assert.deepEqual(names(searchModels(sample,'32')),['Qwen: Qwen3 32B']);
assert.deepEqual(names(searchModels(sample,'seek')),['DeepSeek: DeepSeek V3']);  // letters inside a longer word only as a fallback
assert.deepEqual(names(searchModels(sample,'nvidia')),['NVIDIA: Nemotron 3 Super']);  // the Hugging Face id counts too
assert.deepEqual(names(searchModels(sample,'120b')),['OpenAI: gpt-oss-120b','NVIDIA: Nemotron 3 Super']);  // in the name (rank 1) before the Hugging Face id only (rank 3)
assert.deepEqual(names(searchModels(sample,'gpt')),['OpenAI: GPT-3.5 Turbo','OpenAI: GPT-5.1','OpenAI: GPT-5','OpenAI: gpt-oss-120b','OpenAI: GPT-4o']);
// Ranks: 0 the name (after "Maker: ") starts with the query, 1 the name has every query word, 2 the maker starts with it, 3 the rest (Hugging Face id).
const ranked=[{n:'Zed: Thing',hf:'beta/thing'},{n:'Beta Corp: Alpha',hf:null},{n:'Maker: Alpha Beta',hf:null},{n:'Gamma: Alphabeta',hf:null},{n:'Other: Beta Alpha',hf:null},{n:'Beta Two',hf:null}];
assert.deepEqual(names(searchModels(ranked,'beta')),['Other: Beta Alpha','Beta Two','Maker: Alpha Beta','Beta Corp: Alpha','Zed: Thing']);
assert.deepEqual(names(searchModels(ranked,'phabet')),['Maker: Alpha Beta','Gamma: Alphabeta']);  // fallback (nothing matched word by word): inside the joined parts, across words
assert.deepEqual(names(searchModels(sample,'openai o')),['OpenAI: GPT-3.5 Turbo','OpenAI: GPT-5.1','OpenAI: GPT-5','OpenAI: gpt-oss-120b','OpenAI: o3 Mini','OpenAI: GPT-4o']);  // "o" starts "openai": all rank 2, list order
for(const q of ['H100','MI300X','RTX 4090','80GB','بطاقة','zz'])assert.deepEqual(searchModels(sample,q),[],q);
assert.deepEqual(modelSuggestions(sample,''),[]);assert.deepEqual(modelSuggestions(sample,' q '),[]);assert.deepEqual(modelSuggestions(sample,'o'),[]);
assert.deepEqual(names(modelSuggestions(sample,'o3')),['OpenAI: o3 Mini']);assert.deepEqual(modelSuggestions(null,'qwen'),[]);
// The real list, in the page's slim shape (scripts/build.py render_page).
const real=require('../data/models.json').models.map(m=>({n:m.name,b:m.params_b,o:m.open,s:m.params_source,moe:m.moe||false,c:m.context,hf:m.hf}));
// The list is refreshed from OpenRouter with every scheduled run, so counts come from the data, not fixed numbers
// (a 7th NVIDIA model on 3 Oct 2026 failed four runs while this test expected exactly 6).
const own=m=>m.n.includes(': ')?m.n.slice(m.n.indexOf(': ')+2):m.n;  // the name after "Maker: "
let hits=modelSuggestions(real,'qwen');assert.equal(hits.length,real.filter(m=>/qwen/i.test(m.n)).length);assert.ok(hits.length>=20,'qwen finds the Qwen family');
assert.ok(/^qwen/i.test(own(hits[0])),'a name that starts with Qwen comes first');
const coder=real.find(m=>m.n==='Qwen2.5 Coder 32B Instruct');if(coder)assert.ok(hits.some(m=>m.n===coder.n&&m.b===coder.b));
assert.equal(modelSuggestions(real,'Qwen').length,hits.length);
hits=modelSuggestions(real,'gpt 5');assert.ok(hits.length>0&&/^gpt-5/i.test(own(hits[0])),'gpt 5 lists GPT-5 first');assert.ok(hits.every(m=>!/3\.5/.test(m.n)),'gpt 5 never lists GPT-3.5');
assert.deepEqual(names(modelSuggestions(real,'o3')).sort(),real.filter(m=>/^o3( |$)/i.test(own(m))&&/^OpenAI:/.test(m.n)).map(m=>m.n).sort());
for(const q of ['gemma 2b','llama 7b','MI3','B2','H2','L4','H100','RTX 4090','MI300X','B200','DGX Spark','80GB','بطاقة'])assert.deepEqual(modelSuggestions(real,q),[],q);
hits=modelSuggestions(real,'seek');assert.ok(hits.length>0&&hits.every(m=>/deepseek/i.test(m.n+' '+(m.hf||''))),'seek -> DeepSeek');
hits=modelSuggestions(real,'qwen3');assert.ok(hits.length>0&&!hits.some(m=>m.n==='Qwen2.5 Coder 32B Instruct'),'qwen3 never lists Qwen2.5 Coder 32B');
hits=modelSuggestions(real,'nvidia');assert.equal(hits.length,real.filter(m=>/nvidia/i.test(m.n)).length);assert.ok(hits.length>0&&hits.every(m=>m.n.startsWith('NVIDIA:')));
console.log('PASS: AI models in the hardware search (sample and real list)');
// News search (#news, #uae): one normalizer and matcher for the site and the Android app. These cases are shared: keep
// them identical to app/src/test/java/io/github/buafra/cipherlacuna/ui/news/NewsSearchTest.kt in cipher-lacuna-android.
const {normText,searchWords,matchesWords}=require('../web/app.js');
const NORM=[
  ['Café  NVIDIA','cafe nvidia'],
  ['أإآٱ','اااا'],
  ['الذّكَاءُ','الذكاء'],
  ['ـالـذكـاء','الذكاء'],
  ['مدرسة على','مدرسه علي'],
  ['مسؤول هيئة','مسوول هييه'],
  ['٢٠٢٦ ۱۲','2026 12'],
  ['GPT\u20115.1 — «Falcon»','gpt 5 1 falcon'],
  ['\u2068NVIDIA\u2069','nvidia'],
  ['کی','كي'],
  ['ڤپگچ','فبكج'],
  ['ڤيديو','فيديو'],
  ['پگچ','بكج'],
];
for(const [input,want] of NORM)assert.equal(normText(input),want,'normText '+JSON.stringify(input));
const WORDS=[['a',[]],['  ,. ',[]],['',[]],[' إنفيديا  H200 ',['انفيديا','h200']]];
for(const [input,want] of WORDS)assert.deepEqual(searchWords(input),want,'searchWords '+JSON.stringify(input));
const MATCH=[
  ['nvidia','NVIDIA ships a new chip',true],
  ['cafe','Café opens',true],
  ['ذكاء','الذكاء الاصطناعي',true],
  ['اخطاء','أخطاء شائعة',true],
  ['انفيديا','إنفيديا تطرح شريحة',true],
  ['مدينه','مدينة مصدر',true],
  ['علي','على الإنترنت',true],
  ['مسوول','مسؤول',true],
  ['٢٠٢٦','in 2026',true],
  ['2026','عام ٢٠٢٦',true],
  ['gpt-5','OpenAI releases GPT 5',true],
  ['openai gpt','OpenAI releases GPT-5',true],
  ['openai google','OpenAI releases GPT-5',false],
  ['falcon','«Falcon» من معهد الابتكار التكنولوجي',true],
  ['nvidia','إنفيديا تطرح',false],
  ['gpt5','OpenAI releases GPT-5',true],
  ['2000','2,000 users',true],
  ['ڤيديو','فيديو جديد',true],
  ['فيديو','ڤيديو جديد',true],
  ['بيتزا','پيتزا',true],
  ['جيكابايت','چيگابايت',true],
];
for(const [q,text,want] of MATCH)assert.equal(matchesWords(normText(text),searchWords(q)),want,`${q} / ${text}`);
// Limits: nothing below 2 characters, 100 characters at most (a longer query is cut, never an error).
assert.deepEqual(searchWords('ذ'),[]);assert.deepEqual(searchWords('٢'),[]);assert.deepEqual(searchWords('ab'),['ab']);
assert.deepEqual(searchWords('x'.repeat(150)),['x'.repeat(100)]);
assert.equal(matchesWords('anything',[]),true);
// The searches in the URL: ?nq= (AI news) and ?uq= (UAE AI), trimmed and cut to 100 characters; empty ones are left out.
// Without a hash they open their view (the head script in template.html agrees); hardware keys still win.
assert.equal(parseRoute('','?nq=g42').view,'news');assert.equal(parseRoute('#nope','?uq=x&lang=ar').view,'uae');
assert.equal(parseRoute('','?q=4090&nq=x').view,'hardware');assert.equal(parseRoute('','?nq=x&uq=y').view,'news');
assert.equal(parseRoute('','?region=global&uq=x').view,'news');assert.equal(parseRoute('#uae','?nq=x').view,'uae');
assert.equal(decodeState(encodeState({...decodeState(''),nq:'  إنفيديا '})).nq,'إنفيديا');
assert.equal(encodeState({...decodeState(''),nq:''}),'');assert.equal(encodeState({...decodeState(''),nq:'   '}),'');
assert.equal(encodeState({...decodeState(''),uq:'falcon ',lang:'ar'}),'lang=ar&uq=falcon');
assert.equal(decodeState('?uq='+'x'.repeat(150)).uq.length,100);assert.equal(decodeState('?nq=%20g42%20').nq,'g42');
assert.equal(decodeState('').nq,'');assert.equal(decodeState('').uq,'');
assert.ok(!HW_KEYS.includes('nq')&&!HW_KEYS.includes('uq'),'?q= stays the hardware search');
assert.ok(tpl.includes("/[?&](region|nq|nt)(=|&|$)/.test(s)?'news':/[?&]uq(=|&|$)/.test(s)?'uae':'home'"),'head script opens the news and UAE views for ?nq=, ?nt= and ?uq=');
console.log('PASS: news search (normalizer, words, matching, URL state, implied views)');
// Language pages (scripts/lang_pages.py): / is English and /ar/ Arabic, so the address app.js writes never repeats the
// language (urlQuery() encodes the state with the default lang), and the language link carries the view and the filters
// to the other page. A legacy ?lang=ar still decodes, so the head script can send it on.
{
  const st={...decodeState('?lang=ar&q=h100&vendor=NVIDIA&nq=openai'),lang:'en'};
  const qs=encodeState(st);
  assert.ok(!/(^|&)lang=/.test(qs),qs);assert.equal(qs,'q=h100&vendor=NVIDIA&nq=openai');
  assert.equal(pageUrl('../',qs,'hardware'),'../?q=h100&vendor=NVIDIA&nq=openai#hardware');
  assert.equal(pageUrl('ar/',encodeState({...decodeState(''),lang:'en'}),'news'),'ar/#news');
  assert.equal(decodeState('?lang=ar').lang,'ar');assert.equal(decodeState('?lang=xx').lang,'en');
  const app=require('node:fs').readFileSync(require('node:path').join(__dirname,'..','web','app.js'),'utf8');
  assert.ok(app.includes('function urlQuery() { return encodeState({...state, lang: DEFAULTS.lang}); }'),'the URL never carries the language');
  assert.ok(app.includes("langLink.setAttribute('href', pageUrl(langBase, urlQuery(), hashNow()));"),'the language link keeps the view (and a product or key-fact deep link) and the filters');
  assert.ok(app.includes(String.raw`langHref.replace(/(^|\/)index\.html$/, '$1')`),'over http(s) the link is /ar/ or /, not index.html');
  assert.ok(!tpl.includes("d.classList.add('i18n-wait')"),'no in-place Arabic: the head script sends the visit to /ar/');
  assert.ok(tpl.includes('__LANG_JS__'),'the language rule runs first in the head script');
}
console.log('PASS: language pages (URL without lang, language link, legacy ?lang=)');
// Topic chips in AI news: ?nt= holds a topic id of scripts/topics.py, kept with the other news state; it opens AI news.
assert.equal(decodeState('?nt=models').nt,'models');assert.equal(decodeState('').nt,'');
for(const bad of ['?nt=Models','?nt=x','?nt=a%20b','?nt=%3Cscript%3E','?nt='+'a'.repeat(30)])assert.equal(decodeState(bad).nt,'',bad);
assert.equal(encodeState({...decodeState(''),nt:'hardware',region:'uae',nq:'g42'}),'region=uae&nq=g42&nt=hardware');
assert.deepEqual(decodeState(encodeState({...decodeState(''),nt:'robotics',lang:'ar'})),{...decodeState(''),nt:'robotics',lang:'ar'});
assert.equal(parseRoute('','?nt=models').view,'news');assert.equal(parseRoute('','?q=4090&nt=models').view,'hardware');
assert.ok(!HW_KEYS.includes('nt'),'?nt= is not a hardware key');
console.log('PASS: topic chips URL state');
// Share buttons: a story shares "<headline> — via cipherlacuna.ae" and the original link; products and facts their own deep link.
const {sharePayload,deepLink,olderView,olderMatches}=require('../web/app.js');
assert.deepEqual(sharePayload('story','  NVIDIA ships\n a chip ','https://pub.example/a','en'),
  {title:'NVIDIA ships a chip',text:'NVIDIA ships a chip — via cipherlacuna.ae',url:'https://pub.example/a',copy:'NVIDIA ships a chip — via cipherlacuna.ae https://pub.example/a'});
assert.equal(sharePayload('story','إنفيديا تطرح شريحة','https://pub.example/b','ar').text,'إنفيديا تطرح شريحة — عبر cipherlacuna.ae');
assert.equal(sharePayload('story','Startup raises $& and $1','https://x.example/','en').text,'Startup raises $& and $1 — via cipherlacuna.ae');  // never a replacement pattern
assert.deepEqual(sharePayload('product','H200 · Cipher Lacuna','https://cipherlacuna.ae/#hardware/p/h200','en'),{title:'H200 · Cipher Lacuna',url:'https://cipherlacuna.ae/#hardware/p/h200',copy:'https://cipherlacuna.ae/#hardware/p/h200'});
assert.equal(deepLink('https://cipherlacuna.ae/','hardware/p/h200'),'https://cipherlacuna.ae/#hardware/p/h200');
// The Arabic page's address says its language (/ar/), so its deep links never carry ?lang=.
assert.equal(deepLink('https://cipherlacuna.ae/ar/','uae/f/jais-arabic-llm'),'https://cipherlacuna.ae/ar/#uae/f/jais-arabic-llm');
console.log('PASS: share payloads and deep links');
// Older stories (dist/news-archive/): the card's text per language and the matcher, the same rules as the current list.
const SRCS={g:{name:'Global Pub',name_ar:'ناشر عالمي',region:'global'},u:{name:'Gulf Daily',name_ar:'صحيفة الخليج',region:'uae'},a:{name:'Arabic Pub',name_ar:'ناشر عربي',region:'uae'}};
const OLD=[
  {id:'1',source:'g',lang:'en',uae:false,topic:'hardware',published:'2026-09-20T10:00:00+00:00',title:'NVIDIA ships a new GPU',title_ar:'إنفيديا تشحن معالجاً جديداً',url:'https://g.example/1',summary_en:'The H300 has 300 GB.',summary_ar:'المعالج H300 بذاكرة 300 جيجابايت.',excerpt:null},
  {id:'2',source:'u',lang:'en',uae:true,topic:'uae',published:'2026-09-19T10:00:00+00:00',title:'Abu Dhabi opens AI campus',title_ar:null,url:'https://u.example/2',summary_en:null,summary_ar:null,excerpt:'A campus for 2,000 students.'},
  {id:'3',source:'a',lang:'ar',uae:true,topic:'education',published:'2026-09-18T10:00:00+00:00',title:'دبي تطلق برنامجاً للذكاء الاصطناعي',title_ar:null,url:'https://a.example/3',summary_en:'Dubai launches an AI programme.',summary_ar:'أطلقت دبي برنامجاً جديداً.',excerpt:'نص الناشر.'},
  {id:'4',source:'u',lang:'en',uae:false,topic:'models',published:'2026-09-17T10:00:00+00:00',title:'OpenAI releases GPT-5',title_ar:null,url:'https://u.example/4',summary_en:null,summary_ar:null,excerpt:null},
];
let ov=olderView(OLD[0],'ar',SRCS);assert.deepEqual(ov,{title:'إنفيديا تشحن معالجاً جديداً',summary:'المعالج H300 بذاكرة 300 جيجابايت.',kind:'ai',mt:true,publisher:'ناشر عالمي'});
ov=olderView(OLD[1],'en',SRCS);assert.deepEqual([ov.summary,ov.kind,ov.mt,ov.publisher],['A campus for 2,000 students.','publisher',false,'Gulf Daily']);
ov=olderView(OLD[1],'ar',SRCS);assert.deepEqual([ov.title,ov.summary,ov.kind],['Abu Dhabi opens AI campus','','']);  // an English excerpt never stands in for Arabic
ov=olderView(OLD[2],'ar',SRCS);assert.deepEqual([ov.summary,ov.kind,ov.mt],['أطلقت دبي برنامجاً جديداً.','ai',false]);
const ids=o=>olderMatches(OLD,SRCS,{lang:'en',view:'news',...o}).map(i=>i.id);
assert.deepEqual(ids({terms:[]}),[]);  // no search: nothing listed
assert.deepEqual(ids({terms:searchWords('nvidia')}),['1']);assert.deepEqual(ids({terms:searchWords('h300')}),['1']);  // the summary counts
assert.deepEqual(ids({terms:searchWords('gulf daily')}),['2','4']);  // the publisher counts
assert.deepEqual(ids({terms:searchWords('2000 students')}),['2']);  // "2,000" across punctuation
assert.deepEqual(ids({terms:searchWords('gpt5')}),['4']);
assert.deepEqual(ids({terms:searchWords('gulf'),region:'uae'}),['2']);assert.deepEqual(ids({terms:searchWords('gulf'),region:'global'}),['4']);  // a UAE outlet's world story is global
assert.deepEqual(ids({terms:searchWords('gulf'),topic:'models'}),['4']);
assert.deepEqual(olderMatches(OLD,SRCS,{lang:'en',view:'uae',terms:searchWords('gulf'),topic:'models',region:'global'}).map(i=>i.id),['2']);  // UAE AI: UAE stories, no chips
assert.deepEqual(olderMatches(OLD,SRCS,{lang:'ar',view:'news',terms:searchWords('دبي')}).map(i=>i.id),['3']);
assert.deepEqual(olderMatches(OLD,SRCS,{lang:'ar',view:'news',terms:searchWords('انفيديا')}).map(i=>i.id),['1']);  // the AI translation in Arabic
assert.deepEqual(olderMatches(OLD,SRCS,{lang:'ar',view:'news',terms:searchWords('campus')}).map(i=>i.id),[]);  // not in the Arabic list
console.log('PASS: older stories (archive) card text and matching');
