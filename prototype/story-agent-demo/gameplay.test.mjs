import test from 'node:test';
import assert from 'node:assert/strict';
import {createGame,presentation} from './content.mjs';
import {prepareGameplayPlan} from './gameplay.mjs';

function runtime() {
  return createGame('0'.repeat(64),'1'.repeat(64),[{number:68,media_sha256:'2'.repeat(64),media_path:'media/68.webp'}]);
}

test('selects registered mechanics and binds them to exact task IDs',async()=>{
  const plan=await prepareGameplayPlan(runtime(),presentation);
  assert.equal(plan.status,'ready');
  assert.equal(plan.build_requests.length,0);
  assert.equal(plan.bindings.length,presentation.chapters.length);
  const scene=runtime().game.scenes.find(item=>item.scene_id==='s05');
  const binding=plan.bindings.find(item=>item.task_id===scene.tasks[0].task_id);
  assert.equal(binding.plugin_id,'pastport.activity.tiling');
  assert.equal(binding.mechanic,'tiling');
  assert.match(binding.config_sha256,/^[a-f0-9]{64}$/);
});

test('reports an explicit build request when a mechanic has no registered plugin',async()=>{
  const current=structuredClone(presentation);
  current.chapters[0].plugin={kind:'unregistered-reconstruction',steps:[]};
  const plan=await prepareGameplayPlan(runtime(),current);
  assert.equal(plan.status,'blocked');
  assert.equal(plan.bindings.length,presentation.chapters.length-1);
  assert.equal(plan.build_requests.length,1);
  assert.equal(plan.build_requests[0].task_id,'task-s01');
  assert.equal(plan.build_requests[0].requested_mechanic,'unregistered-reconstruction');
});

test('rejects story/runtime scene identity drift before binding',async()=>{
  const current=structuredClone(presentation);
  current.chapters[0].id='foreign-scene';
  await assert.rejects(()=>prepareGameplayPlan(runtime(),current),/scene identities differ/);
});
