import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,mkdir,writeFile,rm} from 'node:fs/promises';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {createServer} from 'node:net';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import {fileURLToPath} from 'node:url';
import {DatabaseSync} from 'node:sqlite';
import {createGame,presentation as source} from './fixtures/game/content.mjs';
import {GameSession} from '../frontend/game/session.mjs';
import {contentHash} from '../src/pastport/player/validation.mjs';
import {GameSessionCompletionVerifier,CompletionRejected} from '../frontend/player/completion-verifier.mjs';

async function fixture(){
 const numbers=[...new Set(source.chapters.flatMap(c=>c.requiredSources))];
 const objects=numbers.map(number=>({number,media_sha256:'a'.repeat(64),media_path:`media/${number}.png`}));
 const runtime=createGame('0'.repeat(64),'1'.repeat(64),objects);
 const reference={artifact_id:'completion-fixture',kind:'runtime',project_id:runtime.project_id,schema_version:runtime.schema_version,content_version:runtime.content_version,sha256:await contentHash(runtime)};
 const presentation={...source,objects,saveKey:'completion-save'};
 const create=()=>GameSession.create(runtime,reference,presentation);
 return {runtime,reference,presentation,create};
}
async function finish(session){
 const solution=[[0,0,false],[0,2,false],[0,3,false],[3,2,true],[2,0,false],[2,1,false]];
 while(!session.state.ending_id){
  const scene=session.current,plugin=scene.plugin;
  for(const n of scene.requiredSources)session.observeSource(n);
  if(plugin.kind==='question')await session.dispatch({kind:'answer',id:plugin.options.find(o=>o.correct).id});
  if(plugin.kind==='routing')for(const card of plugin.cards)await session.dispatch({kind:'route',bin:card.target});
  if(plugin.kind==='dialogue')for(const item of plugin.items)await session.dispatch({kind:'read',id:item.id});
  if(plugin.kind==='tiling')for(const [id,[x,y,rotated]] of solution.entries())await session.dispatch({kind:'place',id,x,y,rotated});
  if(plugin.kind==='budget'){await session.dispatch({kind:'select',id:'family'});await session.dispatch({kind:'confirm'});}
  if(scene.decision)await session.choose(scene.options[0].id);
  if(!session.state.ending_id)await session.advance();
 }
 return session;
}
test('shared engine rejects early/forged endings, missing tasks and foreign saves; accepts a completed route',async()=>{
 const f=await fixture(),initial=await f.create(),verifier=new GameSessionCompletionVerifier(initial);
 const entries=s=>({[f.presentation.saveKey]:s.serialize()});
 assert.throws(()=>verifier.verify({},'E01'),CompletionRejected);
 assert.throws(()=>verifier.verify(entries(initial),'E01'),CompletionRejected);
 const fake=initial.snapshot();fake.engine=structuredClone(fake.engine);fake.engine.ending_id='E01';
 assert.throws(()=>verifier.verify({[f.presentation.saveKey]:JSON.stringify(fake)},'E01'),CompletionRejected);
 const complete=await finish(await f.create());
 assert.equal(verifier.verify(entries(complete),complete.state.ending_id),complete.state.ending_id);
 assert.throws(()=>verifier.verify(entries(complete),'foreign-ending'),CompletionRejected);
 const forged=complete.snapshot();forged.local=structuredClone(forged.local);forged.local.s05.activity.done=false;
 assert.throws(()=>verifier.verify({[f.presentation.saveKey]:JSON.stringify(forged)},complete.state.ending_id),CompletionRejected);
 const foreign=complete.snapshot();foreign.identity='0'.repeat(64);
 assert.throws(()=>verifier.verify({[f.presentation.saveKey]:JSON.stringify(foreign)},complete.state.ending_id),CompletionRejected);
});
test('HTTP stamp requires completed progress; reopening after retraction automatically starts fresh',async()=>{
 const f=await fixture(),directory=await mkdtemp(join(tmpdir(),'pastport-completion-'));
 const organizer=join(directory,'organizer'),job='c'.repeat(32),game=join(organizer,'jobs',job,'game'),data=join(directory,'players');
 let child;
 try {
  await mkdir(join(game,'data'),{recursive:true});
  for(const [name,value] of Object.entries({runtime:f.runtime,reference:f.reference,presentation:f.presentation,'scene3d-input':{worlds:[]}}))await writeFile(join(game,'data',name+'.json'),JSON.stringify(value));
  await writeFile(join(game,'index.html'),'<script type="module" src="app.mjs"></script>');
  await writeFile(join(game,'session.mjs'),'export class GameSession {snapshot(){return {};}}');
  await writeFile(join(game,'app.mjs'),'document.title="synthetic completion test";');
  const catalog=join(directory,'sites.json');await writeFile(catalog,JSON.stringify([{id:'site'}]));
  await writeFile(join(organizer,'player-map-site.json'),JSON.stringify({site_id:'site',version:'d'.repeat(64),job_id:job,game_directory:`jobs/${job}/game`}));
  const socket=createServer();socket.listen(0,'127.0.0.1');await once(socket,'listening');const port=socket.address().port;await new Promise(resolve=>socket.close(resolve));
  const origin=`http://127.0.0.1:${port}`;
  child=spawn(process.execPath,[fileURLToPath(new URL('../frontend/player/server.mjs',import.meta.url))],{env:{PATH:process.env.PATH,PLAYER_PORT:String(port),PLAYER_DATA:data,ORGANIZER_DATA:organizer,SITE_CATALOG:catalog},stdio:['ignore','pipe','pipe']});
  await Promise.race([once(child.stdout,'data'),once(child,'exit').then(()=>{throw new Error('Player exited');})]);
  const post=async(route,value,cookie='')=>{const r=await fetch(origin+'/api/'+route,{method:'POST',headers:{Origin:origin,Cookie:cookie,'Content-Type':'application/json'},body:JSON.stringify(value)});return {status:r.status,value:await r.json(),cookie:r.headers.get('set-cookie')?.split(';')[0]};};
  const alice=await post('register',{username:'alice',name:'Fixture',password:'isolated-completion-fixture'}),bob=await post('register',{username:'bob',name:'Fixture',password:'isolated-completion-fixture'});
  const active=(await post('launch',{site_id:'site'},alice.cookie)).value;
  const stamp=run=>post('stamp',{run,ending_id:'E01'},alice.cookie);
  assert.equal((await post('stamp',{run:active.run},alice.cookie)).status,409);
  assert.equal((await stamp(active.run)).status,409);
  let revision=0;
  const save=async(run,session)=>{const response=await post('save',{run,revision,operation:crypto.randomUUID(),changes:{'completion-save':session.serialize()}},alice.cookie);assert.equal(response.status,200);revision=response.value.revision;};
  await save(active.run,await f.create());
  assert.equal((await stamp(active.run)).status,409);
  const complete=await finish(await f.create());await save(active.run,complete);
  assert.equal((await post('stamp',{run:active.run,ending_id:'foreign'},alice.cookie)).status,409);
  assert.equal((await post('stamp',{run:active.run,ending_id:'E01'},bob.cookie)).status,403);
  assert.equal((await stamp(active.run)).value.stamps.length,1);
  assert.equal((await stamp(active.run)).value.stamps.length,1);
  const database=new DatabaseSync(join(data,'players.sqlite'));
  try {database.prepare('DELETE FROM stamp WHERE game=?').run('site');}finally{database.close();}
  const restored=(await post('launch',{site_id:'site'},alice.cookie)).value;
  assert.deepEqual(restored.save.entries,{},'one launch returns the first-play state without a restart click');
  assert.equal(restored.save.revision,revision+1);
  const archive=new DatabaseSync(join(data,'players.sqlite'));
  try {
    const previous=archive.prepare('SELECT payload FROM game_save_archive WHERE site=?').all('site');
    assert.equal(previous.length,1);
    assert.equal(JSON.parse(previous[0].payload)['completion-save'],complete.serialize());
  } finally {archive.close();}
  assert.equal((await stamp(restored.run)).status,409);
  assert.equal((await stamp(active.run)).status,409,'an old run cannot reclaim from the reset save');
  const stale=await post('save',{run:active.run,revision,operation:crypto.randomUUID(),changes:{'completion-save':complete.serialize()}},alice.cookie);
  assert.equal(stale.value.code,'SAVE_CONFLICT');
  revision=restored.save.revision;
  const openedAgain=(await post('launch',{site_id:'site'},alice.cookie)).value;
  assert.equal(openedAgain.save.revision,revision,'an empty new attempt is not reset twice');
  await save(restored.run,await f.create());
  const unfinished=(await post('launch',{site_id:'site'},alice.cookie)).value;
  assert.equal(unfinished.save.revision,revision,'unfinished progress resumes normally');
  assert.equal(unfinished.save.entries['completion-save'],(await f.create()).serialize());
  assert.equal((await stamp(restored.run)).status,409);
  const replayed=await finish(await f.create());
  await save(restored.run,replayed);
  assert.equal((await stamp(restored.run)).value.stamps.length,1);
  const earned=(await post('launch',{site_id:'site'},alice.cookie)).value;
  assert.equal(earned.save.entries['completion-save'],replayed.serialize(),'completed progress with a medal is preserved');
 }finally{
  if(child&&child.exitCode===null){const stopped=once(child,'exit');child.kill();await stopped;}
  await rm(directory,{recursive:true,force:true});
 }
});
