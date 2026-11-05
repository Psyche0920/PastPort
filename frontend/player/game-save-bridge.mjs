/** Hydrate before boot; namespace browser cache so accounts cannot share progress. */
export async function connectPlayerSave(platformOrigin, keys) {
  const run=new URL(location.href).searchParams.get('passportRun');
  if (!run || window.parent===window) return;
  const nativeGet=Storage.prototype.getItem;
  const nativeSet=Storage.prototype.setItem;
  const nativeRemove=Storage.prototype.removeItem;
  const saved=await new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>{cleanup();reject(new Error('Cannot load your account save. Return to the map and retry.'));},10000);
    const listener=event=>{
      if(event.source!==window.parent || event.origin!==platformOrigin || event.data?.type!=='pastport:save-state' || event.data.run!==run)return;
      cleanup();resolve(event.data);
    };
    function cleanup(){clearTimeout(timer);window.removeEventListener('message',listener);}
    window.addEventListener('message',listener);
    window.parent.postMessage({type:'pastport:save-ready',run},platformOrigin);
  });
  const prefix='pastport:account:'+saved.namespace+':';
  for(const key of keys){
    const raw=saved.entries[key];
    if(typeof raw==='string')nativeSet.call(localStorage,prefix+key,raw);
    else nativeRemove.call(localStorage,prefix+key);
  }
  const tracked=(storage,key)=>storage===localStorage && keys.includes(String(key));
  const changed=(key,value)=>window.parent.postMessage({type:'pastport:save-change',run,key:String(key),value},platformOrigin);
  Storage.prototype.getItem=function(key){return nativeGet.call(this,tracked(this,key)?prefix+key:key);};
  Storage.prototype.setItem=function(key,value){
    const match=tracked(this,key);nativeSet.call(this,match?prefix+key:key,value);
    if(match)changed(key,String(value));
  };
  Storage.prototype.removeItem=function(key){
    const match=tracked(this,key);nativeRemove.call(this,match?prefix+key:key);
    if(match)changed(key,null);
  };
}
