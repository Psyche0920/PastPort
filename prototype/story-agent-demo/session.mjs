import {PlayerContext} from './engine/context.mjs';
import {PlayerRuntime} from './engine/runtime.mjs';
import {ConditionEvaluator} from './engine/rules.mjs';
import {contentHash} from './engine/validation.mjs';
import {Activity} from './plugins.mjs';
import {prepareGameplayPlan} from './gameplay.mjs';
import {WalkMesh} from './walkmesh.mjs';
export class SessionError extends Error {}
const requireValue=(test,message)=>{if(!test)throw new SessionError(message);};
/** One owner for shared runtime transitions and atomic browser snapshots. */
export class GameSession {
  static async create(pkg,reference,presentation,storage=null) {
    const context=await PlayerContext.create(pkg,reference,presentation.releaseId??'murat-local-demo-1');
    const gameplayPlan=await prepareGameplayPlan(pkg,presentation);
    requireValue(gameplayPlan.status==='ready','当前任务缺少已验证玩法插件，不能开始游戏。');
    const identity=await contentHash({packageHash:reference.sha256,presentation:JSON.stringify(presentation),gameplayPlan});
    return new GameSession(context,presentation,gameplayPlan,identity,storage);
  }
  constructor(context,presentation,gameplayPlan,identity,storage) {
    this.context=context;this.runtime=new PlayerRuntime(context);this.presentation=presentation;this.gameplayPlan=gameplayPlan;this.identity=identity;
    this.storage=storage;this.key=presentation.saveKey??'pastport:murat-story-demo:save:v2';this.lastSavedRaw=null;this.sequence=0;
    this.state=context.initialState();this.local={};this.notebook=[];this.positions={};this.conditions=new ConditionEvaluator();this.paused=false;this.unsaved=false;this.shotState=null;
  }
  get current(){const scene=this.presentation.chapters.find(c=>c.id===this.state.current_scene_id);requireValue(scene,'Missing presentation stage');return scene;}
  evaluate(guard){return guard==null||this.conditions.evaluate(guard,this.state);}
  config(scene=this.current){const task=this.context.scene(scene.id).tasks[0];const binding=this.gameplayPlan.bindings.find(item=>item.task_id===task.task_id&&item.scene_id===scene.id);requireValue(binding,'当前任务没有精确的玩法绑定');const config=structuredClone(binding.config);if(config.plans)config.plans=config.plans.map(p=>({...p,allowed:this.evaluate(p.guard)}));return config;}
  entry(scene=this.current){return this.local[scene.id]??{sources:[],activity:new Activity(this.config(scene)).initialize()};}
  taskId(scene=this.current){return this.context.scene(scene.id).tasks[0].task_id;}
  taskDone(scene=this.current){return this.state.completed_task_ids.includes(this.taskId(scene));}
  nextSource(scene=this.current){return scene.requiredSources.find(n=>!this.entry(scene).sources.includes(n))??null;}
  decision(scene=this.current){const id=scene.decision??scene.automaticDecision;return this.state.decisions.find(d=>d.decision_id===id)?.option_id??null;}
  variables(){return Object.fromEntries(this.state.variables.map(v=>[v.name,v.value]));}
  async apply(state,kind,target,extra={}) {
    return (await this.runtime.apply(state,{project_id:state.project_id,release_id:state.release_id,package_hash:state.package_hash,action:{kind,target_id:target,action_id:crypto.randomUUID(),expected_revision:state.revision,...extra}})).state;
  }
  async dispatch(command){
    requireValue(!this.paused,'游戏已暂停');requireValue(!this.state.ending_id,'本局已结束');const scene=this.current;
    const entry=structuredClone(this.entry());requireValue(scene.requiredSources.every(n=>entry.sources.includes(n)),'先查看资料，并选择“加入本次观察”。');
    const step=new Activity(this.config()).reduce(entry.activity,command);entry.activity=step.state;let next=this.state;
    if(step.result.status==='completed'){
      next=await this.apply(next,'observe',this.taskId(scene),{spot_id:'result'});
      if(scene.automaticDecision)next=await this.apply(next,'choose',scene.automaticDecision,{option_id:step.result.outcome});
    }
    this.local={...this.local,[scene.id]:entry};this.state=next;this.persist();return step;
  }
  observeSource(number){
    requireValue(this.current.requiredSources.includes(number),'该资料不是当前正式观察项');
    const entry=structuredClone(this.entry());if(!entry.sources.includes(number))entry.sources.push(number);entry.sources.sort((a,b)=>a-b);
    this.local={...this.local,[this.current.id]:entry};if(!this.notebook.includes(number))this.notebook.push(number);this.persist();
  }
  recordBrowse(number){requireValue(this.presentation.objects.some(o=>o.number===number),'Unknown source');if(!this.notebook.includes(number)){this.notebook.push(number);this.persist();}}
  async choose(id){requireValue(!this.paused,'游戏已暂停');const scene=this.current;requireValue(scene.decision&&scene.options.some(o=>o.id===id),'本阶段没有这个选择');this.state=await this.apply(this.state,'choose',scene.decision,{option_id:id});this.persist();}
  async advance(){requireValue(!this.paused,'游戏已暂停');const scene=this.context.scene(this.state.current_scene_id);requireValue(scene.next_scene_ids.length===1,'当前没有下一阶段');this.state=await this.apply(this.state,'advance',scene.next_scene_ids[0]);this.persist();}
  rememberPosition(id,point){requireValue(this.presentation.chapters.some(c=>c.id===id)&&Array.isArray(point)&&point.length===2&&point.every(n=>Number.isFinite(n)&&n>=0&&n<=100),'Invalid position');this.positions[id]=[...point];this.persist();}
  rememberShot(view){this.validateShot(view);this.shotState=structuredClone(view);this.persist();}
  validateShot(view){if(view===null)return;const shot=this.presentation.shots?.find(s=>s.number===view?.number&&s.available);requireValue(shot&&['walking','task'].includes(view.phase)&&Array.isArray(view.position)&&view.position.length===2&&view.position.every(Number.isFinite)&&new WalkMesh(shot.boundary,shot.obstacles).allows(view.position),'Invalid fixed-shot save');if(view.beforeView!==null){const b=view.beforeView;requireValue(b&&this.presentation.scenes.some(s=>s.id===b.scene)&&[b.yaw,b.pitch,b.hfov].every(Number.isFinite)&&b.pitch>=-90&&b.pitch<=90&&b.hfov>=35&&b.hfov<=125,'Invalid saved camera');}}
  snapshot(){return {version:2,shotState:this.shotState,identity:this.identity,sequence:this.sequence,engine:this.state,local:this.local,notebook:[...this.notebook].sort((a,b)=>a-b),positions:this.positions};}
  serialize(){return JSON.stringify(this.snapshot());}
  restore(raw){
    requireValue(typeof raw==='string'&&raw.length<=300000,'存档过大或格式错误');const parsed=JSON.parse(raw);
    requireValue(parsed&&parsed.version===2&&parsed.identity===this.identity,'存档对应其他内容版本；原存档保留，请下载后再决定是否重开。');
    requireValue(Number.isSafeInteger(parsed.sequence)&&parsed.sequence>=0&&parsed.sequence<1000000,'Invalid save revision');this.context.validateState(parsed.engine);this.validateShot(parsed.shotState);
    requireValue(parsed.local&&typeof parsed.local==='object'&&!Array.isArray(parsed.local)&&Object.keys(parsed.local).length<=this.presentation.chapters.length,'Invalid activity collection');
    const previous=this.state;this.state=parsed.engine;
    try{
      for(const [id,entry] of Object.entries(parsed.local)){
        const scene=this.presentation.chapters.find(c=>c.id===id);requireValue(scene&&entry&&Object.keys(entry).sort().join(',')==='activity,sources','Unknown saved stage');
        requireValue(Array.isArray(entry.sources)&&new Set(entry.sources).size===entry.sources.length&&entry.sources.every(n=>scene.requiredSources.includes(n)),'Invalid source observations');
        const activity=new Activity(this.config(scene));activity.validateState(entry.activity);
        requireValue(this.taskDone(scene)===entry.activity.done,'任务和小游戏存档不一致');
        if(entry.activity.done)requireValue(scene.requiredSources.every(n=>entry.sources.includes(n)),'Completed task lacks observations');
      }
      for(const task of this.state.completed_task_ids){const scene=this.context.game.scenes.find(scene=>scene.tasks.some(item=>item.task_id===task));requireValue(scene&&parsed.local[scene.scene_id]?.activity.done,'Missing completed activity');}
      requireValue(Array.isArray(parsed.notebook)&&new Set(parsed.notebook).size===parsed.notebook.length&&parsed.notebook.every(n=>this.presentation.objects.some(o=>o.number===n)),'Invalid notebook');
      requireValue(parsed.positions&&typeof parsed.positions==='object'&&!Array.isArray(parsed.positions),'Invalid positions');
      for(const [id,point]of Object.entries(parsed.positions))requireValue(this.presentation.chapters.some(c=>c.id===id)&&Array.isArray(point)&&point.length===2&&point.every(n=>Number.isFinite(n)&&n>=0&&n<=100),'Invalid saved position');
    }catch(error){this.state=previous;throw error;}
    this.shotState=parsed.shotState;this.sequence=parsed.sequence;this.local=parsed.local;this.notebook=parsed.notebook;this.positions=parsed.positions;
  }
  load(){if(!this.storage)return false;const raw=this.storage.getItem(this.key);if(raw===null)return false;this.restore(raw);this.lastSavedRaw=raw;return true;}
  persist(){
    if(!this.storage)return;
    try{
      requireValue(this.storage.getItem(this.key)===this.lastSavedRaw,'另一个页面已经更新了存档。请刷新当前页面，避免覆盖。');
      this.sequence++;const raw=this.serialize();this.storage.setItem(this.key,raw);this.lastSavedRaw=raw;this.unsaved=false;
    }catch(error){this.unsaved=true;throw new SessionError('未保存：'+error.message);}
  }
}
