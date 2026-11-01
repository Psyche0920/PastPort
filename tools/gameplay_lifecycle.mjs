import {readFileSync} from 'node:fs';
import assert from 'node:assert/strict';
import {Activity} from '../prototype/story-agent-demo/plugins.mjs';
import {gameplayCatalogSha256} from '../prototype/story-agent-demo/gameplay-catalog.mjs';
const config=JSON.parse(readFileSync(0,'utf8'));
assert.ok(['dialogue','tiling'].includes(config.kind),'Unregistered verifier profile');
const activity=new Activity(config),initial=activity.initialize();
let state=initial;const checks=['initialize','invalid_action_rejected','serialize_restore_each_step'];
let solution=[];
if(config.kind==='dialogue'){
  assert.throws(()=>activity.reduce(initial,{kind:'read',id:'not-registered'}));
  for(const item of config.items){state=activity.reduce(state,{kind:'read',id:item.id}).state;state=activity.restore(activity.serialize(state));}
  checks.push('source_reading_completes');
}else{
  solution=activity.solution;assert.equal(solution.length,config.pieces.length);
  assert.throws(()=>activity.reduce(initial,{kind:'place',id:0,x:config.width,y:config.height,rotated:false}));
  if(config.source_gate){
    assert.throws(()=>activity.reduce(state,{kind:'place',...solution[0]}));
    const wrong=config.source_gate.options.find(item=>item.id!==config.source_gate.target_claim_id);
    const failed=activity.reduce(state,{kind:'evidence',id:wrong.id});assert.equal(failed.result.status,'failed');assert.equal(failed.state.done,false);
    state=activity.reduce(activity.restore(activity.serialize(failed.state)),{kind:'retry'}).state;
    state=activity.reduce(state,{kind:'evidence',id:config.source_gate.target_claim_id}).state;
    checks.push('source_required','wrong_source_fails_without_completion','failed_save_retries');
  }
  if(solution.length>1)state=activity.reduce(state,{kind:'place',...solution[0]}).state;
  const partial=activity.serialize(state);
  const exited=activity.reduce(state,{kind:'exit'});assert.equal(exited.result.status,'exited');assert.equal(exited.state.done,false);
  state=activity.reduce(activity.restore(activity.serialize(exited.state)),{kind:'resume'}).state;
  assert.equal(activity.serialize(state),partial);
  const failed=activity.reduce(state,{kind:'give_up'});assert.equal(failed.result.status,'failed');assert.equal(failed.state.done,false);
  state=activity.reduce(failed.state,{kind:'retry'}).state;
  if(config.source_gate)state=activity.reduce(state,{kind:'evidence',id:config.source_gate.target_claim_id}).state;
  for(const placement of solution){state=activity.reduce(state,{kind:'place',...placement}).state;state=activity.restore(activity.serialize(state));}
  checks.push('solvable_witness',solution.length>1?'partial_board_restores':'single_piece_checkpoint_restores','exit_resume_preserves_board','failure_retries_without_progress','board_coverage_completes');
}
assert.equal(activity.result(state).status,'completed');assert.throws(()=>activity.reduce(state,{kind:'clear'}));
assert.throws(()=>activity.restore('{"version":99}'));assert.equal(activity.result(activity.initialize()).status,'running');
checks.push('repeat_completion_rejected','malformed_save_rejected','fresh_state_reset');
process.stdout.write(JSON.stringify({status:'passed',checks,solution,catalog_sha256:gameplayCatalogSha256}));
