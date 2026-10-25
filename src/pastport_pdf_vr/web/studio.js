'use strict';
const byId = id => document.getElementById(id);
let documentFile = null, tourFiles = [], sending = false;
const statusLabels = {running:'正在生成',completed:'生成完成',completed_with_gaps:'完成 · 有缺口',failed:'未完成',recovery_required:'需核对中断记录'};
const stageLabels = {reuse_reference:'输入未变，保留已有编辑',environment_prepare:'读取新 PDF 与 VR',matched_pdf:'读取匹配与来源',fresh_localization:'重新定位与覆盖图复核',structural_review:'整体与部件关系审核',reference_publish:'装配同款后台与 VR'};
async function api(url, options) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '输入校验失败，请检查文件与设置。');
  return data;
}
function showSelections() {
  byId('document-selection').textContent = documentFile ? `${documentFile.name} · ${(documentFile.size/1048576).toFixed(1)} MiB` : '尚未选择 · 默认上限 64 MiB';
  byId('tour-selection').textContent = tourFiles.length ? `${tourFiles.length} 个文件 · ${(tourFiles.reduce((sum,f)=>sum+f.file.size,0)/1048576).toFixed(1)} MiB` : '尚未选择 · HTML / 文件夹 / ZIP';
}
byId('document').onchange = event => {documentFile=event.target.files[0] || null; showSelections();};
for (const id of ['tour','tour-folder']) byId(id).onchange = event => {
  tourFiles = Array.from(event.target.files).map(file=>({file,path:file.webkitRelativePath || file.name})); showSelections();
};
// Traverse dropped directories without discarding asset-relative paths.
async function readEntry(entry, prefix='') {
  if (entry.isFile) return await new Promise((resolve,reject)=>entry.file(file=>resolve([{file,path:prefix+file.name}]),reject));
  const reader=entry.createReader(); let entries=[], batch;
  do {batch=await new Promise((resolve,reject)=>reader.readEntries(resolve,reject)); entries.push(...batch); if(entries.length>1000) throw new Error('文件数量过多，请打包为 ZIP。');} while(batch.length);
  const nested=await Promise.all(entries.map(child=>readEntry(child,prefix+entry.name+'/')));
  return nested.flat();
}
for (const kind of ['document','tour']) {
  const drop=byId(kind+'-drop');
  drop.addEventListener('dragover',event=>{event.preventDefault();drop.classList.add('over');});
  drop.addEventListener('dragleave',()=>drop.classList.remove('over'));
  drop.addEventListener('drop',async event=>{
    event.preventDefault(); drop.classList.remove('over');
    try {
      if (kind==='document') {
        if(event.dataTransfer.files.length!==1) throw new Error('请放入一份 PDF 文档。');
        documentFile=event.dataTransfer.files[0];
      } else {
        const entries=Array.from(event.dataTransfer.items).map(item=>item.webkitGetAsEntry?.()).filter(Boolean);
        const uploaded=entries.length ? (await Promise.all(entries.map(entry=>readEntry(entry)))).flat() : Array.from(event.dataTransfer.files).map(file=>({file,path:file.name}));
        tourFiles=uploaded;
      }
      showSelections();
    } catch(error) {byId('form-status').textContent=error.message;}
  });
}
function gapLabel(value) {
 const [kind,number]=value.split(':');
 const labels={matched_entry_omitted:`PDF 条目 ${number} 未完整读取`,
 pdf_inspection_budget_exhausted:'PDF 读取达到本次上限，后续条目尚未完成',
 localization_budget_exhausted:'部分视点的定位达到本次上限，未补造热点',
 location_audit_budget_exhausted:'部分点位未完成复核，未挂载',
 unlocated:`物件 ${number}：某视点未确认可见点位，未挂载`,
 structural_part_excluded:`物件 ${number}：整体与部件关系不成立或尚未确认，已排除热点`,
 no_visible_anchor:`物件 ${number}：没有已核实的可见点位`};
 return labels[kind]||value;
}
async function refresh() {
  const jobs=await api('/api/jobs');
  const current=byId('project').value;
  const select=byId('project'); select.replaceChildren(new Option('新建项目',''));
  const projects=new Set();
  for(const job of jobs) if(!projects.has(job.project_id)) {projects.add(job.project_id);if(['completed','completed_with_gaps'].includes(job.status)) select.add(new Option(job.title+' · 保留已有人工修改',job.project_id));}
  select.value=current;
  const container=byId('jobs'); container.replaceChildren();
  for (const job of jobs) {
    const card=document.createElement('article');card.className='job';
    const title=document.createElement('h3');title.textContent=job.title;
    const badge=document.createElement('span');badge.className='badge';badge.textContent=statusLabels[job.status];title.append(badge);card.append(title);
    const note=document.createElement('p');note.textContent=job.message || '已提交，正在读取资料。可以保持此页查看进度。';card.append(note);
    const phases=document.createElement('div');phases.className='stages';
    for(const item of job.stages) {const [name,status]=item.split(':');const label=document.createElement('span');label.className='stage '+status;label.textContent=(stageLabels[name]||name)+(status==='completed'?' ✓':status==='running'?' …':' · 需核对');phases.append(label);}card.append(phases);
    if(job.gaps?.length) {
      const details=document.createElement('details'), summary=document.createElement('summary');
      summary.textContent=`查看生成缺口（${job.gaps.length}）`;details.append(summary);
      for(const gap of job.gaps) {const p=document.createElement('p');p.textContent=gapLabel(gap);details.append(p);}card.append(details);
    }
    if(['completed','completed_with_gaps'].includes(job.status)) {
      const nav=document.createElement('nav');
      for(const [label,path] of [['打开 VR 展示','vr/'],['打开审核工作台','']]) {const link=document.createElement('a');link.href=`/projects/${job.project_id}/runs/${job.job_id}/${path}`;link.textContent=label;nav.append(link);}card.append(nav);
    }
    container.append(card);
  }
  if(!jobs.length) {const p=document.createElement('p');p.className='empty';p.textContent='还没有生成记录。上传第一组资料开始。';container.append(p);}
  byId('generate').disabled=sending||jobs.some(job=>job.status==='running');
}
byId('build-form').onsubmit=async event=>{
  event.preventDefault(); if(sending) return;
  try {
    if(!documentFile || !documentFile.name.toLowerCase().endsWith('.pdf')) throw new Error('请选择匹配 PDF。');
    if(!tourFiles.length) throw new Error('请选择完整的 360° 导览。');
    if(documentFile.size>(byId('large-pdf').checked?512:64)*1048576) throw new Error('PDF 超过大小限制；大文件请启用“大 PDF”选项。');
    if(tourFiles.length>100||tourFiles.reduce((sum,f)=>sum+f.file.size,0)>200*1048576) throw new Error('导览超过上传数量或大小限制，请精简并打包为 ZIP。');
    const options={workflow:'environment_build',title:byId('project-title').value.trim(),project_id:byId('project').value||null,large_pdf:byId('large-pdf').checked,max_calls:Number(byId('max-calls').value),max_recorded_tokens:Number(byId('max-tokens').value),authorize_model:byId('authorize').checked};
    const form=new FormData();form.append('options',JSON.stringify(options));form.append('document',documentFile);
    for(const item of tourFiles) form.append('tour',item.file,item.path);
    sending=true;byId('generate').disabled=true;byId('form-status').textContent='正在上传文件，请勿关闭页面…';
    await api('/api/jobs',{method:'POST',headers:{'X-PastPort-Edit':'1'},body:form});
    byId('form-status').textContent='文件已接收。生成进度见下方，完成后可直接打开结果。';
    await refresh();
  } catch(error) {byId('form-status').textContent=error.message;}
  finally {sending=false;await refresh().catch(()=>{});}
};
(async()=>{
  const capabilities=await api('/api/capabilities');
  for(const item of capabilities) {const row=document.createElement('div');row.className='capability';const title=document.createElement('strong');title.textContent=item.label+' · '+({supported:'已支持',planned:'待接入',conversion_required:'需转换'}[item.status]);const detail=document.createElement('small');detail.textContent=item.detail;row.append(title,detail);byId('capabilities').append(row);}
  await refresh();
})().catch(error=>byId('form-status').textContent=error.message);
setInterval(()=>refresh().catch(()=>byId('form-status').textContent='暂时无法连接本地服务，请检查服务是否仍在运行。'),2500);
