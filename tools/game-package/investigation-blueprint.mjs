import {readFile,realpath,lstat} from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {StoryPackageCompiler} from './story-package.mjs';
import {Activity} from '../../gameplay/plugins/plugins.mjs';
import {isInvestigation} from '../../gameplay/plugins/investigation.mjs';
import {contentHash} from '../../src/pastport/player/validation.mjs';
const requireValue=(test,message)=>{if(!test)throw Error('INVESTIGATION_BLUEPRINT_INVALID: '+message);};
const keys=(v,list)=>requireValue(v&&typeof v==='object'&&!Array.isArray(v)&&Object.keys(v).every(k=>list.includes(k)),'unexpected fields');
const bilingual=v=>v&&['zh','en'].every(l=>typeof v[l]==='string'&&v[l].trim());
const identifier=s=>typeof s==='string'&&/^[a-z0-9-]{1,80}$/.test(s);
function proveActivity(config){
 const activity=new Activity(config);let state=activity.initialize();const commands=[];
 if(config.kind==='spot-difference')for(const d of config.differences){const[x,y,w,h]=d.left;commands.push({kind:'find-difference',panel:'left',x:Math.floor(x+w/2),y:Math.floor(y+h/2)});}
 else if(['timeline','image-puzzle'].includes(config.kind)){for(const item of config.kind==='timeline'?config.cards:config.pieces)commands.push({kind:'place-piece',id:item.id,slot:item.target_slot});commands.push({kind:'check-arrangement'});}
 else commands.push({kind:'complete-search',verified_numbers:config.targets.map(t=>t.number)});
 let partialChecked=false;
 for(const command of commands){state=activity.reduce(state,command).state;if(!state.done&&!partialChecked){state=activity.restore(activity.serialize(state));state=activity.reduce(state,{kind:'exit'}).state;requireValue(activity.result(state).status==='exited','exit lifecycle');state=activity.reduce(state,{kind:'resume'}).state;partialChecked=true;}}
 requireValue(activity.result(state).status==='completed','declared solution does not complete');activity.restore(activity.serialize(state));
 return {checks:['initialize','serialize_restore','bounded_solution','completion',...(partialChecked?['partial_exit_resume']:[])],host_receipts_simulated:config.kind==='scene-search'};
}
/** Bind authored patterns to existing source/spatial identities, then use the canonical compiler. */
export async function prepareInvestigationBlueprint(baseInput,museum,blueprint,{assetRoot,narrativeSchema=null}={}){
 keys(blueprint,['schema_version','package_id','asset_manifest','interludes','intro','instructions']);
 requireValue(blueprint.schema_version==='investigation-blueprint/1'&&identifier(blueprint.package_id),'version/package ID');
 const baseline=await new StoryPackageCompiler().compile(baseInput,museum,{narrativeSchema});
 requireValue(Array.isArray(blueprint.interludes)&&blueprint.interludes.length>0&&blueprint.interludes.length<=8,'interlude count');
 requireValue(Array.isArray(blueprint.asset_manifest)&&blueprint.asset_manifest.length<=16,'asset manifest');
 const allowedAssets=new Set();const assetReceipts=[];let totalBytes=0;
 for(const asset of blueprint.asset_manifest){
  keys(asset,['path','sha256','content_kind','source_claim_ids']);
  requireValue(typeof asset.path==='string'&&/^assets\/[a-zA-Z0-9_./-]+\.(svg|png|jpg|jpeg|webp)$/.test(asset.path)&&!asset.path.split('/').includes('..')&&!allowedAssets.has(asset.path),'asset path');
  requireValue(/^[a-f0-9]{64}$/.test(asset.sha256)&&['original_fiction','source_attributed'].includes(asset.content_kind)&&Array.isArray(asset.source_claim_ids),'asset provenance/hash');
  requireValue(asset.content_kind==='original_fiction'?asset.source_claim_ids.length===0:asset.source_claim_ids.length>0&&asset.source_claim_ids.every(id=>baseInput.story.payload.game.scenes.some(s=>s.tasks.some(t=>t.evidence_refs.includes(id)))),'source claim identity');
  requireValue(assetRoot,'asset root required');const root=await realpath(assetRoot),candidate=path.resolve(root,asset.path),resolved=await realpath(candidate);
  requireValue(resolved.startsWith(root+path.sep)&&(await lstat(candidate)).isFile()&&!(await lstat(candidate)).isSymbolicLink(),'asset escaped root');
  const bytes=await readFile(candidate);totalBytes+=bytes.length;requireValue(bytes.length<=2000000&&totalBytes<=12000000,'asset budget exceeded');
  requireValue(createHash('sha256').update(bytes).digest('hex')===asset.sha256,'asset changed');allowedAssets.add(asset.path);assetReceipts.push({path:asset.path,sha256:asset.sha256,bytes:bytes.length});
 }
 const input=structuredClone(baseInput);
 input.story={kind:'runtime-package',payload:structuredClone(baseline.runtime),authoring_mode:baseInput.story.authoring_mode??'reviewed'};
 const pkg=input.story.payload,game=pkg.game;
 delete input.presentation.continuation;input.presentation.openingLines??={};
 const tables=new Map(game.locales.map(table=>[table.locale,new Map(table.entries.map(e=>[e.key,e.text]))]));
 for(const table of tables.values())if(table.has('preparation.investigation_v1'))for(const key of [...table.keys()])if(key.startsWith('preparation.investigation_'))table.delete(key);
 const text=(key,value)=>{requireValue(bilingual(value),'bilingual text');for(const[locale,table]of tables){requireValue(!table.has(key),'locale key collision');table.set(key,value[locale]);}return key;};
 const bindings=[];
 for(const row of blueprint.interludes){
  keys(row,['after_scene_id','scene_id','task_id','source_object','required_sources','title','body','objective','opening_lines','plugin','reward']);
  requireValue(identifier(row.scene_id)&&identifier(row.task_id)&&!game.scenes.some(s=>s.scene_id===row.scene_id||s.tasks.some(t=>t.task_id===row.task_id)),'new IDs');
  const anchor=game.scenes.find(s=>s.scene_id===row.after_scene_id);requireValue(anchor&&anchor.decision_id===null&&anchor.next_scene_ids.length===1,'insertion requires one unambiguous edge');
  const outgoing=anchor.next_scene_ids[0];const anchorBinding=input.tasks.find(t=>t.scene_id===anchor.scene_id);
  const oldBinding=input.tasks.find(t=>t.asset_object_number===row.source_object&&(!anchorBinding?.access||t.access?.view_id===anchorBinding.access.view_id));
  requireValue(oldBinding,'primary source object missing');
  const sourceScene=game.scenes.find(s=>s.scene_id===oldBinding.scene_id);const scene=structuredClone(sourceScene),task=scene.tasks[0];
  requireValue(Array.isArray(row.required_sources)&&new Set(row.required_sources).size===row.required_sources.length&&row.required_sources.every(n=>museum.objects.some(o=>o.number===n)),'required sources');
  requireValue(isInvestigation(row.plugin?.kind),'unregistered requested mechanic');new Activity(row.plugin);
  const requestedImages=row.plugin.kind==='spot-difference'?[row.plugin.left_image,row.plugin.right_image]:row.plugin.kind==='image-puzzle'?Object.values(row.plugin.image):[];
  requireValue(requestedImages.every(image=>allowedAssets.has(image)),'activity asset not in checked manifest');
  if(row.plugin.kind==='scene-search'){
   requireValue(typeof oldBinding.access?.view_id==='string','search needs an explicit prepared view');
   requireValue(row.plugin.targets.length===row.required_sources.length&&row.plugin.targets.every(t=>row.required_sources.includes(t.number)),'search/source receipts differ');
   requireValue(row.plugin.targets.every(target=>input.tasks.some(t=>t.asset_object_number===target.number&&t.access?.view_id===oldBinding.access?.view_id)),'search targets not bound to the same prepared view');
  }
  const changed=game.rules.filter(r=>r.event==='task_completed'&&r.target_id===anchor.tasks[0].task_id&&r.effects.some(e=>e.kind==='unlock_scene'&&e.scene_id===outgoing));requireValue(changed.length===1,'ambiguous task completion rule');
  changed[0].effects=changed[0].effects.map(e=>e.kind==='unlock_scene'&&e.scene_id===outgoing?{kind:'unlock_scene',scene_id:row.scene_id}:e);anchor.next_scene_ids=[row.scene_id];
  Object.assign(scene,{scene_id:row.scene_id,title_key:text(row.scene_id+'.title',row.title),body_key:text(row.scene_id+'.body',row.body),required_task_ids:[row.task_id],decision_id:null,next_scene_ids:[outgoing],feedback:[]});
  Object.assign(task,{task_id:row.task_id,objective_key:text(row.task_id+'.objective',row.objective),feedback_key:text(row.task_id+'.feedback',row.plugin.success),hint_keys:[text(row.task_id+'.hint',row.objective)]});game.scenes.splice(game.scenes.findIndex(s=>s.scene_id===anchor.scene_id)+1,0,scene);
  const binding=structuredClone(oldBinding);Object.assign(binding,{scene_id:row.scene_id,task_id:row.task_id,chapter:input.tasks.find(t=>t.scene_id===anchor.scene_id)?.chapter??1,objects:[...new Set([row.source_object,...row.required_sources])],required_sources:row.required_sources,target_number:row.source_object,plugin:row.plugin});delete binding.automatic_decision;input.tasks.push(binding);
  requireValue(Array.isArray(row.opening_lines)&&row.opening_lines.length<=12&&row.opening_lines.every(l=>typeof l.speaker==='string'&&bilingual(l.text)),'opening context');input.presentation.openingLines[row.scene_id]=row.opening_lines;
  const effects=[{kind:'unlock_scene',scene_id:outgoing}];
  if(row.reward){
   requireValue(identifier(row.reward.id)&&bilingual(row.reward.text),'reward ID/copy');
   const previous=game.props.find(p=>p.prop_id===row.reward.id);
   if(previous)requireValue(previous.content_kind==='original_fiction'&&['zh','en'].every(locale=>tables.get(locale)?.get(previous.text_key)===row.reward.text[locale]),'existing reward copy differs');
   else game.props.push({prop_id:row.reward.id,text_key:text(row.reward.id+'.text',row.reward.text),content_kind:'original_fiction'});
   effects.push({kind:'grant_item',item_id:row.reward.id});
  }
  game.rules.push({rule_id:row.task_id+'-completed',priority:140+bindings.length,event:'task_completed',target_id:row.task_id,guard:{kind:'observed_all',scene_id:row.scene_id,spot_ids:['result']},effects,once_key:'once:'+row.task_id+'-completed'});
  bindings.push({scene_id:row.scene_id,task_id:row.task_id,plugin:row.plugin.kind,source_object:row.source_object,after_scene_id:row.after_scene_id,lifecycle:proveActivity(row.plugin)});
 }
 game.locales=[...tables].map(([locale,entries])=>({locale,entries:[...entries].map(([key,text])=>({key,text}))}));
 pkg.package_id=blueprint.package_id;pkg.narrative_package_hash=await contentHash(game);
 if(blueprint.intro){requireValue(bilingual(blueprint.intro),'intro');input.presentation.intro=blueprint.intro;}
 if(baseline.presentation.fictionNotice){const intro=input.presentation.intro;input.presentation.intro=Object.fromEntries(['zh','en'].map(locale=>[locale,baseline.presentation.fictionNotice+'\n'+(typeof intro==='string'?intro:intro[locale])]));}
 if(blueprint.instructions){requireValue(bilingual(blueprint.instructions),'instructions');input.presentation.instructions=blueprint.instructions;}
 const compiled=await new StoryPackageCompiler().compile(input,museum);compiled.report.unverified=baseline.report.unverified;
 const pluginDigest=createHash('sha256');
 for(const name of ['plugins.mjs','investigation.mjs','coverage.mjs','gameplay-catalog.mjs']){pluginDigest.update(name+'\0');pluginDigest.update(await readFile(new URL('../../gameplay/plugins/'+name,import.meta.url)));pluginDigest.update('\0');}
 const receipt={schema_version:'investigation-blueprint-receipt/1',plugin_code_sha256:pluginDigest.digest('hex'),base_input_sha256:await contentHash(baseInput),base_runtime_sha256:baseline.reference.sha256,runtime_sha256:compiled.reference.sha256,blueprint_sha256:await contentHash(blueprint),bindings,assets:assetReceipts,upstream_unverified:baseline.report.unverified,model_calls:0,review_authority:'unchanged',automatic_story_generation:'not_performed'};
 return {input,compiled,receipt};
}


/** Read compiler-owned, bounded design metadata; it grants no review or asset authority. */
export function embeddedInvestigationBlueprint(input){
 const game=input.story.kind==='narrative-draft'?input.story.payload.package.game:input.story.payload.game;
 const tables=new Map(game.locales.map(table=>[table.locale,new Map(table.entries.map(e=>[e.key,e.text]))]));
 const marker='preparation.investigation_v1';
 if(![...tables.values()].some(table=>table.has(marker)))return null;
 const exact=key=>{const value=tables.get('en')?.get(key);requireValue(typeof value==='string'&&value.length>0&&value===tables.get('zh')?.get(key),'embedded design differs between locales');return value;};
 requireValue(exact(marker)==='investigation-blueprint/1','embedded design version');
 const count=exact('preparation.investigation_parts');requireValue(/^[1-9][0-9]?$/.test(count)&&Number(count)<=16,'embedded design part count');
 const parts=[];for(let index=1;index<=Number(count);index++){const part=exact('preparation.investigation_part.'+index);requireValue(part.length<=8000,'embedded design part budget');parts.push(part);}
 const result=JSON.parse(parts.join(''));requireValue(result?.schema_version==='investigation-blueprint/1','embedded blueprint version');return result;
}
