(()=>{
  const root=document.getElementById('scene3d-jobs');if(!root)return;
  const labels={running:'处理中',generation_pending:'等待 Marble 完成',pending_manual_acceptance:'输出就绪 · 待人工验收',not_submitted:'尚未提交',recovery_required:'已停止 · 需核对'};
  let refreshing=false;
  async function refresh(){
    if(refreshing)return;refreshing=true;
    try{
      const response=await fetch('/api/scene3d-deliveries');if(!response.ok)throw Error('无法读取 3D 记录，请确认工作台已重启到最新代码。');
      const rows=await response.json(),fragment=document.createDocumentFragment();
      for(const row of rows){
        const card=document.createElement('article');card.className='job';
        const title=document.createElement('h3');title.textContent=row.title||'3D 场景';
        const badge=document.createElement('span');badge.className='badge';badge.textContent=labels[row.status]||row.status;title.append(badge);
        const note=document.createElement('p');note.textContent=row.message||'输出已保存，等待人工验收。';
        const nav=document.createElement('nav');
        if(row.url){const a=document.createElement('a');a.href=row.url;a.textContent='查看 3D 输出';nav.append(a);}
        if(row.resume){const button=document.createElement('button');button.textContent='查询原任务';button.onclick=async()=>{button.disabled=true;try{const r=await fetch(row.resume,{method:'POST',headers:{'X-PastPort-Edit':'1'}});if(!r.ok){const d=await r.json();throw Error(d.detail||'查询失败，原记录保留。');}await refresh();}catch(e){note.textContent=e.message;}finally{button.disabled=false;}};nav.append(button);}
        card.append(title,note,nav);fragment.append(card);
      }
      if(!rows.length){const empty=document.createElement('p');empty.className='empty';empty.textContent='还没有 3D 生成记录。点击上方对应 VR 记录的“生成 3D”即可开始。';fragment.append(empty);}
      root.replaceChildren(fragment);
    }catch(e){root.textContent=e.message;}finally{refreshing=false;}
  }
  refresh();setInterval(refresh,5000);window.addEventListener('scene3d-records-changed',refresh);
})();
