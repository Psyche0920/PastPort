import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {messages,turkishMessages,translate,setLanguage,getLanguage} from '../frontend/organizer/i18n.mjs';
import {DisplayLexicon,templateParts} from '../frontend/player/game-display-locale.mjs';
const catalog=JSON.parse(await readFile(new URL('../frontend/player/game-display-locales.json',import.meta.url),'utf8'));
const lexicon=new DisplayLexicon(catalog);
test('Organizer Turkish catalog covers every English key and preserves project identities',()=>{
 assert.deepEqual(Object.keys(turkishMessages).sort(),Object.keys(messages).sort());
 for(const key of Object.keys(messages)){assert.equal(typeof turkishMessages[key],'string');assert.ok(turkishMessages[key].trim());assert.doesNotMatch(turkishMessages[key],/[\u3400-\u9fff]/u);}
 setLanguage('tr');assert.equal(getLanguage(),'tr');assert.equal(translate('制作游戏'),'Oyun oluştur');
 assert.equal(translate('wcheung · 当前第 3 版'),'wcheung · geçerli sürüm 3');
 assert.equal(translate('/Users/test/muradiye/game-3d'),'/Users/test/muradiye/game-3d');setLanguage('zh');
});
test('player shell translates Turkish text, dynamic save statuses and errors',async()=>{
 // The served app keeps its catalog inline so an already-running static host needs no new route.
 const source=await readFile(new URL('../frontend/player/app.mjs',import.meta.url),'utf8');
 const catalogModule=await import('data:text/javascript;base64,'+Buffer.from(source.slice(0,source.indexOf("import {SaveSynchronizer}"))).toString('base64'));
 const t=catalogModule.playerText;
 assert.equal(t('排行榜','Leaderboard','tr'),'Sıralama');assert.equal(t('已恢复账号进度','Account progress restored','tr'),'Hesap ilerlemesi geri yüklendi');
 assert.equal(t('错误','Incorrect username or password.','tr'),'Kullanıcı adı veya parola yanlış.');
 assert.equal(t('你好','Hello','zh'),'你好');assert.equal(t('你好','Hello','en'),'Hello');assert.throws(()=>t('未知','Missing entry','tr'),/Missing Turkish/);
});
test('all game display entries have three complete languages and simplified Chinese',()=>{
 assert.ok(catalog.entries.length>900);
 for(const entry of catalog.entries){for(const lang of ['zh','en','tr'])assert.ok(entry[lang]?.trim());for(const lang of ['en','tr'])assert.doesNotMatch(entry[lang],/[\u3400-\u9fff]/u);}
 assert.equal(lexicon.translate('展開簽收賬','zh'),'展开签收账');
 assert.equal(lexicon.translate('展开签收账','tr'),'Teslimat defterini aç');
 assert.equal(lexicon.translate('走近管事交谈','en'),'Approach Steward to talk');
 assert.equal(lexicon.translate('走近管事交谈','tr'),'Görevli ile konuşmak için yaklaş');
 assert.equal(lexicon.translate('PastPort · 最后两袋 · 可行走剧场','en'),'PastPort · The Last Two Sacks · Walkable theatre');
});
test('display language changes preserve event logs, identifiers and numeric task values',()=>{
 const save={version:'muradiye-walk-1',chapter_id:'chapter-record-and-service',events:[{kind:'inspect',args:['pool']}]};const frozen=JSON.stringify(save);
 for(const lang of ['zh','en','tr']){assert.equal(lexicon.translate('chapter-record-and-service',lang),'chapter-record-and-service');assert.equal(lexicon.translate('012 / 017',lang),'012 / 017');assert.equal(JSON.stringify(save),frozen);}
 assert.deepEqual(templateParts('Perde ${one} / ${two}').chunks,['Perde ',' / ','']);
 assert.throws(()=>lexicon.translate('abc','de'),RangeError);
});

test('game-origin language requests require the active frame, origin, run and a supported language',async()=>{
 const sourceText=await readFile(new URL('../frontend/player/app.mjs',import.meta.url),'utf8');
 const module=await import('data:text/javascript;base64,'+Buffer.from(sourceText.slice(0,sourceText.indexOf('import {SaveSynchronizer}'))).toString('base64'));
 const frame={},context={source:frame,origin:'http://game.local',run:'active-run'};
 const event={source:frame,origin:context.origin,data:{type:'pastport:language-change',run:context.run,locale:'tr'}};
 assert.equal(module.requestedGameLanguage(event,context),'tr');
 for(const invalid of [{...event,source:{}},{...event,origin:'http://other.local'},{...event,data:{...event.data,run:'stale-run'}},{...event,data:{...event.data,locale:'de'}},{...event,data:{...event.data,type:'other'}}])assert.equal(module.requestedGameLanguage(invalid,context),null);
});

test('nested game views follow language and release their mounts/listeners on navigation',async()=>{
 const {SameOriginFrameLocalizations}=await import('../frontend/player/game-display-locale.mjs');
 let document={body:{},URL:'http://game.local/world/1'},frameListeners=new Map(),live=[];const mounts=[];
 const frame={get contentDocument(){return document;},addEventListener:(type,fn)=>frameListeners.set(type,fn),removeEventListener:(type)=>frameListeners.delete(type)};
 const controller=new SameOriginFrameLocalizations({querySelectorAll:()=>live},(doc,locale)=>{const value={locale,closed:false,setLocale(next){this.locale=next;},close(){this.closed=true;}};mounts.push(value);return value;});
 live=[frame];controller.sync('tr');assert.equal(mounts.length,1);assert.equal(mounts[0].locale,'tr');
 controller.sync('en');assert.equal(mounts.length,1);assert.equal(mounts[0].locale,'en');
 document={body:{},URL:'http://game.local/world/2'};frameListeners.get('load')();assert.equal(mounts[0].closed,true);assert.equal(mounts.length,2);
 live=[];controller.sync('zh');assert.equal(mounts[1].closed,true);assert.equal(frameListeners.size,0);
 document=null;live=[frame];controller.sync('zh');assert.equal(mounts.length,2);controller.close();assert.equal(frameListeners.size,0);
});

test('The Last Tour catalog contains localized case-card assets and stable actor/evidence names',()=>{
 assert.equal(lexicon.translate('The Last Tour','tr'),'Son Tur');
 assert.equal(lexicon.translate('I withdraw approval for this version.','tr'),'Bu sürüm için verdiğim onayı geri çekiyorum.');
 assert.equal(lexicon.translate('I withdraw approval for this version.','zh'),'我撤回对这一版的批准。');
 assert.deepEqual(Object.keys(catalog.display_assets['assets/investigation/chat-zh.svg']),['zh','en','tr']);
 for(const source of ['assets/investigation/chat-zh.svg','assets/investigation/chat-en.svg'])for(const lang of ['zh','en','tr'])assert.equal(catalog.display_assets[source][lang],`assets/i18n/${lang}/chat.svg`);
});


test('compound 3D quality, view and short object labels never retain Chinese in Turkish mode',()=>{
 assert.equal(lexicon.translate('畫面品質：低','tr'),'Görüntü kalitesi: Düşük');
 assert.equal(lexicon.translate('畫面品質：標準','tr'),'Görüntü kalitesi: Standart');
 assert.equal(lexicon.translate('場景 1','tr'),'Görünüm 1');
 assert.doesNotMatch(lexicon.translate('05 · 電腦','tr'),/[\u3400-\u9fff]/u);
});

test('map game names use actual publication versions and preserve older-release identity',async()=>{
 const source=await readFile(new URL('../frontend/player/app.mjs',import.meta.url),'utf8');
 const module=await import('data:text/javascript;base64,'+Buffer.from(source.slice(0,source.indexOf('import {SaveSynchronizer}'))).toString('base64'));
 const title=module.publishedGameTitle;
 const tour='839c304f27ecc6f3496ba5a58aacb56f29c5d1bfc907e862823f91509d8b1358';
 const sacks='812d71853b4c1c2f16ed80267b4b2d020f497f7bbf32600ffa83ab514c0233ce';
 for(const lang of ['zh','en','tr']){
  assert.match(title(tour,lang),/The Last Tour/);
  assert.doesNotMatch(title(tour,lang),/Two Sacks|最后两袋|UI Trial/);
  assert.match(title(sacks,lang),lang==='zh'?/最后两袋.*三语/:/The Last Two Sacks/);
  if(lang!=='zh')assert.doesNotMatch(title(sacks,lang),/[\u3400-\u9fff]/u);
 }
 const old=title('1730505587e81ddfda0d6d64f8738c2f0c6fab34c629c58f04376cbba04ada1f','en');
 assert.match(old,/archive/);assert.doesNotMatch(old,/Trilingual/);
 assert.equal(title('unknown-release','en'),null);
 assert.equal(title('42heilbronn','en'),null);
 assert.throws(()=>title(tour,'de'),RangeError);
});
