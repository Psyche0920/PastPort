const $=id=>document.getElementById(id);
async function request(url,options){const r=await fetch(url,options),d=await r.json();if(!r.ok)throw Error(d.detail||'请求未完成');return d;}
async function viewpoints(){const rows=await request(`/api/scene3d-sources/${$('job').value}`);$('scene').replaceChildren(...rows.map(id=>new Option(id,id)));}
$('job').onchange=()=>viewpoints().catch(e=>$('status').textContent=e.message);
let resumeURL=null;
function showResult(d){if(d.url){const a=document.createElement('a');a.href=d.url;a.textContent='打开 3D 场景并校准';$('status').replaceChildren(a);resumeURL=null;}else{resumeURL=d.resume;$('status').textContent='Marble 正在处理。点击“查询原任务”继续，不会重复生成。';$('submit').textContent='查询原任务';}}
$('mode').onchange=()=>{$('existing').hidden=$('mode').value!=='existing';$('generation').hidden=$('mode').value!=='generate';};
$('attach').onsubmit=async e=>{e.preventDefault();$('submit').disabled=true;try{if(resumeURL){showResult(await request(resumeURL,{method:'POST',headers:{'X-PastPort-Edit':'1'}}));return;}const f=new FormData();f.append('job_id',$('job').value);f.append('scene_id',$('scene').value);const generate=$('mode').value==='generate';if(generate){if(!$('authorize-marble').checked)throw Error('请明确授权本次生成；此操作会消耗Marble积分。');f.append('model',$('model').value);f.append('credit_budget',$('credit-budget').value);f.append('authorize','yes');}else{if(!$('world').files.length)throw Error('请选择已有 world.json');f.append('world',$('world').files[0]);}$('status').textContent='正在处理，请勿关闭本地工作台…';showResult(await request(generate?'/api/scene3d-generate':'/api/scene3d-attach',{method:'POST',headers:{'X-PastPort-Edit':'1'},body:f}));}catch(e){$('status').textContent=e.message;}finally{$('submit').disabled=false;}};

(async()=>{const jobs=(await request('/api/jobs')).filter(j=>['completed','completed_with_gaps'].includes(j.status));$('job').replaceChildren(...jobs.map(j=>new Option(j.title,j.job_id)));if(jobs.length)await viewpoints();else{$('status').textContent='先在原流程完成一次 PDF + 全景匹配。';$('submit').disabled=true;}})().catch(e=>$('status').textContent=e.message);

request("/api/scene3d-deliveries").then(rows=>{for(const row of rows){const p=document.createElement("p"),a=document.createElement("a");a.href=row.url;a.textContent="打开已保存的 3D 结果（待人工验收）";p.append(a);$("previous").append(p);}}).catch(e=>$("status").textContent=e.message);
