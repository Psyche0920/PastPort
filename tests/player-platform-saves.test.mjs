import {spawn} from 'node:child_process';
import {createServer} from 'node:net';
import {once} from 'node:events';
import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';
import test from 'node:test';
import {DatabaseSync} from 'node:sqlite';
import {mkdir,mkdtemp,writeFile,rm} from 'node:fs/promises';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {PlayerSaveRepository,SaveConflict,InvalidSave} from '../frontend/player/cloud-saves.mjs';
import {SaveSynchronizer} from '../frontend/player/save-sync.mjs';
const snapshot=sequence=>JSON.stringify({version:2,identity:'a'.repeat(64),sequence,engine:{current_scene_id:'investigate'},local:{},notebook:[5],positions:{},shotState:null});
const write=(repository,revision,sequence=1,operation=crypto.randomUUID(),player='alice',version='v1')=>repository.write(player,'site',version,{revision,operation,changes:{save:snapshot(sequence)}},['save']);
function create(path=':memory:'){
  const db=new DatabaseSync(path);
  db.exec('PRAGMA foreign_keys=ON;CREATE TABLE IF NOT EXISTS player(id TEXT PRIMARY KEY);INSERT OR IGNORE INTO player VALUES ("alice"),("bob")'.replaceAll('"',"'"));
  return {db,repository:new PlayerSaveRepository(db)};
}
test('account, site and release isolate saves; stale writes cannot overwrite; retries are idempotent',()=>{
  const {db,repository:r}=create();
  try {
    const operation=crypto.randomUUID();
    assert.equal(write(r,0,1,operation).revision,1);
    assert.equal(write(r,0,1,operation).revision,1);
    assert.deepEqual(r.read('bob','site','v1').entries,{});
    assert.deepEqual(r.read('alice','other','v1').entries,{});
    assert.deepEqual(r.read('alice','site','v2').entries,{});
    assert.throws(()=>write(r,0,2),SaveConflict);
    assert.equal(JSON.parse(r.read('alice','site','v1').entries.save).sequence,1);
    assert.equal(write(r,1,2).revision,2);
    const removed=r.write('alice','site','v1',{revision:2,operation:crypto.randomUUID(),changes:{save:null}},['save']);
    assert.deepEqual(removed.entries,{});assert.equal(removed.revision,3);
  } finally {db.close();}
});
test('malformed, excessive and unknown save records are rejected without altering the previous snapshot',()=>{
  const {db,repository:r}=create();
  try {
    write(r,0);
    for(const changes of [{other:snapshot(1)},{save:'{'},{save:JSON.stringify({version:2})},{save:'x'.repeat(300001)}]){
      assert.throws(()=>r.write('alice','site','v1',{revision:1,operation:crypto.randomUUID(),changes},['save']),InvalidSave);
      assert.equal(r.read('alice','site','v1').revision,1);
    }
  }finally{db.close();}
});
test('SQLite recovery survives closing the service connection',async()=>{
  const directory=await mkdtemp(join(tmpdir(),'pastport-save-test-'));
  try {
    let value=create(join(directory,'players.sqlite'));
    write(value.repository,0,7);value.db.close();
    value=create(join(directory,'players.sqlite'));
    assert.equal(JSON.parse(value.repository.read('alice','site','v1').entries.save).sequence,7);
    value.db.close();
  } finally {await rm(directory,{recursive:true,force:true});}
});
test('failed writes keep their operation for retry; queued changes cannot overtake the failed batch',async()=>{
  const writes=[];let fail=true;
  const sync=new SaveSynchronizer({revision:0,status:()=>{},persist:async batch=>{
    writes.push(structuredClone(batch));if(fail)throw new Error('offline');return {revision:batch.revision+1};
  }});
  sync.queue('save',snapshot(1));await assert.rejects(sync.flush(),/offline/);
  sync.queue('save',snapshot(2));assert.equal(sync.dirty,true);fail=false;await sync.retry();
  assert.equal(writes[0].operation,writes[1].operation);
  assert.deepEqual(writes.map(w=>w.revision),[0,0,1]);
  assert.equal(JSON.parse(writes[2].changes.save).sequence,2);assert.equal(sync.dirty,false);
});
test('concurrent flushes serialize writes and preserve the newest snapshot',async()=>{
  let release;const writes=[];
  const barrier=new Promise(resolve=>{release=resolve;});
  const sync=new SaveSynchronizer({revision:0,status:()=>{},persist:async batch=>{writes.push(batch);if(writes.length===1)await barrier;return {revision:batch.revision+1};}});
  sync.queue('save',snapshot(1));const first=sync.flush();sync.queue('save',snapshot(2));const second=sync.flush();release();
  await Promise.all([first,second]);assert.deepEqual(writes.map(w=>w.revision),[0,1]);assert.equal(sync.revision,2);
});

test('HTTP saves require the correct login/run; resume after service restart and isolate release versions',async()=>{
  const directory=await mkdtemp(join(tmpdir(),'pastport-save-http-'));
  const organizer=join(directory,'organizer');const job='a'.repeat(32);const game=join(organizer,'jobs',job,'game');
  await mkdir(join(game,'data'),{recursive:true});
  await writeFile(join(game,'index.html'),'<html><script type="module" src="app.mjs"></script></html>');
  // Minimal protocol fixture; rendered gameplay is verified separately with the real bundle.
  await writeFile(join(game,'session.mjs'),'export class GameSession {snapshot(){return {};}}');
  await writeFile(join(game,'app.mjs'),'document.title="protocol fixture";');
  await writeFile(join(game,'data/presentation.json'),JSON.stringify({saveKey:'save'}));
  await writeFile(join(game,'data/scene3d-input.json'),JSON.stringify({worlds:[]}));
  const catalog=join(directory,'sites.json');await writeFile(catalog,JSON.stringify([{id:'site'}]));
  const publish=version=>writeFile(join(organizer,'player-map-site.json'),JSON.stringify({site_id:'site',job_id:job,version,game_directory:`jobs/${job}/game`}));
  await publish('a'.repeat(64));
  const socket=createServer();socket.listen(0,'127.0.0.1');await once(socket,'listening');const port=socket.address().port;await new Promise(resolve=>socket.close(resolve));
  const origin=`http://127.0.0.1:${port}`;let child;
  async function start(){
    child=spawn(process.execPath,[fileURLToPath(new URL('../frontend/player/server.mjs',import.meta.url))],{env:{PATH:process.env.PATH,PLAYER_PORT:String(port),PLAYER_DATA:join(directory,'players'),ORGANIZER_DATA:organizer,SITE_CATALOG:catalog},stdio:['ignore','pipe','pipe']});
    await Promise.race([once(child.stdout,'data'),once(child,'exit').then(()=>{throw new Error('Player service exited');})]);
  }
  async function stop(){if(child && child.exitCode===null){const done=once(child,'exit');child.kill();await done;}}
  async function post(path,input,cookie='',source=origin){
    const response=await fetch(origin+'/api/'+path,{method:'POST',headers:{Origin:source,Cookie:cookie,'Content-Type':'application/json'},body:JSON.stringify(input)});
    return {status:response.status,value:await response.json(),cookie:response.headers.get('set-cookie')?.split(';')[0]};
  }
  try {
    await start();
    const credentials={username:'alice',name:'Test',password:'isolated-fixture-only'};
    const alice=await post('register',credentials);const bob=await post('register',{...credentials,username:'bob'});
    const run=(await post('launch',{site_id:'site'},alice.cookie)).value;
    const browser2=(await post('login',credentials)).cookie;
    const otherRun=(await post('launch',{site_id:'site'},browser2)).value;
    const input={run:run.run,revision:0,operation:crypto.randomUUID(),changes:{save:snapshot(9)}};
    assert.equal((await post('save',input)).status,401);
    assert.equal((await post('save',input,bob.cookie)).status,403);
    assert.equal((await post('save',input,alice.cookie,'http://other.invalid')).status,403);
    assert.equal((await post('save',input,alice.cookie)).status,200);
    assert.equal((await post('save',input,alice.cookie)).value.revision,1);
    assert.equal((await post('save',{...input,run:otherRun.run,operation:crypto.randomUUID()},browser2)).value.code,'SAVE_CONFLICT');
    const bobRun=(await post('launch',{site_id:'site'},bob.cookie)).value;assert.deepEqual(bobRun.save.entries,{});
    await stop();await start();
    const restored=(await post('launch',{site_id:'site'},alice.cookie)).value;
    assert.equal(JSON.parse(restored.save.entries.save).sequence,9);
    assert.equal(restored.namespace,run.namespace);
    assert.notEqual(new URL(restored.url).port,new URL(run.url).port);
    await publish('b'.repeat(64));
    const next=(await post('launch',{site_id:'site'},alice.cookie)).value;
    assert.equal(next.save.revision,0);assert.notEqual(next.namespace,run.namespace);
    assert.equal((await post('stamp',{run:next.run},bob.cookie)).status,403);
    assert.equal((await post('stamp',{run:next.run},alice.cookie)).value.stamps.length,1);
    assert.equal((await post('stamp',{run:next.run},alice.cookie)).value.stamps.length,1);
    assert.equal((await post('stamp',{run:restored.run},alice.cookie)).value.stamps.length,1);
    const bobActive=(await post('launch',{site_id:'site'},bob.cookie)).value;
    assert.equal((await post('stamp',{run:bobActive.run},bob.cookie)).value.stamps.length,1);
    const ranking=await (await fetch(origin+'/api/leaderboard')).json();
    assert.equal(ranking.length,2);assert.ok(ranking.every(row=>row.rank===1 && row.games.length===1));
  }finally{await stop();await rm(directory,{recursive:true,force:true});}
});

test('game bridge hydrates before boot, namespaces account cache and preserves unbound old browser saves',async()=>{
  const original={Storage:globalThis.Storage,localStorage:globalThis.localStorage,window:globalThis.window,location:globalThis.location};
  class TestStorage {
    constructor(){this.entries=new Map();}
    getItem(key){return this.entries.get(String(key))??null;}
    setItem(key,value){this.entries.set(String(key),String(value));}
    removeItem(key){this.entries.delete(String(key));}
  }
  const messages=[];const listeners=new Set();
  const parent={postMessage:(message,origin)=>messages.push({message,origin})};
  const host={parent,addEventListener:(_,fn)=>listeners.add(fn),removeEventListener:(_,fn)=>listeners.delete(fn)};
  const nativeGet=TestStorage.prototype.getItem;
  try {
    globalThis.Storage=TestStorage;globalThis.localStorage=new TestStorage();globalThis.window=host;globalThis.location={href:'http://game.local/?passportRun=run'};
    localStorage.setItem('save','old-unbound-snapshot');
    const {connectPlayerSave}=await import('../frontend/player/game-save-bridge.mjs');
    const ready=connectPlayerSave('http://platform.local',['save']);
    assert.equal(messages[0].message.type,'pastport:save-ready');
    for(const fn of listeners)fn({source:{},origin:'http://platform.local',data:{type:'pastport:save-state',run:'run',namespace:'wrong',entries:{save:'wrong'}}});
    assert.equal(listeners.size,1);
    for(const fn of [...listeners])fn({source:parent,origin:'http://platform.local',data:{type:'pastport:save-state',run:'run',namespace:'account-site-version',entries:{save:snapshot(7)}}});
    await ready;
    assert.equal(JSON.parse(localStorage.getItem('save')).sequence,7);
    assert.equal(nativeGet.call(localStorage,'save'),'old-unbound-snapshot');
    localStorage.setItem('save',snapshot(8));assert.equal(messages.at(-1).message.type,'pastport:save-change');
    assert.equal(JSON.parse(messages.at(-1).message.value).sequence,8);
    const count=messages.length;localStorage.setItem('pastport:ui-locale','en');assert.equal(messages.length,count);
    localStorage.removeItem('save');assert.equal(messages.at(-1).message.value,null);
  } finally {for(const [key,value] of Object.entries(original)){if(value===undefined)delete globalThis[key];else globalThis[key]=value;}}
});
