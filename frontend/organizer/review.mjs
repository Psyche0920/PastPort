import {mountLocalization} from './i18n.mjs';
const element=(tag,value)=>{const node=document.createElement(tag);if(value!==undefined)node.textContent=value;return node;};
export class ReviewWorkbench{
  constructor(root,api,{onApply,onMessage,onChange,isActive=()=>true}){this.root=root;this.api=api;this.isActive=isActive;this.onApply=onApply;this.onMessage=onMessage;this.onChange=onChange;this.dirty=false;this.data=null;this.frame=null;this.syncing=false;this.pendingSaved=false;this.checking=false;
    window.addEventListener('message',event=>{if(event.origin!==location.origin||event.source!==this.frame?.contentWindow)return;if(event.data?.type==='pastport-review-dirty')this.dirty=true;if(event.data?.type==='pastport-review-saved'){this.dirty=false;this.afterSaved().catch(error=>this.onMessage(error.message));}});
    window.addEventListener('focus',()=>this.checkChanges());document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible')this.checkChanges();});
  }
  async load(source){if(this.dirty){this.onMessage('审核后台有未保存修改，请先保存，或点“放弃未保存修改”。');return;}try{this.data=await this.api('review/'+encodeURIComponent(source));this.root.replaceChildren(element('h2','项目：'+this.data.project_id));this.controls=element('div');this.controls.className='review-actions';this.root.append(this.controls);this.frame=element('iframe');this.frame.title='VR与3D共用物件审核后台';this.frame.className='native-review-frame';this.frame.setAttribute('sandbox','allow-scripts allow-same-origin allow-forms allow-popups');this.frame.addEventListener('load',()=>{this.unmountLanguage?.();if(this.frame.contentDocument)this.unmountLanguage=mountLocalization(this.frame.contentDocument,{exactOnly:true,protectedSelector:'#list button, #detail h2'});});this.frame.src='/organizer/api/review/'+encodeURIComponent(source)+'/workbench/';this.root.append(this.frame);this.renderControls();if(!this.data.snapshot_current)this.afterSaved().catch(error=>this.onMessage(error.message));}catch(error){this.root.replaceChildren(element('p',error.message));}}
  async checkChanges(){if(!this.isActive()||!this.data||this.checking||this.syncing||this.dirty)return;this.checking=true;try{const current=await this.api('review/'+encodeURIComponent(this.data.source_id));if(!this.isActive())return;if(!current.snapshot_current||current.revision!==this.data.revision){this.data=current;await this.afterSaved();}}catch(error){this.onMessage(error.message);}finally{this.checking=false;}}
  async afterSaved(){if(!this.isActive())return;this.pendingSaved=true;if(this.syncing)return;this.syncing=true;try{for(let round=0;round<3&&this.pendingSaved;round++){this.pendingSaved=false;this.data=await this.api('review/'+encodeURIComponent(this.data.source_id));if(!this.isActive())return;if(this.onChange)await this.onChange();this.renderControls();if(!this.data.snapshot_current){this.onMessage('修改已保存，正在检查并衔接当前资料；不调用模型或Marble。');const result=await this.api('review/'+encodeURIComponent(this.data.source_id)+'/apply',{method:'POST',body:JSON.stringify({revision:this.data.revision})});if(!this.isActive())return;await this.onApply(result.source_id,this.data.source_id);this.data=await this.api('review/'+encodeURIComponent(result.source_id));if(!this.data.snapshot_current)this.pendingSaved=true;this.renderControls();}}
    this.onMessage(this.pendingSaved?'审核修改已保存，最后的输入版本仍待同步；不会使用旧版本生成故事。':'审核修改已保存并自动衔接。可以进入故事步骤；不需要再次选择或确认传递资料。');
  }catch(error){this.onMessage('审核已保存，但后续输入尚未同步：'+error.message);this.pendingSaved=true;}finally{this.syncing=false;this.renderControls();}}
  renderControls(){if(!this.controls||!this.data)return;const data=this.data;const controls=this.controls;controls.replaceChildren(element('p','已自动接入上一步的资料与环境。下方使用当前SDK的VR/3D共用审核界面；介绍和审核共用，空间位置分别保存。'));
    const link=(title,url)=>{const a=element('a',title);a.href=url;a.target='_blank';a.rel='noopener';return a;};const prefix='/organizer/api/review/'+encodeURIComponent(data.source_id);const links=element('p');links.append(link(data.source_format==='idml'?'原始史料 IDML':'原始史料 PDF',prefix+'/media/original-pdf'),element('span',' · '),link(data.source_format==='idml'?'IDML原始来源':'映射来源 PDF',prefix+'/media/mapping-pdf'),element('span',' · '),link('原始VR环境',prefix+'/environment/0/vr_trial/index.html'),element('span',' · '),link('3D点位一',prefix+'/environment/0/scene3d/index.html'));if(data.view_count>1)links.append(element('span',' · '),link('3D点位二',prefix+'/environment/1/scene3d/index.html'));controls.append(links);
    if(data.database_path){const database=element('section');database.className='storage-location';database.append(element('strong','本机审核数据库（SQLite）'),element('p','位于运行后台服务的电脑，保存物件介绍与审核记录。'));
    const path=element('code',data.database_path);path.className='storage-path';database.append(path);
    const copy=element('button','复制数据库路径');copy.type='button';copy.addEventListener('click',async()=>{try{await navigator.clipboard.writeText(data.database_path);this.onMessage('审核数据库路径已复制。');}catch{const selection=window.getSelection();const range=document.createRange();range.selectNodeContents(path);selection?.removeAllRanges();selection?.addRange(range);this.onMessage('路径已选中，请手动复制。');}});database.append(copy);controls.append(database);}
    controls.append(element('p',this.syncing?'修改已保存，正在同步本次制作输入…':data.snapshot_current?'当前审核资料已衔接，可继续故事步骤。':'审核修改待同步，故事步骤暂不可用。'));
    if(this.pendingSaved&&!this.syncing){const retry=element('button','重试本机资料同步');retry.onclick=()=>this.afterSaved();controls.append(retry);}
    const discard=element('button','放弃未保存修改');discard.addEventListener('click',()=>{this.dirty=false;this.load(data.source_id);});controls.append(discard);
  }
}


export function environmentActionState(jobs,project){
  const own=jobs.filter(job=>job.project_id===project);
  if(own.some(job=>['queued','running','awaiting_external'].includes(job.status)))
    return {disabled:true,label:'准备中…'};
  if(own.some(job=>['environment_ready','story_ready','completed'].includes(job.status)&&job.prepared_source_id))
    return {disabled:true,label:'已完成'};
  if(own.some(job=>job.status==='awaiting_materials'))
    return {disabled:true,label:'等待补充材料'};
  return {disabled:false,label:'准备资料与环境'};
}


export function restoredWorkflow(jobs,workspace,session={}){
  const active=['queued','running','awaiting_external'];
  const environment=jobs.find(job=>job.job_id===session.environmentJob&&[...active,'awaiting_materials'].includes(job.status));
  const story=jobs.find(job=>job.job_id===session.storyJob&&active.includes(job.status)&&job.source_id===workspace?.source_id);
  return {
    environmentSource:environment?null:workspace?.source_id||null,
    storySource:!environment&&workspace?.story_ready?workspace.source_id:null,
    environmentJob:environment?.job_id||null,
    storyJob:story?.job_id||null,
    projectId:environment?.project_id||workspace?.project_id||null,
  };
}
