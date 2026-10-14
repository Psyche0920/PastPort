import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {StoryEngine} from '../prototype/engine.mjs';
const chapter=JSON.parse(readFileSync(new URL('../data/muradiye-story.json',import.meta.url),'utf8'));
const fresh=()=>new StoryEngine(chapter);
function reachEnding(friend,witness,final) {
  const engine=fresh();engine.openTally();engine.advance();
  engine.inspect('pool');engine.choose(friend);engine.advance();
  engine.inspect('cup-left');engine.inspect('cup-right');engine.choose(witness);engine.advance();
  engine.inspect('star');engine.assign('grain','store');engine.assign('flour','kitchen');assert.equal(engine.checkSorting(),true);engine.advance();
  for(const id of ['loading-slip','kitchen-slip','tally']) engine.toggleBoard(id);
  assert.equal(engine.checkBoard(),true);engine.choose(final);return engine;
}
test('Scenes cannot be skipped, and a decision is required before continuing',()=>{
 const e=fresh();assert.equal(e.friend,'pending');assert.throws(()=>e.advance(),/locked/);e.openTally();e.advance();
 e.inspect('iwan');assert.equal(e.canAdvance(),false);e.inspect('pool');assert.equal(e.canAdvance(),false);
 e.choose('vouch');assert.equal(e.canAdvance(),true);assert.throws(()=>e.choose('detain'),/committed/);
});
test('An unrelated modern detail cannot unlock a witness task',()=>{
 const e=fresh();e.openTally();e.advance();e.inspect('pool');e.choose('detain');e.advance();
 e.inspect('tap');e.inspect('cup-left');assert.throws(()=>e.choose('help'),/Finish/);
 e.inspect('cup-right');e.inspect('cup-right');e.choose('help');assert.equal(e.state.elapsed,2);
 assert.ok(e.state.inventory.includes('witness'));
});
test('Sorting must follow photo observation, and wrong destinations do not advance',()=>{
 const e=fresh();e.openTally();e.advance();e.inspect('pool');e.choose('vouch');e.advance();e.inspect('cup-left');e.inspect('cup-right');e.choose('hurry');e.advance();
 assert.throws(()=>e.assign('grain','store'),/landmark/);e.inspect('sign');assert.equal(e.canSort(),false);
 e.inspect('star');e.assign('grain','kitchen');e.assign('flour','store');assert.equal(e.checkSorting(),false);
 e.assign('grain','store');e.assign('flour','kitchen');assert.equal(e.checkSorting(),true);const elapsed=e.state.elapsed;e.checkSorting();assert.equal(e.state.elapsed,elapsed);
});
test('Witness choice changes exoneration, not just score or ending wording',()=>{
 const withWitness=reachEnding('vouch','help','confess');const without=reachEnding('vouch','hurry','confess');
 assert.equal(withWitness.state.ending.id,'signed-truth');assert.equal(without.state.ending.id,'unfinished-truth');
 assert.equal(withWitness.state.ending.late,true);assert.equal(without.state.ending.late,false);
 assert.ok(!without.state.inventory.includes('witness'));
});
test('Friend detention persists through later scenes and the final outcome',()=>{
 const e=reachEnding('detain','help','confess');assert.equal(e.friend,'detained');assert.match(e.state.ending.friend,/获释/);assert.match(e.state.ending.friend,/记忆/);
});
test('Cover-up and blame create distinct career and service consequences',()=>{
 assert.equal(reachEnding('vouch','help','erase').state.ending.id,'clean-page');
 const e=reachEnding('detain','hurry','accuse');assert.equal(e.state.ending.id,'other-signature');assert.match(e.state.ending.service,/暂停/);
});
test('Save and resume preserves evidence, choices, time and scene locks',()=>{
 const e=fresh();e.openTally();e.advance();e.inspect('pool');e.choose('vouch');e.advance();
 const restored=new StoryEngine(chapter,e.snapshot());assert.equal(restored.scene.id,'fountain');assert.equal(restored.state.elapsed,2);assert.equal(restored.friend,'with_you');assert.ok(restored.state.inventory.includes('loading-slip'));assert.equal(restored.canAdvance(),false);
});
