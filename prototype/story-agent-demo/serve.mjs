import http from 'node:http';
import {realpath,stat} from 'node:fs/promises';
import {createReadStream} from 'node:fs';
import {pipeline} from 'node:stream';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
/** Local-only static delivery; no-store prevents stale ES modules during review. */
class DemoServer {
  constructor(root,port){this.root=root;this.port=port;this.server=http.createServer((request,response)=>this.handle(request,response).catch(error=>{console.error(JSON.stringify({event:'demo_static_error',code:error.code??error.name}));if(!response.headersSent)response.writeHead(503);response.end('Resource unavailable');}));this.server.requestTimeout=10000;this.server.headersTimeout=10000;this.server.keepAliveTimeout=2000;}
  async handle(request,response){
    if(!['GET','HEAD'].includes(request.method)){response.writeHead(405,{'Allow':'GET, HEAD'});response.end();return;}
    let pathname;try{pathname=decodeURIComponent(new URL(request.url,'http://127.0.0.1').pathname);}catch{response.writeHead(400);response.end('Invalid path');return;}
    let filename=path.resolve(this.root,'.'+pathname);if(filename!==this.root&&!filename.startsWith(this.root+path.sep)){response.writeHead(403);response.end();return;}
    try{let info=await stat(filename);if(info.isDirectory())filename=path.join(filename,'index.html');filename=await realpath(filename);if(!filename.startsWith(this.root+path.sep))throw Object.assign(new Error('Forbidden'),{code:'EACCES'});info=await stat(filename);if(!info.isFile())throw Object.assign(new Error('Not a file'),{code:'ENOENT'});
      const types={'.html':'text/html; charset=utf-8','.mjs':'text/javascript; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.json':'application/json; charset=utf-8','.png':'image/png','.jpg':'image/jpeg','.svg':'image/svg+xml'};
      response.writeHead(200,{'Content-Type':types[path.extname(filename)]??'application/octet-stream','Content-Length':info.size,'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'});if(request.method==='HEAD'){response.end();return;}const stream=createReadStream(filename);response.on('close',()=>{if(!response.writableFinished)stream.destroy();});pipeline(stream,response,error=>{if(error&&!response.destroyed)response.destroy();});
    }catch(error){if(['ENOENT','ENOTDIR','EACCES'].includes(error.code)){response.writeHead(error.code==='EACCES'?403:404,{'Cache-Control':'no-store'});response.end('Resource not found');return;}throw error;}
  }
  start(){this.server.listen(this.port,'127.0.0.1',()=>console.log(`Murat Demo: http://127.0.0.1:${this.port}/`));for(const signal of ['SIGINT','SIGTERM'])process.on(signal,()=>this.server.close(()=>process.exit(0)));this.server.on('error',error=>{console.error(JSON.stringify({event:'demo_server_error',code:error.code}));process.exitCode=1;});}
}
const port=Number(process.argv[2]??18823);if(!Number.isInteger(port)||port<1024||port>65535)throw new Error('Port must be between 1024 and 65535');
new DemoServer(await realpath(path.dirname(fileURLToPath(import.meta.url))),port).start();
