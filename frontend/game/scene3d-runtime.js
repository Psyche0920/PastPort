// Appended only to the isolated viewer response; never written into the input.
import {sourceArrival,screenBearing} from '/scene3d-navigation.mjs';
import {prepareRenderer} from '/scene-preparation.mjs';
import {NavigationBoundary} from '../navigation_boundary.js?v=plane-3';
const storyPost=message=>parent.postMessage(message,location.origin);
let storyRoute=null,storyPaused=false,storyReady=false;
let storyLocale='zh';const storyT=(zh,en)=>storyLocale==='en'?en:zh;
function storySetLocale(locale){if(!['zh','en'].includes(locale))return;storyLocale=locale;document.documentElement.lang=locale==='en'?'en':'zh-Hant';document.title=locale==='en'?'PastPort · Scene':'PastPort · 場景';for(const marker of markers){if(marker.userData.storyTargetMap){marker.userData.storyTargetMap.dispose();marker.userData.storyTargetMap=null;}}if(storyObjective)storySetObjective(storyObjective);}

// Player labels use CSS pixels, independent of the low-resolution scene canvas.
const storySharpLabels=new URLSearchParams(location.search).get('player')==='1';
const storyLabelNodes=new Map();
if(storySharpLabels){
 const style=document.createElement('style');style.textContent='.story-object-label{position:fixed;left:0;top:0;width:44px;height:44px;box-sizing:border-box;border:2px solid #f5df9d;border-radius:50%;background:#142d2bf5;color:#fff5d4;display:flex;align-items:center;justify-content:center;font:700 20px/1 system-ui;box-shadow:0 2px 7px #000b;pointer-events:none;z-index:20;transform:translate(-50%,-50%)}.story-object-label[data-pending="true"]{border-style:dashed}.story-object-label[data-target="true"]{width:50px;height:50px;border:3px solid #ffe29a;background:#534016fa;color:#fff;box-shadow:0 0 0 3px #142d2bd9,0 2px 8px #000b}.story-object-label[hidden]{display:none}';document.head.append(style);
}
function storyUpdateSharpLabels(){
 if(!storySharpLabels)return;
 const live=new Set();
 for(const marker of markers){
  const id=marker.userData.object.id;live.add(id);
  let label=storyLabelNodes.get(id);
  if(!label){label=document.createElement('span');label.className='story-object-label';label.setAttribute('aria-hidden','true');label.textContent=String(id).padStart(2,'0');document.body.append(label);storyLabelNodes.set(id,label);}
  const world=marker.getWorldPosition(new THREE.Vector3()),projected=world.clone().project(camera);
  const forward=world.clone().sub(camera.position).applyQuaternion(camera.quaternion.clone().invert());
  label.hidden=!marker.visible||forward.z>=0||projected.z < -1||projected.z > 1||Math.abs(projected.x)>1.08||Math.abs(projected.y)>1.08;
  if(!label.hidden){label.style.left=`${(projected.x+1)*innerWidth/2}px`;label.style.top=`${(1-projected.y)*innerHeight/2}px`;}
  label.dataset.target=String(id===storyObjective?.number);label.dataset.pending=String(marker.userData.pending===true);
  marker.material.opacity=0;
 }
 for(const[id,label]of storyLabelNodes)if(!live.has(id)){label.remove();storyLabelNodes.delete(id);}
}

const storyActors=[],storyPortals=[];
let storyObjective=null,storyObjectiveVisit={key:null,arrived:false},storyFocusMode=false;
const storyArrivalRadius=2.2;
const storyObjectiveHint=document.createElement('button');storyObjectiveHint.type='button';storyObjectiveHint.style.cssText='position:fixed;left:50%;top:95px;transform:translateX(-50%);padding:7px 12px;max-width:78vw;background:#342c16e8;color:#ffe29a;border:1px solid #efce7788;border-radius:18px;font:12px system-ui;z-index:21';storyObjectiveHint.hidden=true;document.body.append(storyObjectiveHint);
storyObjectiveHint.onclick=()=>{if(storyObjective?.number===null){storyPost({type:'story3d:task'});return;}const marker=markers.find(m=>m.userData.object.id===storyObjective?.number);if(marker)camera.lookAt(marker.position);};
function storySetObjective(message){
  if(message.number!==null&&!Number.isSafeInteger(message.number))return;
  storyFocusMode=false;
  const key=`${message.stage??''}:${message.number??'none'}`;
  storyObjective={number:message.number,stage:message.stage??'',token:Number.isSafeInteger(message.token)?message.token:0,mode:message.mode==='search'?'search':'inspect',title:typeof message.title==='string'?message.title:''};
  if(storyObjectiveVisit.key!==key)storyObjectiveVisit={key,arrived:false};
  for(const marker of markers){
    marker.visible=true;
    const selected=marker.userData.object.id===message.number;
    if(!marker.userData.storyBaseMap)marker.userData.storyBaseMap=marker.material.map;
    if(selected&&!marker.userData.storyTargetMap){
      const canvas=document.createElement('canvas');canvas.width=128;canvas.height=128;const ctx=canvas.getContext('2d');ctx.strokeStyle='#ffe099';ctx.fillStyle='#342c16e0';ctx.lineWidth=5;ctx.beginPath();ctx.arc(64,64,56,0,Math.PI*2);ctx.fill();ctx.stroke();ctx.fillStyle='#ffe099';ctx.textAlign='center';ctx.font='bold 43px sans-serif';ctx.fillText(String(message.number).padStart(2,'0'),64,76);ctx.font='16px sans-serif';ctx.fillText(storyT('目前目標','TARGET'),64,105);marker.userData.storyTargetMap=new THREE.CanvasTexture(canvas);
    }
    marker.material.map=selected?marker.userData.storyTargetMap:marker.userData.storyBaseMap;marker.material.needsUpdate=true;marker.material.opacity=storySharpLabels?0:selected?1:.55;
  }
}
addEventListener('pointerdown',()=>{storyFocusMode=false;},{capture:true});
showPopup=async object=>storyPost({type:'story3d:object',number:object.id});
// Pick the visible label footprint, independent of the sprite's world-space bounds.
const storyOriginalPointerUp=renderer.domElement.onpointerup;
renderer.domElement.onpointerup=async event=>{
  if(!storyPaused&&moved<=6&&!markerDrag){
    camera.updateMatrixWorld();
    const rect=renderer.domElement.getBoundingClientRect();
    let closest=null,closestDistance=Infinity;
    for(const marker of markers){
      if(!marker.visible)continue;
      const projected=marker.getWorldPosition(new THREE.Vector3()).project(camera);
      if(projected.z<-1||projected.z>1)continue;
      const x=rect.left+(projected.x+1)*rect.width/2,y=rect.top+(1-projected.y)*rect.height/2;
      const distance=Math.hypot(event.clientX-x,event.clientY-y),radius=marker.userData.object.id===storyObjective?.number?36:32;
      if(distance<=radius&&distance<closestDistance){closest=marker;closestDistance=distance;}
    }
    if(closest){dragging=false;await showPopup(closest.userData.object);return;}
  }
  await storyOriginalPointerUp.call(renderer.domElement,event);
};
function storyFloor(x,z,y){
  const probe=new THREE.Raycaster(new THREE.Vector3(x,y+1,z),new THREE.Vector3(0,-1,0),0,4);
  for(const hit of probe.intersectObject(collider,true)){
    if(!hit.face)continue;
    const normal=hit.face.normal.clone().transformDirection(hit.object.matrixWorld);
    if(Math.abs(normal.y)>.7)return hit.point;
  }
  return null;
}
function storySegment(from,to){
  const delta=to.clone().sub(from),distance=delta.length();
  if(distance<.001)return true;
  for(const offset of [-Math.max(.1,storyEyeHeight-.12),-storyEyeHeight*.5,0]){
    const start=from.clone();start.y+=offset;
    const probe=new THREE.Raycaster(start,delta.clone().normalize(),0,distance+.2);
    if(probe.intersectObject(collider,true).length)return false;
  }
  return true;
}
class StoryRouteError extends Error{constructor(code,message){super(message);this.code=code;}}
function storyPath(marker){
  const start=camera.position.clone(),target=marker.position.clone();
  target.y=start.y;
  const delta=target.sub(start),length=delta.length();
  if(length>20)throw new StoryRouteError('too_far',storyT('物件距离过远，请先手动走近。','This object is too far away; move closer first.'));
  const end=start.clone().addScaledVector(delta,Math.max(0,(length-1.4)/Math.max(length,.001)));
  const steps=Math.max(1,Math.ceil(start.distanceTo(end)/.2)),points=[];
  let previous=start;
  for(let i=1;i<=steps;i++){
    const p=start.clone().lerp(end,i/steps),floor=storyFloor(p.x,p.z,previous.y);
    if(!floor)throw new StoryRouteError('unverified_ground',storyT('没有确认连续地面，已拦截自动接近。','Continuous ground is unverified; automatic approach was blocked.'));
    p.y=floor.y+storyEyeHeight;
    if(Math.abs(p.y-previous.y)>.35||!storySegment(previous,p))throw new StoryRouteError('blocked_path',storyT('路线被墙体、窗户或地面高差阻挡。','The route is blocked by a wall, window or change in floor height.'));
    points.push(p);previous=p;
  }
  return points;
}
addEventListener('message',async event=>{
  if(event.origin!==location.origin||event.source!==parent)return;
  const msg=event.data;
  if(msg?.type==='story3d:views'&&Number.isInteger(msg.count)&&msg.count>0){for(const portal of storyPortals){portal.userData.storyAllowed=portal.userData.world<=msg.count;if(!portal.userData.storyAllowed)portal.visible=false;}if(!storyPortals.some(portal=>portal.userData.storyAllowed!==false))storyRouteHint.hidden=true;return;}
  if(msg?.type==='story3d:locale'){storySetLocale(msg.locale);return;}
  if(msg?.type==='story3d:activity'){globalThis.pastportScenePreparation?.setActivityActive?.(msg.active===true);return;}
  if(msg?.type==='story3d:quality'){
    const preparation=globalThis.pastportScenePreparation;
    if(preparation&&['low','standard'].includes(msg.value)){const value=preparation.setQuality(msg.value);storyPost({type:'story3d:quality-changed',value});}return;
  }
  if(msg?.type==='story3d:prepare'&&typeof msg.request==='string'){
    storySetLocale(msg.locale);const preparation=globalThis.pastportScenePreparation;
    try{storyPost({type:'story3d:preparation-progress',request:msg.request,phase:msg.buildLod===false?'loading':'optimizing'});const value=await prepareRenderer(preparation,msg.buildLod!==false);if(value)storyPost({type:'story3d:quality-changed',value});storyPost({type:'story3d:prepared',request:msg.request});}
    catch(error){console.error('Scene preparation failed',error);storyPost({type:'story3d:preparation-failed',request:msg.request});}return;
  }

  if(msg?.type==='story3d:objective')storySetObjective(msg);
  if(msg?.type==='story3d:ping'&&storyReady)storySendReady();
  if(msg?.type==='story3d:pause'){storyPaused=msg.paused===true||!storySpawnValid;if(storyPaused)keys.clear();}
  if(msg?.type==='story3d:cancel'){storyRoute=null;keys.clear();}
  if(msg?.type==='story3d:check-access'){
    const marker=markers.find(item=>item.userData.object.id===msg.number);let code='missing_object';
    if(marker){try{storyPath(marker);code='approachable';}catch(error){code=error instanceof StoryRouteError?error.code:'route_failed';}}
    storyPost({type:'story3d:access',number:msg.number,request:msg.request,code});return;
  }
  if(msg?.type==='story3d:navigate'&&!storyPaused){const portal=storyPortals.find(item=>item.userData.world===msg.world);if(portal)storyUsePortal(portal);else storyPost({type:'story3d:blocked',reason:storyT('当前点位没有这条导航关系。','No registered route to that view is available here.')});return;}
  if(!['story3d:focus','story3d:approach'].includes(msg?.type))return;
  const marker=markers.find(m=>m.userData.object.id===msg.number);
  if(!marker){storyPost({type:'story3d:blocked',reason:storyT('此点位没有该物件的空间位置，请切换点位。','This object is not positioned in this view. Follow navigation to its view.')});return;}
  camera.lookAt(marker.position);
  if(msg.type==='story3d:focus'){storyFocusMode=true;return;}
  try{storyRoute={points:storyPath(marker),number:msg.number,token:msg.token,index:0};}
  catch(error){storyPost({type:'story3d:blocked',number:msg.number,token:msg.token,code:error instanceof StoryRouteError?error.code:'route_failed',reason:error.message});}
});
// The original render loop runs first; constrain its manual movement every frame.
// Preserve the supplied starting X/Z and heading; only settle onto its floor.
// Generated model scale is not a measured human scale, so bound eye clearance
// by the supplied capture height instead of unconditionally adding 1.6 units.
let storySpawnValid=false;
let storyEyeHeight=1.6;
{
  const seed=camera.position.clone(),floor=storyFloor(seed.x,seed.z,seed.y);
  if(floor){
    storyEyeHeight=Math.max(.35,Math.min(1.6,seed.y-floor.y));
    camera.position.set(seed.x,floor.y+storyEyeHeight,seed.z);
    if(!new URLSearchParams(location.search).has('arrival_yaw'))camera.rotation.x=0;
    camera.rotation.z=0;
    storySpawnValid=true;
    document.documentElement.dataset.storySpawn=JSON.stringify({basis:'original-horizontal-origin',floor:[floor.x,floor.y,floor.z],eye:[camera.position.x,camera.position.y,camera.position.z],eyeHeight:storyEyeHeight});
  }
}
if(!storySpawnValid){storyPaused=true;storyPost({type:'story3d:blocked',reason:storyT('原起点的地面校验未通过，已停止移动。','The entry ground check failed; movement is stopped.')});}
// World-space character standees are disabled; dialogue portraits remain in the host.
for(const transition of data.story_transitions??[]){
  if(![1,2].includes(transition.targetWorld))continue;
  let position;
  if(transition.point)position=new THREE.Vector3(transition.point.x,transition.point.y,transition.point.z);
  else{
    const yaw=radians(transition.yaw),pitch=radians(transition.pitch),direction=new THREE.Vector3(Math.sin(yaw)*Math.cos(pitch),Math.sin(pitch),-Math.cos(yaw)*Math.cos(pitch)).applyQuaternion(alignmentQuaternion());
    const probe=new THREE.Raycaster(new THREE.Vector3(data.alignment.origin.x,data.alignment.origin.y,data.alignment.origin.z),direction);
    position=probe.intersectObject(collider,true)[0]?.point?.clone();
  }
  if(!position)continue;
  const floor=storyFloor(position.x,position.z,position.y);if(!floor)continue;
  const canvas=document.createElement('canvas');canvas.width=256;canvas.height=128;const ctx=canvas.getContext('2d');ctx.fillStyle='#12392fe8';ctx.fillRect(0,0,256,128);ctx.fillStyle='#f4e2ad';ctx.textAlign='center';ctx.font='bold 46px sans-serif';ctx.fillText('↑',128,54);ctx.font='24px sans-serif';ctx.fillText(String(transition.targetWorld),128,94);
  const yaw=radians(transition.yaw),fallback=new THREE.Vector3(Math.sin(yaw),0,-Math.cos(yaw)).applyQuaternion(alignmentQuaternion());
  const portal=new THREE.Sprite(new THREE.SpriteMaterial({map:new THREE.CanvasTexture(canvas),transparent:true,depthTest:false,depthWrite:false}));portal.position.set(floor.x,floor.y+.25,floor.z);portal.scale.set(.7,.35,1);portal.userData={world:transition.targetWorld,arrival:sourceArrival(transition.target_url),point:position.clone(),fallback,boundary:new NavigationBoundary()};scene.add(portal);storyPortals.push(portal);
}
document.documentElement.dataset.storyPortalCount=String(storyPortals.length);
const storyRouteHint=document.createElement('button');storyRouteHint.type='button';storyRouteHint.style.cssText='position:fixed;left:14px;bottom:18px;padding:7px 12px;background:#143d34dd;color:#f1d9a3;border:1px solid #dbc89488;border-radius:20px;font:12px system-ui;z-index:20';storyRouteHint.hidden=true;document.body.append(storyRouteHint);
let storyLeaving=false;
function storyUsePortal(portal){if(portal.userData.storyAllowed===false)return;if(storyLeaving||storyPaused)return;storyLeaving=true;storyPost({type:'story3d:world',world:portal.userData.world,arrival:portal.userData.arrival});}
storyRouteHint.onclick=()=>{if(!storyPaused&&storyPortals[0])storyUsePortal(storyPortals[0]);};
renderer.domElement.addEventListener('pointerup',event=>{
  if(moved>6||storyPaused)return;setScreenRay(event);
  const portal=ray.intersectObjects(storyPortals)[0];if(portal){storyUsePortal(portal.object);return;}
  if(ray.intersectObjects(storyActors).length)storyPost({type:'story3d:guide'});
});
let storyLast=performance.now(),storyPosition=camera.position.clone(),storyLastAudit=0;
function storyTick(now){
  const performanceDiagnostic=window.__pastportPerformance;
  if(performanceDiagnostic?.mode==='scene-only'){
    storyLast=now;storyPosition.copy(camera.position);keys.clear();requestAnimationFrame(storyTick);return;
  }
  const storyCpuStarted=performance.now();
  const dt=Math.min((now-storyLast)/1000,.05);storyLast=now;
  if(storyPaused){camera.position.copy(storyPosition);keys.clear();}
  else if(storyRoute){
    if(keys.size){storyRoute=null;}
    else{
      const next=storyRoute.points[storyRoute.index],d=camera.position.distanceTo(next);
      if(d<=dt*1.8+.01){camera.position.copy(next);storyRoute.index++;if(storyRoute.index===storyRoute.points.length){const done=storyRoute;storyRoute=null;if(storyObjective?.number===done.number)storyObjectiveVisit.arrived=true;storyPost({type:'story3d:arrived',number:done.number,token:done.token});}}
      else camera.position.addScaledVector(next.clone().sub(camera.position).normalize(),dt*1.8);
    }
  }else if(camera.position.distanceTo(storyPosition)>.001){
    const floor=storyFloor(camera.position.x,camera.position.z,storyPosition.y);
    if(!floor||Math.abs(floor.y+storyEyeHeight-storyPosition.y)>.35||!storySegment(storyPosition,camera.position))camera.position.copy(storyPosition);
    else camera.position.y=floor.y+storyEyeHeight;
  }
  for(const portal of storyPortals){
    const source=portal.userData;
    if(portal.userData.storyAllowed!==false&&source.boundary.crossed(camera.position,data.alignment.origin,source.point,source.fallback,!storyPaused&&!storyLeaving))storyUsePortal(portal);
  }
  if(!storyPaused&&!storyRoute&&storyObjective&&storyObjective.number!==null&&!storyObjectiveVisit.arrived){
    const marker=markers.find(m=>m.userData.object.id===storyObjective.number);
    if(marker&&Math.hypot(camera.position.x-marker.position.x,camera.position.z-marker.position.z)<=storyArrivalRadius){
      storyObjectiveVisit.arrived=true;
      storyPost({type:'story3d:arrived',number:storyObjective.number,token:storyObjective.token,manual:true});
    }
  }
  const firstPortal=storyPortals.find(portal=>portal.userData.storyAllowed!==false);
  if(firstPortal){
    const projected=firstPortal.position.clone().project(camera),direction=firstPortal.position.clone().sub(camera.position).applyQuaternion(camera.quaternion.clone().invert());
    const outside=direction.z>=0||Math.abs(projected.x)>1||Math.abs(projected.y)>1;
    firstPortal.visible=false;storyRouteHint.hidden=storyPaused;
    storyRouteHint.style.left=outside?'14px':`${Math.max(90,Math.min(innerWidth-90,(projected.x+1)*innerWidth/2))}px`;
    storyRouteHint.style.top=outside?'auto':`${Math.max(145,Math.min(innerHeight-65,(1-projected.y)*innerHeight/2))}px`;
    storyRouteHint.style.bottom=outside?'18px':'auto';storyRouteHint.style.transform=outside?'none':'translate(-50%,-50%)';
    storyRouteHint.textContent=`${outside?screenBearing(direction,projected):'↑'} ${storyT('前往場景','Go to view')} ${firstPortal.userData.world}`;
    storyRouteHint.setAttribute('aria-label',`${storyT('沿箭頭前往場景','Follow the arrow to view')} ${firstPortal.userData.world}`);
  }
  if(storyObjective){
    const marker=markers.find(m=>m.userData.object.id===storyObjective.number);storyObjectiveHint.hidden=storyPaused||storyFocusMode;
    if(marker){
      const projected=marker.position.clone().project(camera),direction=marker.position.clone().sub(camera.position).applyQuaternion(camera.quaternion.clone().invert());
      const arrow=screenBearing(direction,projected);
      storyObjectiveHint.textContent=`${arrow} ${storyT('目前物件','Current object')} ${String(storyObjective.number).padStart(2,'0')}`;
      const markerSize=camera.position.distanceTo(marker.position)*2*Math.tan(THREE.MathUtils.degToRad(camera.fov)/2)*36/innerHeight;
      const pulse=1.35+.07*Math.sin(now/300);marker.scale.set(markerSize*pulse,markerSize*pulse,1);
    }else storyObjectiveHint.textContent=storyObjective.number===null?(storyObjective.mode==='search'?storyObjective.title:storyT('可以繼續調查','Continue investigation')):`${storyObjective.number} · ${storyT('請沿導航前往目標','Follow navigation to the target')}`;
  }
  storyUpdateSharpLabels();
  if(now-storyLastAudit>200){document.documentElement.dataset.storyPosition=JSON.stringify(camera.position);camera.getWorldDirection(storyMapDirection);storyPost({type:'story3d:pose',x:camera.position.x,z:camera.position.z,dx:storyMapDirection.x,dz:storyMapDirection.z});storyLastAudit=now;}
  if(performanceDiagnostic)performanceDiagnostic.storyCpuMs=performance.now()-storyCpuStarted;
  storyPosition.copy(camera.position);requestAnimationFrame(storyTick);
}
document.querySelectorAll('.tour-header,.tour-actions,.tour-hint,#editor-panel,#popup').forEach(node=>{node.hidden=true;node.style.display='none';});
// Keep both playable renderings; comparison must not overlap scene navigation.
for(const button of document.querySelectorAll('button'))if(['Compare original','Show stylized scene'].includes(button.textContent.trim())){
  if(new URLSearchParams(location.search).get('player')==='1'){button.hidden=true;button.style.display='none';}
  button.style.top='58px';button.style.bottom='auto';button.style.right='16px';
  const compare=button.onclick;
  button.onclick=async event=>{await compare.call(button,event);storyPost({type:'story3d:render-mode',mode:button.textContent.trim()==='Show stylized scene'?'original':'stylized'});};
  if(new URLSearchParams(location.search).get('render')==='original')await button.onclick(new Event('click'));
}
const storyArrivalDirection=new THREE.Vector3(0,0,-1).applyQuaternion(camera.quaternion).applyQuaternion(alignmentQuaternion().clone().invert());
document.documentElement.dataset.storyArrivalPose=JSON.stringify({yaw:THREE.MathUtils.radToDeg(Math.atan2(storyArrivalDirection.x,-storyArrivalDirection.z)),pitch:THREE.MathUtils.radToDeg(Math.asin(THREE.MathUtils.clamp(storyArrivalDirection.y,-1,1)))});
function storySendMap(){
  const bounds=new THREE.Box3().setFromObject(collider);
  storyPost({type:'story3d:map',bounds:{minX:bounds.min.x,maxX:bounds.max.x,minZ:bounds.min.z,maxZ:bounds.max.z},objects:markers.map(marker=>{const p=marker.getWorldPosition(new THREE.Vector3());return {number:marker.userData.object.id,x:p.x,z:p.z};})});
}
function storySendReady(){storyPost({type:'story3d:ready',qualityControl:typeof globalThis.pastportScenePreparation?.setQuality==='function'});storySendMap();}
const storyMapDirection=new THREE.Vector3();
storyReady=true;storySendReady();requestAnimationFrame(storyTick);
