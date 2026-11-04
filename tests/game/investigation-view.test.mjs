import test from 'node:test';import assert from 'node:assert/strict';
import {renderInvestigation} from '../../frontend/game/investigation-view.mjs';import {Activity} from '../../gameplay/plugins/plugins.mjs';
class Node{constructor(tag){this.tag=tag;this.children=[];this.style={};this.attrs={};this.classList={add(){}};}append(...n){this.children.push(...n);}setAttribute(k,v){this.attrs[k]=v;}getBoundingClientRect(){return{x:0,y:0,left:0,top:0,width:1000,height:600};}querySelector(tag){return flatten(this).find(n=>n.tag===tag);}}
function flatten(n){return[n,...n.children.filter(x=>x instanceof Node).flatMap(flatten)];}
const L={zh:'測試',en:'Test'};
test('native drag/drop handlers transfer a piece ID and use the shared reducer',()=>{
 const before=globalThis.document;globalThis.document={createElement:t=>new Node(t)};
 try{const config={kind:'timeline',content_kind:'original_fiction',prompt:L,success:L,cards:[{id:'early',text:L,target_slot:'one'},{id:'late',text:L,target_slot:'two'}],slots:[{id:'one',label:L},{id:'two',label:L}]},activity=new Activity(config);let state=activity.initialize();const root=new Node('section'),commands=[];renderInvestigation(root,config,state,{locale:'en',send:cmd=>{commands.push(cmd);state=activity.reduce(state,cmd).state;}});
 const piece=flatten(root).find(n=>n.className==='activity-piece'),slot=flatten(root).find(n=>n.className==='activity-slot');const payload={};piece.ondragstart({dataTransfer:{setData:(k,v)=>payload[k]=v}});assert.equal(payload['text/plain'],'early');let prevented=false;slot.ondragover({preventDefault:()=>prevented=true,dataTransfer:{}});slot.ondrop({preventDefault(){},dataTransfer:{getData:k=>payload[k]}});assert.equal(prevented,true);assert.deepEqual(commands,[{kind:'place-piece',id:'early',slot:'one'}]);assert.equal(state.done,false);assert.deepEqual(state.placements,[{id:'early',slot:'one'}]);
 }finally{globalThis.document=before;}
});
test('picture clicks normalize against the actual image, not the containing panel',()=>{
 const before=globalThis.document;globalThis.document={createElement:t=>new Node(t)};
 try{const root=new Node('section'),commands=[];renderInvestigation(root,{kind:'spot-difference',prompt:L,success:L,left_image:'assets/a.svg',right_image:'assets/b.svg',differences:[]},{done:false,seen:[]},{locale:'en',send:c=>commands.push(c)});const panel=flatten(root).find(n=>n.className==='difference-image');panel.onclick({detail:1,clientX:250,clientY:150});assert.deepEqual(commands,[{kind:'find-difference',panel:'left',x:2500,y:2500}]);}
 finally{globalThis.document=before;}
});
