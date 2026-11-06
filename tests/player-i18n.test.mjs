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
