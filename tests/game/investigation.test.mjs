import test from 'node:test';import assert from 'node:assert/strict';
import {Activity} from '../../gameplay/plugins/plugins.mjs';
import {Scene3DView} from '../../frontend/game/scene3d-view.mjs';
const L={zh:'測試',en:'Test'},base={prompt:L,success:L,content_kind:'original_fiction'};
const configs={
 'spot-difference':{...base,kind:'spot-difference',left_image:'assets/a.svg',right_image:'assets/b.svg',differences:[{id:'one',left:[1000,1000,1000,1000],right:[2000,1000,1000,1000],label:L},{id:'two',left:[6000,6000,1000,1000],right:[6000,6000,1000,1000],label:L}]},
 timeline:{...base,kind:'timeline',cards:[{id:'late',text:L,target_slot:'second'},{id:'unknown',text:L,target_slot:'untimed'},{id:'early',text:L,target_slot:'first'}],slots:[{id:'first',label:L},{id:'second',label:L},{id:'untimed',label:L}]},
 'image-puzzle':{...base,kind:'image-puzzle',image:{zh:'assets/chat-zh.svg',en:'assets/chat-en.svg'},columns:2,rows:2,pieces:[{id:'a',target_slot:2},{id:'b',target_slot:0},{id:'c',target_slot:3},{id:'d',target_slot:1}]},
 'scene-search':{...base,kind:'scene-search',targets:[{number:1,clue:L},{number:3,clue:L}]}
};
test('image differences use image coordinates, count each region once and reject invented finds',()=>{
 const a=new Activity(configs['spot-difference']);let s=a.initialize();s=a.reduce(s,{kind:'find-difference',panel:'left',x:9999,y:9999}).state;assert.equal(s.done,false);assert.equal(s.attempts,1);
 s=a.reduce(s,{kind:'find-difference',panel:'left',x:1500,y:1500}).state;assert.deepEqual(s.seen,['one']);s=a.reduce(s,{kind:'find-difference',panel:'right',x:2500,y:1500}).state;assert.deepEqual(s.seen,['one']);
 s=a.restore(a.serialize(s));s=a.reduce(s,{kind:'exit'}).state;assert.equal(a.result(s).status,'exited');assert.throws(()=>a.reduce(s,{kind:'find-difference',panel:'left',x:6500,y:6500}));s=a.reduce(s,{kind:'resume'}).state;s=a.reduce(s,{kind:'find-difference',panel:'left',x:6500,y:6500}).state;assert.equal(s.done,true);
 assert.throws(()=>a.validateState({...s,seen:['one','invented']}));assert.throws(()=>a.reduce(a.initialize(),{kind:'find-difference',panel:'left',x:NaN,y:0}));
});
for(const kind of ['timeline','image-puzzle'])test(kind+' supports rearranging, explicit check, partial restore and rejects fake completion',()=>{
 const a=new Activity(configs[kind]),items=kind==='timeline'?configs[kind].cards:configs[kind].pieces;let s=a.initialize();
 assert.throws(()=>a.validateState({...s,done:true}));s=a.reduce(s,{kind:'place-piece',id:items[0].id,slot:items[1].target_slot}).state;s=a.reduce(s,{kind:'check-arrangement'}).state;assert.equal(s.done,false);assert.equal(s.attempts,1);s=a.restore(a.serialize(s));
 s=a.reduce(s,{kind:'clear-arrangement'}).state;for(const item of items)s=a.reduce(s,{kind:'place-piece',id:item.id,slot:item.target_slot}).state;assert.equal(s.done,false);s=a.reduce(s,{kind:'check-arrangement'}).state;assert.equal(s.done,true);assert.equal(a.restore(a.serialize(s)).done,true);
 assert.throws(()=>a.reduce(a.initialize(),{kind:'place-piece',id:'invented',slot:items[0].target_slot}));
});
test('search needs all host receipts and scene selection does not come from the notebook',()=>{
 const a=new Activity(configs['scene-search']);assert.throws(()=>a.reduce(a.initialize(),{kind:'complete-search',verified_numbers:[1]}));assert.equal(a.reduce(a.initialize(),{kind:'complete-search',verified_numbers:[1,3]}).state.done,true);
 const view=Object.create(Scene3DView.prototype);Object.assign(view,{session:{current:{id:'search',plugin:{kind:'scene-search'}}},scenePickedSources:new Set(),atTaskView:()=>true,readOnlyObservation:()=>true,hasArrived:()=>false});assert.equal(view.canObserve(1),false);view.scenePickedSources.add('search:1');assert.equal(view.canObserve(1),true);view.session.current.id='other';assert.equal(view.canObserve(1),false);
});
test('all patterns reject invalid assets, non-bilingual prompts or impossible tile mappings',()=>{
 assert.throws(()=>new Activity({...configs['spot-difference'],left_image:'https://elsewhere/a.png'}));assert.throws(()=>new Activity({...configs['image-puzzle'],image:{zh:'../secret.png',en:'assets/a.png'}}));assert.throws(()=>new Activity({...configs.timeline,prompt:{en:'Only English'}}));assert.throws(()=>new Activity({...configs['image-puzzle'],pieces:configs['image-puzzle'].pieces.map(i=>({...i,target_slot:0}))}));
});
