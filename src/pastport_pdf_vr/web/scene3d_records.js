(()=>{
  const displayTitle=value=>String(value||'').replace(/\s*·\s*已有匹配成品(?:[（(].*[）)])?\s*$/u,'');
  const root=document.getElementById('scene3d-jobs');if(!root)return;
  const labels={running:'处理中',generation_pending:'等待 Marble 完成',pending_manual_acceptance:'已就绪',not_submitted:'尚未提交',recovery_required:'已停止 · 需核对'};
  let refreshing=false;
  async function refresh(){
    if(refreshing)return;refreshing=true;
    try{
      const response=await fetch('/api/scene3d-deliveries');if(!response.ok)throw Error('无法读取 3D 记录，请确认工作台已重启到最新代码。');
      const rows=await response.json(),fragment=document.createDocumentFragment();
      const groups=new Map();
      for(const row of rows){
        const key=row.job_id||row.run_id;
        if(!groups.has(key))groups.set(key,[]);
        groups.get(key).push(row);
      }
      for(const [jobId,items] of groups){
        const first=items[0],group=document.createElement('section');group.className='scene3d-site';
        const heading=document.createElement('h3');heading.className='scene3d-site-title';heading.textContent=displayTitle(first.source_title||first.title)||'3D 场景';
        group.append(heading);fragment.append(group);
        const views=new Map();
        for(const row of items)if(row.url&&!views.has(row.source_scene_id))views.set(row.source_scene_id,row);
        const expected=first.viewpoint_count;
        if(first.job_id&&expected>1){
          const card=document.createElement('article');card.className='job';
          const title=document.createElement('h4');title.textContent='完整 3D 导览';
          const note=document.createElement('p');note.textContent=`${views.size} / ${expected} 个点位已就绪`;
          const nav=document.createElement('nav');
          if(views.size===expected){
            const entry=[...views.values()].sort((a,b)=>a.viewpoint_number-b.viewpoint_number)[0];
            const view=document.createElement('a');view.href=entry.url;view.textContent='查看完整 3D 导览';
            const download=document.createElement('a');download.href=`/api/scene3d-tour/${encodeURIComponent(jobId)}/package`;download.textContent='下载完整导览文件包';
            nav.append(view,download);
          }else note.textContent+=' · 等待其余点位生成';
          card.append(title,note,nav);group.append(card);
        }
      for(const row of [...items].sort((a,b)=>(a.viewpoint_number||0)-(b.viewpoint_number||0))){
        const card=document.createElement('article');card.className='job';
        const title=document.createElement('h4');title.textContent=row.viewpoint_number?`点位 ${row.viewpoint_number} · 3D`:(row.title||'3D 场景');
        const badge=document.createElement('span');badge.className='badge';badge.textContent=labels[row.status]||row.status;title.append(badge);
        const note=document.createElement('p');note.textContent=row.message||'';note.hidden=Boolean(row.url);
        const nav=document.createElement('nav');
        if(row.url){const a=document.createElement('a');a.href=row.url;a.textContent='查看 3D 输出';nav.append(a);}
        if(row.package_url){const a=document.createElement('a');a.href=row.package_url;a.textContent='下载开发文件包';nav.append(a);}
        if(row.resume){const button=document.createElement('button');button.textContent='查询原任务';button.onclick=async()=>{button.disabled=true;try{const r=await fetch(row.resume,{method:'POST',headers:{'X-PastPort-Edit':'1'}});if(!r.ok){const d=await r.json();throw Error(d.detail||'查询失败，原记录保留。');}await refresh();}catch(e){note.textContent=e.message;}finally{button.disabled=false;}};nav.append(button);}
        card.append(title,note,nav);group.append(card);
      }
      }
      if(!rows.length){const empty=document.createElement('p');empty.className='empty';empty.textContent='还没有 3D 生成记录。点击上方对应 VR 记录的“生成 3D”即可开始。';fragment.append(empty);}
      root.replaceChildren(fragment);
    }catch(e){root.textContent=e.message;}finally{refreshing=false;}
  }
  refresh();setInterval(refresh,5000);window.addEventListener('scene3d-records-changed',refresh);
})();
