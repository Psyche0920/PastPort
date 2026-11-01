import {contentHash} from './engine/validation.mjs';
import {museumSnapshotHash,StoryPackageError} from './story-package.mjs';
import {Activity} from './plugins.mjs';
import {gameplayCatalog,gameplayCatalogSha256} from './gameplay-catalog.mjs';

const requireValue=(value,message)=>{if(!value)throw new StoryPackageError('PREPARED_GAME_INVALID',message);};
const canonical=value=>Array.isArray(value)?'['+value.map(canonical).join(',')+']':value&&typeof value==='object'?'{'+Object.keys(value).sort().map(key=>JSON.stringify(key)+':'+canonical(value[key])).join(',')+'}':JSON.stringify(value);
const same=(a,b)=>canonical(a)===canonical(b);

/** Deterministic presentation of an exact Story/Gameplay/environment revision. */
export async function preparedStoryInput(draft,plan,environment,museum,pluginCodeSha256,environmentSha256){
  requireValue(plan?.schema_version==='gameplay-preparation/0.4.0'&&plan.status==='prepared'&&plan.gaps.length===0,'Gameplay plan is not ready');
  requireValue(plan.capability_catalog_sha256===gameplayCatalogSha256&&draft.capability_catalog_sha256===gameplayCatalogSha256,'Gameplay catalog identity changed');
  requireValue(plan.host_profile==='pastport.demo.activities/1','Unknown gameplay host');
  requireValue(plan.story_draft_sha256===await contentHash(draft),'Story draft changed after preparation');
  requireValue(plan.environment_sha256===environmentSha256,'Environment changed after preparation');
  requireValue(plan.narrative_ref?.sha256===await contentHash(draft.package)&&plan.project_id===draft.package.project_id&&environment.project_id===plan.project_id,'Story/environment identities differ');
  requireValue(museum.spatialContext?.metric_revision===environment.metric_spatial?.revision,'Museum uses a different metric environment');
  requireValue(same(museum.spatialContext.worlds,environment.metric_spatial.worlds),'Museum geometry or navigation changed');
  const scenes=draft.package.game.scenes;
  const mechanicIntents=new Map(draft.gameplay_intents.map(intent=>[intent.task_id,intent]));
  const tilingIntents=draft.gameplay_intents.filter(intent=>intent.kind==='coverage');
  requireValue(mechanicIntents.size===draft.gameplay_intents.length&&mechanicIntents.size===scenes.length,'Every task needs an explicit mechanic');
  const bindings=new Map(plan.bindings.map(binding=>[binding.task_id,binding]));
  const intents=new Map(draft.spatial_intents.map(intent=>[intent.task_id,intent]));
  requireValue(bindings.size===plan.bindings.length&&bindings.size===scenes.length&&intents.size===scenes.length,'Task coverage differs');
  let previous=environment.entry_view_id;
  const tasks=[];
  for(const [index,scene]of scenes.entries()){
    requireValue(scene.tasks.length===1,'Only one task per scene is supported');
    const task=scene.tasks[0],binding=bindings.get(task.task_id),intent=intents.get(task.task_id);
    requireValue(binding&&intent&&binding.scene_id===scene.scene_id&&binding.object_number===intent.object_number&&task.asset_id===`object-${intent.object_number}`,'Task identity drift');
    const world=environment.metric_spatial.worlds.find(world=>world.view_id===intent.view_id);
    const station=binding.selected_station;
    requireValue(world&&station.view_id===intent.view_id&&station.station_id===intent.station_id&&intent.station_id==='spawn'&&intent.interaction==='inspect_linked_source','Selected task station differs');
    requireValue(station.world_binding===world.world_binding&&station.geometry_input_sha256===world.geometry.input_sha256&&station.geometry_algorithm_sha256===world.geometry.algorithm_sha256,'Station geometry identity differs');
    const node=world.geometry.result.objects.find(node=>node.key===`object:${intent.object_number}`);
    const observation=node?.planning.observation_positions.find(item=>item.station===station.station_id);
    requireValue(node?.planning.enabled_interactions.includes('inspect')&&observation&&same(observation.point,station.point),'Selected station is not registered');
    // This bounded profile supports staying in one view or one registered transition.
    if(previous!==world.view_id){
      const origin=environment.metric_spatial.worlds.find(world=>world.view_id===previous);
      const link=origin?.navigation.find(link=>link.target_view_id===world.view_id);
      requireValue(link?.point&&Number.isFinite(link.arrival_yaw)&&Number.isFinite(link.arrival_pitch),'Task sequence has no registered transition with arrival orientation');
    }
    previous=world.view_id;
    requireValue(same(binding.source_claim_ids,task.evidence_refs)&&binding.lifecycle.status==='passed'&&binding.config_sha256===await contentHash(binding.config)&&binding.lifecycle.config_sha256===binding.config_sha256,'Task source/config receipt differs');
    requireValue(binding.plugin.code_sha256===pluginCodeSha256&&binding.lifecycle.plugin_code_sha256===pluginCodeSha256,'Plugin code changed after verification');
    const requested=mechanicIntents.get(task.task_id);
    requireValue(requested&&requested.capability_id===binding.capability_id,'Task mechanic declaration changed');
    const config=binding.config;
    requireValue(['dialogue','tiling'].includes(config.kind)&&binding.plugin.plugin_id===`pastport.activity.${config.kind}`,'Unsupported prepared mechanic');
    if(config.kind==='tiling'){
      const exercise=tilingIntents.find(item=>item.task_id===task.task_id);
      requireValue(config.source_gate?.target_claim_id===exercise?.source_requirement.target_claim_id&&config.source_gate.options.some(option=>option.id===exercise.source_requirement.target_claim_id),'Source challenge is not grounded');
      requireValue(exercise?.capability_id===binding.capability_id&&gameplayCatalog.profiles.some(profile=>profile.capability_id===exercise.capability_id&&profile.plugin_id===binding.plugin.plugin_id)&&same(exercise.rules,{width:config.width,height:config.height,pieces:config.pieces,rotation_allowed:config.rotation_allowed})&&binding.completion==='board_coverage'&&binding.exercise_notice===exercise.fiction_notice,'Tiling is not explicitly requested by this story');
    }else requireValue(requested.kind==='source_reading'&&binding.completion==='source_exposure_not_comprehension','Reading completion differs');
    new Activity(config);
    tasks.push({task_id:task.task_id,scene_id:scene.scene_id,chapter:index+1,objects:[intent.object_number],required_sources:[intent.object_number],target_number:intent.object_number,asset_object_number:intent.object_number,plugin:structuredClone(config),access:{view_id:intent.view_id,station_id:intent.station_id,interaction:'inspect'}});
  }
  const locales=draft.package.game.locales;
  const firstCopy=locale=>locales.find(table=>table.locale===locale).entries.find(entry=>entry.key===scenes[0].body_key).text;
  const narrativeHash=await contentHash(draft.package);
  return {schema_version:'story-3d-input-0.1.0',story:{kind:'narrative-draft',payload:draft,package_id:`prepared-story-${narrativeHash.slice(0,16)}`,authoring_mode:'internal_preview'},museum:{tour_id:museum.tourId,snapshot_sha256:await museumSnapshotHash(museum)},tasks,presentation:{title:{zh:'遗址故事 · 玩法试玩',en:'Heritage Story · Gameplay Trial'},intro:{zh:firstCopy('zh'),en:firstCopy('en')}}};
}
