// Invoked with a compiler-produced synthetic runtime on stdin by pytest.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {StoryPackageCompiler,museumSnapshotHash} from './tools/game-package/story-package.mjs';
import {GameSession} from './frontend/game/session.mjs';
const pkg=JSON.parse(readFileSync(0,'utf8'));
pkg.media_manifest=[{asset_id:'object-1',relative_path:'one.png',sha256:'a'.repeat(64)}];
const museum={tourId:'branch-fixture',objects:[{number:1,media_path:'one.png',media_sha256:'a'.repeat(64)}],
 sourceNotes:{1:{zh:'Synthetic source',en:'Synthetic source'}},runtimeCapabilities:pkg.runtime_compatibility,
 panoramaHashes:{one:'b'.repeat(64)},scenes:[{id:'one',hotspots:[{number:1,pitch:0}]}],walkArea:{},
 shots:[{number:1,sceneId:'one',taskScenes:[],available:true,camera:{yaw:0,pitch:-10,hfov:90},
 boundary:[[0,0],[100,0],[100,100],[0,100]],obstacles:[],spawn:[20,20],approach:[40,40],actors:[],
 navigation:{status:'visually_reviewed',sourcePanoramaSha256:'b'.repeat(64),camera:{yaw:0,pitch:-10,hfov:90},frame:[960,540],forbiddenTestPoints:[[-1,-1],[101,101],[-1,101]]}}]};
const input={schema_version:'story-3d-input-0.1.0',story:{kind:'runtime-package',payload:pkg},
 museum:{tour_id:museum.tourId,snapshot_sha256:await museumSnapshotHash(museum)},
 tasks:pkg.game.scenes.map(scene=>({task_id:scene.tasks[0].task_id,scene_id:scene.scene_id,
 objects:[1],required_sources:[1],target_number:1,asset_object_number:1,
 plugin:{kind:'dialogue',items:[{id:'read',text:{zh:'Synthetic source',en:'Synthetic source'}}]}})),
 presentation:{intro:{zh:'Synthetic test',en:'Synthetic test'}}};
const compiled=await new StoryPackageCompiler().compile(input,museum);
for(const branch of [1,2,3])for(const ending of [1,2]){
 let session=await GameSession.create(compiled.runtime,compiled.reference,compiled.presentation);
 const complete=async()=>{session.observeSource(1);await session.dispatch({kind:'read',id:'read'});};
 const restore=async()=>{const next=await GameSession.create(compiled.runtime,compiled.reference,compiled.presentation);
 next.restore(session.serialize());assert.deepEqual(next.state,session.state);session=next;};
 await assert.rejects(()=>session.choose('investigation-'+branch));
 await complete();await assert.rejects(()=>session.advance());
 await session.choose('investigation-'+branch);await restore();
 await assert.rejects(()=>session.choose('investigation-'+(branch%3+1)));
 const blocked='scene-'+(branch%3+2);
 await assert.rejects(()=>session.apply(session.state,'advance',blocked));
 await session.advance();assert.equal(session.current.id,'scene-'+(branch+1));
 await complete();await restore();
 assert.deepEqual(session.state.inventory,['finding-'+branch]);
 await session.advance();assert.equal(session.current.id,'scene-5');
 const visible=session.current.feedback.filter(item=>session.evaluate(item.guard));
 assert.equal(visible.length,1);
 assert.equal(visible[0].text.en,pkg.game.locales.find(t=>t.locale==='en').entries.find(e=>e.key==='investigation-'+branch+'.reunion').text);
 await complete();await restore();
 await session.choose('option-'+ending);assert.equal(session.state.ending_id,'ending-'+ending);
 const outcome=compiled.presentation.endings.find(e=>e.id===session.state.ending_id).outcomes[0];
 const variant=outcome.variants.find(v=>session.evaluate(v.guard));
 assert.ok(variant);assert.equal(session.variables()['investigation-complete'],branch);
 assert.equal(session.state.completed_task_ids.length,3);
 assert.equal(session.state.decisions.find(d=>d.decision_id==='investigation-choice').option_id,'investigation-'+branch);
 await restore();
}
console.log('All six route/ending combinations, exclusive access, reunion feedback and save/restore passed');
