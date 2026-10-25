(()=>{
 if(window.PastPortSharedContent)return;
 window.PastPortSharedContent=true;
 const channel=new BroadcastChannel('pastport-shared-content-v1'),dirty=new Set();
 let revision=null,polling=false,eligible=null;
 document.addEventListener('input',event=>{if(event.target.closest?.('#detail'))dirty.add(event.target);});
 async function refreshSourcePopup(id){
  const dialog=document.getElementById('info');
  if(!dialog?.open||Number(dialog.dataset.currentHotspot?.replace('trial-object-',''))!==Number(id))return;
  try{const r=await fetch(`/api/vr-content?object_id=${id}`,{cache:'no-store'});if(!r.ok)throw Error('内容绑定已改变');dialog.querySelector('p').textContent=(await r.json()).content;}
  catch{dialog.querySelector('p').textContent='此编号的介绍或审核状态已变化，请到审核后台核对。';}
 }
 function filterSource(){
  if(!eligible)return;
  for(const hot of window.PastPortSourceHost?.viewer.getConfig().hotSpots||[]){
   if(hot.id?.startsWith('trial-object-')&&hot.div)hot.div.style.display=eligible.has(Number(hot.id.replace('trial-object-','')))?'':'none';
  }
 }
 function refreshReview(){
  if(!document.getElementById('detail')||typeof window.load!=='function')return;
  for(const field of dirty)if(!field.isConnected)dirty.delete(field);
  if(!dirty.size){window.load().catch(()=>{});return;}
  let notice=document.getElementById('shared-content-update');
  if(!notice){notice=document.createElement('button');notice.id='shared-content-update';notice.textContent='其他视角已更新内容；保留当前输入，点此重新读取';notice.onclick=()=>{dirty.clear();notice.remove();window.load().catch(()=>{});};document.getElementById('detail').prepend(notice);}
 }
 async function poll(){
  if(polling||document.hidden)return;polling=true;
  try{
   const r=await fetch('/api/shared-content-revision',{cache:'no-store'});if(!r.ok)throw Error('共享内容暂不可用');
   const state=await r.json();eligible=new Set(state.eligible);filterSource();
   if(revision!==state.revision){const changed=revision!==null;revision=state.revision;
    window.dispatchEvent(new CustomEvent('pastport-shared-changed',{detail:state}));
    const dialog=document.getElementById('info');if(dialog?.open)await refreshSourcePopup(Number(dialog.dataset.currentHotspot?.replace('trial-object-','')));
    if(changed)refreshReview();
   }
  }catch{window.dispatchEvent(new Event('pastport-shared-unavailable'));}
  finally{polling=false;}
 }
 channel.onmessage=e=>{if(e.data?.type==='content-saved')poll();};
 window.addEventListener('pastport-content-saved',e=>{const id=e.detail?.object_id;if(Number.isInteger(id))channel.postMessage({type:'content-saved',object_id:id});poll();});
 async function focusSource(){
  const id=Number(new URLSearchParams(location.search).get('object_id')),host=window.PastPortSourceHost;if(!host)return;
  host.viewer.on('load',filterSource);
  if(!id)return;
  const data=JSON.parse(document.getElementById('tour-data').textContent),scene=data.scenes.find(s=>s.hotspots.some(h=>h.id===`trial-object-${String(id).padStart(2,'0')}`||Number(h.label)===id));if(!scene)return;
  const hot=scene.hotspots.find(h=>Number(h.label)===id),apply=()=>host.viewer.lookAt(hot.pitch,hot.yaw,undefined,false);
  host.viewer.on('load',apply);if(host.viewer.getScene()!==scene.id)host.go(scene.id);apply();
 }
 window.addEventListener('pastport-source-ready',()=>focusSource().catch(()=>{}));
 if(window.PastPortSourceHost)focusSource().catch(()=>{});
 const timer=setInterval(poll,2000);addEventListener('focus',poll);poll();
 addEventListener('pagehide',e=>{if(!e.persisted){clearInterval(timer);channel.close();}});
})();
