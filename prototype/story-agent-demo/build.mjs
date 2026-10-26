import {readFile,writeFile,mkdir,copyFile} from 'node:fs/promises';
import {execFileSync} from 'node:child_process';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {createGame,presentation} from './content.mjs';
import {createShots,stageTargets,castByStage,castFrames,castRows} from './shots.mjs';
import {validateNavigation} from './navigation.mjs';
const root=path.dirname(fileURLToPath(import.meta.url));
const hash=bytes=>createHash('sha256').update(bytes).digest('hex');
const json=value=>JSON.stringify(value,null,2)+'\n';
class DemoBuilder {
  constructor(){this.authoring=path.resolve(process.env.PASTPORT_AUTHORING_DIRECTORY??path.dirname(root));this.repository=process.env.PASTPORT_REPOSITORY??execFileSync('git',['-C',root,'rev-parse','--show-toplevel']).toString().trim();}
  git(rev,file){return execFileSync('git',['-C',this.repository,'show',`${rev}:${file}`],{maxBuffer:4000000});}
  async build(){
    const lockBytes=await readFile(path.join(this.authoring,'input-lock.json'));const lock=JSON.parse(lockBytes);
    const story=await readFile(path.join(this.authoring,'story.md'));if(hash(story)!==lock.draft_sha256)throw new Error('Story differs from locked version');
    const source=await readFile(path.join(lock.environment_directory,'vr_trial/index.html'));
    if(hash(source)!==lock.html_sha256)throw new Error('Museum differs from locked version');
    const review=JSON.parse(await readFile(path.join(root,'navigation.json'),'utf8'));
    for(const dir of ['engine','museum','media','data','evidence','assets'])await mkdir(path.join(root,dir),{recursive:true});
    const engineCommit=execFileSync('git',['-C',this.repository,'rev-parse','main']).toString().trim();
    const walkingCommit=execFileSync('git',['-C',this.repository,'rev-parse','demo-muradiye-ui-trial']).toString().trim();
    const engineFiles=['actions.mjs','context.mjs','errors.mjs','generated-schemas.mjs','rules.mjs','runtime.mjs','validation.mjs'];
    for(const file of engineFiles)await writeFile(path.join(root,'engine',file),this.git(engineCommit,`src/pastport/player/${file}`));
    await writeFile(path.join(root,'walkmesh.mjs'),this.git(walkingCommit,'prototype/walkmesh.mjs'));
    await writeFile(path.join(root,'assets/cast.png'),this.git(walkingCommit,'prototype/assets/adventure/cast.png'));
    for(const obj of lock.selected_objects){const bytes=await readFile(path.join(lock.environment_directory,obj.media_path));if(hash(bytes)!==obj.media_sha256)throw new Error(`Object ${obj.number} image differs`);await copyFile(path.join(lock.environment_directory,obj.media_path),path.join(root,obj.media_path));}
    let html=source.toString();
    const match=html.match(/<script id="tour-data" type="application\/json">(.*?)<\/script>/s);if(!match)throw new Error('Tour data missing');const tour=JSON.parse(match[1]);
    if(tour.id!==lock.tour_id||tour.scenes.length!==2)throw new Error('Wrong tour identity');
    const staging=createShots(tour);
    const worldPoint=(shot,point)=>{const yaw=shot.camera.yaw*Math.PI/180,pitch=shot.camera.pitch*Math.PI/180,t=Math.tan(shot.camera.hfov*Math.PI/360),x=(point[0]/50-1)*t,y=(1-point[1]/50)*t*9/16,z=1;const yy=y*Math.cos(pitch)+z*Math.sin(pitch),zz=z*Math.cos(pitch)-y*Math.sin(pitch),xx=x*Math.cos(yaw)+zz*Math.sin(yaw),wz=zz*Math.cos(yaw)-x*Math.sin(yaw);return {yaw:Math.atan2(xx,wz)*180/Math.PI,pitch:Math.atan2(yy,Math.hypot(xx,wz))*180/Math.PI};};
    const placements=[['ilyas','İlyas',68,0,0,1,1],['davud','Davud',68,1,2,-1,-1],['meryem','Meryem',62,0,1,-1,1],['salih','Salih',23,0,3,-1,1],['kemal','Kemal',16,1,3,-1,-1]];
    const worldActors=placements.map(([id,name,number,index,frame,nativeFacing,facing])=>{const nav=review.objects.find(n=>n.number===number),shot=staging.find(n=>n.number===number);return {id,name,number,frame,nativeFacing,facing,sceneId:shot.sceneId,...worldPoint(shot,nav.actors[index])};});
    const renderTour=structuredClone(tour);renderTour.scenes[0].view={...staging.find(s=>s.number===68).camera};for(const actor of worldActors)renderTour.scenes.find(sc=>sc.id===actor.sceneId).hotspots.push({id:'story-npc-'+actor.id,type:'info',targetId:null,label:actor.name,text:`NPC:${actor.frame}:${actor.number}:${actor.facing/actor.nativeFacing}`,yaw:actor.yaw,pitch:actor.pitch});
    html=html.replace(match[1],JSON.stringify(renderTour));
    const npcTooltip=`if(d.id.startsWith("story-npc-")){f.classList.add("world-npc");f.setAttribute("role","button");f.setAttribute("tabindex","0");f.setAttribute("aria-label","与"+d.label+"交谈");let body=document.createElement("div");body.className="world-cast";let art=document.createElement("div");art.className="world-art";art.style.backgroundPosition=(Number(d.text.split(":")[1])*100/3)+"% 100%";art.style.transform="scaleX("+Number(d.text.split(":")[3])+")";body.append(art);let label=document.createElement("div");label.className="world-name";label.textContent=d.label;body.append(label);f.append(body);f.addEventListener("keydown",event=>{if(event.key==="Enter"){event.preventDefault();this.onInfo({...d,gesture:"approach"});}});return;}`;
    html=html.replace('createTooltipFunc:f=>{','createTooltipFunc:f=>{'+npcTooltip);
    html=html.replace('<script src="vr_position_editor.js"></script>','').replace('new window.PastPortPositionEditor(r).initialize();','');
    const start=html.indexOf('onInfo:async l=>',html.indexOf('var Wr=document.getElementById'));const end=html.indexOf(',onError:e',start);
    if(start<0||end<0)throw new Error('Museum info adapter anchor changed');
    html=html.slice(0,start)+'onInfo:l=>parent.postMessage(l.id.startsWith("story-npc-")?{type:"pastport:npc",number:Number(l.text.split(":")[2]),speaker:l.label}:{type:"pastport:object",number:Number(l.label),sceneId:r.activeId,gesture:l.gesture??"click"},location.origin)'+html.slice(end);
    html=html.replace('(_.key==="Enter"||_.key===" ")&&(_.preventDefault(),f.click())','(_.key==="Enter"||_.key===" ")&&(_.preventDefault(),this.onInfo({...d,gesture:_.shiftKey?"approach":"inspect"}))');
    const anchor='r.load(i.scenes,i.firstSceneId);';if(!html.includes(anchor))throw new Error('Museum load anchor changed');
    const bridge=`
let heldView=null,shotToken=null;
addEventListener("message",event=>{
 if(event.source!==parent||event.origin!==location.origin)return;
 const msg=event.data;if(!msg||!['pastport:focus','pastport:shot','pastport:restore','pastport:ping'].includes(msg.type))return;
 if(msg.type==='pastport:ping'){parent.postMessage({type:'pastport:ready'},location.origin);return;}
 if(msg.type==='pastport:restore'){
   shotToken=null;document.body.classList.remove('cinematic');const prev=heldView??msg.view;heldView=null;
   if(!prev||!i.scenes.some(sc=>sc.id===prev.scene))return;
   const apply=()=>r.viewer?.lookAt(prev.pitch,prev.yaw,prev.hfov,350);
   if(r.activeId===prev.scene)apply();else{const once=()=>{r.viewer.off('load',once);apply();};r.viewer.on('load',once);r.go(prev.scene);}return;
 }
 const scene=i.scenes.find(sc=>sc.id===msg.sceneId&&sc.hotspots.some(h=>Number(h.label)===msg.number))??i.scenes.find(sc=>sc.id===r.activeId&&sc.hotspots.some(h=>Number(h.label)===msg.number))??i.scenes.find(sc=>sc.hotspots.some(h=>Number(h.label)===msg.number));if(!scene)return;
 const target=scene.hotspots.find(h=>Number(h.label)===msg.number);r.rotate(false);
 if(msg.type==='pastport:shot'){
   if(!heldView)heldView=msg.origin??{scene:r.activeId,...r.view()};shotToken=msg.token;document.body.classList.add('cinematic');
   const apply=()=>{const camera=msg.camera;if(!camera||![camera.yaw,camera.pitch,camera.hfov].every(Number.isFinite))return;r.viewer?.lookAt(camera.pitch,camera.yaw,camera.hfov,450,()=>{if(shotToken!==msg.token)return;r.viewer.stopMovement();parent.postMessage({type:'pastport:shot-ready',token:msg.token,number:msg.number,beforeView:heldView},location.origin);});};
   if(r.activeId===scene.id)requestAnimationFrame(apply);else{const once=()=>{r.viewer.off('load',once);apply();};r.viewer.on('load',once);r.go(scene.id);}return;
 }
 const apply=()=>r.viewer?.lookAt(msg.camera?.pitch??target.pitch,msg.camera?.yaw??target.yaw,msg.camera?.hfov??82,350);
 if(r.activeId===scene.id)apply();else{const once=()=>{r.viewer.off('load',once);apply();};r.viewer.on('load',once);r.go(scene.id);}
});
parent.postMessage({type:'pastport:ready'},location.origin);
`;

    html=html.replace(anchor,anchor+bridge).replace('<title>PastPort · Virtual Tour</title>','<title>Murat · 环视</title>');
    html=html.replace(/<aside id="trial-summary">.*?<\/aside>/s,'');
    html=html.replace('</head>','<style>.tour-top,.tour-controls,#tour-notice{display:none!important}#tour-scenes{top:18px!important;bottom:auto!important}.minimap{display:none!important}.cinematic #tour-scenes,.cinematic .trial-number,.cinematic .world-npc{display:none!important}.world-npc{background:none!important;width:26px!important;height:26px!important;cursor:pointer}.world-cast{position:absolute;left:50%;top:50%;width:clamp(55px,8vw,115px);height:clamp(110px,16vw,230px);transform:translate(-50%,-94%);filter:drop-shadow(0 3px 2px #173b3544)}.world-art{position:absolute;inset:0;background-image:url(../assets/cast.png);background-size:400% 200%;background-repeat:no-repeat}.world-name{position:absolute;left:50%;top:4%;transform:translate(-50%,-100%);font:12px system-ui;color:#f9e8bd;background:#173c35ba;padding:3px 7px;border-radius:3px;white-space:nowrap}</style></head>');
    await writeFile(path.join(root,'museum/index.html'),html);
    const pkg=createGame(hash(lockBytes),hash(story),lock.selected_objects);
    await writeFile(path.join(root,'data/runtime.json'),json(pkg));
    const shots=createShots(tour).map(shot=>{const item=review.objects.find(n=>n.number===shot.number);if(!item||item.status!=='visually_reviewed')return {...shot,available:false,reason:item?.reason??'空间尚未检查，暂不允许接近。'};return {...shot,available:true,boundary:item.boundary,obstacles:item.obstacles,spawn:item.spawn,approach:item.approach,actors:item.actors,navigation:item};});
    const display={...presentation,objects:lock.selected_objects,tourId:tour.id,shots,stageTargets,castByStage,castFrames,castRows,worldActors,interactionVersion:4,panoramaHashes:Object.fromEntries(lock.scenes.map(sc=>[sc.scene_id,sc.panorama_sha256])),walkArea:{sceneId:tour.firstSceneId,focusObject:68,boundary:shots.find(s=>s.number===68).boundary,spawn:shots.find(s=>s.number===68).spawn,approach:shots.find(s=>s.number===68).approach},scenes:tour.scenes.map(sc=>({id:sc.id,name:sc.name,hotspots:sc.hotspots.map(h=>({number:Number(h.label),yaw:h.yaw,pitch:h.pitch}))}))};
    for(const item of review.objects.filter(n=>n.status==='visually_reviewed'))if(hash(await readFile(path.join(root,item.projectionEvidence)))!==item.projectionSha256)throw new Error('Navigation projection differs from review');
    validateNavigation(display);await writeFile(path.join(root,'data/presentation.json'),json(display));
    const {contentHash}=await import('./engine/validation.mjs');
    const packageHash=await contentHash(pkg);
    const reference={artifact_id:'murat-runtime-demo',project_id:pkg.project_id,kind:'runtime',schema_version:pkg.schema_version,content_version:pkg.content_version,sha256:packageHash};
    await writeFile(path.join(root,'data/reference.json'),json(reference));
    const files=['scene3d-view.mjs','scene3d-runtime.js','scene3d-navigation.mjs','scene3d-bridge.mjs','serve3d.mjs','data/scene3d-input.json','content.mjs','shots.mjs','navigation.mjs','navigation.json','dialogue.mjs','serve.mjs','interaction.mjs','cinematic-view.mjs','assets/cast.png','plugins.mjs','session.mjs','app.mjs','app.css','index.html','walkmesh.mjs',...engineFiles.map(n=>'engine/'+n),'data/runtime.json','data/reference.json','data/presentation.json','museum/index.html',...lock.selected_objects.map(o=>o.media_path)];
    const fileHashes=[];for(const file of files)fileHashes.push({path:file,sha256:hash(await readFile(path.join(root,file)))});
    await writeFile(path.join(root,'manifest.json'),json({format:'pastport-isolated-story-demo',version:1,sourceTourId:tour.id,sourceHtmlSha256:lock.html_sha256,sourceDatabaseSha256:lock.database_sha256_at_read,storySha256:hash(story),authoringLockSha256:hash(lockBytes),engineCommit,walkingCommit,engineStatus:'unmodified shared wire 0.1.0 engine; local activity-to-inspect adapter, not official SDK plugin integration',packageHash,localOnly:true,humanPlaytest:'not_performed',files:fileHashes}));
    console.log(`Built ${root}\n${packageHash}\n14 source images, 2 viewpoints, ${pkg.game.scenes.length} runtime stages.`);
  }
}
await new DemoBuilder().build();
