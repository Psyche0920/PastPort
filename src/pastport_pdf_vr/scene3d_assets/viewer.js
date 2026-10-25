import {SceneTransitions} from './transitions.js';
import * as THREE from 'three';
import {SparkRenderer,SplatMesh} from '@sparkjsdev/spark';
import {GLTFLoader} from './GLTFLoader.js';
const $=id=>document.getElementById(id), note=text=>{$('notice').textContent=text;if(!text.startsWith('已挂载')&&/保存|失败|不可用|切换|版本|重试/.test(text)){$('toast').textContent=text;$('toast').hidden=false;clearTimeout(note.timer);note.timer=setTimeout(()=>{$('toast').hidden=true;},5000);}};
const renderer=new THREE.WebGLRenderer({antialias:true});renderer.setPixelRatio(devicePixelRatio||1);document.body.append(renderer.domElement);
const scene=new THREE.Scene(),camera=new THREE.PerspectiveCamera(65,1,.03,1000);camera.rotation.order='YXZ';
scene.add(new SparkRenderer({renderer}));
let transitions=null;let data,collider,candidate=null,markers=[],busy=false,pendingSave=null,markerDrag=null,popupId=null;const ray=new THREE.Raycaster(),keys=new Set();
const group=new THREE.Group();scene.add(group);const radians=THREE.MathUtils.degToRad;
const contentChannel=new BroadcastChannel('pastport-shared-content-v1');
async function api(path,body){const r=await fetch(path,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{});if(!r.ok){let d;try{d=await r.json();}catch{}throw Error(d?.detail||(r.status===409?'版本冲突，请刷新；未保存。':'请求失败；未保存。'));}return r.json();}
function alignmentQuaternion(){return new THREE.Quaternion().setFromEuler(new THREE.Euler(radians(data.alignment.pitch_degrees),radians(data.alignment.yaw_degrees),radians(data.alignment.roll_degrees),'YXZ'));}
function origin(){const p=data.alignment.origin;camera.position.set(p.x,p.y,p.z);camera.quaternion.copy(alignmentQuaternion());}
function eligible(o){return o.historical_id&&o.image_review!=='unsuitable'&&o.text_review!=='unsuitable'&&o.proposal_state!=='invalid_structural_relation';}
function selected(){return data.objects.find(o=>String(o.id)===$('object').value);}
function point(p){candidate=p;$('coordinates').textContent=p?`候选（米）：${p.x.toFixed(3)}, ${p.y.toFixed(3)}, ${p.z.toFixed(3)}`:'尚无候选点';}
function markerFor(o,pending){const canvas=document.createElement('canvas');canvas.width=128;canvas.height=128;const c=canvas.getContext('2d');c.strokeStyle=pending?'#e6a451':'#8fcb98';c.lineWidth=3;if(pending)c.setLineDash([12,7]);c.beginPath();c.arc(64,64,53,0,Math.PI*2);c.stroke();c.fillStyle='#fff';c.textAlign='center';c.textBaseline='middle';c.font='bold 48px system-ui';c.fillText(String(o.id).padStart(2,'0'),64,64);const m=new THREE.Sprite(new THREE.SpriteMaterial({map:new THREE.CanvasTexture(canvas),transparent:true,depthTest:false,depthWrite:false,toneMapped:false}));m.scale.set(.24,.24,1);m.renderOrder=100000;m.userData={object:o,pending};return m;}
function releaseMarker(m){scene.remove(m);m.material.map.dispose();m.material.dispose();}
function drawMarkers(){for(const m of markers)releaseMarker(m);markers=[];for(const o of data.objects){if(!eligible(o))continue;const proposed=data.candidates?.find(p=>p.object_id===o.id);const pending=!o.point_json&&o.version===0&&proposed?.point_json;const raw=o.point_json||pending;if(!raw)continue;if(o.parent_id){const parent=data.objects.find(p=>p.id===o.parent_id);if(!parent||!eligible(parent)||!parent.point_json)continue;}const p=JSON.parse(raw),m=markerFor(o,Boolean(pending));m.position.set(p.x,p.y,p.z);scene.add(m);markers.push(m);}}
async function migrateCandidates(){const targets=data.source_hotspots.filter(h=>data.objects.some(o=>o.id===h.object_id&&eligible(o)));if(targets.every(h=>data.candidates?.some(c=>c.object_id===h.object_id)))return;const origin=data.alignment.origin,q=alignmentQuaternion();const positions=targets.map(h=>{const yaw=radians(h.yaw),pitch=radians(h.pitch),direction=new THREE.Vector3(Math.sin(yaw)*Math.cos(pitch),Math.sin(pitch),-Math.cos(yaw)*Math.cos(pitch)).applyQuaternion(q);ray.set(new THREE.Vector3(origin.x,origin.y,origin.z),direction);const hit=ray.intersectObject(collider,true)[0];return {object_id:h.object_id,point:hit?{x:hit.point.x,y:hit.point.y,z:hit.point.z}:null};});await api('/api/scene3d/candidates',{scene_binding:data.binding,alignment_version:data.alignment.version,origin,alignment_kind:data.alignment.confirmed?'human_alignment':'unconfirmed_asset_origin',positions});await reload();}
async function reload(){const current=$('object').value;data=await api('/api/scene3d');if(!data.alignment.confirmed&&data.alignment.version===0&&!data.alignment.editor)data.alignment.origin={x:0,y:data.scene.ground_plane_offset,z:0};$('object').replaceChildren(...data.objects.filter(eligible).map(o=>new Option(`${String(o.id).padStart(2,'0')} · ${o.name}${o.point_json?' ✓':''}`,o.id)));if(current)$('object').value=current;drawMarkers();}
function fromFields(){return {origin:{x:Number($('ox').value),y:Number($('oy').value),z:Number($('oz').value)},yaw_degrees:Number($('yaw').value),pitch_degrees:Number($('pitch').value),roll_degrees:Number($('roll').value)};}
$('capture').onclick=()=>{for(const [id,v]of [['ox',camera.position.x],['oy',camera.position.y],['oz',camera.position.z],['yaw',THREE.MathUtils.radToDeg(camera.rotation.y)],['pitch',THREE.MathUtils.radToDeg(camera.rotation.x)],['roll',THREE.MathUtils.radToDeg(camera.rotation.z)]])$(id).value=v.toFixed(3);};
$('origin').onclick=()=>origin();
$('save-alignment').onclick=async()=>{try{await api('/api/scene3d/alignment',{...fromFields(),scene_binding:data.binding,expected_version:data.alignment.version,confirmed:$('aligned').checked,editor:$('editor').value.trim(),basis:$('alignment-basis').value.trim()});await reload();await migrateCandidates();point(null);origin();note('对齐已保存；候选点仍需逐项确认身份。');}catch(e){note(e.message);}};
$('object').onchange=()=>{point(null);$('popup').style.display='none';};
$('propose').onclick=()=>{try{if(!data.alignment.confirmed)throw Error('请先人工对齐并保存拍摄点。');const o=selected(),h=data.source_hotspots.find(h=>h.object_id===o.id);if(!h)throw Error('该视点没有此物件的原热点；请点选校准。');const yaw=radians(h.yaw),pitch=radians(h.pitch),direction=new THREE.Vector3(Math.sin(yaw)*Math.cos(pitch),Math.sin(pitch),-Math.cos(yaw)*Math.cos(pitch)).applyQuaternion(alignmentQuaternion());ray.set(new THREE.Vector3(data.alignment.origin.x,data.alignment.origin.y,data.alignment.origin.z),direction);const hits=ray.intersectObject(collider,true);if(!hits.length)throw Error('方向没有碰到几何表面，不能补造深度；请人工点选。');point(hits[0].point.clone());note('黄色候选方向命中表面，不代表已经认对物件；确认身份后保存。');}catch(e){note(e.message);}};
async function persistPosition(edit){
 if(busy)return false;busy=true;pendingSave=edit;$('retry-position').hidden=true;
 try{await api('/api/scene3d/anchor',edit);pendingSave=null;await reload();point(null);note(edit.point?'人工位置已保存。原全景位置保持不变，介绍仍共用。':'已撤下此3D编号，历史保留。');return true;}
 catch(e){note('位置保存未确认：'+e.message);$('retry-position').hidden=!pendingSave;return false;}
 finally{busy=false;}
}
async function save(remove=false,method='aligned_confirmation',object=null){
 const o=object||selected();if(!o){note('请选择物件');return false;}if(!remove&&!candidate){note('请先拖动或点选位置');return false;}
 if(!remove&&$('pick').checked)method='surface_pick';
 const manual=method==='surface_pick';
 const edit={operation_id:crypto.randomUUID(),scene_binding:data.binding,object_id:o.id,historical_id:o.historical_id,expected_version:o.version,
 point:remove?null:{x:candidate.x,y:candidate.y,z:candidate.z},editor:$('editor').value.trim()||(manual?'local_editor':''),
 identity_basis:$('basis').value.trim()||(manual?'User manually placed this numbered marker on a 3D collision surface.':''),
 relation_basis:$('relation').value.trim(),placement_method:method};
 return persistPosition(edit);
}
$('edit-panel').onclick=()=>{$('editor-panel').hidden=false;};$('close-editor').onclick=()=>{$('drag-arrows').checked=false;$('drag-markers').checked=false;$('pick').checked=false;$('editor-panel').hidden=true;};$('home-view').onclick=origin;$('fullscreen').onclick=()=>{(document.fullscreenElement?document.exitFullscreen():document.documentElement.requestFullscreen()).catch(()=>note('当前设备无法全屏'));};$('next-viewpoint').onclick=()=>{const arrow=transitions?.markers[0];if(arrow)transitions.go(arrow);else note('点位导航尚未载入，请从工作台重新打开');};
$('confirm').onclick=()=>save();$('remove').onclick=()=>save(true);
$('retry-position').onclick=()=>pendingSave&&persistPosition(pendingSave);
function setScreenRay(event){ray.setFromCamera(new THREE.Vector2(event.clientX/innerWidth*2-1,1-event.clientY/innerHeight*2),camera);}
async function showPopup(o,pending=false){
 try{const content=await api(`/api/scene3d/content?object_id=${o.id}`);popupId=o.id;$('object').value=String(o.id);$('popup').replaceChildren();
 const text=document.createElement('p');text.textContent=`${o.id} · ${o.name}${pending?'（自动迁移候选，位置待核对）':''}\n\n${content.content}`;
 const link=document.createElement('a');link.href=`/?object_id=${o.id}`;link.textContent='在后台编辑共用介绍';
 const move=document.createElement('button');move.textContent='拖拽调整此编号';move.onclick=()=>{$('drag-markers').checked=true;$('popup').style.display='none';note('拖动此编号到正确表面，松开自动保存；文字和原全景位置不受影响。');};
 const close=document.createElement('button');close.textContent='关闭';close.onclick=()=>{$('popup').style.display='none';popupId=null;};
 $('popup').append(text,link,move,close);$('popup').style.display='block';
 }catch(e){note(e.message);await reload();}
}
contentChannel.onmessage=async event=>{if(event.data?.type==='content-saved'&&Number(event.data.object_id)===popupId&&$('popup').style.display!=='none'){const marker=markers.find(m=>m.userData.object.id===popupId);if(marker)await showPopup(marker.userData.object,marker.userData.pending);}};
let dragging=false,moved=0;
renderer.domElement.onpointerdown=event=>{
 if(busy)return;if(transitions?.startDrag(event))return;dragging=true;moved=0;renderer.domElement.setPointerCapture(event.pointerId);
 if($('drag-markers').checked){setScreenRay(event);const hit=ray.intersectObjects(markers)[0];if(hit){markerDrag={marker:hit.object,original:hit.object.position.clone(),point:null};$('object').value=String(hit.object.userData.object.id);$('popup').style.display='none';event.preventDefault();}}
};
renderer.domElement.onpointermove=event=>{
 if(transitions?.moveDrag(event))return;if(!dragging)return;moved+=Math.abs(event.movementX)+Math.abs(event.movementY);
 if(markerDrag){setScreenRay(event);const hit=ray.intersectObject(collider,true)[0];markerDrag.point=hit?hit.point.clone():null;if(hit){markerDrag.marker.position.copy(hit.point);point(hit.point.clone());}return;}
 camera.rotation.y-=event.movementX*.003;camera.rotation.x=THREE.MathUtils.clamp(camera.rotation.x-event.movementY*.003,-1.55,1.55);
};
renderer.domElement.onpointerup=async event=>{
 if(await transitions?.finishDrag(event))return;dragging=false;
 if(markerDrag){const drag=markerDrag;markerDrag=null;if(moved>3){if(!drag.point){drag.marker.position.copy(drag.original);point(null);note('未命中3D表面，位置未保存。');return;}point(drag.point);const saved=await save(false,'surface_pick',drag.marker.userData.object);if(!saved)drag.marker.position.copy(drag.original);return;}}
 if(moved>6||!collider)return;if(transitions?.click(event,innerWidth,innerHeight))return;setScreenRay(event);
 if($('pick').checked){const hit=ray.intersectObject(collider,true)[0];if(hit)point(hit.point.clone());else note('没有命中表面。');return;}
 const hit=ray.intersectObjects(markers)[0];if(hit){point(hit.object.position.clone());await showPopup(hit.object.userData.object,hit.object.userData.pending);}
};
renderer.domElement.onpointercancel=()=>{transitions?.cancelDrag();dragging=false;if(markerDrag)markerDrag.marker.position.copy(markerDrag.original);markerDrag=null;};
addEventListener('beforeunload',event=>{if(busy||pendingSave||markerDrag||transitions?.pending||transitions?.drag){event.preventDefault();event.returnValue='';}});
addEventListener('keydown',e=>{if(['INPUT','TEXTAREA','SELECT'].includes(document.activeElement.tagName))return;keys.add(e.code);});addEventListener('keyup',e=>keys.delete(e.code));addEventListener('blur',()=>keys.clear());
function resize(){renderer.setSize(innerWidth,innerHeight);camera.aspect=innerWidth/innerHeight;camera.updateProjectionMatrix();}addEventListener('resize',resize);resize();
let last=performance.now();renderer.setAnimationLoop(now=>{const dt=Math.min((now-last)/1000,.05);last=now;const speed=(keys.has('ShiftLeft')?3:1)*dt;const forward=new THREE.Vector3(0,0,-1).applyQuaternion(camera.quaternion),right=new THREE.Vector3(1,0,0).applyQuaternion(camera.quaternion);camera.position.addScaledVector(forward,(Number(keys.has('KeyW'))-Number(keys.has('KeyS')))*speed).addScaledVector(right,(Number(keys.has('KeyD'))-Number(keys.has('KeyA')))*speed);camera.position.y+=(Number(keys.has('KeyE'))-Number(keys.has('KeyQ')))*speed;for(const m of markers){const size=camera.position.distanceTo(m.position)*2*Math.tan(radians(camera.fov)/2)*36/innerHeight;m.scale.set(size,size,1);}transitions?.update();renderer.render(scene,camera);});
try{await reload();$('source').src=data.source_panorama;const s=data.scene;group.scale.setScalar(s.metric_scale_factor);group.quaternion.set(1,0,0,0);group.position.y=s.ground_plane_offset;const splat=new SplatMesh({url:data.render_variant?.splat||s.splat});group.add(splat);const gltf=await new GLTFLoader().loadAsync('collider.glb');collider=gltf.scene;collider.traverse(o=>{if(o.isMesh)o.material=new THREE.MeshBasicMaterial({visible:false,side:THREE.DoubleSide});});group.add(collider);group.updateMatrixWorld(true);await splat.initialized;await migrateCandidates();origin();transitions=new SceneTransitions({camera,scene,collider,getData:()=>data,getOrientation:alignmentQuaternion,note,canLeave:()=>!busy&&!pendingSave&&!markerDrag&&!$('drag-markers').checked});await transitions.initialize();$('next-viewpoint').disabled=!transitions.markers.length;transitions.applyArrival();for(const[id,v]of[['ox',data.alignment.origin.x],['oy',data.alignment.origin.y],['oz',data.alignment.origin.z],['yaw',data.alignment.yaw_degrees],['pitch',data.alignment.pitch_degrees],['roll',data.alignment.roll_degrees]])$(id).value=v;$('aligned').checked=data.alignment.confirmed;const requested=Number(new URLSearchParams(location.search).get('object_id'));if(requested){const marker=markers.find(m=>m.userData.object.id===requested);if(marker){camera.lookAt(marker.position);point(marker.position.clone());await showPopup(marker.userData.object,marker.userData.pending);}}const suggested=markers.filter(m=>m.userData.pending).length;note(`已挂载 ${markers.length} 个可点击编号，其中 ${suggested} 个为自动迁移候选（橙色虚线，位置待核对）。原介绍与审核后台已联动。${transitions?.statusText||''}`);}catch(e){note('场景加载失败：'+e.message);}
addEventListener('pagehide',event=>{if(event.persisted)return;contentChannel.close();transitions?.dispose();renderer.setAnimationLoop(null);renderer.dispose();for(const m of markers)releaseMarker(m);});
