import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {environmentActionState} from '../frontend/organizer/review.mjs';
import {readFile} from 'node:fs/promises';
const source=await readFile(new URL('../frontend/organizer/app.mjs',import.meta.url),'utf8');
const begin=source.indexOf('async function reviewProject(){');
const end=source.indexOf('async function refreshJobs()',begin);
class Element {
 constructor(tag,content=''){this.tag=tag;this.textContent=content;this.children=[];this.dataset={};this.handlers={};}
 append(...items){this.children.push(...items);}
 replaceChildren(...items){this.children=items;}
 addEventListener(name,handler){this.handlers[name]=handler;}
}
for(const [entry,evidenceBudget] of [['catalog3d',8],['idmlscene3d',16]]) test(`${entry} UI stops at environment preparation before Story and assembly`,async()=>{
 const root=new Element('section'),calls=[],pages=[];
 const context={loadedProject:'ordinary-pdf',document:{createElement:tag=>new Element(tag),querySelectorAll:()=>root.children.filter(n=>n.dataset.environmentProject)},environmentActionState,
   $:()=>root,text:(tag,value)=>new Element(tag,value),labels:{},stageLabels:{},
   api:async(path,options)=>{if(options){calls.push({path,options});return {job_id:'job'};}
     return path==='jobs'?[]:{materials:{project_id:'ordinary-pdf',entry_level:entry,files:[]},plan:{review_focus:[],reused:[],stages:[],missing_roles:[],generation_connected:true,message:''}};},
   generationOptions:(parent,needs3d,resume,budget)=>{assert.equal(needs3d,false);assert.equal(budget,evidenceBudget);return ()=>({authorize_model:true,max_evidence_calls:budget});},
   page:name=>pages.push(name),message:()=>{},refreshJobs:async()=>{},resetEnvironment:()=>{},
   environmentJob:null,sessionStorage:{setItem(){}},
   crypto:{randomUUID:()=> 'one-explicit-request'},};
 vm.createContext(context);vm.runInContext(source.slice(begin,end),context);
 await context.reviewProject();
 assert.equal(root.children.some(n=>n.textContent==='运行完整 3D 流程'),false);
 const button=root.children.find(n=>n.textContent==='准备资料与环境');
 assert.ok(button);assert.equal(button.disabled,false);await button.handlers.click();
 assert.equal(calls.length,1);assert.equal(calls[0].path,'materials/ordinary-pdf/jobs');
 const body=JSON.parse(calls[0].options.body);
 assert.equal(body.stop_after,'environment');assert.equal(body.authorize_model,true);assert.equal(body.max_evidence_calls,evidenceBudget);
 assert.deepEqual(pages,['make']);
});
