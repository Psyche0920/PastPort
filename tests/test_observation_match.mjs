import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {ObservationMatch} from '../prototype/observation-match.mjs';
import {GameSession} from '../prototype/adventure-session.mjs';

const chapter=JSON.parse(readFileSync(new URL('../data/locales/zh/muradiye-story.json',import.meta.url)));
const storage=()=>({value:null,getItem(){return this.value;},setItem(key,value){this.value=value;}});
const solve=puzzle=>{for(const option of puzzle.options)puzzle.assign(option.id,puzzle.markers.find(marker=>marker.spotId===option.id).label);};

test('All observation scenes have numbered options and shuffled markers at original image coordinates',()=>{
  for(const scene of chapter.scenes.filter(scene=>scene.task.hotspots)){
    const puzzle=new ObservationMatch(scene.task.hotspots,()=>.999);
    assert.deepEqual(puzzle.options.map(option=>option.number),[1,2,3]);
    puzzle.markers.forEach((marker,index)=>{
      assert.notEqual(marker.spotId,puzzle.options[index].id);
      const source=scene.task.hotspots.find(spot=>spot.id===marker.spotId);
      assert.deepEqual([marker.x,marker.y],[source.x,source.y]);
    });
  }
});

test('Incomplete and incorrect assignments can be revised without moving marker labels',()=>{
  const puzzle=new ObservationMatch(chapter.scenes[2].task.hotspots,()=>.999), labels=JSON.stringify(puzzle.markers);
  puzzle.assign(puzzle.options[0].id,'A');
  assert.equal(puzzle.check().missing,2);
  puzzle.options.forEach((option,index)=>puzzle.assign(option.id,String.fromCharCode(65+index)));
  assert.equal(puzzle.check().missing,0); assert.equal(puzzle.check().complete,false);
  puzzle.assign(puzzle.options[1].id,'A');
  assert.equal(puzzle.assignments.has(puzzle.options[0].id),false,'One marker cannot be assigned to two options');
  solve(puzzle); assert.equal(puzzle.check().complete,true);
  assert.equal(JSON.stringify(puzzle.markers),labels);
});

test('Wrong answers and unsubmitted correct drafts grant no evidence, unlock or time cost',()=>{
  const session=new GameSession(chapter,'matching-test',storage());
  session.dispatch('openTally'); session.dispatch('advance');
  const puzzle=new ObservationMatch(session.engine.scene.task.hotspots,()=>.999), before=session.engine.snapshot();
  puzzle.options.forEach((option,index)=>puzzle.assign(option.id,String.fromCharCode(65+index)));
  assert.equal(session.submitObservationMatch(puzzle),false);
  assert.deepEqual(session.engine.snapshot(),before);
  solve(puzzle); assert.deepEqual(session.engine.snapshot(),before,'Solving a draft requires explicit submission');
  assert.equal(session.submitObservationMatch(puzzle),true);
  assert.ok(session.engine.state.inventory.includes('loading-slip'));
  assert.equal(session.engine.state.completed.includes('courtyard'),true);
  assert.equal(session.engine.canAdvance(),false,'The original character decision remains required');
});

test('Fountain requires all pairs; imaret matching still leaves classification locked until sorting',()=>{
  const store=storage(),session=new GameSession(chapter,'matching-test',store);
  session.dispatch('openTally');session.dispatch('advance');
  let puzzle=new ObservationMatch(session.engine.scene.task.hotspots);solve(puzzle);session.submitObservationMatch(puzzle);
  session.dispatch('choose','vouch');session.dispatch('advance');
  puzzle=new ObservationMatch(session.engine.scene.task.hotspots);solve(puzzle);
  puzzle.assign(puzzle.options[2].id,puzzle.assignments.get(puzzle.options[0].id));
  assert.equal(session.submitObservationMatch(puzzle),false);
  assert.deepEqual(session.engine.state.observed.fountain,undefined);
  solve(puzzle);session.submitObservationMatch(puzzle);session.dispatch('choose','help');session.dispatch('advance');
  puzzle=new ObservationMatch(session.engine.scene.task.hotspots);solve(puzzle);session.submitObservationMatch(puzzle);
  assert.ok(session.engine.state.inventory.includes('kitchen-slip'));
  assert.equal(session.engine.canSort(),true);
  assert.equal(session.engine.state.completed.includes('imaret'),false);
  const restored=new GameSession(chapter,'matching-test',store);restored.restore();
  assert.deepEqual(restored.engine.snapshot(),session.engine.snapshot());
});

test('Reject unknown assignments and a puzzle from a different scene',()=>{
  const session=new GameSession(chapter,'matching-test',storage());
  const puzzle=new ObservationMatch(chapter.scenes[1].task.hotspots);
  assert.throws(()=>puzzle.assign('missing','A'),/未知/);
  assert.throws(()=>puzzle.assign(puzzle.options[0].id,'Z'),/未知/);
  assert.throws(()=>session.submitObservationMatch(puzzle),/不一致/);
});
