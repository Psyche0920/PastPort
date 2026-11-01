import test from 'node:test';
import assert from 'node:assert/strict';
import {validateNavigation} from './navigation.mjs';

function fixture(){
 const node={key:'object:68',planning:{enabled_interactions:['inspect'],observation_positions:[{station:'spawn'}]}};
 return {objects:[{number:68}],scenes:[{id:'one'},{id:'two'}],chapters:[{id:'chapter',requiredSources:[68],access:{view_id:'one',station_id:'spawn',interaction:'inspect'}}],
 spatialContext:{schema_version:'story-spatial-context-0.1.0',input_sha256:'a'.repeat(64),metric_revision:'b'.repeat(64),worlds:[
  {view_id:'one',geometry:{status:'computed',result:{spawn_ground:true,objects:[node]}},navigation:[{target_view_id:'two',arrival_yaw:90,arrival_pitch:0}]},
  {view_id:'two',geometry:{status:'computed',result:{spawn_ground:true,objects:[]}},navigation:[{target_view_id:'one',arrival_yaw:0,arrival_pitch:0}]}]}};
}
test('registered inspect task uses its computed 3D station without claiming image-floor review',()=>{
 assert.equal(validateNavigation(fixture()),true);
});
test('wrong task view, missing inspect binding, uncomputed ground and invalid arrival fail',()=>{
 for(const mutate of [
  p=>p.chapters[0].access.view_id='foreign',
  p=>p.spatialContext.worlds[0].geometry.result.objects[0].planning.enabled_interactions=[],
  p=>p.spatialContext.worlds[0].geometry.result.spawn_ground=false,
  p=>p.spatialContext.worlds[0].navigation[0].arrival_yaw=null,
 ]){const input=fixture();mutate(input);assert.throws(()=>validateNavigation(input));}
});

test('3D source inspection requires the task view and its registered interaction',async()=>{
 const {Scene3DView}=await import('./scene3d-view.mjs');
 const presentation=fixture();
 const view=Object.create(Scene3DView.prototype);
 Object.assign(view,{world:2,arrivedSources:new Set(),readOnlySources:new Set(),session:{
  current:presentation.chapters[0],presentation,
 }});
 assert.equal(view.atTaskView(),false);
 assert.equal(view.canObserve(68),false);
 view.world=1;
 assert.equal(view.canObserve(68),true);
 assert.equal(view.canObserve(999),false);
});
