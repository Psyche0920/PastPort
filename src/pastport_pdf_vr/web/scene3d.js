(()=>{
  const displayTitle=value=>String(value||'').replace(/\s*·\s*已有匹配成品(?:[（(].*[）)])?\s*$/u,'');
  const $=id=>document.getElementById(id),jobId=new URLSearchParams(location.search).get('job_id');
  let context=null,resumeURL=null,ready=false;
  async function request(url,options){const r=await fetch(url,options),d=await r.json();if(!r.ok)throw Error(d.detail||'操作未完成，已有记录保留。');return d;}
  function display(d){if(d.url){resumeURL=null;$('submit').hidden=true;const a=document.createElement('a');a.href=d.url;a.textContent='查看 3D 输出并校准';$('status').replaceChildren(a);}else{resumeURL=d.resume;$('status').textContent='正在生成。可以返回工作台；下次查询会继续原任务，不重复生成。';$('submit').textContent='查询生成进度';}window.dispatchEvent(new Event('scene3d-records-changed'));}
  $('generate-3d').onsubmit=async event=>{
    event.preventDefault();if(!ready)return;$('submit').disabled=true;
    try{
      if($('api-key').value){const key=$('api-key').value;$('api-key').value='';await request('/api/scene3d-key',{method:'POST',headers:{'X-PastPort-Edit':'1','Content-Type':'application/json'},body:JSON.stringify({key})});$('key-state').textContent='密钥已配置，不回显；仅供本次会话使用。';}
      if(!(await request('/api/scene3d-key')).configured)throw Error('请先输入 Marble API Key。尚未提交生成。');
      if(resumeURL){display(await request(resumeURL,{method:'POST',headers:{'X-PastPort-Edit':'1'}}));return;}
      const form=new FormData();form.append('job_id',jobId);form.append('scene_id',context.scene_id);form.append('model','marble-1.1');form.append('credit_budget','1500');form.append('authorize','yes');
      $('status').textContent='正在提交一次生成，请勿重复点击…';
      display(await request('/api/scene3d-generate',{method:'POST',headers:{'X-PastPort-Edit':'1'},body:form}));
    }catch(e){$('status').textContent=e.message;window.dispatchEvent(new Event('scene3d-records-changed'));}
    finally{$('api-key').value='';$('submit').disabled=false;}
  };
  $('import-3d').onsubmit=async event=>{event.preventDefault();if(!ready)return;$('import-submit').disabled=true;try{const file=$('existing-world').files[0];if(!file)throw Error('请选择已有 Marble 导出记录。');const form=new FormData();form.append('job_id',jobId);form.append('scene_id',context.scene_id);form.append('world',file);$('import-status').textContent='正在导入已有资产…';const d=await request('/api/scene3d-attach',{method:'POST',headers:{'X-PastPort-Edit':'1'},body:form});const a=document.createElement('a');a.href=d.url;a.textContent='查看 3D 输出并校准';$('import-status').replaceChildren(a);window.dispatchEvent(new Event('scene3d-records-changed'));}catch(e){$('import-status').textContent=e.message;}finally{$('import-submit').disabled=false;}};
  (async()=>{if(!jobId)throw Error('请从工作台某一条 VR 记录点击“生成 3D”。');context=await request(`/api/scene3d-context/${encodeURIComponent(jobId)}`);$('source-title').textContent=displayTitle(context.title);const views=await request(`/api/scene3d-sources/${encodeURIComponent(jobId)}`);const select=$('source-view');views.forEach((id,i)=>{const option=document.createElement('option');option.value=id;option.textContent=`点位 ${i+1}`;option.selected=id===context.scene_id;select.append(option);});select.disabled=false;select.onchange=()=>{context.scene_id=select.value;};const state=await request('/api/scene3d-key');if(state.configured){$('api-key').placeholder='本次会话已配置；可留空';$('key-state').textContent='密钥已配置，不回显；无需重复填写。';}ready=true;$('submit').disabled=false;})().catch(e=>{$('source-title').textContent='未选择 VR 记录';$('status').textContent=e.message;});
})();
