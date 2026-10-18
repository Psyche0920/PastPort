import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { WalkMesh, Walker } from '../prototype/walkmesh.mjs';
import { GameSession } from '../prototype/adventure-session.mjs';

const chapter = JSON.parse(readFileSync(new URL('../data/locales/zh/muradiye-story.json', import.meta.url)));
const worlds = JSON.parse(readFileSync(new URL('../data/adventure.zh.json', import.meta.url)));
const storage = () => ({value:null,getItem(){return this.value;},setItem(key,value){this.value=value;}});

test('Every authored interaction and exit is reachable from its scene spawn', () => {
  for (const scene of worlds.scenes) {
    const mesh = new WalkMesh(scene.boundary,scene.obstacles);
    for (const object of scene.objects) {
      const route = mesh.path(scene.spawn,object.approach);
      assert.ok(route.length,`${scene.scene_id}/${object.id} is unreachable`);
      let previous = scene.spawn;
      for (const point of route) { assert.ok(mesh.clear(previous,point)); previous=point; }
    }
  }
});

test('A route around the courtyard pool does not cross the water or leave the floor', () => {
  const courtyard = worlds.scenes.find(scene=>scene.scene_id==='courtyard');
  const mesh = new WalkMesh(courtyard.boundary,courtyard.obstacles);
  const origin = [34,88], target = [91,88], route = mesh.path(origin,target);
  assert.equal(mesh.clear(origin,target),false);
  assert.ok(route.length>1);
  let previous=origin;
  for (const point of route) { assert.ok(mesh.clear(previous,point)); previous=point; }
  assert.deepEqual(mesh.path(origin,[60,87]),[],'The pool is not walkable');
});

test('Keyboard movement advances both axes without crossing blocked geometry', () => {
  const mesh = new WalkMesh([[0,0],[100,0],[100,100],[0,100]],[[[40,20],[60,20],[60,80],[40,80]]]);
  const walker = new Walker(mesh,[20,50]);
  walker.tick(.05,[1,0]);
  assert.ok(walker.position[0]>20);
  const previous=[...walker.position];
  walker.tick(.05,[1,1]);
  assert.ok(walker.position[0]>previous[0]); assert.ok(walker.position[1]>previous[1]);
  for(let i=0;i<300;i++) walker.tick(.05,[1,0]);
  assert.ok(walker.position[0]<40);
  assert.ok(mesh.allows(walker.position));
});

test('Walking reaches the target at a bounded speed and does not change story time', () => {
  const scene=worlds.scenes[1], mesh=new WalkMesh(scene.boundary,scene.obstacles);
  const walker=new Walker(mesh,scene.spawn), session=new GameSession(chapter,worlds.version,storage());
  const target=[91,88]; assert.ok(walker.goTo(target));
  for(let i=0;i<1500 && walker.route.length;i++) {
    const previous=[...walker.position]; walker.tick(.016);
    assert.ok(mesh.clear(previous,walker.position));
    assert.ok(Math.hypot((walker.position[0]-previous[0])*16,(walker.position[1]-previous[1])*9)<=230*.016+.001);
  }
  assert.deepEqual(walker.position,target);
  assert.equal(session.engine.state.elapsed,0);
});

test('Save replay preserves choices and positions while rejecting forged evidence and impossible jumps', () => {
  const store=storage(), session=new GameSession(chapter,worlds.version,store);
  session.started=true; session.dispatch('openTally'); session.dispatch('advance');
  session.dispatch('inspect','pool'); session.dispatch('choose','vouch');
  session.positions.courtyard=[28,92]; session.persist();
  const restored=new GameSession(chapter,worlds.version,store); restored.restore();
  assert.deepEqual(restored.engine.snapshot(),session.engine.snapshot());
  assert.deepEqual(restored.positions.courtyard,[28,92]);
  const corrupt=JSON.parse(store.value); corrupt.events=[{kind:'addEvidence',args:['witness']}]; store.value=JSON.stringify(corrupt);
  assert.throws(()=>new GameSession(chapter,worlds.version,store).restore(),/无法重放/);
  corrupt.events=[{kind:'advance',args:[]}]; store.value=JSON.stringify(corrupt);
  assert.throws(()=>new GameSession(chapter,worlds.version,store).restore(),/无法重放/);
});

test('All five scenes and the signed truth ending survive a complete action replay', () => {
  const store=storage(), session=new GameSession(chapter,worlds.version,store);
  for(const [kind,...args] of [
    ['openTally'],['advance'],['inspect','pool'],['choose','vouch'],['advance'],
    ['inspect','cup-left'],['inspect','cup-right'],['choose','help'],['advance'],['inspect','star'],
    ['assign','grain','store'],['assign','flour','kitchen'],['checkSorting'],['advance'],
    ['toggleBoard','tally'],['toggleBoard','loading-slip'],['toggleBoard','kitchen-slip'],['checkBoard'],['choose','confess'],
  ]) session.dispatch(kind,...args);
  const restored=new GameSession(chapter,worlds.version,store); restored.restore();
  assert.equal(restored.engine.state.ending.id,'signed-truth');
  assert.deepEqual(restored.engine.snapshot(),session.engine.snapshot());
});
