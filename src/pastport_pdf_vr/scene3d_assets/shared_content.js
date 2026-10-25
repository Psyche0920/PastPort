(()=>{
 const channel=new BroadcastChannel('pastport-shared-content-v1');
 async function refreshSourcePopup(id){const dialog=document.getElementById('info');if(!dialog?.open||Number(dialog.dataset.currentHotspot?.replace('trial-object-',''))!==Number(id))return;try{const r=await fetch(`/api/vr-content?object_id=${id}`,{cache:'no-store'});if(!r.ok)throw Error('内容绑定已改变');dialog.querySelector('p').textContent=(await r.json()).content;}catch(e){dialog.querySelector('p').textContent='未能读取更新后的介绍，请重新打开编号。';}}
 channel.onmessage=e=>{if(e.data?.type==='content-saved')refreshSourcePopup(e.data.object_id);};
 window.addEventListener('pastport-content-saved',e=>{const id=e.detail?.object_id;if(Number.isInteger(id))channel.postMessage({type:'content-saved',object_id:id});});
 async function focusSource(){const id=Number(new URLSearchParams(location.search).get('object_id')),host=window.PastPortSourceHost;if(!id||!host)return;const data=JSON.parse(document.getElementById('tour-data').textContent),scene=data.scenes.find(s=>s.hotspots.some(h=>h.id===`trial-object-${String(id).padStart(2,'0')}`||Number(h.label)===id));if(!scene)return;const hot=scene.hotspots.find(h=>Number(h.label)===id);const apply=()=>host.viewer.lookAt(hot.pitch,hot.yaw,undefined,false);host.viewer.on('load',apply);if(host.viewer.getScene()!==scene.id)host.go(scene.id);apply();}
 window.addEventListener('pastport-source-ready',()=>focusSource().catch(()=>{}));
 if(window.PastPortSourceHost)focusSource().catch(()=>{});
 addEventListener('pagehide',e=>{if(!e.persisted)channel.close();});
})();
