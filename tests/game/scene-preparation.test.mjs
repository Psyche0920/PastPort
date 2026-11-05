import {formatCaseFile} from '../../frontend/game/dialogue.mjs';
import test from 'node:test';
import assert from 'node:assert/strict';
import {ScenePreparation,prepareRenderer} from '../../frontend/game/scene-preparation.mjs';
import {DialoguePlayer} from '../../frontend/game/dialogue.mjs';

test('preparation is user-started, single-flight and nonce-bound; progress is not success',async()=>{
 const phases=[],sent=[];const gate=new ScenePreparation({id:()=> 'request-one',onProgress:x=>phases.push(x)});
 assert.equal(gate.phase,'idle');assert.equal(sent.length,0);
 const first=gate.start(x=>sent.push(x));assert.equal(first,gate.start(x=>sent.push(x)));assert.equal(sent.length,1);
 assert.equal(gate.accept({type:'story3d:prepared',request:'stale'}),false);
 gate.accept({type:'story3d:preparation-progress',request:'request-one',phase:'optimizing'});
 assert.equal(gate.phase,'preparing');assert.deepEqual(phases,['optimizing']);
 gate.accept({type:'story3d:prepared',request:'request-one'});await first;assert.equal(gate.phase,'ready');
 await gate.start(()=>assert.fail('Ready preparation must not rebuild'));
});

test('failure needs an explicit retry and timeout cannot silently enter gameplay',async()=>{
 let number=0;const gate=new ScenePreparation({id:()=>String(++number),timeoutMs:15});
 const first=gate.start(()=>{});gate.accept({type:'story3d:preparation-failed',request:'1'});
 await assert.rejects(first,/FAILED/);assert.equal(gate.phase,'error');
 const second=gate.start(()=>{});assert.equal(number,2);assert.equal(gate.accept({type:'story3d:prepared',request:'1'}),false);
 await assert.rejects(second,/TIMEOUT/);assert.equal(gate.phase,'error');
});

class Node {
 constructor(tag){this.tag=tag;this.children=[];this.style={setProperty(){}};this.classList={toggle(){}};this.hidden=false;}
 append(...items){this.children.push(...items);}
 replaceChildren(...items){this.children=items;}
}
test('previous line exists only when usable and revisiting text does not acknowledge it',async()=>{
 const original=globalThis.document;globalThis.document={createElement:tag=>new Node(tag)};
 try{
  const root=new Node('section'),ack=[];const player=new DialoguePlayer({root,getLocale:()=> 'en'});
  const lines=[{speaker:'maya',speakerLabel:'Maya Brooks',text:'First'},{speaker:'elliot',speakerLabel:'Elliot Reed',text:'Second'}];
  player.open(lines,{acknowledge:async line=>ack.push(line.text)});
  let buttons=root.children.at(-1).children;assert.equal(buttons.some(b=>b.textContent.includes('Previous')),false);
  await buttons.find(b=>b.textContent==='Continue →').onclick();assert.deepEqual(ack,['First']);
  buttons=root.children.at(-1).children;buttons.find(b=>b.textContent==='← Previous line').onclick();
  assert.equal(player.conversation.index,0);assert.deepEqual(ack,['First']);
  player.open(lines,{startIndex:1});assert.equal(player.conversation.index,1);
  assert.ok(root.children.at(-1).children.some(b=>b.textContent==='← Previous line'));
 }finally{globalThis.document=original;}
});

test('case-file formatting separates notices and limitations without changing dialogue',()=>{
 const value=formatCaseFile('【遊戲虛構舊通知 A】問題甲？【通知 B】問題乙。聲明冇列出兩種題目。');
 assert.ok(value.startsWith('舊通知 A\n\n'));assert.ok(value.includes('\n\n通知 B\n'));assert.ok(value.includes('問題甲？'));assert.ok(value.includes('聲明冇列出兩種題目。'));assert.ok(!value.includes('遊戲虛構'));
 assert.ok(formatCaseFile('[Fictional notice A] Question one. [Notice B] Question two.').includes('\n\nNotice B\n'));
});

 test('LOD off waits for scene readiness but never invokes optimizer; quality stays independent',async()=>{
  let calls=0,originalCalls=0;const renderer={prepare:async()=>{calls++;},prepareWithoutLod:async()=>{originalCalls++;},getQuality:()=> 'standard'};
  assert.equal(await prepareRenderer(renderer,false),'standard');assert.equal(calls,0);assert.equal(originalCalls,1);
  assert.equal(await prepareRenderer(renderer,true),'standard');assert.equal(calls,1);
  assert.equal(await prepareRenderer(undefined,false),null);
  await assert.rejects(prepareRenderer(undefined,true),/unavailable/);
  const gate=new ScenePreparation({id:()=> 'off'});let sent;
  const waiting=gate.start(message=>{sent=message;},{buildLod:false});
  assert.equal(sent.buildLod,false);assert.equal(gate.phase,'preparing');
  gate.accept({type:'story3d:prepared',request:'off'});await waiting;
 });
