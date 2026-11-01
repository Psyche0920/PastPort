import http from 'node:http';
import {readFile,realpath,stat} from 'node:fs/promises';
import {createReadStream} from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=path.dirname(fileURLToPath(import.meta.url));
const localDemo=path.resolve(process.env.PASTPORT_LOCAL_DEMO??root);
const port=Number(process.env.PASTPORT_PORT??18824);if(!Number.isSafeInteger(port)||port<1||port>65535)throw new RangeError('Invalid PASTPORT_PORT');
const input=JSON.parse(await readFile(path.resolve(process.env.PASTPORT_SCENE3D_INPUT??path.join(localDemo,'data/scene3d-input.json')),'utf8'));
for(const world of input.worlds)world.root=path.resolve(localDemo,world.root);
const extension={'.html':'text/html; charset=utf-8','.mjs':'text/javascript','.js':'text/javascript','.css':'text/css','.json':'application/json','.jpg':'image/jpeg','.png':'image/png','.svg':'image/svg+xml'};
function respond(res,status,body,type='application/json'){res.writeHead(status,{'Content-Type':type,'Cache-Control':'no-store'});res.end(body);}
async function file(res,base,name){const location=await realpath(path.resolve(base,name));if(!location.startsWith((await realpath(base))+path.sep))return respond(res,403,'Forbidden','text/plain');const info=await stat(location);res.writeHead(200,{'Content-Type':extension[path.extname(location)]??'application/octet-stream','Content-Length':info.size,'Cache-Control':'no-store'});const stream=createReadStream(location);stream.on('error',()=>res.destroy());res.on('close',()=>stream.destroy());stream.pipe(res);}
const server=http.createServer(async(req,res)=>{
 try{
  if(req.method!=='GET')return respond(res,405,'Read-only Story preview','text/plain');
  const url=new URL(req.url,'http://127.0.0.1');
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
  if(suffix==='scene3d/portal-navigation.json')return respond(res,200,JSON.stringify({endpoint:`http://127.0.0.1:${port}/api/scene3d-navigation/00000000000000000000000000000000`}));
  if(suffix==='scene3d/viewer.js'||suffix==='scene3d/transitions.js'){
    let code=await readFile(path.join(world.root,suffix),'utf8');
    code=code.replaceAll("'/api/",`'${prefix}/api/`).replaceAll('`/api/',`\`${prefix}/api/`);
    if(suffix.endsWith('viewer.js'))code+='\n'+await readFile(path.join(root,'scene3d-runtime.js'),'utf8');
    return respond(res,200,code,'text/javascript');
  }
  if(!suffix.startsWith('scene3d/'))return respond(res,404,'Not found','text/plain');
  return await file(res,world.root,suffix);
 }catch(error){console.error(JSON.stringify({event:'story3d_request_failed',code:error.code??error.name}));if(!res.headersSent)respond(res,503,'Scene resource unavailable','text/plain');else res.destroy();}
});
server.listen(port,'127.0.0.1',()=>console.log(`Story 3D integration: http://127.0.0.1:${port}/?scene=3d`));
for(const signal of ['SIGINT','SIGTERM'])process.on(signal,()=>server.close(()=>process.exit(0)));
