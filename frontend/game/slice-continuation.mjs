import {GameSession} from './session.mjs';
const same=(a,b)=>JSON.stringify(canonical(a))===JSON.stringify(canonical(b));
const canonical=v=>Array.isArray(v)?v.map(canonical):v&&typeof v==='object'?Object.fromEntries(Object.keys(v).sort().map(k=>[k,canonical(v[k])])):v;
const requireValue=(v,m)=>{if(!v)throw Error('Continuation rejected: '+m);};
/** Replay a package-bound local game snapshot through the same rule engine.
 * This is gameplay continuation only, never historical review or credential authority. */
export async function continueCompletedSlice(manifest,nextBundle,raw){
 requireValue(manifest.schema_version==='completed-slice-continuation/1','unknown manifest');
 requireValue(manifest.next_runtime_sha256===nextBundle.reference.sha256,'destination package changed');
 const old=await GameSession.create(manifest.previous.runtime,manifest.previous.reference,manifest.previous.presentation);
 old.restore(raw);
 requireValue(old.state.ending_id&&old.current.id===manifest.boundary_scene_id,'previous slice is not complete');
 const next=await GameSession.create(nextBundle.runtime,nextBundle.reference,nextBundle.presentation);
 requireValue(old.context.package.project_id===next.context.package.project_id,'project differs');
 const oldGame=old.context.game,newGame=next.context.game;
 requireValue(same(old.presentation.objects,next.presentation.objects)&&same(old.presentation.spatialContext,next.presentation.spatialContext),'source or spatial identities changed');
 requireValue(same(old.context.package.media_manifest,next.context.package.media_manifest),'media changed');
 for(const scene of oldGame.scenes){
  const candidate=newGame.scenes.find(s=>s.scene_id===scene.scene_id);requireValue(candidate,'missing prior scene');
  const expected=structuredClone(scene);if(scene.scene_id===manifest.boundary_scene_id)expected.next_scene_ids=[manifest.entry_scene_id];
  requireValue(same(candidate,expected),'prior scene changed');
  const a=old.presentation.chapters.find(c=>c.id===scene.scene_id),b=next.presentation.chapters.find(c=>c.id===scene.scene_id);
  requireValue(b&&same(a.plugin,b.plugin)&&same(a.requiredSources,b.requiredSources)&&same(a.access,b.access),'prior activity or access changed');
 }
 const boundary=oldGame.scenes.find(s=>s.scene_id===manifest.boundary_scene_id);
 requireValue(boundary.next_scene_ids.length===0&&newGame.scenes.some(s=>s.scene_id===manifest.entry_scene_id),'not a terminal extension');
 for(const rule of oldGame.rules){
  const expected=structuredClone(rule);
  if(rule.event==='option_chosen'&&rule.target_id===boundary.decision_id){
   requireValue(rule.effects.some(e=>e.kind==='resolve_ending'),'terminal decision has no ending');
   expected.effects=rule.effects.map(e=>e.kind==='resolve_ending'?{kind:'unlock_scene',scene_id:manifest.entry_scene_id}:e);
  }
  requireValue(same(newGame.rules.find(r=>r.rule_id===rule.rule_id),expected),'prior rule changed');
 }
 for(const field of ['props','characters','decisions','variables'])for(const row of oldGame[field]){
  const key={props:'prop_id',characters:'character_id',decisions:'decision_id',variables:'name'}[field];
  requireValue(same(newGame[field].find(r=>r[key]===row[key]),row),'prior '+field+' changed');
 }
 for(const table of oldGame.locales)for(const row of table.entries)requireValue(same(newGame.locales.find(t=>t.locale===table.locale)?.entries.find(r=>r.key===row.key),row),'prior story text changed');
 let count=0;
 while(next.current.id!==manifest.entry_scene_id){
  requireValue(++count<=oldGame.scenes.length,'unexpected continuation loop');
  const chapter=old.presentation.chapters.find(c=>c.id===next.current.id);
  requireValue(chapter&&old.taskDone(chapter),'cannot skip an unfinished task');
  const entry=old.entry(chapter);
  for(const n of entry.sources)next.observeSource(n);
  if(chapter.plugin.kind==='dialogue')for(const id of entry.activity.seen)await next.dispatch({kind:'read',id});
  else if(chapter.plugin.kind==='question')await next.dispatch({kind:'answer',id:entry.activity.selected});
  else throw Error('Continuation rejected: unsupported prior activity');
  requireValue(next.taskDone(),'activity replay did not complete');
  next.local[chapter.id]=structuredClone(entry);
  if(chapter.decision){const decision=old.state.decisions.find(d=>d.decision_id===chapter.decision);requireValue(decision,'missing saved decision');await next.choose(decision.option_id);}
  await next.advance();
 }
 requireValue(same(next.state.decisions,old.state.decisions)&&same([...next.state.inventory].sort(),[...old.state.inventory].sort())&&same([...next.state.completed_task_ids].sort(),[...old.state.completed_task_ids].sort()),'replay changed prior progress');
 for(const variable of old.state.variables)requireValue(same(next.state.variables.find(v=>v.name===variable.name),variable),'replay changed prior variable');
 for(const n of old.notebook)next.recordBrowse(n);
 next.restore(next.serialize());return next;
}
