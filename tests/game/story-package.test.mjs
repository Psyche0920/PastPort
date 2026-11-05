import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {rm} from 'node:fs/promises';
import {prepareInvestigationBlueprint} from '../../tools/game-package/investigation-blueprint.mjs';
import {mkdtemp,mkdir,writeFile,unlink,rmdir} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {continueCompletedSlice} from '../../frontend/game/slice-continuation.mjs';
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
    if(plugin.kind==='spot-difference')for(const d of plugin.differences){const[x,y,w,h]=d.left;await session.dispatch({kind:'find-difference',panel:'left',x:Math.floor(x+w/2),y:Math.floor(y+h/2)});}
    if(['timeline','image-puzzle'].includes(plugin.kind)){for(const item of plugin.kind==='timeline'?plugin.cards:plugin.pieces)await session.dispatch({kind:'place-piece',id:item.id,slot:item.target_slot});await session.dispatch({kind:'check-arrangement'});}
    if(plugin.kind==='scene-search')await session.dispatch({kind:'complete-search',verified_numbers:[]});
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


test('localizes speaker labels without changing stable identities or accepting incomplete labels',async()=>{
  const {input,museum}=await fixture();
  input.presentation.speakerNames={maya:{zh:'方晴',en:'Maya Brooks'}};
  const compiled=await new StoryPackageCompiler().compile(input,museum);
  assert.deepEqual(compiled.presentation.speakerNames.maya,{zh:'方晴',en:'Maya Brooks'});
  assert.deepEqual(compiled.runtime.game,input.story.payload.game);
  input.presentation.speakerNames.maya={en:'Maya Brooks'};
  await assert.rejects(()=>new StoryPackageCompiler().compile(input,museum),error=>error.code==='STORY_CAST_INVALID');
});


test('opening-only character profiles preserve saves while gameplay changes remain incompatible',async()=>{
  const {input,museum}=await fixture();
  const original=await new StoryPackageCompiler().compile(input,museum);
  const oldPresentation=structuredClone(original.presentation);delete oldPresentation.characterProfiles;
  const old=await GameSession.create(original.runtime,original.reference,oldPresentation);
  input.presentation.speakerNames={maya:{zh:'方晴',en:'Maya Brooks'}};
  input.presentation.startupPreparation='lod';
  input.presentation.characterProfiles=[{id:'maya',introduction:{zh:'召集重聚嘅舊組員。',en:'A former teammate who organized the reunion.'}}];
  // Use the same speaker metadata in both versions; only profiles are cosmetic.
  oldPresentation.speakerNames=input.presentation.speakerNames;
  const before=await GameSession.create(original.runtime,original.reference,oldPresentation);
  const compiled=await new StoryPackageCompiler().compile(input,museum);
  const after=await GameSession.create(compiled.runtime,compiled.reference,compiled.presentation);
  assert.equal(before.identity,after.identity);after.restore(before.serialize());
  const changed=structuredClone(compiled.presentation);changed.chapters[0].plugin={kind:'dialogue',items:[{id:'different-evidence',text:{zh:'另一份材料',en:'Different evidence'}}]};
  const incompatible=await GameSession.create(compiled.runtime,compiled.reference,changed);
  assert.notEqual(before.identity,incompatible.identity);
  assert.throws(()=>incompatible.restore(before.serialize()),/其他内容版本/);
  input.presentation.characterProfiles=[null];
  await assert.rejects(()=>new StoryPackageCompiler().compile(input,museum),error=>error.code==='STORY_CAST_INVALID');
  assert.ok(old.identity);
});


test('completed slice continuation replays exact prior choices and rejects mismatched gameplay',async()=>{
 const {input,museum}=await fixture();const g=input.story.payload.game;
 g.scenes=g.scenes.slice(0,1);const boundary=g.scenes[0];boundary.next_scene_ids=[];boundary.decision_id=g.decisions[0].decision_id;g.decisions=g.decisions.slice(0,1);g.decisions[0].options=g.decisions[0].options.slice(0,2);
 g.variables.push({name:'continuation-choice',initial:0},{name:'continuation-ready',initial:false});
 const table=structuredClone(g.endings[0]);table.endings=table.endings.slice(0,2);table.endings.forEach((e,i)=>{e.guard=i===1?null:{kind:'variable_equals',name:'continuation-choice',value:1};e.fallback=i===1;});g.endings=[table];
 g.rules=[{rule_id:'continuation-ready',priority:1,event:'task_completed',target_id:boundary.tasks[0].task_id,guard:{kind:'variable_equals',name:'started',value:true},effects:[{kind:'set_variable',name:'continuation-ready',value:true}],once_key:'once:continuation-ready'},...g.decisions[0].options.map((o,i)=>({rule_id:'continuation-choice-'+i,priority:2+i,event:'option_chosen',target_id:boundary.decision_id,guard:{kind:'all',conditions:[{kind:'variable_equals',name:'continuation-ready',value:true},{kind:'choice_equals',decision_id:boundary.decision_id,option_id:o.option_id}]},effects:[{kind:'set_variable',name:'continuation-choice',value:i+1},{kind:'resolve_ending',ending_table_id:table.ending_table_id}],once_key:'once:continuation-choice-'+i}))];
 input.tasks=input.tasks.slice(0,1);delete input.tasks[0].automatic_decision;
 const old=await new StoryPackageCompiler().compile(input,museum);const unfinished=await GameSession.create(old.runtime,old.reference,old.presentation);
 const prior=await GameSession.create(old.runtime,old.reference,old.presentation);for(const n of prior.current.requiredSources)prior.observeSource(n);await prior.dispatch({kind:'answer',id:prior.current.plugin.options.find(o=>o.correct).id});await prior.choose(prior.current.options[0].id);assert.ok(prior.state.ending_id);
 const extended=structuredClone(input);extended.story.payload.package_id='continuation-fixture-r2';const game=extended.story.payload.game;game.scenes[0].next_scene_ids=['continuation-entry'];for(const r of game.rules)if(r.event==='option_chosen')r.effects=r.effects.map(e=>e.kind==='resolve_ending'?{kind:'unlock_scene',scene_id:'continuation-entry'}:e);
 const extra=structuredClone(game.scenes[0]);extra.scene_id='continuation-entry';extra.tasks[0].task_id='continuation-task';extra.required_task_ids=['continuation-task'];extra.decision_id=null;extra.next_scene_ids=[];game.scenes.push(extra);
 game.rules.push({rule_id:'continuation-end',priority:9,event:'task_completed',target_id:'continuation-task',guard:{kind:'variable_equals',name:'started',value:true},effects:[{kind:'resolve_ending',ending_table_id:table.ending_table_id}],once_key:'once:continuation-end'});
 const binding=structuredClone(extended.tasks[0]);binding.scene_id=extra.scene_id;binding.task_id=extra.tasks[0].task_id;extended.tasks.push(binding);
 const next=await new StoryPackageCompiler().compile(extended,museum);const manifest={schema_version:'completed-slice-continuation/1',previous:old,next_runtime_sha256:next.reference.sha256,boundary_scene_id:boundary.scene_id,entry_scene_id:extra.scene_id};
 const resumed=await continueCompletedSlice(manifest,next,prior.serialize());assert.equal(resumed.current.id,extra.scene_id);assert.equal(resumed.state.ending_id,null);assert.deepEqual(resumed.state.decisions,prior.state.decisions);assert.deepEqual(resumed.state.completed_task_ids,prior.state.completed_task_ids);
 await assert.rejects(()=>continueCompletedSlice(manifest,next,unfinished.serialize()),/not complete/);
 await assert.rejects(()=>continueCompletedSlice({...manifest,next_runtime_sha256:'0'.repeat(64)},next,prior.serialize()),/destination/);
 const changed=structuredClone(extended);changed.tasks[0].plugin.options[0].correct=!changed.tasks[0].plugin.options[0].correct;changed.tasks[0].plugin.options[1].correct=true;
 const incompatible=await new StoryPackageCompiler().compile(changed,museum);await assert.rejects(()=>continueCompletedSlice({...manifest,next_runtime_sha256:incompatible.reference.sha256},incompatible,prior.serialize()),/activity/);
});


test('scene-search ignores caller-supplied finds until host observations exist',async()=>{
 const {input,museum}=await fixture();const binding=input.tasks[0];binding.plugin={kind:'scene-search',content_kind:'original_fiction',prompt:{zh:'搵物件',en:'Find objects'},success:{zh:'完成',en:'Complete'},targets:binding.required_sources.map(number=>({number,clue:{zh:'測試物件',en:'Test object'}}))};
 const compiled=await new StoryPackageCompiler().compile(input,museum);const session=await GameSession.create(compiled.runtime,compiled.reference,compiled.presentation);
 await assert.rejects(()=>session.dispatch({kind:'complete-search',verified_numbers:binding.required_sources}));session.observeSource(binding.required_sources[0]);await assert.rejects(()=>session.dispatch({kind:'complete-search',verified_numbers:binding.required_sources}));
 for(const n of binding.required_sources)session.observeSource(n);await session.dispatch({kind:'complete-search',verified_numbers:[]});assert.equal(session.taskDone(),true);
});

test('blueprint checks actual asset hashes and inserts a solvable activity on an existing edge',async()=>{
 const root=await mkdtemp(path.join(tmpdir(),'pastport-blueprint-test-'));await mkdir(path.join(root,'assets'));
 try{
  const names=['left.svg','right.svg'];const assets=[];for(const name of names){const bytes='<svg xmlns="http://www.w3.org/2000/svg"><rect width="20" height="20" fill="'+(name==='left.svg'?'red':'blue')+'"/></svg>';await writeFile(path.join(root,'assets',name),bytes);assets.push({path:'assets/'+name,sha256:createHash('sha256').update(bytes).digest('hex'),content_kind:'original_fiction',source_claim_ids:[]});}
  const {input,museum}=await fixture();const source=input.tasks[0],L={zh:'合成測試',en:'Synthetic test'};
  const blueprint={schema_version:'investigation-blueprint/1',package_id:'blueprint-fixture',asset_manifest:assets,interludes:[{after_scene_id:source.scene_id,scene_id:'blueprint-scene',task_id:'blueprint-task',source_object:source.asset_object_number,required_sources:[source.asset_object_number],title:L,body:L,objective:L,opening_lines:[],plugin:{kind:'spot-difference',content_kind:'original_fiction',prompt:L,success:L,left_image:assets[0].path,right_image:assets[1].path,differences:[{id:'color',left:[0,0,10000,10000],right:[0,0,10000,10000],label:L}]}}]};
  const result=await prepareInvestigationBlueprint(input,museum,blueprint,{assetRoot:root});assert.equal(result.compiled.presentation.chapters.length,9);assert.deepEqual(result.compiled.runtime.game.scenes[0].next_scene_ids,['blueprint-scene']);assert.ok(result.receipt.bindings[0].lifecycle.checks.includes('completion'));assert.equal(result.receipt.assets.length,2);
  input.story.payload.game.props.push({prop_id:'existing-reward',text_key:'existing-reward.text',content_kind:'original_fiction'});
  for(const table of input.story.payload.game.locales)table.entries.push({key:'existing-reward.text',text:L[table.locale]});
  const reuse=structuredClone(blueprint);reuse.interludes[0].reward={id:'existing-reward',text:L};
  const reused=await prepareInvestigationBlueprint(input,museum,reuse,{assetRoot:root});
  assert.equal(reused.compiled.runtime.game.props.filter(p=>p.prop_id==='existing-reward').length,1);
  reuse.interludes[0].reward.text={zh:'改寫',en:'Changed'};
  await assert.rejects(()=>prepareInvestigationBlueprint(input,museum,reuse,{assetRoot:root}),/existing reward copy differs/);
  const bad=structuredClone(blueprint);bad.asset_manifest[0].sha256='0'.repeat(64);await assert.rejects(()=>prepareInvestigationBlueprint(input,museum,bad,{assetRoot:root}),/asset changed/);
  const missing=structuredClone(blueprint);missing.interludes[0].source_object=999999;await assert.rejects(()=>prepareInvestigationBlueprint(input,museum,missing,{assetRoot:root}),/source object missing/);
 }finally{await unlink(path.join(root,'assets','left.svg'));await unlink(path.join(root,'assets','right.svg'));await rmdir(path.join(root,'assets'));await rmdir(root);}
});

test('opening briefing survives compilation without changing gameplay and rejects incomplete copy',async()=>{
 const {input,museum}=await fixture();const compiler=new StoryPackageCompiler();const original=await compiler.compile(input,museum);
 input.presentation.startupPreparation='none';input.presentation.briefing={title:{zh:'今晚',en:'Tonight'},sections:[{heading:{zh:'你',en:'You'},body:{zh:'舊組員',en:'Former teammate'}}],closing:{zh:'開始',en:'Begin'}};
 const result=await compiler.compile(input,museum);assert.deepEqual(result.runtime,original.runtime);assert.deepEqual(result.presentation.briefing,input.presentation.briefing);
 input.presentation.briefing.sections[0].body={en:'Missing Chinese'};await assert.rejects(compiler.compile(input,museum),/briefing/);
});

test('station cards preserve museum identity and reject unknown objects or escaping references',async()=>{
 const {input,museum}=await fixture();const compiler=new StoryPackageCompiler(),original=await compiler.compile(input,museum);const number=museum.objects[0].number;
 input.presentation.stationRecords=[{number,title:{zh:'來源站',en:'Source station'},body:{zh:'遊戲工作站，與原始資料分開。',en:'A fictional station, separate from the original source.'},reference_path:'assets/reference/catalogue.pdf'}];
 const result=await compiler.compile(input,museum);assert.deepEqual(result.runtime,original.runtime);assert.equal(result.presentation.stationRecords[0].number,number);
 input.presentation.stationRecords[0].reference_path='assets/reference/../../private.pdf';await assert.rejects(compiler.compile(input,museum),/station records/);
 input.presentation.stationRecords[0].reference_path='assets/reference/catalogue.pdf';input.presentation.stationRecords[0].number=-99;await assert.rejects(compiler.compile(input,museum),/station records/);
});


for(const inputKind of ['runtime-package','narrative-draft','embedded-design'])test(inputKind+' investigation command packages all four activities and their checked images, preserving the playable ending',async()=>{
 const root=await mkdtemp(path.join(tmpdir(),'pastport-investigation-command-'));
 const run=promisify(execFile),tool=path.resolve('tools/game-package/build-story-package.mjs');
 const execute=args=>process.env.PASTPORT_GAMEPLAY_PYTHON?run(process.env.PASTPORT_GAMEPLAY_PYTHON,['-m','pastport_gameplay','investigate',...args.slice(1)]):run(process.execPath,[tool,...args]);
 try{
  const {input,museum}=await fixture();const L={zh:'合成測試',en:'Synthetic test'};
  const museumDir=path.join(root,'museum'),assetRoot=path.join(root,'activity');
  await mkdir(path.join(museumDir,'data'),{recursive:true});await mkdir(path.join(museumDir,'assets'));
  await mkdir(path.join(museumDir,'media'));await mkdir(path.join(museumDir,'scene3d'));
  await writeFile(path.join(museumDir,'scene3d','index.html'),'<html>synthetic geometry fixture</html>');
  const media=Buffer.from('synthetic media'),mediaHash=createHash('sha256').update(media).digest('hex');
  for(const object of museum.objects){object.media_sha256=mediaHash;await writeFile(path.join(museumDir,object.media_path),media);}
  for(const asset of input.story.payload.media_manifest)asset.sha256=mediaHash;
  input.museum.snapshot_sha256=await museumSnapshotHash(museum);
  await writeFile(path.join(museumDir,'data/presentation.json'),JSON.stringify(museum));
  await writeFile(path.join(museumDir,'data/runtime.json'),JSON.stringify(input.story.payload));
  await writeFile(path.join(museumDir,'data/scene3d-input.json'),JSON.stringify({worlds:[{root:'.'}]}));
  await mkdir(path.join(assetRoot,'assets','investigation'),{recursive:true});
  const assets=[];
  for(const name of ['left.svg','right.svg','chat-zh.svg','chat-en.svg']){
   const bytes='<svg xmlns="http://www.w3.org/2000/svg"><text>'+name+'</text></svg>',relative='assets/investigation/'+name;
   await writeFile(path.join(assetRoot,relative),bytes);assets.push({path:relative,sha256:createHash('sha256').update(bytes).digest('hex'),content_kind:'original_fiction',source_claim_ids:[]});
  }
  const numbers=[...new Set(input.tasks.map(t=>t.asset_object_number))].slice(0,2);
  const configs=[
   {kind:'spot-difference',left_image:assets[0].path,right_image:assets[1].path,differences:[{id:'change',left:[0,0,5000,5000],right:[0,0,5000,5000],label:L}]},
   {kind:'timeline',cards:[{id:'later',text:L,target_slot:'second'},{id:'earlier',text:L,target_slot:'first'}],slots:[{id:'first',label:L},{id:'second',label:L}]},
   {kind:'image-puzzle',image:{zh:assets[2].path,en:assets[3].path},columns:2,rows:2,pieces:[2,0,3,1].map((target_slot,i)=>({id:'piece-'+i,target_slot}))},
   {kind:'scene-search',targets:numbers.map(number=>({number,clue:L}))},
  ];
  const anchors=input.story.payload.game.scenes.filter(s=>s.decision_id===null&&s.next_scene_ids.length===1);
  assert.ok(anchors.length>=1);
  for(const task of input.tasks)task.access={view_id:"physical-scene",station_id:"spawn",interaction:"inspect"};
  const blueprint={schema_version:'investigation-blueprint/1',package_id:'automatic-investigation-fixture',asset_manifest:assets,interludes:configs.map((config,index)=>{
   const source=input.tasks.find(t=>t.scene_id===anchors[0].scene_id);
   return {after_scene_id:index===0?source.scene_id:'activity-scene-'+(index-1),scene_id:'activity-scene-'+index,task_id:'activity-task-'+index,source_object:source.asset_object_number,required_sources:config.kind==='scene-search'?numbers:[source.asset_object_number],title:L,body:L,objective:L,opening_lines:[],plugin:{...config,prompt:L,success:L,content_kind:'original_fiction'}};
  })};
  if(inputKind!=='runtime-package'){
   const source=input.story.payload;
   const referenceDraft=JSON.parse(await readFile(new URL('../fixtures/reference/draft-result.json',import.meta.url)));
   input.story={kind:'narrative-draft',package_id:'synthetic-investigation',payload:{package:{project_id:source.project_id,schema_version:source.schema_version,content_version:source.content_version,evidence_package_hash:source.evidence_package_hash,candidate_id:'synthetic-candidate',routes:[{artifact_id:'synthetic-route',project_id:source.project_id,kind:'route',schema_version:'0.1.0',content_version:'1',sha256:'c'.repeat(64)}],game:source.game,fiction_notice:'Synthetic fiction notice.'},authoring_report:[referenceDraft.payload.authoring_report[0]],unresolved_items:[]}};
  }
  if(inputKind==='embedded-design'){
   const encoded=JSON.stringify(blueprint),chunks=encoded.match(/[\s\S]{1,8000}/g);
   for(const table of input.story.payload.package.game.locales){
    table.entries.push({key:'preparation.investigation_v1',text:'investigation-blueprint/1'},{key:'preparation.investigation_parts',text:String(chunks.length)});
    chunks.forEach((text,index)=>table.entries.push({key:'preparation.investigation_part.'+(index+1),text}));
   }
  }
  const inputFile=path.join(root,'input.json'),blueprintFile=path.join(root,'blueprint.json'),output=path.join(root,'game');
  await writeFile(inputFile,JSON.stringify(input));await writeFile(blueprintFile,JSON.stringify(blueprint));
  const args=['from-investigation','--input',inputFile,'--museum',museumDir,...(inputKind==='embedded-design'?[]:['--blueprint',blueprintFile]),'--activity-assets',assetRoot,'--output',output];
  await execute(args);
  const load=async name=>JSON.parse(await readFile(path.join(output,'data',name+'.json'),'utf8'));
  const receipt=await load('investigation-receipt');assert.equal(receipt.model_calls,0);assert.equal(receipt.assets.length,4);assert.equal(receipt.bindings.length,4);
  for(const asset of assets)assert.equal(createHash('sha256').update(await readFile(path.join(output,asset.path))).digest('hex'),asset.sha256);
  const compiled={runtime:await load('runtime'),reference:await load('reference'),presentation:await load('presentation')};
  assert.equal((await play(compiled,'family')).state.ending_id,'E01');
  if(inputKind!=='runtime-package')assert.ok(compiled.presentation.intro.en.includes('Synthetic fiction notice.'));
  assert.ok(!compiled.runtime.game.locales[0].entries.some(e=>e.key==='preparation.investigation_v1'));
  await assert.rejects(execute(args),/Output exists/);
  await mkdir(path.join(museumDir,'assets','investigation'));
  await writeFile(path.join(museumDir,assets[0].path),'museum content');
  await assert.rejects(execute([...args.slice(0,-1),path.join(root,'collision-game')]),/overwrite museum content/);
  await assert.rejects(readFile(path.join(root,'collision-game','manifest.json')));
  await unlink(path.join(museumDir,assets[0].path));
  await writeFile(path.join(assetRoot,assets[0].path),'changed');
  await assert.rejects(execute([...args.slice(0,-1),path.join(root,'bad-game')]),/asset changed/);
  await assert.rejects(readFile(path.join(root,'bad-game','manifest.json')));
 }finally{await rm(root,{recursive:true,force:true});}
});
