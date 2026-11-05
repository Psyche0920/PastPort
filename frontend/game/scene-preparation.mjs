/** Bounded user-started renderer preparation. No gameplay or source approval changes. */
export class ScenePreparation {
  constructor({onProgress=()=>{},timeoutMs=600000,id=()=>crypto.randomUUID()}={}) {
    Object.assign(this,{onProgress,timeoutMs,id});this.phase='idle';this.pending=null;
  }
  start(send,{buildLod=true}={}){
    if(this.phase==='ready')return Promise.resolve();
    if(this.pending)return this.pending.promise;
    const request=this.id();let resolve,reject;
    const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});
    const timer=setTimeout(()=>this.finish(false,new Error('SCENE_PREPARATION_TIMEOUT')),this.timeoutMs);
    this.phase='preparing';this.pending={request,promise,resolve,reject,timer};
    try{send({type:'story3d:prepare',request,buildLod});}catch(error){this.finish(false,error);}
    return promise;
  }
  accept(message){
    if(!this.pending||message?.request!==this.pending.request)return false;
    if(message.type==='story3d:preparation-progress'){this.onProgress(message.phase);return true;}
    if(message.type==='story3d:prepared'){this.finish(true);return true;}
    if(message.type==='story3d:preparation-failed'){this.finish(false,new Error('SCENE_PREPARATION_FAILED'));return true;}
    return false;
  }
  finish(ok,error){const pending=this.pending;if(!pending)return;clearTimeout(pending.timer);this.pending=null;this.phase=ok?'ready':'error';if(ok)pending.resolve();else pending.reject(error);}
}

/** Skipping LOD still waits for the loaded scene, without invoking its optimizer. */
export async function prepareRenderer(renderer, buildLod = true) {
  if (buildLod) {
    if (typeof renderer?.prepare !== 'function') throw new Error('Renderer LOD is unavailable');
    await renderer.prepare();
  }
  if (!buildLod) await renderer?.prepareWithoutLod?.();
  const quality = renderer?.getQuality?.();
  return ['low','standard'].includes(quality) ? quality : null;
}
