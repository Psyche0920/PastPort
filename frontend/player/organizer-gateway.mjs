/** Publish only the authenticated Organizer surface, never its local bootstrap or other APIs. */
import {createServer,request} from 'node:http';
import {once} from 'node:events';
import {browserOrigin} from './network.mjs';
export class OrganizerGateway {
  constructor(target) {
    const url=new URL(target);
    if(url.origin!==target || url.protocol!=='http:' || url.hostname!=='127.0.0.1' || !url.port)throw new Error('Organizer must use a loopback HTTP origin.');
    this.target=url;this.origin=null;this.connections=new Set();
    this.server=createServer((req,res)=>this.forward(req,res));
    this.server.on('connection',socket=>{
      this.connections.add(socket);socket.once('close',()=>this.connections.delete(socket));
    });
  }
  async listen() {
    this.server.listen(0,'127.0.0.1');
    await once(this.server,'listening');
    return 'http://127.0.0.1:'+this.server.address().port;
  }
  setOrigin(value) {this.origin=browserOrigin(value);}
  forward(req,res) {
    const deny=(status)=>{res.writeHead(status,{'Cache-Control':'no-store'});res.end('Organizer remote access unavailable');};
    if(!this.origin)return deny(503);
    if(!req.url?.startsWith('/') || req.url.startsWith('//'))return deny(403);
    const incoming=new URL(req.url,'http://127.0.0.1');
    const path=incoming.pathname;
    if(!path.startsWith('/organizer/') || /%|\\|\/\//.test(path)
      || path.replace(/\/$/,'')==='/organizer/api/admin-setup')return deny(403);
    if(req.headers.host!==new URL(this.origin).host)return deny(403);
    if(path==='/organizer/__pastport_ready'){res.writeHead(200,{'Cache-Control':'no-store'});res.end('pastport-remote-ready');return;}
    const headers={...req.headers,host:new URL(this.origin).host,'x-forwarded-proto':'https'};
    for(const key of ['forwarded','x-forwarded-host','x-forwarded-port','x-forwarded-for','connection','upgrade','proxy-authorization'])delete headers[key];
    const upstream=request(new URL(incoming.pathname+incoming.search,this.target),{method:req.method,headers},response=>{
      const responseHeaders={...response.headers};
      delete responseHeaders.connection;
      res.writeHead(response.statusCode??502,responseHeaders);response.pipe(res);
    });
    upstream.on('error',()=>{if(!res.headersSent)deny(502);else res.destroy();});
    upstream.setTimeout(120000,()=>upstream.destroy());
    req.on('aborted',()=>upstream.destroy());
    res.on('close',()=>{if(!res.writableFinished)upstream.destroy();});
    req.pipe(upstream);
  }
  async close() {
    for(const socket of this.connections)socket.destroy();
    if(this.server.listening)await new Promise(resolve=>this.server.close(resolve));
  }
}
