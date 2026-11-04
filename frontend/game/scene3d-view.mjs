import {ObjectGesture} from './interaction.mjs';
import {ScenePreparation} from './scene-preparation.mjs';
/** Browser adapter for the isolated 3D host, retaining the existing story UI. */
export class Scene3DView {
  constructor({session,inspect,openTask,notify,refresh,closeDialogue,guide,getLocale=()=>'zh'}) {
    Object.assign(this,{session,inspect,openTask,notify,refresh,closeDialogue,guide,getLocale});
    this.frame=document.getElementById('museum');this.ready=false;this.active=false;this.token=0;this.world=1;this.arrivedSources=new Set();this.readOnlySources=new Set();this.renderMode=new URLSearchParams(location.search).get('render')==='original'?'original':'stylized';
    this.locale=getLocale();this.deferred=session.presentation.startupPreparation==='lod';this.preparation=new ScenePreparation();this.preparationMessage=null;this.qualityName='low';
    this.scenePickedSources=new Set();this.accessSequence=0;this.pendingInspection=null;
    this.gesture=new ObjectGesture({inspect:n=>this.inspectWithAccess(n),approach:n=>this.approach(n)});
    document.body.classList.add('scene3d-mode');
    document.querySelector('.brand').href='/?scene=3d';
    const tools=document.querySelector('.topbar nav'),menu=document.createElement('details'),summary=document.createElement('summary');
    menu.className='scene-tools';this.menuSummary=summary;summary.textContent=this.t('選單','Menu');menu.append(summary);tools.before(menu);menu.append(tools);
    this.frame.src=this.deferred?'about:blank':'/world/1/scene3d/index.html?render='+this.renderMode;
    this.listener=event=>{
      if(event.origin!==location.origin||event.source!==this.frame.contentWindow)return;
      const msg=event.data;
      if(msg?.type==='story3d:ready'){this.ready=true;this.setLocale(this.getLocale(),true);this.post({type:'story3d:views',count:this.session.presentation.scenes.length});if(this.preparationMessage)this.post({...this.preparationMessage,locale:this.locale});this.refresh();if(!this.deferred)this.startGuide();}
      if(this.preparation.accept(msg))return;
      if(msg?.type==='story3d:quality-changed'&&['low','standard'].includes(msg.value)){this.qualityName=msg.value;this.updateQualityLabel();}
      if(msg?.type==='story3d:render-mode'&&['original','stylized'].includes(msg.mode)){this.renderMode=msg.mode;const url=new URL(location.href);url.searchParams.set('render',msg.mode);history.replaceState(null,'',url);}
      if(msg?.type==='story3d:access'&&this.pendingInspection?.request===msg.request&&this.pendingInspection.number===msg.number&&this.pendingInspection.stage===this.session.current.id&&this.pendingInspection.world===this.world){
        clearTimeout(this.pendingInspection.timer);
        this.pendingInspection=null;
        if(['blocked_path','unverified_ground'].includes(msg.code))this.readOnlySources.add(`${this.session.current.id}:${msg.number}`);
        this.cancelMotion();this.inspect(msg.number);
      }
      if(msg?.type==='story3d:guide'){if(this.session.current.id===this.session.context.game.initial_state.current_scene_id)this.guide();else this.openTask();}
      if(msg?.type==='story3d:task'&&this.session.nextSource()===null)this.openTask();
      if(msg?.type==='story3d:world'&&Number.isInteger(msg.world)&&msg.world>=1&&msg.world<=this.session.presentation.scenes.length&&!this.blocked())this.switchWorld(msg.world,msg.arrival);
      if(msg?.type==='story3d:object'&&this.session.presentation.objects.some(o=>o.number===msg.number)){this.scenePickedSources.add(`${this.session.current.id}:${msg.number}`);this.gesture.click(msg.number);}
      if(msg?.type==='story3d:blocked'){
        this.notify(msg.reason);this.active=false;
        if(msg.token===this.token&&['blocked_path','unverified_ground'].includes(msg.code)&&this.session.current.requiredSources.includes(msg.number)){
          this.readOnlySources.add(`${this.session.current.id}:${msg.number}`);this.inspect(msg.number);
        }
      }
      if(msg?.type==='story3d:arrived'&&(msg.token===this.token||msg.manual===true&&this.session.current.requiredSources.includes(msg.number))){
        this.active=false;
        if(this.session.current.requiredSources.includes(msg.number)){
          this.arrivedSources.add(`${this.session.current.id}:${msg.number}`);this.scenePickedSources.add(`${this.session.current.id}:${msg.number}`);
          this.inspect(msg.number);
        }
        else if(this.session.presentation.stageTargets[this.session.current.id]===msg.number)this.openTask();
        else this.notify(this.t('已走近；呢度冇目前任務。','You have arrived; there is no current task here.'));
      }
    };
    addEventListener('message',this.listener);
    this.frame.addEventListener('load',()=>this.post({type:'story3d:ping'}));
    this.blocked=()=>this.session.paused||Boolean(document.querySelector('dialog:modal'))||!document.getElementById('dialogue').hidden;
    this.observer=new MutationObserver(()=>{this.post({type:'story3d:pause',paused:this.blocked()});this.post({type:'story3d:activity',active:['spot-difference','timeline','image-puzzle'].includes(this.session.current.plugin?.kind)&&Boolean(document.getElementById('story-panel').matches(':modal'))});});
    this.observer.observe(document.body,{subtree:true,attributes:true,attributeFilter:['open','hidden']});
    const nav=document.createElement('nav');nav.className='world-select';this.worldButtons=new Map();
    for(const [index]of this.session.presentation.scenes.entries()){const i=index+1;const b=document.createElement('button');b.textContent=this.t(`場景 ${i}`,`View ${i}`);b.disabled=i===this.world;b.setAttribute('aria-pressed',String(i===this.world));b.onclick=()=>this.post({type:'story3d:navigate',world:i});this.worldButtons.set(i,b);nav.append(b);}
    if(this.session.presentation.scenes.length>1)document.getElementById('stage').append(nav);
    if(this.deferred){this.qualityButton=document.createElement('button');this.qualityButton.id='quality-button';this.qualityButton.hidden=true;this.qualityButton.onclick=()=>this.post({type:'story3d:quality',value:this.qualityName==='low'?'standard':'low'});menu.before(this.qualityButton);this.updateQualityLabel();}
  }
  t(zh,en){return this.getLocale()==='en'?en:zh;}
  setLocale(locale,force=false){if(this.locale===locale&&!force)return;this.locale=locale;this.menuSummary.textContent=this.t('選單','Menu');for(const[i,b]of this.worldButtons??[])b.textContent=this.t(`場景 ${i}`,`View ${i}`);this.updateQualityLabel();this.post({type:'story3d:locale',locale});}
  updateQualityLabel(){if(!this.qualityButton)return;this.qualityButton.textContent=this.t('畫面品質：','Graphics quality: ')+this.t(this.qualityName==='low'?'低':'標準',this.qualityName==='low'?'Low':'Standard');this.qualityButton.title=this.t('按一下切換低／標準畫面品質；保留已建立嘅 LOD','Switch Low / Standard graphics quality without rebuilding LOD');}
  prepare(onProgress){
    this.preparation.onProgress=onProgress;
    return this.preparation.start(message=>{this.preparationMessage=message;if(this.ready)this.post({...message,locale:this.getLocale()});else this.frame.src=`/world/${this.world}/scene3d/index.html?render=${this.renderMode}&player=1`;}).then(()=>{this.preparationMessage=null;if(this.qualityButton)this.qualityButton.hidden=false;});
  }
  post(message){this.frame.contentWindow?.postMessage(message,location.origin);}
  switchWorld(world,arrival=null){
    if(world===this.world)return;
    if(arrival&&(!Number.isFinite(arrival.yaw)||!Number.isFinite(arrival.pitch)||Math.abs(arrival.yaw)>180||Math.abs(arrival.pitch)>90)){this.notify(this.t('導航方向資料無效，已停止切換。','Invalid arrival orientation; view change stopped.'));return;}
    this.cancelMotion();this.ready=false;this.world=world;
    for(const [number,button]of this.worldButtons){button.disabled=number===world;button.setAttribute('aria-pressed',String(number===world));}
    const query=new URLSearchParams({render:this.renderMode});if(this.deferred)query.set('player','1');if(arrival){query.set('arrival_yaw',String(arrival.yaw));query.set('arrival_pitch',String(arrival.pitch));}
    this.frame.src=`/world/${world}/scene3d/index.html?${query}`;
  }
  startGuide(){if(this.ready&&this.world===1&&!this.blocked()&&this.session.current.id===this.session.context.game.initial_state.current_scene_id&&!this.guideStarted){this.guideStarted=true;this.guide();}}
  click(n){this.gesture.click(n);}
  key(n,approach){this.gesture.key(n,approach);}
  locate(number){this.post({type:'story3d:focus',number});}
  hasArrived(number){return this.arrivedSources.has(`${this.session.current.id}:${number}`);}
  atTaskView(){
    const access=this.session.current.access;
    return !access||this.session.presentation.scenes[this.world-1]?.id===access.view_id;
  }
  navigateToTask(){
    const target=this.session.presentation.scenes.findIndex(scene=>scene.id===this.session.current.access?.view_id)+1;
    if(!target||target===this.world)return;
    for(const id of ['source-dialog','notebook-dialog','story-panel'])document.getElementById(id).close();
    this.closeDialogue();
    this.post({type:'story3d:pause',paused:false});
    this.post({type:'story3d:navigate',world:target});
  }
  supportsInspection(number){
    const view=this.session.presentation.scenes[this.world-1]?.id;
    const world=this.session.presentation.spatialContext?.worlds.find(world=>world.view_id===view);
    return Boolean(world?.geometry?.result.objects.find(node=>node.key===`object:${number}`)
      ?.planning.enabled_interactions.includes('inspect'));
  }
  readOnlyObservation(number){if(this.session.current.access?.interaction==='inspect')return this.atTaskView()&&this.supportsInspection(number);return this.readOnlySources.has(`${this.session.current.id}:${number}`)||this.session.presentation.shots.some(shot=>shot.number===number&&!shot.available)||this.session.presentation.scenes.some(scene=>scene.hotspots.some(spot=>spot.number===number&&spot.pitch>=35));}
  canObserve(number){if(!this.atTaskView())return false;if(this.session.current.plugin?.kind==='scene-search'&&!this.scenePickedSources.has(`${this.session.current.id}:${number}`))return false;return this.readOnlyObservation(number)||this.hasArrived(number);}
  inspectWithAccess(number){
    if(!this.atTaskView()){
      const target=this.session.presentation.scenes.findIndex(scene=>scene.id===this.session.current.access.view_id)+1;
      this.notify(this.t(`請沿導航到場景 ${target} 再查看。`,`Follow navigation to view ${target} to inspect this record.`));return;
    }
    if(this.session.current.access&&!this.supportsInspection(number)){
      if(!this.session.current.requiredSources.includes(number)){this.cancelMotion();this.inspect(number);return;}
      this.notify(this.t('呢個視點未登記此物件嘅查看位置，請沿導航前往。','This object is not registered for inspection here. Follow navigation to its view.'));return;
    }
    this.notify(this.t(`正在查看 ${String(number).padStart(2,'0')} 號物件…`,`Opening object ${String(number).padStart(2,'0')}…`));
    if(!this.ready||this.canObserve(number)){this.cancelMotion();this.inspect(number);return;}
    clearTimeout(this.pendingInspection?.timer);
    const request=++this.accessSequence;const timer=setTimeout(()=>{if(this.pendingInspection?.request===request){this.cancelMotion();this.inspect(number);}},1500);
    this.pendingInspection={request,number,stage:this.session.current.id,world:this.world,timer};
    this.post({type:'story3d:check-access',number,request});
  }
  approach(number){
    if(!this.ready){this.notify(this.t('場景仍在準備。','The scene is still preparing.'));return;}
    for(const id of ['source-dialog','notebook-dialog','story-panel'])document.getElementById(id).close();
    this.closeDialogue();this.active=true;
    if(this.readOnlyObservation(number)){this.active=false;this.locate(number);this.inspect(number);return;}
    this.post({type:'story3d:approach',number,token:++this.token});
  }
  cancelMotion(){this.active=false;clearTimeout(this.pendingInspection?.timer);this.pendingInspection=null;this.token++;this.post({type:'story3d:cancel'});}
  remember(){}
  restore(){this.notify(this.t('故事進度已恢復；位置從場景起點開始。','Story progress restored; the camera starts at the scene entry.'));}
  leave(){this.cancelMotion();this.closeDialogue();}
  closeTask(){this.post({type:'story3d:pause',paused:this.blocked()});}
  setSpeaker(){}
  highlightSpeaker(){}
  renderActors(){
    this.post({type:'story3d:activity',active:['spot-difference','timeline','image-puzzle'].includes(this.session.current.plugin?.kind)&&Boolean(document.getElementById('story-panel').matches(':modal'))});
    this.post({type:'story3d:pause',paused:this.blocked()});
    const search=this.session.current.plugin?.kind==='scene-search'&&!this.session.taskDone();const number=search?null:this.session.nextSource();
    const object=this.session.presentation.objects.find(o=>o.number===number);
    this.post({type:'story3d:objective',number,stage:this.session.current.id,token:this.token,mode:search?'search':'inspect',title:search?this.t('搜尋房間物件','Find the room objects'):object?.historical_title??'',paused:this.blocked()});
  }
}
