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
  if (!buildLod) {
    if (typeof renderer?.prepareWithoutLod !== 'function') throw new Error('Renderer readiness is unavailable');
    await renderer.prepareWithoutLod();
  }
  const quality = renderer?.getQuality?.();
  return ['low','standard'].includes(quality) ? quality : null;
}


/** Adapt the bundled Spark viewer without changing its source snapshot or geometry. */
export class SparkScenePreparation {
  constructor({splat, spark, renderer, scene, camera, pixelRatio=()=>globalThis.devicePixelRatio||1}) {
    if (!splat?.initialized || typeof splat.createLodSplats !== 'function' ||
        typeof spark?.update !== 'function' || typeof renderer?.setPixelRatio !== 'function') {
      throw new Error('Spark scene preparation is unavailable');
    }
    Object.assign(this, {splat, spark, renderer, scene, camera, pixelRatio});
    this.quality='low';this.lodPending=null;
  }
  async prepare() {
    await this.splat.initialized;
    if (!this.splat.packedSplats?.lodSplats && !this.splat.extSplats?.lodSplats) {
      if (!this.lodPending) this.lodPending=this.splat.createLodSplats().catch(error=>{
        this.lodPending=null;throw error;
      });
      await this.lodPending;
      if (!this.splat.packedSplats?.lodSplats && !this.splat.extSplats?.lodSplats) {
        throw new Error('Spark LOD preparation did not produce a usable scene');
      }
    }
    this.splat.enableLod=true;this.spark.enableLod=true;this.spark.enableDriveLod=true;
    this.setQuality(this.quality);
    await this.spark.update({scene:this.scene,camera:this.camera});
  }
  async prepareWithoutLod() {
    await this.splat.initialized;
    this.splat.enableLod=false;this.spark.enableLod=false;this.spark.enableDriveLod=false;
    this.setQuality(this.quality);
    await this.spark.update({scene:this.scene,camera:this.camera});
  }
  setQuality(value) {
    if (!['low','standard'].includes(value)) throw new Error('Unsupported graphics quality');
    this.quality=value;
    this.renderer.setPixelRatio(Math.min(this.pixelRatio(),value==='low'?1:1.5));
    this.spark.lodSplatCount=value==='low'?500000:1500000;
    return value;
  }
  getQuality() {return this.quality;}
}
