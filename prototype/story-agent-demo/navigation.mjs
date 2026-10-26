import {WalkMesh} from './walkmesh.mjs';
const requireNavigation=(ok,message)=>{if(!ok)throw new Error('空间检查未通过：'+message);};
/** Generation and loading share one fail-closed 2D navigation gate. */
export function validateNavigation(presentation){
  requireNavigation(Array.isArray(presentation.shots)&&presentation.shots.length===14,'物件清单不完整');
  for(const shot of presentation.shots){
    if(!shot.available){requireNavigation(typeof shot.reason==='string'&&shot.reason.length>0,`物件${shot.number}缺少阻断原因`);continue;}
    const review=shot.navigation;requireNavigation(review?.status==='visually_reviewed',`物件${shot.number}未核对画面`);
    requireNavigation(review.sourcePanoramaSha256===presentation.panoramaHashes[shot.sceneId],`物件${shot.number}来源画面已变化`);
    requireNavigation(JSON.stringify(review.camera)===JSON.stringify(shot.camera),`物件${shot.number}镜头已变化`);
    requireNavigation(review.frame[0]===960&&review.frame[1]===540&&Array.isArray(shot.boundary)&&shot.boundary.length>=3,`物件${shot.number}画幅或地面无效`);
    const mesh=new WalkMesh(shot.boundary,shot.obstacles);requireNavigation(mesh.allows(shot.spawn)&&mesh.allows(shot.approach),`物件${shot.number}入场或目标不在地面`);
    requireNavigation(shot.actors.every(p=>mesh.allows(p)),`物件${shot.number}人物站在地面外`);
    requireNavigation(mesh.path(shot.spawn,shot.approach).length>0,`物件${shot.number}路径不连通`);
    requireNavigation(review.forbiddenTestPoints.length>=3&&review.forbiddenTestPoints.every(p=>!mesh.allows(p)),`物件${shot.number}禁行区域未拦截`);
  }
  for(const stage of presentation.chapters){const target=presentation.shots.find(s=>s.number===presentation.stageTargets[stage.id]);requireNavigation(target?.available&&target.taskScenes.includes(stage.id),`剧情${stage.id}无有效接近入口`);}
  return true;
}
