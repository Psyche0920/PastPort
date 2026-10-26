import {WalkMesh,Walker} from './walkmesh.mjs';
/** One arbiter prevents an introduction modal from swallowing the second click. */
export class ObjectGesture {
  constructor({inspect,approach,schedule=(callback,delay)=>globalThis.setTimeout(callback,delay),cancel=timer=>globalThis.clearTimeout(timer),delay=350}){this.inspect=inspect;this.approach=approach;this.schedule=schedule;this.cancel=cancel;this.delay=delay;this.pending=null;}
  clear(){if(this.pending)this.cancel(this.pending.timer);this.pending=null;}
  click(number){if(this.pending?.number===number){this.clear();this.approach(number);return;}if(this.pending){const old=this.pending.number;this.clear();this.inspect(old);}const pending={number,timer:null};pending.timer=this.schedule(()=>{if(this.pending===pending){this.pending=null;this.inspect(number);}},this.delay);this.pending=pending;}
  key(number,approach=false){this.clear();(approach?this.approach:this.inspect)(number);}
}
/** Deterministic camera/entry/walking/arrival state; scene rendering stays in the view. */
export class ApproachFlow {
  constructor(){this.phase='viewing';this.shot=null;this.walker=null;this.token=0;this.elapsed=0;this.armed=false;this.mustLeave=false;this.beforeView=null;this.entryDuration=.65;}
  begin(shot){if(!shot.available)throw new Error(shot.reason);this.token++;this.shot=shot;this.phase='turning';this.walker=null;this.elapsed=0;this.armed=false;this.mustLeave=false;return this.token;}
  ready(token,beforeView=null,restored=null){if(token!==this.token||this.phase!=='turning')return false;this.beforeView=beforeView;this.walker=new Walker(new WalkMesh(this.shot.boundary,this.shot.obstacles),restored??this.shot.spawn,210);this.phase=restored?'walking':'entering';this.elapsed=0;this.armed=true;if(restored)this.walker.goTo(this.shot.approach);return true;}
  get position(){if(!this.walker)return null;if(this.phase==='entering'){const fraction=Math.min(1,this.elapsed/this.entryDuration);return[this.shot.spawn[0],110+(this.shot.spawn[1]-110)*fraction];}return this.walker.position;}
  near(){return this.walker&&Math.hypot((this.walker.position[0]-this.shot.approach[0])*16,(this.walker.position[1]-this.shot.approach[1])*9)<=this.shot.radius;}
  stop(){this.walker?.stop();if(this.phase==='entering')return;this.mustLeave=this.near();this.armed=true;if(this.phase!=='viewing'&&this.phase!=='turning')this.phase='walking';}
  goTo(point){if(!this.walker||this.phase==='turning'||this.phase==='entering')return false;this.phase='walking';this.armed=true;this.mustLeave=false;return this.walker.goTo(point);}
  reopen(){return this.goTo(this.shot.approach);}
  closeTask(){if(this.phase==='task'){this.phase='walking';this.armed=false;this.mustLeave=true;}}
  tick(seconds,axis=[0,0],paused=false){if(paused||!this.walker)return false;const dt=Math.min(.05,Math.max(0,seconds));
    if(this.phase==='entering'){this.elapsed+=dt;if(this.elapsed>=this.entryDuration){this.phase='walking';this.walker.goTo(this.shot.approach);this.armed=true;}return false;}
    if(this.phase!=='walking')return false;
    if(axis[0]||axis[1]){if(!this.manual){this.mustLeave=this.near();this.armed=true;}this.manual=true;}else this.manual=false;
    this.walker.tick(dt,axis);
    if(this.mustLeave&&!this.near()){this.mustLeave=false;this.armed=true;}
    if(this.armed&&!this.mustLeave&&this.near()&&!this.walker.route.length){this.armed=false;this.phase='task';this.walker.stop();return true;}return false;
  }
  leave(){this.token++;this.walker?.stop();this.phase='viewing';this.shot=null;this.walker=null;this.armed=false;this.manual=false;}
}
