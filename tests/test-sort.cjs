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
rp=routePatch(parseRoute('#p-h200'),known);assert.equal(rp.focus,'p-h200');assert.equal(rp.patch.view,'cards');assert.equal(rp.hash,'hardware');
assert.equal(routePatch(parseRoute('#hardware/p/unknown'),known).focus,null);
assert.deepEqual(routePatch(parseRoute('#hardware/timeline'),known).patch,{view:'timeline'});
assert.equal(routePatch(parseRoute('#hardware/run'),known).focus,'estimator');
assert.equal(routePatch(parseRoute('#hardware/compare'),known).focus,'compare');
assert.deepEqual(routePatch(parseRoute('#news/all'),known).patch,{region:''});
assert.deepEqual(routePatch(parseRoute('#news/global'),known).patch,{region:'global'});
assert.equal(routePatch(parseRoute('#uae/f/jais-arabic-llm'),known).focus,'fact-jais-arabic-llm');
assert.equal(routePatch(parseRoute('#uae/f/nope'),known).focus,null);
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
assert.ok(tpl.includes("h==='about'?'contact'"),'head script maps #about to the contact view');
assert.equal(pageUrl('/','q=4090',''),'/?q=4090');assert.equal(pageUrl('/','',''),'/');
// Arabic agreement with formatted numbers; dates for people (same cases as tests/test_build.py).
assert.equal(countLabel(131072,'token','ar',n=>n.toLocaleString('en-US')),'131,072 رمزاً');assert.equal(countLabel(8192,'token','en',n=>n.toLocaleString('en-US')),'8,192 tokens');
assert.equal(countLabel(100,'token','ar'),'100 رمز');
const cases={'2025-Q3|en':'Q3 2025','2025-Q3|ar':'الربع الثالث 2025','2026-H2|ar':'النصف الثاني 2026','2025-Summer|en':'Summer 2025','2025-Summer|ar':'صيف 2025',
  '2026-end|en':'End of 2026','2026-end|ar':'نهاية 2026','2025-03-05|en':'5 Mar 2025','2025-03-05|ar':'5 مارس 2025','2023-07|en':'Jul 2023','2026-09-26T22:30:00+00:00|ar':'27 سبتمبر 2026'};
for(const [k,want] of Object.entries(cases)){const [v,lang]=k.split('|');assert.equal(when(v,lang),want,k);}
assert.equal(when('soon','en'),'soon');
console.log('PASS: hash routes, legacy query links, deep links, canonical URL, region state, count labels, dates');
