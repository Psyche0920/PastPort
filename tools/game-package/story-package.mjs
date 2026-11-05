import {PlayerContext} from '../../src/pastport/player/context.mjs';
import {SchemaValidator, contentHash, sameSet} from '../../src/pastport/player/validation.mjs';
import {prepareGameplayPlan} from '../../gameplay/gameplay.mjs';
import {validateNavigation} from '../../frontend/game/navigation.mjs';

import {StoryPackageError, museumSnapshot, museumSnapshotHash} from '../../gameplay/contracts.mjs';
export {StoryPackageError, museumSnapshot, museumSnapshotHash};
const requireValue=(condition,code,message)=>{if(!condition)throw new StoryPackageError(code,message);};
const unique=values=>new Set(values).size===values.length;
const object=value=>value!==null&&typeof value==='object'&&!Array.isArray(value);
const keys=(value,allowed,required=allowed)=>{
  requireValue(object(value)&&required.every(key=>Object.hasOwn(value,key))&&Object.keys(value).every(key=>allowed.includes(key)), 'STORY_INPUT_INVALID', 'Unexpected or missing story package fields');
};
const displayText=value=>typeof value==='string'&&value.trim().length>0||object(value)&&['zh','en'].every(locale=>typeof value[locale]==='string'&&value[locale].trim().length>0);

/** A local, versioned bridge; the shared wire package and rules remain unchanged. */
export class StoryPackageCompiler {
  async compile(input, museum, {narrativeSchema=null}={}) {
    keys(input,['schema_version','story','museum','tasks','presentation']);
    requireValue(input.schema_version==='story-3d-input-0.1.0','STORY_VERSION_UNSUPPORTED','Unsupported Story-to-3D input version');
    keys(input.museum,['tour_id','snapshot_sha256']);
    requireValue(input.museum.tour_id===museum.tourId&&input.museum.snapshot_sha256===await museumSnapshotHash(museum), 'MUSEUM_IDENTITY_MISMATCH','Museum snapshot changed since story binding');
    requireValue(Array.isArray(museum.objects)&&museum.objects.length>0&&unique(museum.objects.map(item=>item.number)), 'MUSEUM_OBJECT_INVALID','Museum object identities are missing or duplicated');
    keys(input.story,['kind','payload','package_id','authoring_mode'],['kind','payload']);
    requireValue(input.story.authoring_mode===undefined||['reviewed','internal_preview'].includes(input.story.authoring_mode),'STORY_MODE_INVALID','Unknown authoring mode');
    const unverified=[];
    let pkg;
    if(input.story.kind==='runtime-package') {
      pkg=structuredClone(input.story.payload);
    } else {
      requireValue(input.story.kind==='narrative-draft'&&narrativeSchema!==null,'STORY_FORMAT_UNSUPPORTED','Provide a RuntimePackage or a schema-validated NarrativeDraft');
      const validator=new SchemaValidator(narrativeSchema);
      validator.assertDefinition('NarrativeDraft',input.story.payload,'STORY_NARRATIVE_INVALID');
      const narrative=input.story.payload.package;
      unverified.push(...input.story.payload.unresolved_items);
      requireValue(unverified.length===0||input.story.authoring_mode==='internal_preview','STORY_UNRESOLVED','Narrative has unresolved items');
      pkg={project_id:narrative.project_id,schema_version:narrative.schema_version,content_version:narrative.content_version,
        package_id:input.story.package_id,runtime_compatibility:structuredClone(museum.runtimeCapabilities),
        evidence_package_hash:narrative.evidence_package_hash,narrative_package_hash:await contentHash(narrative),
        game:structuredClone(narrative.game),media_manifest:[]};
      requireValue(Array.isArray(input.tasks),'STORY_BINDING_INVALID','Task bindings are required');
      for(const binding of input.tasks) {
        const task=pkg.game.scenes.flatMap(scene=>scene.tasks).find(task=>task.task_id===binding.task_id);
        const source=museum.objects.find(item=>item.number===binding.asset_object_number);
        requireValue(task?.kind==='inspect'&&source,'STORY_ASSET_MISSING','Every inspect task needs a real museum asset binding');
        const entry={asset_id:task.asset_id,sha256:source.media_sha256,relative_path:source.media_path};
        const previous=pkg.media_manifest.find(item=>item.asset_id===entry.asset_id);
        requireValue(!previous||JSON.stringify(previous)===JSON.stringify(entry),'STORY_ASSET_CONFLICT','An asset identity maps to different museum files');
        if(!previous)pkg.media_manifest.push(entry);
      }
    }
    const packageHash=await contentHash(pkg);
    const reference={artifact_id:pkg.package_id,project_id:pkg.project_id,kind:'runtime',schema_version:pkg.schema_version,content_version:pkg.content_version,sha256:packageHash};
    const context=await PlayerContext.create(pkg,reference,'story-3d-preview');
    context.initialState();
    requireValue(Array.isArray(input.tasks)&&input.tasks.length===pkg.game.scenes.length&&unique(input.tasks.map(item=>item.task_id)), 'STORY_BINDING_INVALID','Each scene requires exactly one unique task binding');
    const tables=new Map(pkg.game.locales.map(table=>[table.locale,new Map(table.entries.map(item=>[item.key,item.text]))]));
    const text=key=>Object.fromEntries(['zh','en'].map(locale=>{
      const value=tables.get(locale)?.get(key);
      requireValue(typeof value==='string'&&value.trim().length>0,'STORY_TEXT_MISSING',`Missing ${locale} story text: ${key}`);
      return [locale,value];
    }));
    const decisions=new Map(pkg.game.decisions.map(decision=>[decision.decision_id,decision]));
    const objects=new Map(museum.objects.map(item=>[item.number,item]));
    const stageTargets={};
    const chapters=pkg.game.scenes.map((scene,index)=>{
      requireValue(scene.tasks.length===1&&(scene.next_scene_ids.length<=1||(scene.decision_id!==null&&scene.next_scene_ids.length<=4)),'STORY_HOST_UNSUPPORTED','This 3D host requires one task per scene and at most four decision-gated routes');
      const task=scene.tasks[0],binding=input.tasks.find(item=>item.task_id===task.task_id);
      keys(binding,['task_id','scene_id','chapter','objects','required_sources','target_number','asset_object_number','plugin','automatic_decision','access'],['task_id','scene_id','objects','required_sources','target_number','asset_object_number','plugin']);
      requireValue(binding.scene_id===scene.scene_id,'STORY_BINDING_INVALID','Task binding belongs to another scene');
      requireValue(task.kind==='inspect'&&sameSet(task.required_spot_ids,['result'])&&sameSet(task.spots.map(spot=>spot.spot_id),['result'])&&task.guard===null,'STORY_HOST_UNSUPPORTED','Local activities require an unguarded inspect result adapter; other task shapes need another host');
      requireValue(sameSet(scene.required_task_ids,[task.task_id]),'STORY_HOST_UNSUPPORTED','The scene must require its bound activity');
      requireValue(Array.isArray(binding.objects)&&binding.objects.length>0&&unique(binding.objects)&&binding.objects.every(number=>objects.has(number))&&Array.isArray(binding.required_sources)&&unique(binding.required_sources)&&binding.required_sources.every(number=>binding.objects.includes(number))&&objects.has(binding.target_number)&&binding.objects.includes(binding.asset_object_number), 'STORY_OBJECT_MISSING','Task objects, required sources or target do not exist in this museum');
      requireValue(binding.chapter===undefined||Number.isSafeInteger(binding.chapter)&&binding.chapter>0,'STORY_BINDING_INVALID','Chapter number is invalid');
      if(binding.access){
        keys(binding.access,['view_id','station_id','interaction']);
        requireValue(binding.access.station_id==='spawn'&&binding.access.interaction==='inspect'&&typeof binding.access.view_id==='string','STORY_ACCESS_INVALID','Unsupported spatial task access');
      }
      const source=objects.get(binding.asset_object_number),asset=pkg.media_manifest.find(item=>item.asset_id===task.asset_id);
      requireValue(asset&&asset.sha256===source.media_sha256,'STORY_ASSET_MISMATCH','Task asset differs from its museum object');
      const decision=scene.decision_id===null?null:decisions.get(scene.decision_id);
      requireValue(scene.decision_id===null||decision,'STORY_DECISION_MISSING','Scene decision is not declared');
      requireValue(binding.automatic_decision===undefined||typeof binding.automatic_decision==='boolean','STORY_BINDING_INVALID','Automatic decision flag must be boolean');
      requireValue(!binding.automatic_decision||decision,'STORY_BINDING_INVALID','Automatic decision needs an existing decision');
      if(binding.automatic_decision) {
        const outcomes=binding.plugin.kind==='routing'?['clean','rework']:binding.plugin.kind==='budget'?binding.plugin.plans.map(plan=>plan.id):['complete'];
        requireValue(sameSet(outcomes,decision.options.map(option=>option.option_id)),'STORY_OUTCOME_MISMATCH','Plugin outcomes differ from the narrative decision options');
      }
      stageTargets[scene.scene_id]=binding.target_number;
      return {id:scene.scene_id,taskId:task.task_id,...(binding.access?{access:structuredClone(binding.access)}:{}),chapter:binding.chapter??index+1,title:text(scene.title_key),body:text(scene.body_key),feedback:scene.feedback.map(item=>({guard:structuredClone(item.guard),text:text(item.text_key)})),after:text(task.feedback_key),hints:task.hint_keys.map(text),objects:[...binding.objects],requiredSources:[...binding.required_sources],plugin:structuredClone(binding.plugin),
        ...(decision?{[binding.automatic_decision?'automaticDecision':'decision']:decision.decision_id,options:decision.options.map(option=>({id:option.option_id,text:text(option.text_key)}))}:{})};
    });
    requireValue(unique(pkg.game.scenes.map(scene=>scene.scene_id))&&unique(pkg.game.scenes.flatMap(scene=>scene.tasks.map(task=>task.task_id))),'STORY_ID_DUPLICATED','Scene or task identities are duplicated');
    const sceneIds=new Set(chapters.map(chapter=>chapter.id));
    requireValue(pkg.game.scenes.every(scene=>scene.next_scene_ids.every(id=>sceneIds.has(id))),'STORY_SCENE_MISSING','Next scene is not declared');
    const presentation=structuredClone(museumSnapshot(museum));
    const copy=input.presentation;
    keys(copy,['title','intro','openingLines','guideLines','castFrames','castRows','sourceTitle','speakerNames','endingNotice','instructions','startLabel','characterProfiles','startupPreparation','continuation'],['intro']);
    requireValue(displayText(copy.intro)&&(!copy.title||displayText(copy.title))&&(!copy.sourceTitle||displayText(copy.sourceTitle))&&(!copy.endingNotice||displayText(copy.endingNotice))&&(!copy.instructions||displayText(copy.instructions))&&(!copy.startLabel||displayText(copy.startLabel)),'STORY_TEXT_MISSING','Presentation needs readable story title and introduction');
    requireValue(copy.speakerNames===undefined||object(copy.speakerNames)&&Object.values(copy.speakerNames).every(displayText),'STORY_CAST_INVALID','Speaker display names require readable locales');
    requireValue(copy.characterProfiles===undefined||Array.isArray(copy.characterProfiles)&&copy.characterProfiles.length<=20&&copy.characterProfiles.every(p=>object(p)&&typeof p.id==='string'&&p.id.length>0&&displayText(p.introduction)&&copy.speakerNames&&Object.hasOwn(copy.speakerNames,p.id))&&unique(copy.characterProfiles.map(p=>p.id)),'STORY_CAST_INVALID','Character introductions need unique stable identities, localized names and readable copy');
    requireValue(copy.startupPreparation===undefined||copy.startupPreparation==='lod','STORY_INPUT_INVALID','Unknown scene preparation mode');
    if(copy.continuation){keys(copy.continuation,['manifest','boundary_scene_id','entry_scene_id']);requireValue(copy.continuation.manifest==='data/previous-slice.json'&&sceneIds.has(copy.continuation.boundary_scene_id)&&sceneIds.has(copy.continuation.entry_scene_id),'STORY_INPUT_INVALID','Invalid continuation metadata');}
    const lines=values=>Array.isArray(values)&&values.length<=128&&values.every(line=>object(line)&&typeof line.speaker==='string'&&line.speaker.length>0&&displayText(line.text));
    requireValue((copy.guideLines===undefined||lines(copy.guideLines))&&(copy.openingLines===undefined||object(copy.openingLines)&&Object.entries(copy.openingLines).every(([id,value])=>sceneIds.has(id)&&lines(value))),'STORY_DIALOGUE_INVALID','Opening dialogue must belong to a declared story scene');
    requireValue((copy.castFrames===undefined||object(copy.castFrames)&&Object.values(copy.castFrames).every(value=>Number.isSafeInteger(value)&&value>=0&&value<=3))&&(copy.castRows===undefined||object(copy.castRows)&&Object.values(copy.castRows).every(value=>value===0||value===100)),'STORY_CAST_INVALID','Portrait frame or row is unsupported');
    const initialScene=pkg.game.scenes.find(scene=>scene.scene_id===pkg.game.initial_state.current_scene_id);
    requireValue(initialScene,'STORY_SCENE_MISSING','Initial scene is not declared');
    const hero=pkg.game.characters.find(character=>character.character_id===pkg.game.protagonist);
    requireValue(hero,'STORY_CHARACTER_MISSING','Protagonist is not declared');
    Object.assign(presentation,{profile:'story-3d-0.1.0',title:copy.title??{zh:pkg.game.chapter_id,en:pkg.game.chapter_id},intro:copy.intro,chapters,stageTargets,
      sourceNotes:structuredClone(museum.sourceNotes),sourceTitle:copy.sourceTitle??{zh:'馆藏资料',en:'Museum sources'},
      openingLines:copy.openingLines??{},guideLines:copy.guideLines??[],castFrames:copy.castFrames??{},castRows:copy.castRows??{},castByStage:{},worldActors:[],spokenCopy:{},
      ...(copy.startupPreparation?{startupPreparation:copy.startupPreparation}:{}),...(copy.continuation?{continuation:structuredClone(copy.continuation)}:{}),characterProfiles:structuredClone(copy.characterProfiles??[]),instructions:copy.instructions??null,startLabel:copy.startLabel??null,endingNotice:copy.endingNotice??null,speakerNames:structuredClone(copy.speakerNames??{}),protagonist:text(hero.name_key),fictionNotice:input.story.kind==='narrative-draft'?input.story.payload.package.fiction_notice:null,
      endings:pkg.game.endings.flatMap(table=>table.endings.map(ending=>({id:ending.ending_id,title:text(ending.outcomes[0].label_key),text:text(ending.outcomes[0].text_key),outcomes:ending.outcomes.map(outcome=>({title:text(outcome.label_key),text:text(outcome.text_key),variants:outcome.variants.map(variant=>({...variant,text:text(variant.text_key)}))}))}))),
      interactionVersion:4,releaseId:'story-3d-preview',saveKey:`pastport:story-3d:${pkg.project_id}:${packageHash}:${input.museum.snapshot_sha256.slice(0,16)}`});
    for(const shot of presentation.shots)shot.taskScenes=chapters.filter(chapter=>chapter.objects.includes(shot.number)||stageTargets[chapter.id]===shot.number).map(chapter=>chapter.id);
    validateNavigation(presentation);
    const gameplayPlan=await prepareGameplayPlan(pkg,presentation);
    requireValue(gameplayPlan.status==='ready','STORY_PLUGIN_MISSING',JSON.stringify(gameplayPlan.build_requests));
    return {runtime:pkg,reference,presentation,gameplayPlan,report:{schema_version:'story-3d-report-0.1.0',status:'ready',input_sha256:await contentHash({input:JSON.stringify(input)}),museum_snapshot_sha256:input.museum.snapshot_sha256,runtime_sha256:packageHash,scene_count:chapters.length,task_count:input.tasks.length,object_count:objects.size,model_calls:0,authoring_mode:input.story.authoring_mode??'reviewed',unverified,human_acceptance:'not_performed'}};
  }
}
