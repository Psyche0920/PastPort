import test from 'node:test';
import assert from 'node:assert/strict';
import {contentHash} from '../../src/pastport/player/validation.mjs';
import {preparedStoryInput} from '../../gameplay/prepared-game.mjs';
import {gameplayCatalogSha256} from '../../gameplay/plugins/gameplay-catalog.mjs';

async function fixture(){
  const point={x:0,y:0.25,z:0};
  const world={view_id:'one',world_binding:'world',geometry:{input_sha256:'geometry',algorithm_sha256:'algorithm',result:{objects:[{key:'object:1',planning:{enabled_interactions:['inspect'],observation_positions:[{station:'spawn',point}]}}]}},navigation:[]};
  const environment={project_id:'project',entry_view_id:'one',metric_spatial:{revision:'metric',worlds:[world]}};
  const museum={tourId:'museum',spatialContext:{metric_revision:'metric',worlds:[world]}};
  const task={task_id:'task',asset_id:'object-1',evidence_refs:['claim']};
  const draft={capability_catalog_sha256:gameplayCatalogSha256,package:{project_id:'project',game:{scenes:[{scene_id:'scene',body_key:'body',tasks:[task]}],locales:['zh','en'].map(locale=>({locale,entries:[{key:'body',text:'A public synthetic exercise'}]}))}},spatial_intents:[{task_id:'task',object_number:1,view_id:'one',station_id:'spawn',interaction:'inspect_linked_source'}],gameplay_intents:[{kind:'source_reading',task_id:'task',capability_id:'source-reading:1'}]};
  const config={kind:'dialogue',items:[{id:'claim',text:{zh:'原文',en:'Source'}}]};
  const configHash=await contentHash(config);
  const plan={capability_catalog_sha256:gameplayCatalogSha256,schema_version:'gameplay-preparation/0.4.0',status:'prepared',gaps:[],host_profile:'pastport.demo.activities/1',story_draft_sha256:await contentHash(draft),environment_sha256:'wire-hash',narrative_ref:{sha256:await contentHash(draft.package)},project_id:'project',bindings:[{task_id:'task',scene_id:'scene',object_number:1,selected_station:{view_id:'one',station_id:'spawn',point:structuredClone(point),world_binding:'world',geometry_input_sha256:'geometry',geometry_algorithm_sha256:'algorithm'},source_claim_ids:['claim'],config,config_sha256:configHash,completion:'source_exposure_not_comprehension',capability_id:'source-reading:1',plugin:{plugin_id:'pastport.activity.dialogue',code_sha256:'code'},lifecycle:{status:'passed',config_sha256:configHash,plugin_code_sha256:'code'}}]};
  return {draft,plan,environment,museum};
}

test('converts exact prepared identities with fractional spatial coordinates',async()=>{
  const f=await fixture();const input=await preparedStoryInput(f.draft,f.plan,f.environment,f.museum,'code','wire-hash');
  assert.equal(input.tasks[0].access.view_id,'one');
  assert.equal(input.tasks[0].plugin.kind,'dialogue');
  assert.deepEqual(input.tasks[0].required_sources,[1]);
});

for(const change of ['draft','wire','station','config','plugin','museum','duplicate']){
  test(`rejects changed ${change} before assembly`,async()=>{
    const f=await fixture();
    if(change==='draft')f.draft.gameplay_intents.push({task_id:'task'});
    if(change==='wire')f.plan.environment_sha256='different';
    if(change==='station')f.plan.bindings[0].selected_station.point.x=2;
    if(change==='config')f.plan.bindings[0].config.items[0].text.zh='tampered';
    if(change==='plugin')f.plan.bindings[0].plugin.code_sha256='different';
    if(change==='museum')f.museum.spatialContext.metric_revision='different';
    if(change==='duplicate')f.plan.bindings.push(f.plan.bindings[0]);
    await assert.rejects(()=>preparedStoryInput(f.draft,f.plan,f.environment,f.museum,'code','wire-hash'));
  });
}


async function forkFixture(){
  const f=await fixture(), original=f.draft.package.game.scenes[0];
  const originalBinding=f.plan.bindings[0], originalIntent=f.draft.spatial_intents[0];
  const ids=['opening','left','right','reunion'], views=['one','left-view','right-view','one'];
  const edges=[['left','right'],['reunion'],['reunion'],[]];
  const base=f.environment.metric_spatial.worlds[0];
  const link=target_view_id=>({target_view_id,point:{x:0,y:0,z:0},arrival_yaw:0,arrival_pitch:0});
  const worlds=['one','left-view','right-view'].map(view_id=>({...structuredClone(base),view_id,
    navigation:(view_id==='one'?['left-view','right-view']:['one']).map(link)}));
  f.environment.metric_spatial.worlds=worlds;f.museum.spatialContext.worlds=structuredClone(worlds);
  f.draft.package.game.scenes=ids.map((id,i)=>({...structuredClone(original),scene_id:id,
    tasks:[{...structuredClone(original.tasks[0]),task_id:'task-'+id}],next_scene_ids:edges[i]}));
  f.draft.package.game.initial_state={current_scene_id:'opening'};
  f.draft.spatial_intents=ids.map((id,i)=>({...originalIntent,task_id:'task-'+id,view_id:views[i]}));
  f.draft.gameplay_intents=ids.map(id=>({...f.draft.gameplay_intents[0],task_id:'task-'+id}));
  f.plan.bindings=ids.map((id,i)=>({...structuredClone(originalBinding),task_id:'task-'+id,scene_id:id,
    selected_station:{...originalBinding.selected_station,view_id:views[i]}}));
  f.plan.story_draft_sha256=await contentHash(f.draft);
  f.plan.narrative_ref.sha256=await contentHash(f.draft.package);
  return f;
}

test('checks each fork and reunion edge without inventing travel between exclusive routes',async()=>{
  const f=await forkFixture();
  const input=await preparedStoryInput(f.draft,f.plan,f.environment,f.museum,'code','wire-hash');
  assert.equal(input.tasks.length,4);
});

test('rejects a missing navigation edge on an alternative route',async()=>{
  const f=await forkFixture();
  f.environment.metric_spatial.worlds[0].navigation.pop();
  f.museum.spatialContext.worlds=structuredClone(f.environment.metric_spatial.worlds);
  await assert.rejects(()=>preparedStoryInput(f.draft,f.plan,f.environment,f.museum,'code','wire-hash'),/registered transition/);
});
