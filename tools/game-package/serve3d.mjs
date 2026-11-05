import {completionAdapter,completionBootstrap} from './player-completion.mjs';
import http from 'node:http';
import {readFile,realpath,stat} from 'node:fs/promises';
import {createReadStream} from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=path.resolve(process.env.PASTPORT_HOST_ROOT??path.dirname(fileURLToPath(import.meta.url)));
const localDemo=path.resolve(process.env.PASTPORT_LOCAL_DEMO??root);
let port=Number(process.env.PASTPORT_PORT??18824);if(!Number.isSafeInteger(port)||port<0||port>65535)throw new RangeError('Invalid PASTPORT_PORT');
let staticEntry=null,staticManifest=null;
try {staticManifest=JSON.parse(await readFile(path.join(localDemo,'pastport-player.json'),'utf8'));}
catch(error) {if(error.code!=='ENOENT')throw error;}
if(staticManifest){
  if(staticManifest.format!=='pastport-static-v1'||typeof staticManifest.entrypoint!=='string'||
    !/^[a-zA-Z0-9_./-]+\.html$/.test(staticManifest.entrypoint)||staticManifest.entrypoint.split('/').includes('..')||path.isAbsolute(staticManifest.entrypoint))throw new Error('Invalid static player manifest');
  const entry=await realpath(path.join(localDemo,staticManifest.entrypoint));
  if(!entry.startsWith((await realpath(localDemo))+path.sep))throw new Error('Static player entry escapes package');
  staticEntry=staticManifest.entrypoint;
}
const integration=staticEntry ? await completionAdapter(localDemo) : null;
const playerOrigin=process.env.PASTPORT_PLAYER_ORIGIN??'';
if(playerOrigin){
  const target=new URL(playerOrigin);
  const local=target.protocol==='http:' && ['127.0.0.1','localhost','[::1]'].includes(target.hostname);
  if(target.origin!==playerOrigin || target.username || target.password || (!local && target.protocol!=='https:'))throw new Error('Invalid player platform origin');
}
const input=staticEntry ? {worlds:[]} : JSON.parse(await readFile(path.resolve(process.env.PASTPORT_SCENE3D_INPUT??path.join(localDemo,'data/scene3d-input.json')),'utf8'));
for(const world of input.worlds)world.root=path.resolve(localDemo,world.root);
const previewToken=process.env.PASTPORT_PREVIEW_TOKEN??'';
const previewCookie=process.env.PASTPORT_PREVIEW_COOKIE??'pastport_preview';
const extension={'.m4a':'audio/mp4','.html':'text/html; charset=utf-8','.mjs':'text/javascript','.js':'text/javascript','.css':'text/css','.json':'application/json','.jpg':'image/jpeg','.png':'image/png','.svg':'image/svg+xml'};
function respond(res,status,body,type='application/json'){res.writeHead(status,{'Content-Type':type,'Cache-Control':'no-store'});res.end(body);}
async function file(res,base,name){const location=await realpath(path.resolve(base,name));if(!location.startsWith((await realpath(base))+path.sep))return respond(res,403,'Forbidden','text/plain');const info=await stat(location);res.writeHead(200,{'Content-Type':extension[path.extname(location)]??'application/octet-stream','Content-Length':info.size,'Cache-Control':'no-store'});const stream=createReadStream(location);stream.on('error',()=>res.destroy());res.on('close',()=>stream.destroy());stream.pipe(res);}
const server=http.createServer(async(req,res)=>{
 try{
  if(req.method!=='GET')return respond(res,405,'Read-only Story preview','text/plain');
  const url=new URL(req.url,'http://127.0.0.1');
  if(previewToken){
    const host=new URL('http://'+req.headers.host).hostname;
    if(!['127.0.0.1','localhost'].includes(host))return respond(res,403,'Loopback preview only','text/plain');
    if(url.searchParams.get('preview_token')===previewToken){
      url.searchParams.delete('preview_token');
      res.writeHead(302,{'Location':url.pathname+url.search,'Cache-Control':'no-store','Set-Cookie':`${previewCookie}=${previewToken}; HttpOnly; SameSite=Strict; Path=/`,'Referrer-Policy':'no-referrer'});res.end();return;
    }
    if(!(req.headers.cookie??'').split(';').some(value=>value.trim()===`${previewCookie}=${previewToken}`))return respond(res,401,'Open this preview through Organizer','text/plain');
  }
  if(url.pathname==='/__pastport_ready')return respond(res,200,'pastport-remote-ready','text/plain');
  if(staticEntry){
    if(url.pathname==='/'||url.pathname==='/index.html'){
      res.writeHead(302,{'Location':'/'+staticEntry+url.search,'Cache-Control':'no-store'});res.end();return;
    }
    if(url.pathname==='/'+staticEntry && playerOrigin){
      const html=await readFile(path.join(localDemo,staticEntry),'utf8');
      let page=html.replace(/<head(?:\s[^>]*)?>/i,match=>match+completionBootstrap(integration,playerOrigin));
      // Account saves must hydrate before the original modules read storage; the bridge starts them.
      if(integration.saveKeys.length)page=page.replace(/<script\s+type=(["'])module\1(\s[^>]*)?>/gi,(match,quote,rest='')=>`<script type="pastport/deferred-module"${rest}>`);
      return respond(res,200,page,'text/html; charset=utf-8');
    }
    return await file(res,localDemo,'.'+decodeURIComponent(url.pathname));
  }
  if((url.pathname==='/'||url.pathname==='/index.html')&&url.searchParams.get('scene')!=='3d'){
    url.searchParams.set('scene','3d');res.writeHead(302,{'Location':url.pathname+url.search,'Cache-Control':'no-store'});res.end();return;
  }
  const pathname=decodeURIComponent(url.pathname),match=pathname.match(/^\/world\/([12])\/(.*)$/);
  if(pathname==='/'||pathname==='/index.html'){
    const html=(await readFile(path.join(root,'index.html'),'utf8')).replace('src="museum/index.html?views=animated"','src="about:blank"');
    return respond(res,200,html,'text/html; charset=utf-8');
  }
  if(!match){const asset=/^\/(data|assets|media|museum)\//.test(pathname)||pathname==='/manifest.json';return await file(res,asset?localDemo:root,pathname==='/'?'index.html':'.'+pathname);}
  const number=Number(match[1]),world=input.worlds[number-1],suffix=match[2],prefix=`/world/${number}`;
  if(suffix==='scene3d/index.html'){
    // Player bundles use pinned snapshots, not authoring-backend review polling.
    const html=(await readFile(path.join(world.root,suffix),'utf8')).replace('<script src="/shared_content.js"></script>','');
    return respond(res,200,html,'text/html; charset=utf-8');
  }
  if(suffix==='navigation_boundary.js')return await file(res,world.root,'scene3d/navigation_boundary.js');
  if(suffix==='api/scene3d')return respond(res,200,JSON.stringify(world.snapshot));
  if(suffix==='api/scene3d/arrows')return respond(res,200,JSON.stringify({scene_binding:world.snapshot.binding,arrows:[]}));
  if(suffix==='scene3d/portal-navigation.json')return respond(res,200,JSON.stringify({endpoint:'/api/scene3d-navigation/00000000000000000000000000000000'}));
  if(suffix==='scene3d/viewer.js'||suffix==='scene3d/transitions.js'){
    let code=await readFile(path.join(world.root,suffix),'utf8');
    if(suffix.endsWith('transitions.js'))code=code
      .replace('new URL(config.endpoint)','new URL(config.endpoint,location.origin)')
      .replace("endpoint.protocol!=='http:'||!['127.0.0.1','localhost'].includes(endpoint.hostname)",'endpoint.origin!==location.origin');
    code=code.replaceAll("'/api/",`'${prefix}/api/`).replaceAll('`/api/',`\`${prefix}/api/`);
    if(suffix.endsWith('viewer.js'))code+='\n'+await readFile(path.join(root,'scene3d-runtime.js'),'utf8');
    return respond(res,200,code,'text/javascript');
  }
  if(!suffix.startsWith('scene3d/'))return respond(res,404,'Not found','text/plain');
  return await file(res,world.root,suffix);
 }catch(error){console.error(JSON.stringify({event:'story3d_request_failed',code:error.code??error.name}));if(!res.headersSent)respond(res,503,'Scene resource unavailable','text/plain');else res.destroy();}
});
const ready=()=>{port=server.address().port;console.log(`Story 3D integration: http://127.0.0.1:${port}/?scene=3d`);};
if(process.env.PASTPORT_LISTEN_FD)server.listen({fd:Number(process.env.PASTPORT_LISTEN_FD)},ready);
else server.listen(port,'127.0.0.1',ready);
for(const signal of ['SIGINT','SIGTERM'])process.on(signal,()=>server.close(()=>process.exit(0)));
