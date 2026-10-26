import {ObjectGesture} from './interaction.mjs';
/** Browser adapter for the isolated 3D host, retaining the existing story UI. */
export class Scene3DView {
  constructor({session,inspect,openTask,notify,refresh,closeDialogue,guide}) {
    Object.assign(this,{session,inspect,openTask,notify,refresh,closeDialogue,guide});
    this.frame=document.getElementById('museum');this.ready=false;this.active=false;this.token=0;this.world=1;this.arrivedSources=new Set();this.readOnlySources=new Set();this.renderMode=new URLSearchParams(location.search).get('render')==='original'?'original':'stylized';
    this.accessSequence=0;this.pendingInspection=null;
    this.gesture=new ObjectGesture({inspect:n=>this.inspectWithAccess(n),approach:n=>this.approach(n)});
    document.body.classList.add('scene3d-mode');
    document.querySelector('.brand').href='/?scene=3d';
    const tools=document.querySelector('.topbar nav'),menu=document.createElement('details'),summary=document.createElement('summary');
    menu.className='scene-tools';summary.textContent='菜单';menu.append(summary);tools.before(menu);menu.append(tools);
    this.frame.src='/world/1/scene3d/index.html?render='+this.renderMode;
    this.listener=event=>{
      if(event.origin!==location.origin||event.source!==this.frame.contentWindow)return;
      const msg=event.data;
      if(msg?.type==='story3d:ready'){this.ready=true;this.refresh();this.startGuide();}
      if(msg?.type==='story3d:render-mode'&&['original','stylized'].includes(msg.mode)){this.renderMode=msg.mode;const url=new URL(location.href);url.searchParams.set('render',msg.mode);history.replaceState(null,'',url);}
      if(msg?.type==='story3d:access'&&this.pendingInspection?.request===msg.request&&this.pendingInspection.number===msg.number&&this.pendingInspection.stage===this.session.current.id&&this.pendingInspection.world===this.world){
        clearTimeout(this.pendingInspection.timer);
        this.pendingInspection=null;
        if(['blocked_path','unverified_ground'].includes(msg.code))this.readOnlySources.add(`${this.session.current.id}:${msg.number}`);
        this.cancelMotion();this.inspect(msg.number);
      }
      if(msg?.type==='story3d:guide'){if(this.session.current.id==='s01')this.guide();else this.openTask();}
      if(msg?.type==='story3d:task'&&this.session.nextSource()===null)this.openTask();
      if(msg?.type==='story3d:world'&&[1,2].includes(msg.world)&&!this.blocked())this.switchWorld(msg.world,msg.arrival);
      if(msg?.type==='story3d:object'&&this.session.presentation.objects.some(o=>o.number===msg.number))this.gesture.click(msg.number);
      if(msg?.type==='story3d:blocked'){
        this.notify(msg.reason);this.active=false;
        if(msg.token===this.token&&['blocked_path','unverified_ground'].includes(msg.code)&&this.session.current.requiredSources.includes(msg.number)){
          this.readOnlySources.add(`${this.session.current.id}:${msg.number}`);this.inspect(msg.number);
        }
      }
      if(msg?.type==='story3d:arrived'&&(msg.token===this.token||msg.manual===true&&this.session.current.requiredSources.includes(msg.number))){
        this.active=false;
        if(this.session.current.requiredSources.includes(msg.number)){
          this.arrivedSources.add(`${this.session.current.id}:${msg.number}`);
          this.inspect(msg.number);
        }
        else if(this.session.presentation.stageTargets[this.session.current.id]===msg.number)this.openTask();
        else this.notify('已走近，这里没有当前待办任务。');
      }
    };
    addEventListener('message',this.listener);
    this.frame.addEventListener('load',()=>this.post({type:'story3d:ping'}));
    this.blocked=()=>this.session.paused||Boolean(document.querySelector('dialog[open]'))||!document.getElementById('dialogue').hidden;
    this.observer=new MutationObserver(()=>this.post({type:'story3d:pause',paused:this.blocked()}));
    this.observer.observe(document.body,{subtree:true,attributes:true,attributeFilter:['open','hidden']});
    const nav=document.createElement('nav');nav.className='world-select';this.worldButtons=new Map();
    for(const i of [1,2]){const b=document.createElement('button');b.textContent=`点位 ${i}`;b.disabled=i===this.world;b.setAttribute('aria-pressed',String(i===this.world));b.onclick=()=>this.post({type:'story3d:navigate',world:i});this.worldButtons.set(i,b);nav.append(b);}
    document.getElementById('stage').append(nav);
  }
  post(message){this.frame.contentWindow?.postMessage(message,location.origin);}
  switchWorld(world,arrival=null){
    if(world===this.world)return;
    if(arrival&&(!Number.isFinite(arrival.yaw)||!Number.isFinite(arrival.pitch)||Math.abs(arrival.yaw)>180||Math.abs(arrival.pitch)>90)){this.notify('原导航朝向无效，已停止切换。');return;}
    this.cancelMotion();this.ready=false;this.world=world;
    for(const [number,button]of this.worldButtons){button.disabled=number===world;button.setAttribute('aria-pressed',String(number===world));}
    const query=new URLSearchParams({render:this.renderMode});if(arrival){query.set('arrival_yaw',String(arrival.yaw));query.set('arrival_pitch',String(arrival.pitch));}
    this.frame.src=`/world/${world}/scene3d/index.html?${query}`;
  }
  startGuide(){if(this.ready&&this.world===1&&!this.blocked()&&this.session.current.id==='s01'&&!this.guideStarted){this.guideStarted=true;this.guide();}}
  click(n){this.gesture.click(n);}
  key(n,approach){this.gesture.key(n,approach);}
  locate(number){this.post({type:'story3d:focus',number});}
  hasArrived(number){return this.arrivedSources.has(`${this.session.current.id}:${number}`);}
  readOnlyObservation(number){return this.readOnlySources.has(`${this.session.current.id}:${number}`)||this.session.presentation.shots.some(shot=>shot.number===number&&!shot.available)||this.session.presentation.scenes.some(scene=>scene.hotspots.some(spot=>spot.number===number&&spot.pitch>=35));}
  canObserve(number){return this.readOnlyObservation(number)||this.hasArrived(number);}
  inspectWithAccess(number){
    if(!this.ready||this.canObserve(number)){this.cancelMotion();this.inspect(number);return;}
    clearTimeout(this.pendingInspection?.timer);
    const request=++this.accessSequence;const timer=setTimeout(()=>{if(this.pendingInspection?.request===request){this.cancelMotion();this.inspect(number);}},1500);
    this.pendingInspection={request,number,stage:this.session.current.id,world:this.world,timer};
    this.post({type:'story3d:check-access',number,request});
  }
  approach(number){
    if(!this.ready){this.notify('三维场景仍在加载。');return;}
    for(const id of ['source-dialog','notebook-dialog','story-panel'])document.getElementById(id).close();
    this.closeDialogue();this.active=true;
    if(this.readOnlyObservation(number)){this.active=false;this.locate(number);this.inspect(number);return;}
    this.post({type:'story3d:approach',number,token:++this.token});
  }
  cancelMotion(){this.active=false;clearTimeout(this.pendingInspection?.timer);this.pendingInspection=null;this.token++;this.post({type:'story3d:cancel'});}
  remember(){}
  restore(){this.notify('剧情进度已恢复；三维位置从当前场景起点开始。');}
  leave(){this.cancelMotion();this.closeDialogue();}
  closeTask(){this.post({type:'story3d:pause',paused:this.blocked()});}
  setSpeaker(){}
  highlightSpeaker(){}
  renderActors(){
    this.post({type:'story3d:pause',paused:this.blocked()});
    const number=this.session.nextSource();
    const object=this.session.presentation.objects.find(o=>o.number===number);
    this.post({type:'story3d:objective',number,stage:this.session.current.id,token:this.token,title:object?.historical_title??'',paused:this.blocked()});
  }
}
