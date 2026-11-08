import {mountLocalization, setLanguage, getLanguage, deliveryTitle} from './i18n.mjs';
let compatibilityBusy=false;let defaultSourcesLoaded=false;let sourceCatalogLoaded=false;const compatibilityAttempts=new Set();
import {ReviewWorkbench,environmentActionState,restoredWorkflow} from './review.mjs';
const $ = id => document.getElementById(id);
let materialProjects = [], sources = [], polling = null, loadedProject = null, uploadBusy = false, adminSetup = false, environmentSource = null, storySource = null, environmentJob = null, storyJob = null;
const labels = {original_idml:'原始史料 IDML',historical_links:'IDML配套历史图片（Links ZIP，最多3GB）',scene_splat:'已有 3D 场景（SPZ）',scene_mesh:'同场景碰撞网格（PLY）',original_pdf:'原始史料 PDF',photos:'现场物件照片（可多选）',mapping_pdf:'映射 PDF',tour:'360° 导览 ZIP 或自包含 HTML',matched_vr:'已匹配 VR 完整项目包',mounted_3d:'已挂载 3D 完整项目包'};
const fields = {idmlscene3d:['original_idml','historical_links','scene_splat','scene_mesh'],catalog3d:['original_pdf','scene_splat','scene_mesh'],idml3d:['original_idml','historical_links','photos','scene_splat','scene_mesh'],raw3d:['original_pdf','photos','scene_splat','scene_mesh'],raw:['original_pdf','photos','tour'],mapping:['original_pdf','mapping_pdf','tour'],vr:['original_pdf','matched_vr'],'3d':['original_pdf','mounted_3d']};
const stageLabels = {scene_observations:'从3D场景提取物件观察图',pdf_analysis:'分析PDF资料',catalog_extraction:'读取展签与现场照片',catalog_localization:'按展签定位同一实物','evidence.idml_mapping':'IDML史料与现场物件映射','environment.idml_mount':'IDML映射物件的3D定位',idml_source_import:'读取IDML与历史配图','evidence.photo_mapping':'照片与史料映射','environment.environment_build':'物件匹配与环境挂载','environment.scene3d':'准备3D场景',local_scene_import:'导入已有3D并渲染识别视图',story:'故事与任务',gameplay:'玩法准备',presentation:'呈现绑定',assembly:'组包检查',evidence:'照片与史料映射',matched_environment:'全景物件挂载',scene3d_1:'第一个3D视点',scene3d_2:'第二个3D视点',input_handoff:'环境与史料交接'};
const states = {queued:'等待执行',running:'正在制作',completed:'制作完成',failed:'制作停止',recovery_required:'需要先核对恢复摘要',awaiting_materials:'等待补充材料',awaiting_external:'等待3D服务返回',environment_ready:'环境已准备',story_ready:'故事已准备'};
function message(text){$('message').textContent = text;}
async function api(path, options={}){
  const response = await fetch('/organizer/api/'+path, {...options, headers:{'X-PastPort-Edit':'1',...(options.body && typeof options.body==='string'?{'Content-Type':'application/json'}:{}),...options.headers}});
  if(response.status===401){$('workspace').hidden=true;$('login').hidden=false;}
  if(!response.ok){let data;try{data=await response.json();}catch{data={message:'服务未返回有效结果。'};}throw new Error(data.message||data.detail||'请求未完成。');}
  return response.status===204?null:response.json();
}
function page(name){for(const id of ['make','review','jobs']) $(id).hidden=id!==name;document.querySelectorAll('[data-page]').forEach(b=>{if(b.dataset.page===name)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current');});}
function deliveryPanel(name){for(const key of ['packages','publications','history'])$('delivery-'+key).hidden=key!==name;for(const button of document.querySelectorAll('[data-delivery-panel]')){if(button.dataset.deliveryPanel===name)button.setAttribute('aria-current','page');else button.removeAttribute('aria-current');}}
for(const button of document.querySelectorAll('[data-delivery-panel]'))button.addEventListener('click',()=>deliveryPanel(button.dataset.deliveryPanel));
function filterJobs(){const query=$('job-search').value.trim().toLocaleLowerCase();const cards=[...$('job-list').querySelectorAll('article[data-job-id]')];for(const card of cards)card.hidden=!!query&&!card.dataset.search.includes(query);$('job-empty').hidden=cards.some(card=>!card.hidden);}
$('job-search').addEventListener('input',filterJobs);
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
function drawFields(){loadedProject=null;const root=$('upload-fields');root.replaceChildren();for(const role of fields[$('entry').value]){const label=text('label',labels[role]+(role==='historical_links'&&$('entry').value==='idmlscene3d'?'（可选）':''));const input=document.createElement('input');input.type='file';input.dataset.role=role;if(role==='photos'){input.multiple=true;input.accept=['raw3d','idml3d'].includes($('entry').value)?'.jpg,.jpeg,.png,.webp,.zip':'.jpg,.jpeg,.png,.webp';}if(role==='original_idml')input.accept='.idml';if(role==='historical_links')input.accept='.zip';if(role==='scene_splat')input.accept='.spz';if(role==='scene_mesh')input.accept='.ply';if(role.endsWith('pdf'))input.accept='.pdf';if(role==='tour')input.accept='.zip,.html';input.addEventListener('change',resetEnvironment);label.append(input);root.append(label);}defaultChoice();}
function defaultChoice(){
  const box=$('use-default');const available=sources.find(s=>s.is_default&&s.ready&&s.complete_bundle);
  if(['idml3d','idmlscene3d','catalog3d'].includes($('entry').value))box.checked=false;
  box.disabled=['idml3d','idmlscene3d','catalog3d'].includes($('entry').value)||(!available&&!box.checked);
  for(const input of document.querySelectorAll('#upload-fields input[type=file]'))input.disabled=box.checked;
  $('project').disabled=box.checked;$('upload').disabled=uploadBusy||(box.checked&&!available);
  $('upload').textContent=box.checked?'准备默认资料与环境':'保存材料并检查';
  $('upload-note').textContent=box.checked?'仅准备资料和已有环境，不调用模型或Marble，不生成故事，也不制作游戏。':['raw3d','idml3d','idmlscene3d','catalog3d'].includes($('entry').value)?'使用已有SPZ和PLY，仅本地导入取景；匹配需要模型，不调用Marble。':'使用上传材料，从所选阶段真实生成；需要3D时调用Marble，不暗中改用默认缓存。完整3D输入不重复生成3D。';
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
  const model=document.createElement('input');model.type='checkbox';const ml=text('label',' 允许本次模型调用（资料与匹配：SOL 6.1 Medium；故事：SOL 6.1 High）；失败不自动重试');ml.prepend(model);box.append(ml);
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
  const needs3d=!['3d','raw3d','idml3d','idmlscene3d','catalog3d'].includes(materials.entry_level);
  const options=generationOptions(root,needs3d,false,materials.entry_level==='idmlscene3d'?16:['raw3d','idml3d'].includes(materials.entry_level)?100:8);
  const duration=document.createElement('input');duration.type='number';duration.min='3';duration.max='60';duration.value='10';const dl=text('label','体验目标时长（分钟）');dl.append(duration);root.append(dl);
  const b=text('button','准备资料与环境');b.dataset.environmentProject=materials.project_id;b.dataset.materialsBlocked=String(!plan.generation_connected||!!plan.missing_roles.length);b.disabled=true;let submitted=false;
  b.addEventListener('click',async()=>{if(b.disabled)return;submitted=false;b.dataset.submitting='true';b.disabled=true;b.textContent='提交中…';try{const body={...options(),stop_after:'environment',target_minutes:Number(duration.value)};const serialized=JSON.stringify(body);const job=await api('materials/'+encodeURIComponent(materials.project_id)+'/jobs',{method:'POST',headers:{'Idempotency-Key':crypto.randomUUID()},body:serialized});submitted=true;b.textContent='准备中…';resetEnvironment();environmentJob=job.job_id;sessionStorage.setItem('organizer-environment-job',environmentJob);page('make');await refreshJobs();message('环境准备已提交；完成后停在第二步，不会自动调用Story或组包。');}catch(e){message(e.message);}finally{delete b.dataset.submitting;if(!submitted){b.disabled=b.dataset.materialsBlocked==='true';b.textContent='准备资料与环境';}}});root.append(b);
  if(materials.entry_level==='raw'&&!materials.files.some(f=>f.role==='tour'))root.append(text('p','尚无360导览：先生成映射文档并保存，然后等待补充导览，不会声称游戏已完成。'));
  const activeJobs=await api('jobs');updateEnvironmentButtons(activeJobs);const waiting=activeJobs.find(j=>j.project_id===materials.project_id&&j.status==='awaiting_materials');
  if(waiting){const input=document.createElement('input');input.type='file';input.accept='.zip,.html';const add=text('button','补充360导览');add.addEventListener('click',async()=>{try{const f=input.files[0];if(!f)throw new Error('请选择360导览。');await api('materials/'+encodeURIComponent(materials.project_id)+'/files?'+new URLSearchParams({role:'tour',filename:f.name}),{method:'POST',body:f,headers:{'Content-Type':'application/octet-stream'}});await reviewProject();page('jobs');await refreshJobs();message('导览已保存；请先查看恢复摘要，再继续原制作任务。');}catch(e){message(e.message);}});root.append(input,add);b.disabled=true;}
}
function updateEnvironmentButtons(jobs){for(const button of document.querySelectorAll('[data-environment-project]')){if(button.dataset.submitting==='true')continue;const state=environmentActionState(jobs,button.dataset.environmentProject);button.disabled=state.disabled||button.dataset.materialsBlocked==='true';button.textContent=state.disabled?state.label:(button.dataset.actionLabel||state.label);}}
async function refreshJobs(){
  const [jobs,mapSites]=await Promise.all([api('jobs'),api('map-sites')]);updateEnvironmentButtons(jobs);const root=$('job-list');root.replaceChildren();
  environmentSource=environmentSource||sessionStorage.getItem('organizer-environment-source');
  environmentJob=environmentJob||sessionStorage.getItem('organizer-environment-job');storyJob=storyJob||sessionStorage.getItem('organizer-story-job');
  const env=jobs.find(j=>j.job_id===environmentJob);const story=jobs.find(j=>j.job_id===storyJob);
  let needsSources=false;
  if(env?.status==='environment_ready'&&env.prepared_source_id){environmentSource=env.prepared_source_id;sessionStorage.setItem('organizer-environment-source',environmentSource);await api('workspace',{method:'POST',body:JSON.stringify({source_id:environmentSource})});environmentJob=null;sessionStorage.removeItem('organizer-environment-job');$('environment-status').textContent=env.message;needsSources=!sources.some(s=>s.source_id===environmentSource&&s.ready);}
  else if(env)$('environment-status').textContent=env.message;
  if(story?.status==='story_ready'&&story.prepared_source_id){if(story.source_id===environmentSource){environmentSource=story.prepared_source_id;sessionStorage.setItem('organizer-environment-source',environmentSource);environmentJob=null;sessionStorage.removeItem('organizer-environment-job');needsSources=!sources.some(s=>s.source_id===environmentSource&&s.ready);}storySource=story.prepared_source_id;await api('workspace',{method:'POST',body:JSON.stringify({source_id:storySource})});$('story-status').textContent=story.message;storyJob=null;sessionStorage.removeItem('organizer-story-job');}
  else if(story){$('story-status').textContent=story.message;if(!['queued','running','awaiting_external'].includes(story.status)){storyJob=null;sessionStorage.removeItem('organizer-story-job');}}
  if(needsSources)await refreshSources();storyChoice();drawReviewProjects();
  const packaged=new Set(deliveryState.packages.flatMap(item=>item.versions.map(v=>v.job_id)));
  for(const job of jobs){if(packaged.has(job.job_id))continue;const article=document.createElement('article');article.dataset.jobId=job.job_id;article.dataset.search=(deliveryTitle(job.project_id,job.input_sha256)+' '+job.project_id+' '+job.status+' '+states[job.status]).toLocaleLowerCase();article.append(text('h2',deliveryTitle(job.project_id,job.input_sha256)+' · '+(job.mode==='reuse'?'缓存复用':'重新生成')+' · '+states[job.status]),text('p',job.message),text('p','本次新增模型调用：'+(job.new_model_calls===null?'等待真实回执确认':job.new_model_calls)),text('p','已保存步骤：'+(job.completed_stages.map(s=>stageLabels[s]||s).join(' → ')||'暂无阶段完成回执')));
    if(job.prepared_source_id){
      const continueProject=text('button','继续此项目');continueProject.dataset.selectSource=job.prepared_source_id;
      continueProject.addEventListener('click',async()=>{continueProject.disabled=true;try{await selectProjectSource(job.prepared_source_id,'make');}catch(error){message(error.message);}finally{continueProject.disabled=false;}});
      const reviewProject=text('button','查看资料与审核');reviewProject.addEventListener('click',async()=>{try{await selectProjectSource(job.prepared_source_id,'review');}catch(error){message(error.message);}});
      article.append(continueProject,reviewProject);
    }
    const technical=document.createElement('details');technical.className='technical-details';technical.append(text('summary','存储位置与技术信息'));
    if(job.cache_directory){const label=text('p','本次制作缓存（后台所在电脑）：');const path=text('code',job.cache_directory);path.className='storage-path';technical.append(label,path);}
    if(job.game_directory){const label=text('p','游戏包保存位置：');const path=text('code',job.game_directory);path.className='storage-path';technical.append(label,path);}
    if(technical.children.length>1)article.append(technical);
    if(job.issues?.length){const issues=document.createElement('ul');for(const issue of job.issues)issues.append(text('li',issue));article.append(text('p','校验未通过：'),issues);}
    if(job.result_ready){const link=text('a','打开独立玩家预览 ↗');link.href='/organizer/api/jobs/'+job.job_id+'/open';link.target='_blank';link.rel='noopener';article.append(link);}
    if(job.status==='completed'&&job.result_ready){
      const target=document.createElement('select');
      target.setAttribute('aria-label','发布站点');
      const placeholder=text('option','选择地图站点');placeholder.value='';target.append(placeholder);
      for(const site of mapSites){const option=text('option',site.name);option.value=site.id;target.append(option);}
      const publish=text('button','发布到玩家地图');
      publish.disabled=true;
      target.onchange=()=>{publish.disabled=!target.value;};
      publish.onclick=async()=>{
        publish.disabled=true;
        try{
          await api('jobs/'+encodeURIComponent(job.job_id)+'/publish-to-map',{method:'POST',body:JSON.stringify({site_id:target.value})});
          message('已发布到玩家地图：'+target.selectedOptions[0].textContent);
        }catch(error){message(error.message);}
        finally{publish.disabled=false;}
      };
      article.append(target,publish);
    }
    if(job.mounted_preview_ready){
      const link=text('a','打开 3D 审核预览 ↗');
      link.href='/organizer/api/jobs/'+job.job_id+'/open-mounted';
      link.target='_blank';link.rel='noopener';article.append(link);
    }
    if(['failed','recovery_required','awaiting_materials'].includes(job.status)){
      article.append(text('h3','恢复摘要'),text('p','已保存：'+(job.completed_stages.map(s=>stageLabels[s]||s).join('、')||'输入快照')+'。剩余步骤将在核对现有回执后继续，不会自动重发未知用量的模型调用。'));
      if(job.status==='awaiting_materials'){const link=text('a','下载已生成的映射 PDF');link.href='/organizer/api/jobs/'+job.job_id+'/mapping.pdf';article.append(link);const view=text('button','查看项目并补充360导览');view.addEventListener('click',async()=>{loadedProject=job.project_id;page('review');try{await reviewProject();}catch(e){message(e.message);}});article.append(view);}
      const options=job.input_kind==='uploads'?generationOptions(article,!['raw3d','idml3d','idmlscene3d','3d','catalog3d'].includes(job.entry_level),true):()=>({});
      const b=text('button','已查看摘要，确认继续');b.addEventListener('click',async()=>{b.disabled=true;try{const extra=options();delete extra.authorize_model;delete extra.max_evidence_calls;delete extra.max_environment_calls;await api('jobs/'+job.job_id+'/continue',{method:'POST',body:JSON.stringify({confirm_continue:true,...extra})});await refreshJobs();await refreshSources();}catch(e){message(e.message);}finally{b.disabled=false;}});article.append(b);
    }
    root.append(article);
  }
  filterJobs();
  if(!jobs.some(job=>!packaged.has(job.job_id)))root.append(text('p',jobs.length?'其余记录都是上方的共享游戏包版本。':'还没有制作记录。'));
  clearInterval(polling);if(jobs.some(j=>['queued','running','awaiting_external'].includes(j.status)))polling=setInterval(()=>refreshJobs().catch(e=>{clearInterval(polling);message(e.message);}),2500);
}
$('refresh').addEventListener('click',()=>refreshJobs().catch(e=>message(e.message)));
// Shared delivery packages: chunked upload (tunnel-safe), immutable versions, CAS publish/restore.
let deliveryState={packages:[],publications:[],sites:[]},deliveryBusy=0,deliverySignature='',jobSignature='',deliveryDeferred=false,deliveryEpoch=0;
const megabytes=bytes=>(bytes/1024/1024).toFixed(1)+' MB';
const timeText=value=>value?new Date(value).toLocaleString(getLanguage()==='zh'?'zh-CN':getLanguage()):'';
function uploadChunk(id,offset,blob,onProgress){
  return new Promise((resolve,reject)=>{
    const request=new XMLHttpRequest();
    request.open('PUT','/organizer/api/delivery-uploads/'+encodeURIComponent(id)+'?offset='+offset);
    request.setRequestHeader('X-PastPort-Edit','1');request.setRequestHeader('Content-Type','application/octet-stream');
    request.upload.onprogress=event=>onProgress(event.loaded);
    request.onload=()=>{let data={};try{data=JSON.parse(request.responseText);}catch{}
      if(request.status>=200&&request.status<300)resolve(data);else{const error=new Error(data.message||'上传分块失败。');error.status=request.status;reject(error);}};
    request.onerror=()=>{const error=new Error('网络中断，上传分块未完成。');error.status=0;reject(error);};
    request.send(blob);
  });
}
async function uploadDelivery(file,submission,progress){
  const session=await api('delivery-uploads',{method:'POST',body:JSON.stringify({filename:file.name,size:file.size})});
  let received=0;
  while(received<file.size){
    const end=Math.min(file.size,received+session.chunk_bytes);
    for(let attempt=1;;attempt++){
      try{received=(await uploadChunk(session.upload_id,received,file.slice(received,end),loaded=>progress(Math.min(file.size,received+loaded)))).received;break;}
      catch(error){if((error.status!==0&&error.status<500)||attempt>=4)throw error;progress(received,'网络不稳，正在从断点重试（第 '+attempt+' 次）…');await new Promise(r=>setTimeout(r,1500*attempt));}
    }
  }
  progress(file.size,'上传完成，正在校验并解包；不会运行包内代码…');
  return api('delivery-uploads/'+encodeURIComponent(session.upload_id)+'/import',{method:'POST',body:JSON.stringify(submission)});
}
async function runUpload(file,submission,button){
  if(!file){message('请先选择交付包。');return;}
  deliveryBusy++;button.disabled=true;
  const box=$('upload-progress'),bar=$('upload-bar'),label=$('upload-text');box.hidden=false;bar.value=0;
  const show=(bytes,note)=>{bar.value=bytes/file.size;label.textContent=note||('正在上传 '+file.name+'：'+Math.floor(bytes/file.size*100)+'%（'+megabytes(bytes)+' / '+megabytes(file.size)+'）');};
  try{
    show(0);const result=await uploadDelivery(file,submission,show);
    const version=result.delivery.package.versions.find(v=>v.job_id===result.job_id);
    label.textContent=(result.delivery.created?'上传成功：':'内容与已有版本相同，未重复保存：')+deliveryTitle(result.project_id,version.archive_sha256)+' · '+translateVersion(version.number)+'。';
    message(label.textContent);
  }catch(error){label.textContent='上传失败：'+error.message+'（原有版本未受影响）';message(label.textContent);}
  finally{deliveryBusy--;button.disabled=false;await refreshDeliveries(true).catch(e=>message(e.message));}
}
$('import-delivery').addEventListener('click',()=>{const input=$('delivery-file');void runUpload(input.files[0],{base_job_id:null,note:''},$('import-delivery')).then(()=>{input.value='';});});
function translateVersion(number){return getLanguage()==='tr'?'Sürüm '+number:getLanguage()==='en'?'Version '+number:'第 '+number+' 版';}
function versionLabel(jobId){
  for(const item of deliveryState.packages){const version=item.versions.find(v=>v.job_id===jobId);if(version)return deliveryTitle(item.name,version.archive_sha256)+' · '+translateVersion(version.number);}
  return '其他制作记录 '+jobId.slice(0,8);
}
function renderPackages(){
  const root=$('package-list');root.replaceChildren();
  if(!deliveryState.packages.length){root.append(text('p','还没有共享游戏包。上传 .tar.gz 后，所有成员都会看到。'));return;}
  for(const item of deliveryState.packages){
    const current=item.versions.find(v=>v.job_id===item.current_job_id);
    const card=document.createElement('article');card.className='package-card';card.dataset.packageId=item.package_id;
    card.append(text('h3',versionLabel(current.job_id)),text('p',getLanguage()==='tr'?'İçe aktarma kimliği / dosya: '+item.name+' / '+item.name+'.tar.gz':getLanguage()==='en'?'Import ID / file: '+item.name+' / '+item.name+'.tar.gz':'导入标识 / 文件：'+item.name+' / '+item.name+'.tar.gz'),text('p','提交于 '+timeText(current.submitted_at)+' · '+megabytes(current.size_bytes)+(current.note?' · '+current.note:'')));
    const actions=document.createElement('div');actions.className='row';
    const download=text('a','下载当前版');download.href='/organizer/api/jobs/'+current.job_id+'/download';download.setAttribute('download','');
    const preview=text('a','打开独立玩家预览 ↗');preview.href='/organizer/api/jobs/'+current.job_id+'/open';preview.target='_blank';preview.rel='noopener';
    const showMaterials=text('button','查看配套资料');showMaterials.className='secondary';
    const materials=document.createElement('ul');materials.hidden=true;
    showMaterials.onclick=async()=>{materials.hidden=!materials.hidden;if(materials.hidden)return;materials.replaceChildren(text('li','正在读取…'));try{const value=await api('jobs/'+current.job_id+'/materials');materials.replaceChildren();for(const entry of value.items){const li=document.createElement('li');if(entry.href&&entry.available){const a=text('a',entry.label);a.href=entry.href;li.append(a);}else li.append(text('strong',entry.label));li.append(text('span',' · '+(entry.available?'可获取':'缺失')+(entry.detail?'：'+entry.detail:'')));if(!entry.available)li.className='missing';materials.append(li);}}catch(e){materials.replaceChildren(text('li',e.message));}};
    actions.append(download,preview,showMaterials);card.append(actions,materials);
    const publish=document.createElement('div');publish.className='row';
    const site=document.createElement('select');site.setAttribute('aria-label','发布站点');const none=text('option','选择地图站点');none.value='';site.append(none);
    for(const entry of deliveryState.sites){const option=text('option',entry.name);option.value=entry.id;site.append(option);}
    const version=document.createElement('select');version.setAttribute('aria-label','发布版本');
    for(const v of [...item.versions].reverse()){const option=text('option',versionLabel(v.job_id)+(v.job_id===item.current_job_id?'（当前）':''));option.value=v.job_id;version.append(option);}
    version.value=item.current_job_id;
    const go=text('button','发布到玩家地图');go.disabled=true;site.onchange=()=>{go.disabled=!site.value;};
    go.onclick=async()=>{const state=deliveryState.publications.find(p=>p.site_id===site.value);go.disabled=true;deliveryBusy++;try{await api('jobs/'+encodeURIComponent(version.value)+'/publish-to-map',{method:'POST',body:JSON.stringify({site_id:site.value,expected_version:state?.current?.version??'none'})});message('已发布到玩家地图：'+site.selectedOptions[0].textContent+' · '+versionLabel(version.value)+'。玩家地图会在几秒内自动更新。');}catch(e){message(e.message);}finally{deliveryBusy--;go.disabled=false;await refreshDeliveries(true).catch(e=>message(e.message));}};
    publish.append(site,version,go);card.append(publish);
    const submit=document.createElement('div');submit.className='row';
    const file=document.createElement('input');file.type='file';file.accept='.tar.gz,application/gzip';file.setAttribute('aria-label','新版游戏包');
    const note=document.createElement('input');note.type='text';note.maxLength=500;note.placeholder='修改说明（可选）';
    const send=text('button','提交新版（基于第 '+current.number+' 版）');
    send.onclick=()=>{const chosen=file.files[0];if(chosen&&chosen.name!==item.name+'.tar.gz'){message('新版文件名须为 '+item.name+'.tar.gz（包内顶层文件夹同名）。');return;}void runUpload(chosen,{base_job_id:item.current_job_id,note:note.value},send);};
    submit.append(file,note,send);const editing=document.createElement('details');editing.append(text('summary','提交新版'),submit);card.append(editing);
    const list=document.createElement('ol');list.className='version-list';
    for(const v of [...item.versions].reverse()){
      const li=document.createElement('li');li.append(text('span',versionLabel(v.job_id)+' · '+timeText(v.submitted_at)+' · '+megabytes(v.size_bytes)+(v.note?' · '+v.note:'')));
      if(v.job_id===item.current_job_id)li.append(text('span','当前版本','badge'));
      else{const restore=text('button','设为当前版本');restore.className='secondary';restore.onclick=async()=>{if(!confirm(getLanguage()==='tr'?`${versionLabel(v.job_id)} geçerli sürüm yapılsın mı? Diğer sürümler korunur.`:getLanguage()==='en'?`Make ${versionLabel(v.job_id)} current? Other versions are retained.`:'设为当前版本：'+versionLabel(v.job_id)+'？其他版本都会保留。'))return;deliveryBusy++;try{await api('packages/'+item.package_id+'/restore',{method:'POST',body:JSON.stringify({job_id:v.job_id,expected_revision:item.revision})});message(versionLabel(v.job_id)+' · '+(getLanguage()==='tr'?'Geçerli sürüm değişti; harita yayını değişmedi.':getLanguage()==='en'?'Current version changed; map publication is unchanged.':'已设为当前版本；已发布的地图不变，需要时再发布。'));}catch(e){message(e.message);}finally{deliveryBusy--;await refreshDeliveries(true).catch(e=>message(e.message));}};li.append(restore);}
      const link=text('a','下载');link.href='/organizer/api/jobs/'+v.job_id+'/download';link.setAttribute('download','');li.append(link);list.append(li);
    }
    const history=document.createElement('details');history.append(text('summary','版本历史（不会被覆盖或删除）：'),list);card.append(history);root.append(card);
  }
}
function renderPublications(){
  const root=$('publication-list');root.replaceChildren();const live=deliveryState.publications.filter(p=>p.current);
  if(!live.length){root.append(text('p','玩家地图上还没有发布的游戏。'));return;}
  for(const state of live){
    const article=document.createElement('article');article.className='package-card';
    article.append(text('h3',state.name),text('p','当前发布：'+versionLabel(state.current.job_id)+(state.current.published_at?' · '+timeText(state.current.published_at):'')));
    const unpublish=text('button','解除发布');unpublish.className='secondary unpublish-button';
    unpublish.onclick=async()=>{
      const prompt=getLanguage()==='tr'?`“${state.name}” oyununun yayını kaldırılsın mı? Harita noktası, oyun paketi, kayıtlar ve madalyalar korunur.`:getLanguage()==='en'?`Unpublish “${state.name}”? The map node stays; the game package, saves and medals are retained.`:`解除「${state.name}」的游戏发布？地图节点保留，游戏包、存档和奖章均保留。`;
      if(!confirm(prompt))return;
      let unpublished=false;unpublish.disabled=true;deliveryBusy++;
      try{
        const updated=await api('jobs/'+encodeURIComponent(state.current.job_id)+'/publish-to-map',{method:'DELETE',body:JSON.stringify({site_id:state.site_id,expected_version:state.current.version})});
        // Apply the authoritative DELETE result immediately, even if a later refresh fails.
        deliveryEpoch++;deliverySignature='';
        deliveryState={...deliveryState,publications:deliveryState.publications.map(item=>item.site_id===updated.site_id?updated:item)};
        unpublished=true;renderPublications();message('已解除发布；游戏包和玩家数据已保留。');
      }
      catch(error){message(error.message);}
      finally{deliveryBusy--;unpublish.disabled=false;await refreshDeliveries(true).catch(error=>{if(unpublished)message('已解除发布；列表刷新暂不可用，请稍后刷新。');});}
    };article.append(unpublish);
    const previous=[...state.history].reverse().find(entry=>entry.version!==state.current.version);
    if(previous){const back=text('button','回退到上一次发布：'+versionLabel(previous.job_id));back.className='secondary';back.onclick=async()=>{if(!confirm(getLanguage()==='tr'?`${state.name}, ${versionLabel(previous.job_id)} sürümüne döndürülsün mü? Oyuncu kayıtları ve madalyalar korunur.`:getLanguage()==='en'?`Restore ${state.name} to ${versionLabel(previous.job_id)}? Player saves and medals are retained.`:'把「'+state.name+'」回退到 '+versionLabel(previous.job_id)+'？玩家存档和奖章不会删除。'))return;deliveryBusy++;try{await api('jobs/'+encodeURIComponent(previous.job_id)+'/publish-to-map',{method:'POST',body:JSON.stringify({site_id:state.site_id,expected_version:state.current.version})});message('已回退「'+state.name+'」。');}catch(e){message(e.message);}finally{deliveryBusy--;await refreshDeliveries(true).catch(e=>message(e.message));}};article.append(back);}
    root.append(article);
  }
}
function interacting(){
  const element=document.activeElement;
  return deliveryBusy>0||(!!element&&!!element.closest?.('#package-list,#publication-list')&&['SELECT','INPUT'].includes(element.tagName))
    ||[...document.querySelectorAll('#package-list input[type=file]')].some(input=>input.files.length)
    ||[...document.querySelectorAll('#package-list ul')].some(list=>!list.hidden);
}
async function refreshDeliveries(force=false){
  const epoch=deliveryEpoch;
  const [packages,publications,sites]=await Promise.all([api('packages'),api('map-publications'),deliveryState.sites.length?deliveryState.sites:api('map-sites')]);
  if(epoch!==deliveryEpoch)return; // Ignore snapshots requested before a successful unpublish.
  const signature=JSON.stringify([packages,publications]);
  if(!force&&signature===deliverySignature)return;
  if(!force&&interacting()){deliveryDeferred=true;$('delivery-sync').textContent='有新的更新，你完成当前操作后自动显示。';return;}
  deliverySignature=signature;deliveryDeferred=false;deliveryState={packages,publications,sites};
  $('delivery-sync').textContent='同一后台的所有成员看到同一份游戏包、版本与发布；列表每 4 秒自动更新。上次更新 '+new Date().toLocaleTimeString(getLanguage()==='zh'?'zh-CN':getLanguage())+'。';
  renderPackages();renderPublications();
}
// Other members' uploads, versions and publications appear without a manual refresh.
setInterval(async()=>{
  if(document.visibilityState!=='visible'||$('workspace').hidden||$('jobs').hidden)return;
  try{
    await refreshDeliveries();
    const jobs=await api('jobs');const signature=JSON.stringify(jobs.map(j=>[j.job_id,j.status,j.message,j.result_ready]));
    if(jobSignature&&signature!==jobSignature&&!interacting())await refreshJobs();
    jobSignature=signature;
  }catch(error){if(!String(error.message).includes('登录'))console.error(error.message);}
},4000);
document.querySelectorAll('[data-page="jobs"]').forEach(button=>button.addEventListener('click',()=>{void refreshDeliveries(true).catch(e=>message(e.message));}));
$('refresh').addEventListener('click',()=>refreshDeliveries(true).catch(e=>message(e.message)));
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
  await refreshDeliveries(true).catch(error=>message(error.message));
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
document.getElementById('interface-language').addEventListener('change', async event => {setLanguage(event.target.value);renderPackages();renderPublications();if(polling)await refreshJobs().catch(error=>message(error.message));});
