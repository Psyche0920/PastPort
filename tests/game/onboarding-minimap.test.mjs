import test from 'node:test';
import assert from 'node:assert/strict';
import {mapLayout,projectMapPoint,RoomMinimap} from '../../frontend/game/room-minimap.mjs';
import {readAutoLod,saveAutoLod,AUTO_LOD_KEY} from '../../frontend/game/startup-options.mjs';
test('device LOD preference overrides package default and tolerates denied storage',()=>{
 const values=new Map(),storage={getItem:k=>values.get(k),setItem:(k,v)=>values.set(k,v)};
 assert.equal(readAutoLod(storage,{startupPreparation:'none'}),false);
 assert.equal(readAutoLod(storage,{startupPreparation:'lod'}),true);
 saveAutoLod(storage,false);assert.equal(values.get(AUTO_LOD_KEY),'off');assert.equal(readAutoLod(storage,{startupPreparation:'lod'}),false);
 saveAutoLod(storage,true);assert.equal(readAutoLod(storage),true);
 const denied={getItem(){throw Error('denied');},setItem(){throw Error('denied');}};
 assert.equal(readAutoLod(denied),false);assert.doesNotThrow(()=>saveAutoLod(denied,true));
});
test('minimap accepts registered finite geometry and preserves aspect ratio without granting observations',()=>{
 const message={bounds:{minX:0,maxX:20,minZ:0,maxZ:10},objects:[{number:2,x:5,z:5}]};
 assert.deepEqual(mapLayout(message,[2]),message);
 assert.equal(mapLayout(message,[5]),null);
 assert.equal(mapLayout({...message,objects:[...message.objects,...message.objects]},[2]),null);
 assert.equal(mapLayout({...message,bounds:{...message.bounds,maxX:Infinity}},[2]),null);
 assert.equal(mapLayout({...message,objects:[null]},[2]),null);
 assert.deepEqual(projectMapPoint(message.bounds,{x:10,z:5}),{x:90,y:90});
 assert.deepEqual(projectMapPoint(message.bounds,{x:20,z:10}),{x:168,y:129});
 assert.equal(projectMapPoint(message.bounds,{x:NaN,z:0}),null);
 assert.deepEqual(Object.keys(mapLayout(message,[2])),['bounds','objects']);
});

test('minimap draws camera rotation, separates labels and collapses without collecting sources',()=>{
 class Node{constructor(tag){this.tag=tag;this.children=[];this.attributes={};this.style={};this.hidden=false;}append(...n){this.children.push(...n);}setAttribute(k,v){this.attributes[k]=v;}replaceChildren(){this.children=[];}querySelector(tag){return this.children.find(n=>n.tag===tag);}remove(){}}
 const previous=globalThis.document;globalThis.document={createElement:t=>new Node(t),createElementNS:(_,t)=>new Node(t)};
 try{
  const parent=new Node('main'),map=new RoomMinimap({parent,allowedNumbers:[2,5],getLocale:()=> 'en'});
  map.setVisible(true);assert.equal(map.root.hidden,true);
  map.setLayout({bounds:{minX:0,maxX:100,minZ:0,maxZ:100},objects:[{number:2,x:5,z:5},{number:5,x:5.1,z:5.1}]});
  map.updatePose({x:4,z:5,dx:1,dz:0});map.setVisible(true);
  assert.equal(map.root.hidden,false);assert.match(map.player.attributes.transform,/rotate\(90\)/);
  assert.notEqual(map.nodes.get(2).querySelector('text').attributes.y,map.nodes.get(5).querySelector('text').attributes.y);
  map.setTarget(5);assert.equal(map.nodes.get(5).attributes.class,'minimap-target');
  map.toggle.onclick();assert.equal(map.body.hidden,true);assert.equal(map.toggle.attributes['aria-expanded'],'false');
  map.setVisible(false);assert.equal(map.root.hidden,true);
  assert.equal('observeSource' in map,false);
 }finally{globalThis.document=previous;}
});
