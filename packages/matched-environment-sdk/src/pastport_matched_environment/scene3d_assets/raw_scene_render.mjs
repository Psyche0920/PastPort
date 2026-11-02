/** Local-only offscreen rendering of registered SPZ assets; never generates geometry. */
import {spawn} from 'node:child_process';
import {createServer} from 'node:http';
import {readFile,writeFile,mkdtemp,rm} from 'node:fs/promises';
import {createReadStream} from 'node:fs';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {once} from 'node:events';

class DevToolsPipe {
  constructor(process){this.process=process;this.next=0;this.pending=new Map();this.buffer='';process.stdio[4].on('data',chunk=>{this.buffer+=chunk;let end;while((end=this.buffer.indexOf('\0'))>=0){const line=this.buffer.slice(0,end);this.buffer=this.buffer.slice(end+1);if(!line)continue;const msg=JSON.parse(line);if(msg.method==='Runtime.consoleAPICalled')console.log('PAGE',JSON.stringify(msg.params.args.map(a=>a.value??a.description)));if(msg.method==='Runtime.exceptionThrown')console.log('PAGE_ERROR',JSON.stringify(msg.params.exceptionDetails));const p=this.pending.get(msg.id);if(p){this.pending.delete(msg.id);clearTimeout(p.timeout);msg.error?p.reject(new Error(msg.error.message)):p.resolve(msg.result);}}});process.once('exit',()=>{for(const p of this.pending.values()){clearTimeout(p.timeout);p.reject(new Error('Offscreen browser exited'));}this.pending.clear();});}
  send(method,params={},sessionId){return new Promise((resolve,reject)=>{const id=++this.next;const timeout=setTimeout(()=>{this.pending.delete(id);reject(new Error('Offscreen browser operation timed out: '+method));},180000);this.pending.set(id,{resolve,reject,timeout});this.process.stdio[3].write(JSON.stringify({id,method,params,...(sessionId?{sessionId}:{})})+'\0');});}
}
const [directory,assets,browserExecutable]=process.argv.slice(2);
if(!directory||!assets||!browserExecutable)throw Error('Expected scene directory, installed asset directory and browser executable');
const root=path.resolve(directory),assetRoot=path.resolve(assets);
const allowed=new Set(['three.module.js','three.core.js','spark.module.js','Pass.js']);
const server=createServer(async(req,res)=>{try{const name=new URL(req.url,'http://127.0.0.1').pathname.slice(1);let file;if(['scene.spz','capture.html'].includes(name))file=path.join(root,name);else if(allowed.has(name))file=path.join(assetRoot,name);else{res.writeHead(404);res.end();return;}res.setHeader('Content-Type',name.endsWith('.js')?'text/javascript':name.endsWith('.html')?'text/html':'application/octet-stream');res.setHeader('Cache-Control','no-store');createReadStream(file).on('error',()=>{res.destroy();}).pipe(res);}catch{res.writeHead(500);res.end();}});
const profile=await mkdtemp(path.join(tmpdir(),'pastport-raw-capture-'));
let child;
try{
 server.listen(0,'127.0.0.1');await once(server,'listening');const address=server.address();
 child=spawn(browserExecutable,['--headless=new','--no-first-run','--no-default-browser-check','--disable-background-networking','--disable-component-update','--disable-dev-shm-usage',...(process.platform==='darwin'?['--use-angle=metal']:[]),'--disable-background-timer-throttling','--disable-renderer-backgrounding','--remote-debugging-pipe','--user-data-dir='+profile],{stdio:['ignore','ignore','pipe','pipe','pipe']});
 let errors='';child.stderr.on('data',b=>{if(errors.length<16000)errors+=b;});
 const pipe=new DevToolsPipe(child);console.log('CAPTURE_START',new Date().toISOString());const gpu=await pipe.send('SystemInfo.getInfo');console.log('GPU',JSON.stringify(gpu.gpu.devices));
 const target=await pipe.send('Target.createTarget',{url:'about:blank'});
 const attached=await pipe.send('Target.attachToTarget',{targetId:target.targetId,flatten:true});const sid=attached.sessionId;
 await pipe.send('Runtime.enable',{},sid);await pipe.send('Page.enable',{},sid);await pipe.send('Page.setWebLifecycleState',{state:'active'},sid);
 await pipe.send('Page.navigate',{url:'http://127.0.0.1:'+address.port+'/capture.html'},sid);
 const deadline=Date.now()+150000;
 let completed=false;
 while(Date.now()<deadline){const state=await pipe.send('Runtime.evaluate',{expression:'JSON.stringify({ready:window.captureReady,error:window.captureError})',returnByValue:true},sid);const value=JSON.parse(state.result.value||'{}');if(value.error)throw Error(value.error);if(value.ready){completed=true;break;}await new Promise(r=>setTimeout(r,200));}
 if(!completed)throw Error('SPZ rendering did not become ready within its bound');
 const result=await pipe.send('Runtime.evaluate',{expression:'window.captureFaces()',awaitPromise:true,returnByValue:true},sid);
 if(result.exceptionDetails)throw Error(result.exceptionDetails.exception?.description||result.exceptionDetails.text);
 const faces=result.result.value;
 if(!Array.isArray(faces)||faces.length!==6)throw Error('Expected six rendered cube faces');
 const records=[];
 for(let i=0;i<faces.length;i++){const face=faces[i];const image=Buffer.from(face.image.split(',')[1],'base64');if(image.length>8*1024**2)throw Error('Capture image exceeds profile');await writeFile(path.join(root,'face-'+i+'.png'),image);records.push({file:'face-'+i+'.png',matrix:face.matrix});}
 await writeFile(path.join(root,'capture.json'),JSON.stringify({schema:'pastport.raw-capture/1',origin:[0,1.6,0],faces:records}),{flag:'wx'});
 console.log('CAPTURE_COMPLETE',new Date().toISOString());await pipe.send('Browser.close');
}catch(error){if(child)child.kill('SIGTERM');throw error;}finally{
 server.closeAllConnections();await new Promise(resolve=>server.close(resolve));
 if(child&&child.exitCode===null){child.kill('SIGTERM');await Promise.race([once(child,'exit'),new Promise(resolve=>setTimeout(resolve,3000))]);if(child.exitCode===null)child.kill('SIGKILL');}
 await rm(profile,{recursive:true,force:true,maxRetries:3,retryDelay:100});
}
