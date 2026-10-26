import {ObjectGesture,ApproachFlow} from './interaction.mjs?rev=ui3-navigation-dialogue';
const $=id=>document.getElementById(id);
const keyDirections={w:[0,-1],W:[0,-1],ArrowUp:[0,-1],a:[-1,0],A:[-1,0],ArrowLeft:[-1,0],s:[0,1],S:[0,1],ArrowDown:[0,1],d:[1,0],D:[1,0],ArrowRight:[1,0]};
/** View adapter for a fixed-shot actor theatre over the existing panorama. */
export class CinematicView {
  constructor({session,inspect,openTask,notify,refresh,isTalking=()=>false,closeDialogue=()=>{}}){
    this.isTalking=isTalking;this.closeDialogue=closeDialogue;this.session=session;this.inspect=inspect;this.openTask=openTask;this.notify=notify;this.refresh=refresh;this.flow=new ApproachFlow();this.keys=new Set();this.ready=false;this.last=0;this.lastMoving=false;this.frame=$('museum');this.tokenTimeout=null;
    this.gesture=new ObjectGesture({inspect:n=>{this.cancelMotion();inspect(n);},approach:n=>this.approach(n)});
    this.bind();this.post({type:'pastport:ping'});this.raf=requestAnimationFrame(t=>this.tick(t));
  }
  get active(){return this.flow.phase!=='viewing';}
  post(message){this.frame.contentWindow?.postMessage(message,location.origin);}
  click(number){this.gesture.click(number);}
  key(number,approach){this.gesture.key(number,approach);}
  cancelMotion(){this.keys.clear();this.flow.stop();this.remember();}
  locate(number){this.gesture.clear();if(this.active)this.leave();this.post({type:'pastport:focus',number,camera:this.session.presentation.shots.find(s=>s.number===number&&s.available)?.camera});}
  approach(number,restored=null){
    const shot=this.session.presentation.shots.find(s=>s.number===number);
    if(!shot?.available){this.notify(shot?.reason??'暂时没有可用的接近分镜。');return;}
    if(!this.ready){this.notify('全景仍在加载，请稍后再走近。');return;}
    this.gesture.clear();this.keys.clear();for(const id of ['source-dialog','notebook-dialog','story-panel'])if($(id).open)$(id).close();
    const token=this.flow.begin(shot);this.restored=restored;clearTimeout(this.tokenTimeout);
    $('stage').classList.add('shot-active');this.frame.style.pointerEvents='none';$('walk-layer').hidden=true;$('scene-curtain').classList.add('visible');
    $('shot-label').textContent=`${String(number).padStart(2,'0')} · ${this.session.presentation.objects.find(o=>o.number===number).historical_title}`;
    const ground=$('walk-ground-polygon');ground.setAttribute('points',shot.boundary.map(p=>p.join(',')).join(' '));
    this.renderActors();this.post({type:'pastport:shot',number,sceneId:shot.sceneId,camera:shot.camera,token,origin:restored?.beforeView??null});
    this.tokenTimeout=setTimeout(()=>{if(this.flow.phase==='turning'&&this.flow.token===token){this.leave();this.notify('分镜加载未完成，请重新双击物件。');}},7000);this.refresh();
  }
  remember(){if(!this.active||!this.flow.walker||this.flow.phase==='entering')return;try{this.session.rememberShot({number:this.flow.shot.number,position:[...this.flow.walker.position],beforeView:this.flow.beforeView,phase:this.flow.phase==='task'?'task':'walking'});}catch(error){this.notify(error.message);}}
  restore(){const saved=this.session.shotState;if(saved)this.approach(saved.number,saved);}
  leave(){this.gesture.clear();clearTimeout(this.tokenTimeout);this.keys.clear();const before=this.flow.beforeView;this.flow.leave();$('walk-layer').hidden=true;$('stage').classList.remove('shot-active');$('scene-curtain').classList.remove('visible');this.frame.style.pointerEvents='';if($('story-panel').open)$('story-panel').close();this.closeDialogue();this.post({type:'pastport:restore',view:before});try{this.session.rememberShot(null);}catch(error){this.notify(error.message);}this.refresh();}
  canOpenTask(){const id=this.session.current.id;return !this.session.state.ending_id&&this.flow.shot?.taskScenes?.includes(id);}
  renderActors(){
    const root=$('cast');root.replaceChildren();if(!this.flow.shot)return;
    const camera=this.flow.shot.camera;
    const project=actor=>{const cy=camera.yaw*Math.PI/180,cp=camera.pitch*Math.PI/180,y=actor.yaw*Math.PI/180,p=actor.pitch*Math.PI/180;const wx=Math.sin(y)*Math.cos(p),wy=Math.sin(p),wz=Math.cos(y)*Math.cos(p),x=wx*Math.cos(cy)-wz*Math.sin(cy),z=wz*Math.cos(cy)+wx*Math.sin(cy),yy=wy*Math.cos(cp)-z*Math.sin(cp),zz=z*Math.cos(cp)+wy*Math.sin(cp),t=Math.tan(camera.hfov*Math.PI/360);return zz<=0?null:[50+50*x/(zz*t),50-50*yy/(zz*t*9/16)];};
    for(const actor of this.session.presentation.worldActors){const point=project(actor);if(!point||point[0]<3||point[0]>97||point[1]<52||point[1]>101)continue;const name=actor.name,node=document.createElement('button');node.className='actor';node.type='button';node.setAttribute('aria-label',`走近${name}交谈`);node.style.left=point[0]+'%';node.style.top=point[1]+'%';node.style.setProperty('--actor-depth',String(.72+(point[1]-60)/75));node.dataset.speaker=name;node.dataset.nativeFacing=String(actor.nativeFacing);
      const shadow=document.createElement('span');shadow.className='shadow';const sprite=document.createElement('span');sprite.className='sprite';sprite.style.backgroundPosition=`${actor.frame*100/3}% 100%`;const label=document.createElement('span');label.className='actor-label';label.textContent=name;node.append(shadow,sprite,label);
      node.onclick=event=>{event.stopPropagation();if(this.isTalking())return;this.keys.clear();if(actor.number!==this.flow.shot.number)this.approach(actor.number);else this.flow.reopen();$('story-panel').close();};root.append(node);
    }
    const object=this.session.presentation.objects.find(o=>o.number===this.flow.shot.number);$('shot-object').textContent=`ⓘ ${String(object.number).padStart(2,'0')}`;
    const spot=this.session.presentation.scenes.find(s=>s.id===this.flow.shot.sceneId)?.hotspots.find(h=>h.number===object.number);
    const c=this.flow.shot.camera,vf=2*Math.atan(Math.tan(c.hfov*Math.PI/360)*9/16),y=50-50*Math.tan((spot.pitch-c.pitch)*Math.PI/180)/Math.tan(vf/2);$('shot-object').style.left='50%';$('shot-object').style.top=`${y}%`;
    if(this.speaker)this.setSpeaker(this.speaker);else this.highlightSpeaker();
  }
  highlightSpeaker(){const c=this.session.current;const lastId=this.session.entry().activity.seen.at(-1);const speaker=c.plugin.items?.find(i=>i.id===lastId)?.speaker;for(const node of $('cast').children)node.classList.toggle('speaking',speaker===node.dataset.speaker&&$('story-panel').open);}
  setSpeaker(name,action=null){this.speaker=name;for(const node of $('cast').children){node.classList.toggle('speaking',node.dataset.speaker===name);if(node.dataset.speaker===name&&action){node.classList.remove('reacting');void node.offsetWidth;node.classList.add('reacting');}}}
  closeTask(){this.flow.closeTask();this.keys.clear();this.remember();this.highlightSpeaker();}
  bind(){
    addEventListener('message',event=>{if(event.source!==this.frame.contentWindow||event.origin!==location.origin)return;const msg=event.data;if(msg?.type==='pastport:ready'){this.ready=true;if(this.restorePending){this.restorePending=false;this.restore();}return;}
      if(msg?.type==='pastport:npc'&&Number.isSafeInteger(msg.number)){this.key(msg.number,true);return;}
      if(msg?.type==='pastport:object'&&Number.isSafeInteger(msg.number)){if(msg.gesture==='inspect')this.key(msg.number,false);else if(msg.gesture==='approach')this.key(msg.number,true);else this.click(msg.number);}
      if(msg?.type==='pastport:shot-ready'&&msg.token===this.flow.token){clearTimeout(this.tokenTimeout);this.flow.entryDuration=matchMedia('(prefers-reduced-motion: reduce)').matches ? 0.01 : 0.65;if(this.flow.ready(msg.token,msg.beforeView,this.restored?.position??null)){
        $('scene-curtain').classList.remove('visible');$('walk-layer').hidden=false;$('walk-layer').focus();if(this.restored?.phase==='task'){this.flow.phase='task';this.openTask();}this.restored=null;this.refresh();
      }}
    });
    this.frame.addEventListener('load',()=>this.post({type:'pastport:ping'}));
    $('shot-object').onclick=event=>{event.stopPropagation();this.click(this.flow.shot.number);};$('shot-object').onkeydown=event=>{if(event.key==='Enter'){event.preventDefault();event.stopPropagation();this.key(this.flow.shot.number,event.shiftKey);}};
    $('walk-layer').addEventListener('pointerdown',event=>{if(event.target.closest('button')||this.session.paused||document.querySelector('dialog[open]'))return;const rect=$('walk-layer').getBoundingClientRect();const point=[(event.clientX-rect.left)/rect.width*100,(event.clientY-rect.top)/rect.height*100];if(!this.flow.goTo(point))this.notify('这里没有可走的地面。');});
    addEventListener('keydown',event=>{if(!this.active||document.querySelector('dialog[open]')||this.isTalking())return;if(event.key==='Escape'){event.preventDefault();this.leave();return;}if(event.target.closest('button,input,select,textarea'))return;if(keyDirections[event.key]){event.preventDefault();if(!this.keys.has(event.key))this.flow.tick(0.045,keyDirections[event.key],this.session.paused);this.keys.add(event.key);}});
    addEventListener('keyup',event=>this.keys.delete(event.key));
    for(const button of document.querySelectorAll('[data-dir]')){button.onpointerdown=event=>{event.preventDefault();button.setPointerCapture(event.pointerId);const key={up:'w',down:'s',left:'a',right:'d'}[button.dataset.dir];this.flow.tick(0.045,keyDirections[key],this.session.paused);this.keys.add(key);};for(const type of ['pointerup','pointercancel','lostpointercapture'])button.addEventListener(type,()=>this.keys.clear());}
    $('story-panel').addEventListener('close',()=>this.closeTask());addEventListener('blur',()=>this.cancelMotion());document.addEventListener('visibilitychange',()=>{if(document.hidden)this.cancelMotion();});addEventListener('pagehide',()=>{this.remember();this.gesture.clear();cancelAnimationFrame(this.raf);});
  }
  tick(time){const dt=this.last?(time-this.last)/1000:0;this.last=time;const axis=[0,0];for(const key of this.keys){const p=keyDirections[key];if(p){axis[0]+=p[0];axis[1]+=p[1];}}
    const paused=this.session.paused||this.isTalking()||Boolean(document.querySelector('dialog[open]'));const arrived=this.flow.tick(dt,axis,paused);
    if(this.flow.position){const[x,y]=this.flow.position,actor=$('player');actor.style.left=`${x}%`;actor.style.top=`${y}%`;actor.style.transform=`translate(-50%,-94%) scale(${.72+(y-60)/75})`;actor.querySelector('.sprite').style.transform=`scaleX(${this.flow.walker.facing})`;actor.classList.toggle('walking',!paused&&(this.flow.phase==='entering'||this.flow.walker.moving));actor.style.zIndex=String(Math.round(y*10));
      const actors=[...$('cast').children];const speaking=actors.find(n=>n.dataset.speaker===this.speaker);
      for(const npc of actors){const nx=parseFloat(npc.style.left),ny=parseFloat(npc.style.top);npc.style.zIndex=String(Math.round(ny*10));const others=actors.filter(n=>n!==npc).sort((a,b)=>Math.hypot(parseFloat(a.style.left)-nx,parseFloat(a.style.top)-ny)-Math.hypot(parseFloat(b.style.left)-nx,parseFloat(b.style.top)-ny));const target=speaking&&speaking!==npc?speaking:others[0];const targetX=target?parseFloat(target.style.left):x,desired=targetX<nx?-1:1; npc.querySelector('.sprite').style.transform=`scaleX(${desired/Number(npc.dataset.nativeFacing)})`;}
      if(paused&&speaking&&this.flow.walker&&!this.flow.walker.moving)actor.querySelector('.sprite').style.transform=`scaleX(${parseFloat(speaking.style.left)<x?-1:1})`;
      const moving=this.flow.walker.moving;if(this.lastMoving&&!moving)this.remember();this.lastMoving=moving;
    }
    if(arrived){this.remember();if(this.canOpenTask())this.openTask();else{this.flow.closeTask();this.notify('已走近。这里目前没有待办任务，可以查看资料或按Esc返回环视。');}}
    this.raf=requestAnimationFrame(t=>this.tick(t));
  }
}
