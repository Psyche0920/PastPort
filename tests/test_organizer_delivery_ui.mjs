import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFile} from 'node:fs/promises';

// Exercise the actual DOM controller without starting a live Organizer or touching user data.
const source=await readFile(new URL('../frontend/organizer/app.mjs',import.meta.url),'utf8');
function extract(start,end){const begin=source.indexOf(start),finish=source.indexOf(end,begin);assert.ok(begin>=0&&finish>begin);return source.slice(begin,finish);}
class Element {
  constructor(tag,content=''){this.tag=tag;this.textContent=content;this.children=[];}
  append(...nodes){this.children.push(...nodes);}
  replaceChildren(...nodes){this.children=[...nodes];}
}
const live={site_id:'site',name:'Site',current:{job_id:'job',version:'v1'},history:[]};
function controller({confirm=true,api=async()=>({...live,current:null}),refresh=async()=>{}}={}){
  const root=new Element('div'),messages=[];
  const context={document:{createElement:tag=>new Element(tag)},$:()=>root,text:(tag,value)=>new Element(tag,value),versionLabel:()=> 'Demo',timeText:()=>'',getLanguage:()=> 'en',confirm:()=>confirm,api,message:value=>messages.push(value),refreshDeliveries:refresh};
  vm.createContext(context);
  vm.runInContext(`let deliveryState={publications:${JSON.stringify([live,{...live,site_id:'hidden',current:null}])}},deliveryBusy=0,deliveryEpoch=0,deliverySignature='';${extract('function renderPublications(){','function interacting(){')}renderPublications();`,context);
  return {root,messages,context,button:()=>root.children[0].children.find(node=>node.textContent==='解除发布')};
}
test('only current publications have cards; cancelling does not send DELETE',async()=>{
 let calls=0;const ui=controller({confirm:false,api:async()=>{calls++;}});
 assert.equal(ui.root.children.length,1);await ui.button().onclick();assert.equal(calls,0);assert.equal(ui.root.children[0].tag,'article');
});
test('successful unpublish removes the card even when the next refresh fails',async()=>{
 const ui=controller({api:async(path,options)=>{assert.equal(options.method,'DELETE');assert.equal(JSON.parse(options.body).expected_version,'v1');return {...live,current:null};},refresh:async()=>{throw Error('offline');}});
 await ui.button().onclick();assert.equal(ui.root.children[0].tag,'p');assert.match(ui.messages.at(-1),/已解除发布/);
});
test('failed DELETE keeps the card and the error; it is not reported as success',async()=>{
 const ui=controller({api:async()=>{throw Error('version conflict');},refresh:async()=>{throw Error('offline');}});
 await ui.button().onclick();assert.equal(ui.root.children[0].tag,'article');assert.equal(ui.messages.at(-1),'version conflict');
});
test('an earlier in-flight refresh cannot resurrect an unpublished card',async()=>{
 let release;const pending=new Promise(resolve=>{release=resolve;});
 const context={api:async()=>{await pending;return [];},$:()=>({}),interacting:()=>false,renderPackages:()=>{},renderPublications:()=>{},Date};vm.createContext(context);
 vm.runInContext(`let deliveryEpoch=0,deliverySignature='',deliveryDeferred=false;let deliveryState={packages:[],publications:[],sites:[]};${extract('async function refreshDeliveries(force=false){','// Other members')}globalThis.request=refreshDeliveries(true);`,context);
 vm.runInContext("deliveryEpoch++;deliveryState.publications=[{site_id:'site',current:null}];",context);
 release();await context.request;assert.equal(vm.runInContext('deliveryState.publications[0].current',context),null);
});
