import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import path from 'node:path';
import {createGame,presentation as authored} from '../fixtures/game/content.mjs';
import {stageTargets} from '../fixtures/game/shots.mjs';
import {StoryPackageCompiler,museumSnapshotHash} from '../../tools/game-package/story-package.mjs';
import {GameSession} from '../../frontend/game/session.mjs';

/** Public synthetic geometry and media identities; no private museum assets. */
async function fixture({rename=false}={}) {
  const numbers=[...new Set(authored.chapters.flatMap(chapter=>chapter.objects))];
  const objects=numbers.map(number=>({number,historical_title:`Synthetic object ${number}`,media_path:`media/${number}.png`,media_sha256:'a'.repeat(64)}));
  const runtime=createGame('0'.repeat(64),'1'.repeat(64),objects);
  const museum={tourId:'synthetic-museum',objects,sourceNotes:Object.fromEntries(numbers.map(number=>[number,{zh:'测试资料',en:'Test source'}])),runtimeCapabilities:runtime.runtime_compatibility,
    panoramaHashes:{'physical-scene':'b'.repeat(64)},scenes:[{id:'physical-scene',hotspots:numbers.map(number=>({number,pitch:0}))}],walkArea:{},
    shots:numbers.map(number=>({number,sceneId:'physical-scene',taskScenes:[],available:true,camera:{yaw:0,pitch:-10,hfov:90},boundary:[[0,0],[100,0],[100,100],[0,100]],obstacles:[],spawn:[20,20],approach:[40,40],actors:[],navigation:{status:'visually_reviewed',sourcePanoramaSha256:'b'.repeat(64),camera:{yaw:0,pitch:-10,hfov:90},frame:[960,540],forbiddenTestPoints:[[-1,-1],[101,101],[-1,101]]}}))};
  const tasks=authored.chapters.map(chapter=>({task_id:`task-${chapter.id}`,scene_id:chapter.id,chapter:chapter.chapter,objects:chapter.objects,required_sources:chapter.requiredSources,target_number:stageTargets[chapter.id],asset_object_number:chapter.objects[0],plugin:structuredClone(chapter.plugin),automatic_decision:Boolean(chapter.automaticDecision)}));
  if(rename) {
    const ids=new Map(runtime.game.scenes.flatMap((scene,index)=>[[scene.scene_id,`generated-stage-${index}`],[scene.tasks[0].task_id,`generated-activity-${index}`]]));
    const rewrite=value=>typeof value==='string'?(ids.get(value)??value):Array.isArray(value)?value.map(rewrite):value&&typeof value==='object'?Object.fromEntries(Object.entries(value).map(([key,item])=>[key,rewrite(item)])):value;
    runtime.game=rewrite(runtime.game);
    for(const task of tasks){task.scene_id=ids.get(task.scene_id);task.task_id=ids.get(task.task_id);}
  }
  return {museum,input:{schema_version:'story-3d-input-0.1.0',story:{kind:'runtime-package',payload:runtime},museum:{tour_id:museum.tourId,snapshot_sha256:await museumSnapshotHash(museum)},tasks,presentation:{intro:authored.intro}}};
}

const solution=[[0,0,false],[0,2,false],[0,3,false],[3,2,true],[2,0,false],[2,1,false]];
async function play(compiled,route) {
  let session=await GameSession.create(compiled.runtime,compiled.reference,compiled.presentation);
  for(let index=0;index<compiled.presentation.chapters.length;index++) {
    const chapter=session.current,plugin=chapter.plugin;
    for(const number of chapter.requiredSources)session.observeSource(number);
    if(plugin.kind==='question')await session.dispatch({kind:'answer',id:plugin.options.find(option=>option.correct).id});
    if(plugin.kind==='routing')for(const card of plugin.cards)await session.dispatch({kind:'route',bin:card.target});
    if(plugin.kind==='dialogue')for(const item of plugin.items)await session.dispatch({kind:'read',id:item.id});
    if(plugin.kind==='tiling')for(const [id,[x,y,rotated]] of solution.entries())await session.dispatch({kind:'place',id,x,y,rotated});
    if(plugin.kind==='budget'){await session.dispatch({kind:'select',id:route});await session.dispatch({kind:'confirm'});}
    if(chapter.decision)await session.choose(chapter.options[0].id);
    const resumed=await GameSession.create(compiled.runtime,compiled.reference,compiled.presentation);
    resumed.restore(session.serialize());assert.deepEqual(resumed.state,session.state);session=resumed;
    if(!session.state.ending_id)await session.advance();
  }
  return session;
}

test('converts data without invoking the authored story generator and preserves all three playable routes',async()=>{
  const {input,museum}=await fixture();
  const result=await new StoryPackageCompiler().compile(input,museum);
  assert.deepEqual(result.runtime.game,input.story.payload.game);
  assert.equal(result.presentation.chapters.length,8);
  assert.equal(result.gameplayPlan.bindings.length,8);
  assert.equal(result.report.model_calls,0);
  for(const [route,ending] of [['family','E01'],['davud','E02'],['labor','E03']]) {
    const session=await play(result,route);
    assert.equal(session.state.ending_id,ending);
    assert.equal(session.state.completed_task_ids.length,8);
    assert.equal(session.variables().services_completed,true);
  }
});

test('generated scene/task identities play and restore without the Demo naming convention',async()=>{
  const {input,museum}=await fixture({rename:true});
  const result=await new StoryPackageCompiler().compile(input,museum);
  const session=await play(result,'family');
  assert.equal(session.state.ending_id,'E01');
  assert.ok(session.state.completed_task_ids.includes('generated-activity-0'));
  assert.equal(result.presentation.openingLines.s01,undefined);
  assert.ok(session.key.includes(result.reference.sha256));
});

test('accepts the shared NarrativeDraft contract without putting frontend fields into wire 0.1.0',async()=>{
  const {input,museum}=await fixture();
  const source=input.story.payload;
  const referenceDraft=JSON.parse(await readFile(new URL('../fixtures/reference/draft-result.json',import.meta.url)));
  const schema=JSON.parse(await readFile(new URL('../../schemas/draft-result.schema.json',import.meta.url)));
  const report=referenceDraft.payload.authoring_report[0];
  input.story={kind:'narrative-draft',package_id:'synthetic-import',payload:{package:{project_id:source.project_id,schema_version:source.schema_version,content_version:source.content_version,evidence_package_hash:source.evidence_package_hash,candidate_id:'synthetic-candidate',routes:[{artifact_id:'synthetic-route',project_id:source.project_id,kind:'route',schema_version:'0.1.0',content_version:'1',sha256:'c'.repeat(64)}],game:source.game,fiction_notice:'Synthetic test fiction, not historical evidence.'},authoring_report:[report],unresolved_items:[]}};
  const result=await new StoryPackageCompiler().compile(input,museum,{narrativeSchema:schema});
  assert.equal(result.runtime.package_id,'synthetic-import');
  assert.deepEqual(result.runtime.game,source.game);
  assert.equal((await play(result,'labor')).state.ending_id,'E03');
  input.story.payload.unresolved_items=['Unresolved source-to-task binding'];
  await assert.rejects(()=>new StoryPackageCompiler().compile(input,museum,{narrativeSchema:schema}),error=>error.code==='STORY_UNRESOLVED');
});

test('rejects a changed museum, absent object, duplicate task, missing plugin and mismatched outcomes',async()=>{
  for(const [mutate,code] of [
    [({museum})=>{museum.objects[0].historical_title='Changed review';},'MUSEUM_IDENTITY_MISMATCH'],
    [({input})=>{input.tasks[0].required_sources=[999];},'STORY_OBJECT_MISSING'],
    [({input})=>{input.tasks[1].task_id=input.tasks[0].task_id;},'STORY_BINDING_INVALID'],
    [({input})=>{input.tasks[0].plugin={kind:'missing-mechanic'};},'STORY_PLUGIN_MISSING'],
    [({input})=>{input.tasks[1].plugin={kind:'dialogue',items:[{id:'read',text:'test'}]};},'STORY_OUTCOME_MISMATCH'],
  ]) {
    const current=await fixture();mutate(current);
    await assert.rejects(()=>new StoryPackageCompiler().compile(current.input,current.museum),error=>error.code===code);
  }
});

test('does not mark unsupported inspect spots as playable',async()=>{
  const {input,museum}=await fixture();
  input.story.payload.game.scenes[0].tasks[0].spots[0].spot_id='unbound-spatial-spot';
  input.story.payload.game.scenes[0].tasks[0].required_spot_ids=['unbound-spatial-spot'];
  await assert.rejects(()=>new StoryPackageCompiler().compile(input,museum),error=>error.code==='STORY_HOST_UNSUPPORTED');
});

test('the supplied private standalone bundle passes dependency hashes, three routes and save recovery',{skip:!process.env.PASTPORT_STORY_PACKAGE},async()=>{
  const root=process.env.PASTPORT_STORY_PACKAGE;
  const read=async name=>JSON.parse(await readFile(path.join(root,name),'utf8'));
  const result={runtime:await read('data/runtime.json'),reference:await read('data/reference.json'),presentation:await read('data/presentation.json')};
  const manifest=await read('manifest.json'),worlds=await read('data/scene3d-input.json');
  for(const file of manifest.files) {
    assert.equal(path.isAbsolute(file.path),false);
    const bytes=await readFile(path.join(root,file.path));
    assert.equal(createHash('sha256').update(bytes).digest('hex'),file.sha256);
    assert.equal(bytes.length,file.size_bytes);
  }
  for(const world of worlds.worlds) {
    assert.equal(path.isAbsolute(world.root),false);
    assert.ok((await readFile(path.join(root,world.root,'scene3d/index.html'))).length>0);
  }
  for(const [route,ending] of [['family','E01'],['davud','E02'],['labor','E03']])assert.equal((await play(result,route)).state.ending_id,ending);
});

test('registered tiling returns to Story only after completion and restores a partial board',async()=>{
  const {input,museum}=await fixture();
  const compiled=await new StoryPackageCompiler().compile(input,museum);
  let session=await GameSession.create(compiled.runtime,compiled.reference,compiled.presentation);
  // Reach the authored roof-repair task through actual shared runtime transitions.
  while(session.config().kind!=='tiling'){
    const chapter=session.current,config=session.config();
    for(const number of chapter.requiredSources)session.observeSource(number);
    if(config.kind==='question')await session.dispatch({kind:'answer',id:config.options.find(option=>option.correct).id});
    else if(config.kind==='routing')for(const card of config.cards)await session.dispatch({kind:'route',bin:card.target});
    else if(config.kind==='dialogue')for(const item of config.items)await session.dispatch({kind:'read',id:item.id});
    else assert.fail('Unexpected prerequisite mechanic');
    if(chapter.decision)await session.choose(chapter.options[0].id);
    await session.advance();
  }
  const task=session.taskId(),before=session.serialize();
  assert.equal(session.current.id,'s05');
  await assert.rejects(()=>session.dispatch({kind:'place',id:0,x:0,y:0,rotated:false}),/资料/);
  assert.equal(session.serialize(),before);
  for(const number of session.current.requiredSources)session.observeSource(number);
  await session.dispatch({kind:'place',id:0,x:0,y:0,rotated:false});
  assert.equal(session.taskDone(),false);
  const partial=session.serialize();
  await assert.rejects(()=>session.dispatch({kind:'place',id:1,x:0,y:0,rotated:false}));
  assert.equal(session.serialize(),partial,'Rejected overlap must not commit local or global state');
  await assert.rejects(()=>session.advance(),'Incomplete puzzle must not advance Story');
  const resumed=await GameSession.create(compiled.runtime,compiled.reference,compiled.presentation);
  resumed.restore(partial);session=resumed;
  assert.equal(session.entry().activity.placements.length,1);
  assert.equal(session.taskDone(),false);
  session.paused=true;
  await assert.rejects(()=>session.dispatch({kind:'clear'}),/暂停/);
  assert.equal(session.serialize(),partial);
  session.paused=false;
  for(let id=1;id<solution.length;id++){
    const [x,y,rotated]=solution[id];
    await session.dispatch({kind:'place',id,x,y,rotated});
  }
  assert.equal(session.taskDone(),true);
  assert.equal(session.state.completed_task_ids.filter(id=>id===task).length,1);
  const completed=session.serialize();
  await assert.rejects(()=>session.dispatch({kind:'clear'}));
  assert.equal(session.serialize(),completed,'Repeated completion cannot grant Story progress');
  await session.choose(session.current.options[0].id);
  await session.advance();
  assert.notEqual(session.current.id,'s05');
});

test('failed and exited plugin results preserve Story gates and survive host save restoration',async()=>{
  const {input,museum}=await fixture();
  const binding=input.tasks.find(item=>item.scene_id==='s05');
  binding.plugin={kind:'tiling',width:4,height:4,pieces:[[1,4],[1,4],[1,4],[1,4]],rotation_allowed:true,source_gate:{target_claim_id:'cover',options:[{id:'pool',text:{zh:'水池',en:'Pool'}},{id:'cover',text:{zh:'修缮顶盖',en:'Restoration cover'}}]}};
  const compiled=await new StoryPackageCompiler().compile(input,museum);
  let session=await GameSession.create(compiled.runtime,compiled.reference,compiled.presentation);
  while(session.current.id!=='s05'){
    const c=session.current;for(const n of c.requiredSources)session.observeSource(n);
    if(c.plugin.kind==='question')await session.dispatch({kind:'answer',id:c.plugin.options.find(o=>o.correct).id});
    else if(c.plugin.kind==='routing')for(const card of c.plugin.cards)await session.dispatch({kind:'route',bin:card.target});
    else for(const item of c.plugin.items)await session.dispatch({kind:'read',id:item.id});
    if(c.decision)await session.choose(c.options[0].id);await session.advance();
  }
  for(const n of session.current.requiredSources)session.observeSource(n);
  const before=structuredClone(session.state);
  let step=await session.dispatch({kind:'evidence',id:'pool'});assert.equal(step.result.status,'failed');assert.deepEqual(session.state,before);
  await assert.rejects(()=>session.advance());
  const restored=await GameSession.create(compiled.runtime,compiled.reference,compiled.presentation);restored.restore(session.serialize());session=restored;
  await session.dispatch({kind:'retry'});await session.dispatch({kind:'evidence',id:'cover'});
  await session.dispatch({kind:'place',id:0,x:0,y:0,rotated:false});
  step=await session.dispatch({kind:'exit'});assert.equal(step.result.status,'exited');assert.deepEqual(session.state,before);
  const resumed=await GameSession.create(compiled.runtime,compiled.reference,compiled.presentation);resumed.restore(session.serialize());session=resumed;
  await session.dispatch({kind:'resume'});assert.equal(session.entry().activity.placements.length,1);
  for(let id=1;id<4;id++)await session.dispatch({kind:'place',id,x:id,y:0,rotated:false});
  assert.equal(session.taskDone(),true);assert.equal(session.state.completed_task_ids.filter(id=>id===session.taskId()).length,1);
});
