import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {Activity} from '../../gameplay/plugins/plugins.mjs';
import {gameplayCatalog} from '../../gameplay/plugins/gameplay-catalog.mjs';

const problem={kind:'tiling',width:4,height:4,pieces:[[1,4],[1,4],[1,4],[1,4]],rotation_allowed:true};
const gate={target_claim_id:'cover',options:[{id:'pool',text:{zh:'庭院水池',en:'Courtyard pool'}},{id:'cover',text:{zh:'修缮顶盖',en:'Restoration cover'}}]};

test('browser capabilities exactly match the one packaged catalog',async()=>{
  const source=JSON.parse(await readFile(new URL('../../src/pastport/data/gameplay-capabilities.json',import.meta.url),'utf8'));
  assert.deepEqual(gameplayCatalog,source);
});

test('coverage supports configurable inventories and rejects an equal-area unsolvable board',()=>{
  for(const pieces of [problem.pieces,[[2,2],[3,1],[3,1],[2,1],[2,1],[2,1]]]){
    const activity=new Activity({...problem,pieces});let state=activity.initialize();
    for(const p of activity.solution)state=activity.reduce(state,{kind:'place',...p}).state;
    assert.equal(activity.result(state).status,'completed');
  }
  assert.throws(()=>new Activity({...problem,pieces:[[3,3],[2,2],[1,3]]}),/no solution/);
});

test('source inference, failure retry and exit restoration never fabricate completion',()=>{
  const activity=new Activity({...problem,source_gate:gate});let state=activity.initialize();
  assert.throws(()=>activity.reduce(state,{kind:'place',...activity.solution[0]}),/source evidence/);
  let step=activity.reduce(state,{kind:'evidence',id:'pool'});assert.equal(step.result.status,'failed');assert.equal(step.state.done,false);
  state=activity.restore(activity.serialize(step.state));assert.throws(()=>activity.reduce(state,{kind:'place',...activity.solution[0]}));
  state=activity.reduce(state,{kind:'retry'}).state;
  state=activity.reduce(state,{kind:'evidence',id:'cover'}).state;
  state=activity.reduce(state,{kind:'place',...activity.solution[0]}).state;
  step=activity.reduce(state,{kind:'exit'});assert.equal(step.result.status,'exited');assert.equal(step.state.done,false);
  state=activity.reduce(activity.restore(activity.serialize(step.state)),{kind:'resume'}).state;
  assert.equal(state.placements.length,1);assert.equal(state.selected,'cover');
  step=activity.reduce(state,{kind:'give_up'});assert.equal(step.result.status,'failed');
  state=activity.reduce(step.state,{kind:'retry'}).state;assert.equal(state.placements.length,0);assert.equal(state.selected,null);
});

test('legacy activity saves migrate on the next action without losing placements',()=>{
  const activity=new Activity(problem);const legacy={version:1,kind:'tiling',done:false,attempts:0,cursor:0,seen:[],placements:[],selected:null};
  const next=activity.reduce(activity.restore(JSON.stringify(legacy)),{kind:'place',...activity.solution[0]}).state;
  assert.equal(next.version,2);assert.equal(next.placements.length,1);
});

test('shared schema validation accepts bounded dimension tuples and rejects wrong tuple values',async()=>{
  const {SchemaValidator}=await import('../../src/pastport/player/validation.mjs');
  const validator=new SchemaValidator({});
  const schema={type:'array',minItems:2,maxItems:2,prefixItems:[{type:'integer',minimum:1,maximum:4},{type:'integer',minimum:1,maximum:4}],items:false};
  validator.assertSchema(schema,[1,4]);
  assert.throws(()=>validator.assertSchema(schema,[0,4]));
  assert.throws(()=>validator.assertSchema(schema,[1,4,2]));
  assert.throws(()=>validator.assertSchema(schema,['1',4]));
});
