import {WalkMesh} from './walkmesh.mjs';
const requireNavigation=(ok,message)=>{if(!ok)throw new Error('空间检查未通过：'+message);};
/** Generation and loading share one fail-closed 2D navigation gate. */
export function validateNavigation(presentation){
  if(presentation.spatialContext)return validateMetricNavigation(presentation);
  requireNavigation(Array.isArray(presentation.shots)&&Array.isArray(presentation.objects)&&presentation.shots.length===presentation.objects.length&&new Set(presentation.shots.map(shot=>shot.number)).size===presentation.shots.length&&presentation.objects.every(object=>presentation.shots.some(shot=>shot.number===object.number)),'物件清单不完整');
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


/** Existing SDK positions and computed stations replace image-floor polygons in 3D. */
export function validateMetricNavigation(presentation){
  const context=presentation.spatialContext;
  requireNavigation(context?.schema_version==='story-spatial-context-0.1.0'&&
    /^[0-9a-f]{64}$/.test(context.input_sha256)&&/^[0-9a-f]{64}$/.test(context.metric_revision),
    '三维输入版本或来源标识缺失');
  requireNavigation(Array.isArray(context.worlds)&&context.worlds.length===presentation.scenes.length,
    '三维视点数量不一致');
  const views=new Set(context.worlds.map(world=>world.view_id));
  requireNavigation(views.size===context.worlds.length&&
    presentation.scenes.every(scene=>views.has(scene.id)),'三维视点身份不一致');
  for(const chapter of presentation.chapters){
    const access=chapter.access;
    requireNavigation(access?.station_id==='spawn'&&access.interaction==='inspect',
      `任务${chapter.id}缺少明确的资料观察方式`);
    const world=context.worlds.find(world=>world.view_id===access.view_id);
    requireNavigation(world?.geometry?.status==='computed'&&world.geometry.result.spawn_ground,
      `任务${chapter.id}缺少已计算的起始站位`);
    for(const number of chapter.requiredSources){
      const node=world.geometry.result.objects.find(node=>node.key===`object:${number}`);
      requireNavigation(node?.planning.enabled_interactions.includes('inspect')&&
        node.planning.observation_positions.some(position=>position.station==='spawn'),
        `物件${number}缺少该视点的资料查看入口`);
      // Opening linked text does not assert world-inscription legibility or touch.
      requireNavigation(presentation.objects.some(object=>object.number===number),
        `物件${number}未登记`);
    }
  }
  for(const world of context.worlds)for(const link of world.navigation){
    requireNavigation(views.has(link.target_view_id)&&Number.isFinite(link.arrival_yaw)&&
      Number.isFinite(link.arrival_pitch)&&Math.abs(link.arrival_yaw)<=180&&
      Math.abs(link.arrival_pitch)<=90,'跨点位导航缺少目标或到达朝向');
  }
  return true;
}
