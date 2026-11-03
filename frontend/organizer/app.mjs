import {mountLocalization, setLanguage} from './i18n.mjs';
let compatibilityBusy=false;let defaultSourcesLoaded=false;let sourceCatalogLoaded=false;const compatibilityAttempts=new Set();
import {ReviewWorkbench,environmentActionState,restoredWorkflow} from './review.mjs';
const $ = id => document.getElementById(id);
let materialProjects = [], sources = [], polling = null, loadedProject = null, uploadBusy = false, adminSetup = false, environmentSource = null, storySource = null, environmentJob = null, storyJob = null;
const labels = {original_idml:'原始史料 IDML',historical_links:'IDML配套历史图片（Links ZIP，最多3GB）',scene_splat:'已有 3D 场景（SPZ）',scene_mesh:'同场景碰撞网格（PLY）',original_pdf:'原始史料 PDF',photos:'现场物件照片（可多选）',mapping_pdf:'映射 PDF',tour:'360° 导览 ZIP 或自包含 HTML',matched_vr:'已匹配 VR 完整项目包',mounted_3d:'已挂载 3D 完整项目包'};
const fields = {idml3d:['original_idml','historical_links','photos','scene_splat','scene_mesh'],raw3d:['original_pdf','photos','scene_splat','scene_mesh'],raw:['original_pdf','photos','tour'],mapping:['original_pdf','mapping_pdf','tour'],vr:['original_pdf','matched_vr'],'3d':['original_pdf','mounted_3d']};
const stageLabels = {'evidence.idml_mapping':'IDML史料与现场物件映射','environment.idml_mount':'IDML映射物件的3D定位',idml_source_import:'读取IDML与历史配图','evidence.photo_mapping':'照片与史料映射','environment.environment_build':'物件匹配与环境挂载','environment.scene3d':'准备3D场景',local_scene_import:'导入已有3D并渲染识别视图',story:'故事与任务',gameplay:'玩法准备',presentation:'呈现绑定',assembly:'组包检查',evidence:'照片与史料映射',matched_environment:'全景物件挂载',scene3d_1:'第一个3D视点',scene3d_2:'第二个3D视点',input_handoff:'环境与史料交接'};
const states = {queued:'等待执行',running:'正在制作',completed:'制作完成',failed:'制作停止',recovery_required:'需要先核对恢复摘要',awaiting_materials:'等待补充材料',awaiting_external:'等待3D服务返回',environment_ready:'环境已准备',story_ready:'故事已准备'};
function message(text){$('message').textContent = text;}
async function api(path, options={}){
  const response = await fetch('/organizer/api/'+path, {...options, headers:{'X-PastPort-Edit':'1',...(options.body && typeof options.body==='string'?{'Content-Type':'application/json'}:{}),...options.headers}});
  if(response.status===401){$('workspace').hidden=true;$('login').hidden=false;}
  if(!response.ok){let data;try{data=await response.json();}catch{data={message:'服务未返回有效结果。'};}throw new Error(data.message||data.detail||'请求未完成。');}
  return response.status===204?null:response.json();
}
function page(name){for(const id of ['make','review','jobs']) $(id).hidden=id!==name;document.querySelectorAll('[data-page]').forEach(b=>{if(b.dataset.page===name)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current');});}
function text(tag,content){const el=document.createElement(tag);el.textContent=content;return el;}
async function refreshSources(active=environmentSource){
  const storage=await api('storage');$('cache-location').textContent=storage.cache_directory;
  const merge=incoming=>{const replaced=new Set(incoming.map(s=>s.source_id));sources=[...sources.filter(s=>!replaced.has(s.source_id)),...incoming];};
  if(!sourceCatalogLoaded){merge(await api('sources?metadata_only=true'));sourceCatalogLoaded=true;}
  if(!defaultSourcesLoaded||!active){merge(await api('sources?default_only=true'));defaultSourcesLoaded=true;}
  if(active)merge(await api('sources?active_source_id='+encodeURIComponent(active)));
  defaultChoice();storyChoice();drawReviewProjects();
}

function resetStory(){$('consent').checked=false;storySource=null;storyJob=null;sessionStorage.removeItem('organizer-story-job');$('story-status').textContent='请准备故事。';storyChoice();}
function resetEnvironment(){environmentSource=null;environmentJob=null;sessionStorage.removeItem('organizer-environment-source');sessionStorage.removeItem('organizer-environment-job');$('environment-status').textContent='材料选择已改变，请重新准备环境。';resetStory();}
function drawFields(){loadedProject=null;const root=$('upload-fields');root.replaceChildren();for(const role of fields[$('entry').value]){const label=text('label',labels[role]);const input=document.createElement('input');input.type='file';input.dataset.role=role;if(role==='photos'){input.multiple=true;input.accept=['raw3d','idml3d'].includes($('entry').value)?'.jpg,.jpeg,.png,.webp,.zip':'.jpg,.jpeg,.png,.webp';}if(role==='original_idml')input.accept='.idml';if(role==='historical_links')input.accept='.zip';if(role==='scene_splat')input.accept='.spz';if(role==='scene_mesh')input.accept='.ply';if(role.endsWith('pdf'))input.accept='.pdf';if(role==='tour')input.accept='.zip,.html';input.addEventListener('change',resetEnvironment);label.append(input);root.append(label);}defaultChoice();}
function defaultChoice(){
  const box=$('use-default');const available=sources.find(s=>s.is_default&&s.ready&&s.complete_bundle);
  if($('entry').value==='idml3d')box.checked=false;
  box.disabled=$('entry').value==='idml3d'||(!available&&!box.checked);
  for(const input of document.querySelectorAll('#upload-fields input[type=file]'))input.disabled=box.checked;
  $('project').disabled=box.checked;$('upload').disabled=uploadBusy||(box.checked&&!available);
  $('upload').textContent=box.checked?'准备默认资料与环境':'保存材料并检查';
  $('upload-note').textContent=box.checked?'仅准备资料和已有环境，不调用模型或Marble，不生成故事，也不制作游戏。':['raw3d','idml3d'].includes($('entry').value)?'使用已有SPZ和PLY，仅本地导入取景；匹配需要模型，不调用Marble。':'使用上传材料，从所选阶段真实生成；需要3D时调用Marble，不暗中改用默认缓存。完整3D输入不重复生成3D。';
  $('default-detail').textContent=available?'勾选：复用已跑通的配套资料与环境，无需上传。故事在第二步单独选择。':'默认资料尚未通过检查，请上传自己的材料。';
}
function storyChoice(){
  const source=sources.find(s=>s.source_id===environmentSource);
  const box=$('use-saved-story');box.disabled=!source?.reuse_ready;if(box.disabled)box.checked=false;
  $('fresh-options').hidden=box.checked;
  if(source?.ready&&source.review_ready&&!source.reuse_ready&&!source.reuse_checked&&!compatibilityBusy&&!compatibilityAttempts.has(source.source_id)){checkStoryCompatibility(source.source_id);}
  $('story-detail').textContent=compatibilityBusy?'正在检查旧故事的来源、任务和空间兼容性；不调用模型。':source?.reuse_issues?.length?source.reuse_issues.join('；'):!source?'先准备上一步的环境。':source.reuse_ready?'勾选：复用此环境的已有故事，零模型调用。不勾：生成新故事。':'这个环境尚无配套故事，请生成新故事；不能套用默认环境的故事。';
  const confirm=$('confirm-story-reuse');confirm.hidden=!source?.reuse_confirmation_sha256;confirm.disabled=compatibilityBusy||!source?.review_ready||!!storyJob;
  $('reuse-changes').hidden=!source?.reuse_confirmation_sha256;
  const changes=$('reuse-change-list');changes.replaceChildren();
  for(const change of source?.reuse_changes||[]){const row=text('section','任务 '+change.task_id+' · 物件 '+change.object_number);row.append(text('p','原介绍：'+(change.before||'（无）')),text('p','新介绍：'+(change.after||'（无）')));changes.append(row);}
  if(source?.reuse_confirmation_sha256)$('story-detail').textContent='介绍有改动，其他任务检查已通过。请核对后确认是否沿用旧故事。';
  else if(source?.reuse_ready)$('story-detail').textContent='可以沿用旧故事；勾选后不调用模型。';
  else if(source?.reuse_issues?.length)$('story-detail').textContent='任务条件已变化，请先处理：'+source.reuse_issues.join('；');
  $('prepare-story').textContent=box.checked?'准备已有故事与任务':'生成新故事与任务';
  $('prepare-story').disabled=!source?.ready||!source?.review_ready||!!storyJob||compatibilityBusy;$('review-current').disabled=!source?.ready;$('review-status').textContent=!source?'请先准备资料与环境。':source.review_ready?'已接入这版环境的审核资料，可查看或修改后进入故事。':'审核修改正在同步，请稍后再准备故事。';
  $('start').disabled=!storySource||!source?.ready||!source?.review_ready;
  $('game-status').textContent=storySource?(source?.ready&&source?.review_ready?'环境和故事已准备好，可以开始制作。':'正在核对已保存的资料与审核状态。'):'请先准备资料、审核与故事。';
}
$('use-default').addEventListener('change',()=>{resetEnvironment();defaultChoice();});
$('entry').addEventListener('change',()=>{resetEnvironment();drawFields();});
$('project').addEventListener('input',resetEnvironment);
$('use-saved-story').addEventListener('change',resetStory);
for(const id of ['duration','brief'])$(id).addEventListener('input',resetStory);
drawFields();
document.querySelectorAll('[data-page]').forEach(b=>b.addEventListener('click',()=>{page(b.dataset.page);if(b.dataset.page==='review'&&environmentSource){$('material-project').value='source:'+environmentSource;workbench.load(environmentSource).catch(e=>message(e.message));}}));
async function submitRegistered(source,mode,stopAfter){
  const body={source_id:source,mode,stop_after:stopAfter,authorize_model:mode==='regenerate',target_minutes:Number($('duration').value)};
  if(mode==='regenerate'&&$('brief').value.trim())body.brief=$('brief').value.trim();
  const serialized=JSON.stringify(body);
  const job=await api('jobs',{method:'POST',headers:{'Idempotency-Key':crypto.randomUUID()},body:serialized});return job;
}
$('prepare-story').addEventListener('click',async()=>{
  $('prepare-story').disabled=true;
  try{if(!environmentSource)throw new Error('请先准备环境。');const reuse=$('use-saved-story').checked;if(!reuse&&!$('consent').checked)throw new Error('请确认本次新故事生成调用。');
    const job=await submitRegistered(environmentSource,reuse?'reuse':'regenerate','story');storyJob=job.job_id;sessionStorage.setItem('organizer-story-job',storyJob);storySource=null;$('consent').checked=false;$('story-status').textContent='正在准备故事；尚未开始制作游戏。';await refreshJobs();
  }catch(e){message(e.message);}finally{storyChoice();}
});
$('login-form').addEventListener('submit',async event=>{event.preventDefault();try{const body=adminSetup?{password:$('password').value,password_confirmation:$('password-confirmation').value}:{username:$('username').value,password:$('password').value};await api(adminSetup?'admin-setup':'session',{method:'POST',body:JSON.stringify(body)});adminSetup=false;$('confirmation-field').hidden=true;$('password-confirmation').required=false;$('login-title').textContent='管理员登录';$('login-submit').textContent='登录';$('password').autocomplete='current-password';$('password').placeholder='输入管理员密码';$('password').value='';$('password-confirmation').value='';$('login').hidden=true;$('workspace').hidden=false;await restoreWorkspace();message('');}catch(e){message(e.message);}});
$('logout').addEventListener('click',async()=>{try{await api('session',{method:'DELETE'});clearInterval(polling);$('workspace').hidden=true;$('login').hidden=false;}catch(e){message(e.message);}});
$('start').addEventListener('click',async()=>{
  $('start').disabled=true;try{if(!storySource)throw new Error('请先准备环境和故事。');await submitRegistered(storySource,'reuse','game');page('jobs');await refreshJobs();message('开始玩法准备、呈现与组包；不再次生成环境或故事。');}catch(e){message(e.message);}finally{storyChoice();}
});
$('upload').addEventListener('click',async()=>{
  uploadBusy=true;defaultChoice();resetEnvironment();
  try{
    if($('use-default').checked){
      const selected=sources.find(s=>s.is_default&&s.ready&&s.complete_bundle);if(!selected)throw new Error('默认整套资料未就绪，不会改用其它缓存。');
      const job=await submitRegistered(selected.source_id,'reuse','environment');environmentJob=job.job_id;sessionStorage.setItem('organizer-environment-job',environmentJob);$('environment-status').textContent='正在核对默认资料与环境。';await refreshJobs();return;
    }
    const project=$('project').value.trim();if(!project)throw new Error('请填写项目编号。');if(project.length>160||!/^[a-zA-Z0-9][a-zA-Z0-9_.:-]*$/.test(project))throw new Error('项目编号不能含空格或中文，请使用英文字母、数字及 - _ . :，例如 3d-test。');
    const missing=[...document.querySelectorAll('#upload-fields input[type=file]')].filter(input=>!input.files.length&&!(input.dataset.role==='tour'&&$('entry').value==='raw'));if(missing.length)throw new Error('请补充上传：'+missing.map(input=>labels[input.dataset.role]).join('、'));
    await api('materials',{method:'POST',body:JSON.stringify({project_id:project,entry_level:$('entry').value})});
    for(const input of document.querySelectorAll('#upload-fields input[type=file]'))for(const file of input.files){message('正在保存：'+file.name);await api('materials/'+encodeURIComponent(project)+'/files?'+new URLSearchParams({role:input.dataset.role,filename:file.name}),{method:'POST',body:file,headers:{'Content-Type':'application/octet-stream'}});}
    loadedProject=project;await refreshProjects();await reviewProject();page('review');message('材料已保存，请核对后准备环境；不会直接生成故事或游戏。');
  }catch(e){message(e.message);}finally{uploadBusy=false;defaultChoice();}
});
function drawReviewProjects(){
  $('review-project-selector').hidden=false;$('load-project').hidden=false;
  const select=$('material-project');const previous=select.value;select.replaceChildren();const projects=new Map();
  for(const source of sources)if(!projects.has(source.project_id)||source.source_id===environmentSource||source.is_default)projects.set(source.project_id,source);
  if(environmentSource){const current=sources.find(s=>s.source_id===environmentSource);if(current)projects.set(current.project_id,current);}
  for(const source of projects.values()){const option=text('option',source.project_id+' · 已准备环境，可审核');option.value='source:'+source.source_id;select.append(option);}
  for(const project of materialProjects)if(!projects.has(project.project_id)){const option=text('option',project.project_id+' · 上传材料待准备');option.value='upload:'+project.project_id;select.append(option);}
  if([...select.options].some(o=>o.value===previous))select.value=previous;else if(environmentSource)select.value='source:'+environmentSource;else if(loadedProject&&[...select.options].some(o=>o.value==='upload:'+loadedProject))select.value='upload:'+loadedProject;
}
async function refreshProjects(){materialProjects=await api('materials');drawReviewProjects();}
const workbench=new ReviewWorkbench($('review-content'),api,{
  isActive:()=>!!environmentSource&&workbench.data?.source_id===environmentSource,
  onMessage:message,
  onChange:async()=>{const current=sources.find(s=>s.source_id===environmentSource);if(current)current.review_ready=false;resetStory();},
  onApply:async(source,previous)=>{if(environmentSource===previous)await adoptEnvironmentSource(source);}
});
$('review-current').addEventListener('click',async()=>{if(!environmentSource)return;page('review');drawReviewProjects();$('material-project').value='source:'+environmentSource;await workbench.load(environmentSource);});
$('load-project').addEventListener('click',async()=>{const value=$('material-project').value;if(value.startsWith('source:'))await selectProjectSource(value.slice(7),'review');else if(value.startsWith('upload:')){loadedProject=value.slice(7);try{await reviewProject();}catch(e){message(e.message);}}});
function generationOptions(parent, needs3d, resume=false, evidenceDefault=8){
  const box=document.createElement('fieldset');box.append(text('legend','本次生成授权'));
  const model=document.createElement('input');model.type='checkbox';const ml=text('label',' 允许本次生成调用 SOL 6.1 Medium；失败不自动重试');ml.prepend(model);box.append(ml);
  const evidence=document.createElement('input');evidence.type='number';evidence.min='1';evidence.max='100';evidence.value=String(evidenceDefault);const el=text('label','证据模型调用上限（1–100，照片、PDF及史料核验共用）');el.append(evidence);box.append(el);const matching=document.createElement('input');matching.type='number';matching.min='1';matching.max='40';matching.value='20';const gl=text('label','环境匹配模型调用上限（1–40）');gl.append(matching);box.append(gl);
  const marble=document.createElement('input');marble.type='checkbox';
  const budget=document.createElement('input');budget.type='number';budget.min='1500';budget.max='100000';budget.value='1500';
  if(needs3d){const label=text('label',' 允许生成两个3D视点（Marble 1.1）');label.prepend(marble);const bl=text('label','每个视点授权积分预算（非总计，实际计费以服务回执为准）');bl.append(budget);box.append(label,bl);}
  if(resume)ml.hidden=true;
  parent.append(box);return ()=>{if(!resume&&(!Number.isInteger(Number(evidence.value))||Number(evidence.value)<1||Number(evidence.value)>100))throw new Error('证据模型调用上限须为1至100的整数。');if(!resume&&(!Number.isInteger(Number(matching.value))||Number(matching.value)<1||Number(matching.value)>40))throw new Error('环境匹配模型调用上限须为1至40的整数。');if(!resume&&!model.checked)throw new Error('请先确认本次生成调用。');if(needs3d&&!marble.checked)throw new Error('此起点需要生成3D，请确认Marble调用与预算。');return {max_evidence_calls:Number(evidence.value),max_environment_calls:Number(matching.value),authorize_model:true,authorize_marble:needs3d&&marble.checked,marble_credit_budget:needs3d&&marble.checked?Number(budget.value):0};};
}
async function reviewProject(){
  const {materials,plan}=await api('materials/'+encodeURIComponent(loadedProject));const root=$('review-content');root.replaceChildren(text('h2','项目：'+materials.project_id));
  const list=document.createElement('ul');for(const f of materials.files)list.append(text('li',labels[f.role]+' · '+f.filename+' · '+(f.size_bytes/1024/1024).toFixed(1)+' MB'));
  root.append(list,text('p','审核关注：'+plan.review_focus.join('、')),text('p','复用：'+(plan.reused.map(r=>labels[r]||r).join('、')||'无')),text('p','将执行：'+plan.stages.map(s=>stageLabels[s]||s).join(' → ')),text('p',plan.missing_roles.length?'待补材料：'+plan.missing_roles.map(r=>labels[r]).join('、'):'必需材料已上传；开始后会校验原生格式、来源和版本。'),text('p',plan.message));
  const needs3d=!['3d','raw3d','idml3d'].includes(materials.entry_level);
  const canRunFull3D=['raw3d','idml3d'].includes(materials.entry_level);
  const options=generationOptions(root,needs3d,false,canRunFull3D?100:8);
  const duration=document.createElement('input');duration.type='number';duration.min='3';duration.max='60';duration.value='10';const dl=text('label','体验目标时长（分钟）');dl.append(duration);root.append(dl);
  const b=text('button','准备资料与环境');b.dataset.environmentProject=materials.project_id;b.dataset.materialsBlocked=String(!plan.generation_connected||!!plan.missing_roles.length);b.disabled=true;let submitted=false;
  b.addEventListener('click',async()=>{if(b.disabled)return;submitted=false;b.dataset.submitting='true';b.disabled=true;b.textContent='提交中…';try{const body={...options(),stop_after:'environment',target_minutes:Number(duration.value)};const serialized=JSON.stringify(body);const job=await api('materials/'+encodeURIComponent(materials.project_id)+'/jobs',{method:'POST',headers:{'Idempotency-Key':crypto.randomUUID()},body:serialized});submitted=true;b.textContent='准备中…';resetEnvironment();environmentJob=job.job_id;sessionStorage.setItem('organizer-environment-job',environmentJob);page('make');await refreshJobs();message('环境准备已提交；完成后停在第二步，不会自动调用Story或组包。');}catch(e){message(e.message);}finally{delete b.dataset.submitting;if(!submitted){b.disabled=b.dataset.materialsBlocked==='true';b.textContent='准备资料与环境';}}});root.append(b);
  if(canRunFull3D){
    const runAll=text('button','运行完整 3D 流程');
    runAll.dataset.environmentProject=materials.project_id;
    runAll.dataset.materialsBlocked=b.dataset.materialsBlocked;
    runAll.dataset.actionLabel=runAll.textContent;
    runAll.disabled=true;
    runAll.addEventListener('click',async()=>{
      if(runAll.disabled)return;
      runAll.disabled=true;
      runAll.dataset.submitting='true';
      try{
        const body={...options(),stop_after:'game',target_minutes:Number(duration.value)};
        await api('materials/'+encodeURIComponent(materials.project_id)+'/jobs',{
          method:'POST',headers:{'Idempotency-Key':crypto.randomUUID()},body:JSON.stringify(body),
        });
        page('jobs');
      }catch(error){message(error.message);}
      finally{
        delete runAll.dataset.submitting;
        await refreshJobs().catch(error=>message(error.message));
      }
    });
    root.append(runAll);
  }
  if(materials.entry_level==='raw'&&!materials.files.some(f=>f.role==='tour'))root.append(text('p','尚无360导览：先生成映射文档并保存，然后等待补充导览，不会声称游戏已完成。'));
  const activeJobs=await api('jobs');updateEnvironmentButtons(activeJobs);const waiting=activeJobs.find(j=>j.project_id===materials.project_id&&j.status==='awaiting_materials');
  if(waiting){const input=document.createElement('input');input.type='file';input.accept='.zip,.html';const add=text('button','补充360导览');add.addEventListener('click',async()=>{try{const f=input.files[0];if(!f)throw new Error('请选择360导览。');await api('materials/'+encodeURIComponent(materials.project_id)+'/files?'+new URLSearchParams({role:'tour',filename:f.name}),{method:'POST',body:f,headers:{'Content-Type':'application/octet-stream'}});await reviewProject();page('jobs');await refreshJobs();message('导览已保存；请先查看恢复摘要，再继续原制作任务。');}catch(e){message(e.message);}});root.append(input,add);b.disabled=true;}
}
function updateEnvironmentButtons(jobs){for(const button of document.querySelectorAll('[data-environment-project]')){if(button.dataset.submitting==='true')continue;const state=environmentActionState(jobs,button.dataset.environmentProject);button.disabled=state.disabled||button.dataset.materialsBlocked==='true';button.textContent=state.disabled?state.label:(button.dataset.actionLabel||state.label);}}
async function refreshJobs(){
  const jobs=await api('jobs');updateEnvironmentButtons(jobs);const root=$('job-list');root.replaceChildren();
  environmentSource=environmentSource||sessionStorage.getItem('organizer-environment-source');
  environmentJob=environmentJob||sessionStorage.getItem('organizer-environment-job');storyJob=storyJob||sessionStorage.getItem('organizer-story-job');
  const env=jobs.find(j=>j.job_id===environmentJob);const story=jobs.find(j=>j.job_id===storyJob);
  let needsSources=false;
  if(env?.status==='environment_ready'&&env.prepared_source_id){environmentSource=env.prepared_source_id;sessionStorage.setItem('organizer-environment-source',environmentSource);await api('workspace',{method:'POST',body:JSON.stringify({source_id:environmentSource})});environmentJob=null;sessionStorage.removeItem('organizer-environment-job');$('environment-status').textContent=env.message;needsSources=!sources.some(s=>s.source_id===environmentSource&&s.ready);}
  else if(env)$('environment-status').textContent=env.message;
  if(story?.status==='story_ready'&&story.prepared_source_id){if(story.source_id===environmentSource){environmentSource=story.prepared_source_id;sessionStorage.setItem('organizer-environment-source',environmentSource);environmentJob=null;sessionStorage.removeItem('organizer-environment-job');needsSources=!sources.some(s=>s.source_id===environmentSource&&s.ready);}storySource=story.prepared_source_id;await api('workspace',{method:'POST',body:JSON.stringify({source_id:storySource})});$('story-status').textContent=story.message;storyJob=null;sessionStorage.removeItem('organizer-story-job');}
  else if(story){$('story-status').textContent=story.message;if(!['queued','running','awaiting_external'].includes(story.status)){storyJob=null;sessionStorage.removeItem('organizer-story-job');}}
  if(needsSources)await refreshSources();storyChoice();drawReviewProjects();
  for(const job of jobs){const article=document.createElement('article');article.dataset.jobId=job.job_id;article.append(text('h2',job.project_id+' · '+(job.mode==='reuse'?'缓存复用':'重新生成')+' · '+states[job.status]),text('p',job.message),text('p','本次新增模型调用：'+(job.new_model_calls===null?'等待真实回执确认':job.new_model_calls)),text('p','已保存步骤：'+(job.completed_stages.map(s=>stageLabels[s]||s).join(' → ')||'暂无阶段完成回执')));
    if(job.prepared_source_id){
      const continueProject=text('button','继续此项目');continueProject.dataset.selectSource=job.prepared_source_id;
      continueProject.addEventListener('click',async()=>{continueProject.disabled=true;try{await selectProjectSource(job.prepared_source_id,'make');}catch(error){message(error.message);}finally{continueProject.disabled=false;}});
      const reviewProject=text('button','查看资料与审核');reviewProject.addEventListener('click',async()=>{try{await selectProjectSource(job.prepared_source_id,'review');}catch(error){message(error.message);}});
      article.append(continueProject,reviewProject);
    }
    if(job.cache_directory){const label=text('p','本次制作缓存（后台所在电脑）：');const path=text('code',job.cache_directory);path.className='storage-path';article.append(label,path);}
    if(job.game_directory){const label=text('p','游戏包保存位置：');const path=text('code',job.game_directory);path.className='storage-path';article.append(label,path);}
    if(job.issues?.length){const issues=document.createElement('ul');for(const issue of job.issues)issues.append(text('li',issue));article.append(text('p','校验未通过：'),issues);}
    if(job.result_ready){const link=text('a','打开独立玩家预览 ↗');link.href='/organizer/api/jobs/'+job.job_id+'/open';link.target='_blank';link.rel='noopener';article.append(link);}
    if(job.mounted_preview_ready){
      const link=text('a','打开 3D 审核预览 ↗');
      link.href='/organizer/api/jobs/'+job.job_id+'/open-mounted';
      link.target='_blank';link.rel='noopener';article.append(link);
    }
    if(['failed','recovery_required','awaiting_materials'].includes(job.status)){
      article.append(text('h3','恢复摘要'),text('p','已保存：'+(job.completed_stages.map(s=>stageLabels[s]||s).join('、')||'输入快照')+'。剩余步骤将在核对现有回执后继续，不会自动重发未知用量的模型调用。'));
      if(job.status==='awaiting_materials'){const link=text('a','下载已生成的映射 PDF');link.href='/organizer/api/jobs/'+job.job_id+'/mapping.pdf';article.append(link);const view=text('button','查看项目并补充360导览');view.addEventListener('click',async()=>{loadedProject=job.project_id;page('review');try{await reviewProject();}catch(e){message(e.message);}});article.append(view);}
      const options=job.input_kind==='uploads'?generationOptions(article,!['raw3d','idml3d','3d'].includes(job.entry_level),true):()=>({});
      const b=text('button','已查看摘要，确认继续');b.addEventListener('click',async()=>{b.disabled=true;try{const extra=options();delete extra.authorize_model;delete extra.max_evidence_calls;delete extra.max_environment_calls;await api('jobs/'+job.job_id+'/continue',{method:'POST',body:JSON.stringify({confirm_continue:true,...extra})});await refreshJobs();await refreshSources();}catch(e){message(e.message);}finally{b.disabled=false;}});article.append(b);
    }
    root.append(article);
  }
  if(!jobs.length)root.append(text('p','还没有制作记录。'));
  clearInterval(polling);if(jobs.some(j=>['queued','running','awaiting_external'].includes(j.status)))polling=setInterval(()=>refreshJobs().catch(e=>{clearInterval(polling);message(e.message);}),2500);
}
$('refresh').addEventListener('click',()=>refreshJobs().catch(e=>message(e.message)));
$('import-delivery').addEventListener('click', async () => {
  const input = $('delivery-file');
  const button = $('import-delivery');
  const file = input.files[0];
  if (!file) { message('请先选择交付包。'); return; }
  button.disabled = true;
  try {
    const query = new URLSearchParams({filename:file.name});
    const job = await api('jobs/import-delivery?'+query, {
      method:'POST', body:file, headers:{'Content-Type':'application/octet-stream'},
    });
    input.value = '';
    await refreshJobs();
    message('已导入 '+job.project_id+'。');
  } catch (error) {
    message(error.message);
  } finally {
    button.disabled = false;
  }
});
// Recover the server session after reload; never persist the raw bearer token in browser storage.
api('access').then(state=>{adminSetup=state.setup_required;$('username').value='admin';$('login-title').textContent=adminSetup?'首次设置管理员密码':'管理员登录';$('confirmation-field').hidden=!adminSetup;$('password-confirmation').required=adminSetup;$('password').autocomplete=adminSetup?'new-password':'current-password';$('password').placeholder=adminSetup?'首次设置至少12个字符':'输入管理员密码';$('login-submit').textContent=adminSetup?'保存密码并进入':'登录';$('login-submit').disabled=false;}).catch(e=>message(e.message));
api('jobs').then(async()=>{$('login').hidden=true;$('workspace').hidden=false;await restoreWorkspace();}).catch(error=>message(error.message));

async function restoreWorkspace(){
  const jobs=await api('jobs');
  const selected=await api('workspace');
  const restored=restoredWorkflow(jobs,selected,{environmentJob:sessionStorage.getItem('organizer-environment-job'),storyJob:sessionStorage.getItem('organizer-story-job')});
  ({environmentSource,storySource,environmentJob,storyJob}=restored);
  for(const [key,value] of [['organizer-environment-source',environmentSource],['organizer-environment-job',environmentJob],['organizer-story-job',storyJob]]){if(value)sessionStorage.setItem(key,value);else sessionStorage.removeItem(key);}
  if(restored.projectId){loadedProject=restored.projectId;$('project').value=restored.projectId;$('use-default').checked=false;$('environment-status').textContent='已恢复项目：'+restored.projectId+'；按保存的阶段继续。';}
  await refreshJobs();await refreshSources(environmentSource);await refreshProjects();
}

async function selectProjectSource(source,pageName){
  if(workbench.dirty){message('审核后台有未保存修改，请先保存，或点“放弃未保存修改”。');return;}
  const selected=await api('workspace',{method:'POST',body:JSON.stringify({source_id:source})});
  resetStory();environmentSource=selected.source_id;storySource=selected.story_ready?selected.source_id:null;
  environmentJob=null;sessionStorage.removeItem('organizer-environment-job');sessionStorage.setItem('organizer-environment-source',environmentSource);
  loadedProject=selected.project_id;$('project').value=selected.project_id;$('use-default').checked=false;
  $('environment-status').textContent='当前项目：'+selected.project_id+'；沿用已准备的资料与环境。';
  if(storySource)$('story-status').textContent='已有故事已恢复，可以继续制作。';
  await refreshSources(environmentSource);drawReviewProjects();$('material-project').value='source:'+environmentSource;
  page(pageName);if(pageName==='review')await workbench.load(environmentSource);
  message('已接入项目 '+selected.project_id+'；没有重新生成或调用模型。');
}

async function adoptEnvironmentSource(source){await api('workspace',{method:'POST',body:JSON.stringify({source_id:source})});resetStory();environmentSource=source;environmentJob=null;sessionStorage.removeItem('organizer-environment-job');sessionStorage.setItem('organizer-environment-source',source);$('use-default').checked=false;$('environment-status').textContent='审核资料已同步到当前环境。';message('当前审核输入已更新，正在读取故事兼容结果；不调用模型。');await refreshSources(source);$('material-project').value='source:'+source;}

async function checkStoryCompatibility(source){compatibilityBusy=true;compatibilityAttempts.add(source);try{const result=await api('sources/'+encodeURIComponent(source)+'/story-compatibility',{method:'POST'});if(environmentSource===source)await adoptEnvironmentSource(result.source_id);}catch(error){message('旧故事兼容检查未完成：'+error.message);}finally{compatibilityBusy=false;storyChoice();}}

$('confirm-story-reuse').addEventListener('click',async()=>{const source=sources.find(s=>s.source_id===environmentSource);if(!source?.reuse_confirmation_sha256)return;compatibilityBusy=true;storyChoice();try{const result=await api('sources/'+encodeURIComponent(source.source_id)+'/confirm-story-reuse',{method:'POST',body:JSON.stringify({report_sha256:source.reuse_confirmation_sha256,confirm_unchanged_story:true})});if(environmentSource!==source.source_id){message('确认已保存；你已切换项目，当前选择保持不变。');return;}await adoptEnvironmentSource(result.source_id);message('已记录你的确认，可以勾选沿用旧故事；没有调用模型。');}catch(error){message(error.message);}finally{compatibilityBusy=false;storyChoice();}});

mountLocalization(document);
document.getElementById('interface-language').addEventListener('change', event => setLanguage(event.target.value));
