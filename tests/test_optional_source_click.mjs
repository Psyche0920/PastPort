import test from 'node:test';
import assert from 'node:assert/strict';
import {Scene3DView} from '../frontend/game/scene3d-view.mjs';
test('optional sources remain readable without granting task observation access',()=>{
  const viewed=[],notices=[];
  const view=Object.create(Scene3DView.prototype);
  Object.assign(view,{session:{current:{access:{},requiredSources:[6]}},atTaskView:()=>true,supportsInspection:()=>false,cancelMotion:()=>{},inspect:n=>viewed.push(n),notify:s=>notices.push(s)});
  view.inspectWithAccess(8);view.inspectWithAccess(14);
  assert.deepEqual(viewed,[8,14]);assert.equal(notices.length,0);
  view.inspectWithAccess(6);
  assert.deepEqual(viewed,[8,14]);assert.equal(notices.length,1);
});
