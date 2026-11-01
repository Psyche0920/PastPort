import test from 'node:test';
import assert from 'node:assert/strict';
import {SceneStoryBridge} from '../../frontend/game/scene3d-bridge.mjs';
import {sourceArrival,screenBearing} from '../../frontend/game/scene3d-navigation.mjs';
import {Scene3DView} from '../../frontend/game/scene3d-view.mjs';
test('high and unreachable observations allow reading while reachable ground objects require arrival',()=>{
  const view=Object.create(Scene3DView.prototype);
  view.session={current:{id:'one'},presentation:{shots:[{number:2,available:true},{number:23,available:true},{number:40,available:false}],scenes:[{hotspots:[{number:2,pitch:53},{number:23,pitch:0},{number:40,pitch:0}]}]}};
  view.readOnlySources=new Set();view.arrivedSources=new Set();
  assert.equal(view.canObserve(2),true);assert.equal(view.canObserve(40),true);assert.equal(view.canObserve(23),false);
  view.readOnlySources.add('one:23');assert.equal(view.canObserve(23),true);
  view.session.current={id:'two'};assert.equal(view.canObserve(23),false);
  view.arrivedSources.add('two:23');assert.equal(view.canObserve(23),true);assert.equal(view.canObserve(999),false);
});
test('source arrival yaw and pitch survive navigation without invented headings',()=>{assert.deepEqual(sourceArrival('http://127.0.0.1:56082/scene3d-results/test/?arrival_yaw=-142.8918099193271&arrival_pitch=-12.352848325188118'),{yaw:-142.8918099193271,pitch:-12.352848325188118});assert.throws(()=>sourceArrival('http://localhost/?arrival_yaw=Infinity&arrival_pitch=0'),RangeError);});
test('a portal behind the player asks for a turn, not sideways travel',()=>{assert.equal(screenBearing({x:-1,z:2},{x:.2,y:0}),'↶');assert.equal(screenBearing({x:1,z:2},{x:-.2,y:0}),'↷');assert.equal(screenBearing({x:1,z:-2},{x:2,y:0}),'→');});
function fixture(){const sent=[],inspected=[],arrived=[];const bridge=new SceneStoryBridge({sceneIds:['one','two'],objectIds:[68,86],send:m=>sent.push(m),inspect:n=>inspected.push(n),arrive:n=>arrived.push(n)});bridge.attach({sceneId:'one',binding:'fixed-input',markers:[{number:68,position:[2,3,4],navigationReviewed:true},{number:86,position:[4,3,5],navigationReviewed:false}]});return {bridge,sent,inspected,arrived};}
test('inspection does not complete a task or request navigation',()=>{const f=fixture();assert.equal(f.bridge.click(68),true);assert.deepEqual(f.inspected,[68]);assert.deepEqual(f.arrived,[]);assert.deepEqual(f.sent,[]);});
test('unreviewed navigation cannot start an approach',()=>{const f=fixture();assert.equal(f.bridge.approach(86),false);assert.deepEqual(f.sent,[]);});
test('arrival requires the current route receipt and actual proximity',()=>{const f=fixture();f.bridge.approach(68);const receipt={...f.sent[0],routeComplete:true,position:[2,1.6,4]};assert.equal(f.bridge.update({...receipt,token:0}),false);assert.equal(f.bridge.update({...receipt,position:[20,1.6,4]}),false);assert.equal(f.bridge.update({...receipt,routeComplete:false}),false);assert.equal(f.bridge.update(receipt),true);assert.equal(f.bridge.update(receipt),false);assert.deepEqual(f.arrived,[68]);});
test('switching viewpoint invalidates stale arrivals',()=>{const f=fixture();f.bridge.approach(68);const receipt={...f.sent[0],routeComplete:true,position:[2,1.6,4]};f.bridge.attach({sceneId:'two',binding:'second-input',markers:[]});assert.equal(f.bridge.update(receipt),false);assert.deepEqual(f.arrived,[]);});
