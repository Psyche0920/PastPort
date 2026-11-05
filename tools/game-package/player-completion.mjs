/** Runtime adapters translate presentation completion; they never decide game rules. */
import {createHash} from 'node:crypto';
import {readFile} from 'node:fs/promises';
import {join} from 'node:path';
const adapters=Object.freeze([{
  id:'authored-adventure-v1',
  module:'prototype/adventure.mjs',
  sha256:'2ea3ea47c7d45ac45687fa7af22b86916133648d8251eef093e2fa97eadc769d',
  selector:'#panel[open] .ending-grid',
  saveKeys:['pastport:chapter-record-and-service:adventure:v1'],
}]);
export async function completionAdapter(root) {
  for(const adapter of adapters){
    let bytes;
    try {bytes=await readFile(join(root,adapter.module));}
    catch(error){if(error.code==='ENOENT')continue;throw error;}
    if(createHash('sha256').update(bytes).digest('hex')===adapter.sha256)return adapter;
  }
  return {id:'platform-event-v1',selector:null,saveKeys:[]};
}
/** Runs synchronously before original scripts so account caches never mix. */
export function installCompletionBridge(config, platformOrigin) {
  const params=new URL(location.href).searchParams;
  const run=params.get('passportRun'), scope=params.get('passportScope');
  if(!run || !/^[a-f0-9]{64}$/.test(scope??'') || window.parent===window)return;
  if(config.saveKeys.length){
    const prefix='pastport:account:'+scope+':';
    const get=Storage.prototype.getItem,set=Storage.prototype.setItem,remove=Storage.prototype.removeItem;
    const tracked=(storage,key)=>storage===localStorage && config.saveKeys.includes(String(key));
    // Mirror tracked writes to the platform, which saves them to the signed-in account.
    const changed=(key,value)=>window.parent.postMessage({type:'pastport:save-change',run,key:String(key),value},platformOrigin);
    Storage.prototype.getItem=function(key){return get.call(this,tracked(this,key)?prefix+key:key);};
    Storage.prototype.setItem=function(key,value){const match=tracked(this,key);set.call(this,match?prefix+key:key,value);if(match)changed(key,String(value));};
    Storage.prototype.removeItem=function(key){const match=tracked(this,key);remove.call(this,match?prefix+key:key);if(match)changed(key,null);};
    const start=()=>{for(const held of document.querySelectorAll('script[type="pastport/deferred-module"]')){
      const script=document.createElement('script');
      for(const attribute of held.attributes)if(attribute.name!=='type')script.setAttribute(attribute.name,attribute.value);
      script.type='module';script.textContent=held.textContent;held.replaceWith(script);
    }};
    const whenParsed=callback=>document.readyState==='loading' ? document.addEventListener('DOMContentLoaded',callback,{once:true}) : callback();
    const timer=setTimeout(()=>{
      window.removeEventListener('message',hydrate);
      window.parent.postMessage({type:'pastport:save-error',run},platformOrigin);
    },10000);
    function hydrate(event){
      if(event.source!==window.parent || event.origin!==platformOrigin || event.data?.type!=='pastport:save-state' || event.data.run!==run)return;
      clearTimeout(timer);window.removeEventListener('message',hydrate);
      for(const key of config.saveKeys){
        const raw=event.data.entries?.[key];
        if(typeof raw==='string')set.call(localStorage,prefix+key,raw);else remove.call(localStorage,prefix+key);
      }
      whenParsed(start);
    }
    window.addEventListener('message',hydrate);
    window.parent.postMessage({type:'pastport:save-ready',run},platformOrigin);
  }
  let sent=false;
  const finished=()=>{
    if(sent)return;
    sent=true;
    window.parent.postMessage({type:'pastport:ending',run},platformOrigin);
  };
  // New games emit this explicit event; known legacy UIs use a pinned adapter.
  window.addEventListener('pastport:completed',event=>{
    if(typeof event.detail?.endingId==='string' && event.detail.endingId.length)finished();
  });
  if(config.selector){
    const observe=()=>{if(document.querySelector(config.selector))finished();};
    new MutationObserver(observe).observe(document.documentElement,{childList:true,subtree:true,attributes:true,attributeFilter:['open','hidden']});
    observe();
  }
}
export function completionBootstrap(config,origin) {
  const safe=value=>JSON.stringify(value).replaceAll('<','\\u003c');
  return `<script>(${installCompletionBridge.toString()})(${safe(config)},${safe(origin)});</script>`;
}
