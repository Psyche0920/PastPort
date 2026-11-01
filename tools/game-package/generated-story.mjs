import {contentHash} from '../../src/pastport/player/validation.mjs';
import {StoryPackageError} from '../../gameplay/contracts.mjs';

const requireValue=(value,code,message)=>{if(!value)throw new StoryPackageError(code,message);};

/** Join independent Story, Gameplay and Presentation outputs using exact narrative identity. */
export async function generatedStoryInput(result,preparation) {
  let draft=result;
  if(Object.hasOwn(result,'outcome')) {
    requireValue(result.outcome==='completed'&&!result.issues?.some(issue=>issue.severity==='blocking'),'STORY_GENERATION_BLOCKED','Story generation is not complete or has blocking findings');
    draft=result.payload;
  } else if(Object.hasOwn(result,'decision')) {
    requireValue(result.skill==='narrative'&&['draft','revise'].includes(result.mode)&&['complete','review_required'].includes(result.decision)&&!result.issues?.some(issue=>issue.severity==='blocking'),'STORY_GENERATION_BLOCKED','The model result is not a completed narrative draft');
    draft=result.payload;
  }
  const runtime=draft?.game&&Array.isArray(draft.media_manifest)?draft:null;
  requireValue(runtime||draft?.package&&Array.isArray(draft.authoring_report)&&Array.isArray(draft.unresolved_items),'STORY_NARRATIVE_INVALID','Expected NarrativeDraft or the shared assembler RuntimePackage');
  requireValue(preparation?.schema_version==='story-3d-preparation-0.1.0','STORY_PREPARATION_UNSUPPORTED','A versioned downstream preparation output is required');
  requireValue(preparation.narrative_sha256===(runtime?runtime.narrative_package_hash:await contentHash(draft.package)),'STORY_PREPARATION_STALE','Gameplay/presentation preparation belongs to a different generated story version');
  requireValue(preparation.status==='ready','STORY_PREPARATION_BLOCKED','Gameplay/presentation preparation is not ready');
  return {schema_version:'story-3d-input-0.1.0',story:runtime?{kind:'runtime-package',payload:runtime}:{kind:'narrative-draft',package_id:preparation.package_id,payload:draft,...(preparation.authoring_mode?{authoring_mode:preparation.authoring_mode}:{})},museum:preparation.museum,tasks:preparation.tasks,presentation:preparation.presentation};
}
