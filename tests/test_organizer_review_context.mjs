import test from 'node:test';
import assert from 'node:assert/strict';
import {ReviewWorkbench} from '../frontend/organizer/review.mjs';

test('detached project does not fetch or apply old review state',async()=>{
  const workbench=Object.create(ReviewWorkbench.prototype);
  workbench.isActive=()=>false;
  workbench.api=()=>assert.fail('stale review must not fetch');
  await workbench.afterSaved();
  await workbench.checkChanges();
});

test('switching project while review refresh is pending cannot apply its old version',async()=>{
  const workbench=Object.create(ReviewWorkbench.prototype);
  let active=true;
  workbench.isActive=()=>active;
  workbench.data={source_id:'old-source'};
  workbench.api=async()=>{active=false;return {source_id:'old-source',snapshot_current:false};};
  workbench.onChange=()=>assert.fail('stale result must not invalidate new project');
  workbench.onApply=()=>assert.fail('stale result must not replace new project');
  workbench.renderControls=()=>{};
  workbench.onMessage=()=>assert.fail('stale result must not show success');
  await workbench.afterSaved();
  assert.equal(workbench.syncing,false);
});

import {environmentActionState} from '../frontend/organizer/review.mjs';

test('environment action remains disabled while queued or running after reload',()=>{
  for(const status of ['queued','running','awaiting_external']){
    const state=environmentActionState([{project_id:'new',status}],'new');
    assert.equal(state.disabled,true);
  }
});
test('only the same project completed handoff marks environment complete',()=>{
  const ready={project_id:'old',status:'environment_ready',prepared_source_id:'ready'};
  assert.equal(environmentActionState([ready],'new').disabled,false);
  assert.equal(environmentActionState([ready],'old').disabled,true);
  assert.equal(environmentActionState([{...ready,prepared_source_id:null}],'old').disabled,false);
});
test('a running attempt takes precedence over an older completed attempt',()=>{
  const jobs=[{project_id:'p',status:'environment_ready',prepared_source_id:'ready'},{project_id:'p',status:'running'}];
  assert.equal(environmentActionState(jobs,'p').label,environmentActionState([jobs[1]],'p').label);
  assert.equal(environmentActionState([{project_id:'p',status:'failed'}],'p').disabled,false);
});


import {restoredWorkflow} from '../frontend/organizer/review.mjs';
test('server selection restores the same project without old tab state',()=>{
  assert.deepEqual(restoredWorkflow([],{project_id:'new',source_id:'new-source',story_ready:true},{environmentJob:'old-job',storyJob:'old-story'}),{
    environmentSource:'new-source',storySource:'new-source',environmentJob:null,storyJob:null,projectId:'new',
  });
});
test('pending new materials cannot inherit another project story or environment',()=>{
  const jobs=[{job_id:'new-job',project_id:'new',status:'running'}, {job_id:'old-story',source_id:'other-source',status:'running'}];
  const state=restoredWorkflow(jobs,{project_id:'old',source_id:'old-source',story_ready:true},{environmentJob:'new-job',storyJob:'old-story'});
  assert.equal(state.environmentSource,null);assert.equal(state.storySource,null);
  assert.equal(state.projectId,'new');assert.equal(state.environmentJob,'new-job');assert.equal(state.storyJob,null);
});
test('a saved environment does not unlock assembly without a saved story',()=>{
  const state=restoredWorkflow([],{project_id:'p',source_id:'environment',story_ready:false});
  assert.equal(state.environmentSource,'environment');assert.equal(state.storySource,null);
});
