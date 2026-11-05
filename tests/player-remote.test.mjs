import assert from 'node:assert/strict';
import test from 'node:test';
import {createServer,request} from 'node:http';
import {once} from 'node:events';
import {spawn} from 'node:child_process';
import {mkdtemp,writeFile,rm,access,mkdir,readFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {browserOrigin,QuickTunnel} from '../frontend/player/network.mjs';
import {OrganizerGateway} from '../frontend/player/organizer-gateway.mjs';

test('public origins reject credentials, paths, insecure remote origins and HTML injection',()=>{
  for(const value of ['http://example.com','https://a.test/path','https://u:p@a.test','https://a.test/','https://a.test?q=x','https://a.test#x','javascript:alert(1)'])assert.throws(()=>browserOrigin(value));
  assert.equal(browserOrigin('https://example.com'),'https://example.com');
  assert.equal(browserOrigin('http://127.0.0.1:18851'),'http://127.0.0.1:18851');
});
test('tunnel waits for both hostname and connection; shuts down its child and removes temporary config',async()=>{
  let child,config;
  const start=(_binary,args,options)=>{
    config=args[args.indexOf('--config')+1];
    assert.equal(options.env.TUNNEL_TOKEN,undefined);
    assert.equal(args[args.indexOf('--url')+1],'http://127.0.0.1:12345');
    child=spawn(process.execPath,['-e',`process.stderr.write('https://fixture-remote.trycloud');setTimeout(()=>process.stderr.write('flare.com\\nRegistered tunnel connection\\n'),20);setInterval(()=>{},1000);`],{stdio:['ignore','pipe','pipe']});
    return child;
  };
  let lost=false;
  const tunnel=await QuickTunnel.open('http://127.0.0.1:12345',{start,onExit:()=>{lost=true;}});
  assert.equal(tunnel.url,'https://fixture-remote.trycloudflare.com');
  await access(config);await tunnel.close();
  assert.ok(child.exitCode!==null || child.signalCode!==null);
  await assert.rejects(access(config));assert.equal(lost,false);
});
test('tunnel unavailable/timeout failure cleans up and never targets a non-loopback service',async()=>{
  await assert.rejects(QuickTunnel.open('http://other.test:22'),/loopback/);
  await assert.rejects(QuickTunnel.open('http://127.0.0.1:12345',{binary:'/not/a/cloudflared'}),/stopped/);
  let child;
  await assert.rejects(QuickTunnel.open('http://127.0.0.1:12345',{timeout:30,start:()=>{
    child=spawn(process.execPath,['-e','setInterval(()=>{},1000)'],{stdio:['ignore','pipe','pipe']});return child;
  }}),/minute/);
  assert.ok(child.exitCode!==null || child.signalCode!==null);
});
test('staff gateway forwards authenticated surface with explicit host/proto, rejects setup/other APIs/forged Host',async()=>{
  const seen=[];
  const upstream=createServer((req,res)=>{seen.push({url:req.url,headers:req.headers});res.end('staff');});
  upstream.listen(0,'127.0.0.1');await once(upstream,'listening');
  const gateway=new OrganizerGateway('http://127.0.0.1:'+upstream.address().port);
  const local=await gateway.listen();gateway.setOrigin('https://staff-test.trycloudflare.com');
  async function get(path,host='staff-test.trycloudflare.com'){
    return new Promise((resolve,reject)=>{
      const req=request(local,{path,headers:{Host:host,'X-Forwarded-For':'spoofed','Forwarded':'host=evil','X-Forwarded-Proto':'http','Cookie':'pastport_organizer=fixture'}},res=>{
        res.resume();res.on('end',()=>resolve(res.statusCode));});req.on('error',reject);req.end();
    });
  }
  try {
    assert.equal(await get('/organizer/api/jobs'),200);
    assert.equal(seen[0].headers.host,'staff-test.trycloudflare.com');
    assert.equal(seen[0].headers['x-forwarded-proto'],'https');
    assert.equal(seen[0].headers['x-forwarded-for'],undefined);
    assert.equal(seen[0].headers.cookie,'pastport_organizer=fixture');
    for(const path of ['/organizer/api/admin-setup','/organizer/api/admin-setup/','/organizer/api/%61dmin-setup','/api/health','//other.test/organizer/','http://other.test/organizer/'])assert.equal(await get(path),403,path);
    assert.equal(await get('/organizer/','127.0.0.1'),403);
    assert.equal(seen.length,1);
  } finally {await gateway.close();await new Promise(resolve=>upstream.close(resolve));}
});

test('remote player launch returns HTTPS game origin, preserves account saves and uses Secure cookies',async()=>{
  const directory=await mkdtemp(join(tmpdir(),'pastport-remote-http-'));
  const organizer=join(directory,'organizer'),job='c'.repeat(32),game=join(organizer,'jobs',job,'game');
  await import('node:fs/promises').then(({mkdir})=>mkdir(join(game,'data'),{recursive:true}));
  await writeFile(join(game,'index.html'),'<html><script type="module" src="app.mjs"></script></html>');
  await writeFile(join(game,'session.mjs'),'export class GameSession {snapshot(){return {};}}');
  await writeFile(join(game,'app.mjs'),'function renderEnding(root){}');
  await writeFile(join(game,'data/presentation.json'),JSON.stringify({saveKey:'save'}));
  await writeFile(join(game,'data/scene3d-input.json'),JSON.stringify({worlds:[]}));
  await mkdir(join(game,'world','scene3d'),{recursive:true});
  await writeFile(join(game,'world','scene3d','transitions.js'),await readFile(new URL('../packages/matched-environment-sdk/src/pastport_matched_environment/scene3d_assets/transitions.js',import.meta.url),'utf8'));
  await writeFile(join(game,'data/scene3d-input.json'),JSON.stringify({worlds:[{root:'world',snapshot:{binding:'test'}}]}));
  const catalog=join(directory,'sites.json');await writeFile(catalog,JSON.stringify([{id:'site'}]));
  await writeFile(join(organizer,'player-map-site.json'),JSON.stringify({site_id:'site',job_id:job,version:'a'.repeat(64),game_directory:`jobs/${job}/game`}));
  const targets=join(directory,'targets.json');
  await writeFile(join(directory,'cloudflared'),`#!${process.execPath}
import('node:fs').then(fs=>{fs.writeFileSync(${JSON.stringify(targets)},JSON.stringify(process.argv[process.argv.indexOf('--url')+1]));process.stderr.write('https://remote-game-test.trycloudflare.com\\nRegistered tunnel connection\\n');setInterval(()=>{},1000);});
`,{mode:0o700});
  const socket=createServer();socket.listen(0,'127.0.0.1');await once(socket,'listening');const port=socket.address().port;await new Promise(resolve=>socket.close(resolve));
  const hook=join(directory,'fetch-hook.mjs');
  await writeFile(hook,`import {readFile} from 'node:fs/promises';
const original=globalThis.fetch;
globalThis.fetch=async(url,options)=>{
 if(String(url).startsWith('https://remote-game-test.trycloudflare.com/')){
  const target=JSON.parse(await readFile(${JSON.stringify(targets)},'utf8'));
  return original(target+new URL(url).pathname,options);
 }
 return original(url,options);
};`);
  const origin='https://remote-platform-test.trycloudflare.com';
  const child=spawn(process.execPath,[new URL('../frontend/player/server.mjs',import.meta.url).pathname],{
    env:{NODE_OPTIONS:'--import='+hook,PATH:directory+':'+process.env.PATH,PLAYER_PORT:String(port),PLAYER_PUBLIC_ORIGIN:origin,PLAYER_GAME_TUNNELS:'quick',PLAYER_DATA:join(directory,'players'),ORGANIZER_DATA:organizer,SITE_CATALOG:catalog},stdio:['ignore','pipe','pipe'],
  });
  const stop=async()=>{const done=once(child,'exit');child.kill();await done;};
  const post=(route,input,cookie='',source=origin,host=new URL(origin).host)=>new Promise((resolve,reject)=>{
    const data=JSON.stringify(input);
    const req=request({hostname:'127.0.0.1',port,path:'/api/'+route,method:'POST',headers:{Host:host,Origin:source,Cookie:cookie,'Content-Type':'application/json','Content-Length':Buffer.byteLength(data)}},res=>{
      let body='';res.on('data',chunk=>body+=chunk);res.on('end',()=>resolve({status:res.statusCode,value:JSON.parse(body),cookie:res.headers['set-cookie']?.[0]}));});
    req.on('error',reject);req.end(data);
  });
  try {
    await Promise.race([once(child.stdout,'data'),once(child,'exit').then(()=>{throw new Error('player failed');})]);
    assert.equal((await post('register',{},'','https://wrong.test')).status,403);
    assert.equal((await post('register',{},'',origin,'forged.test')).status,403);
    const player=await post('register',{username:'remotealice',name:'Remote fixture',password:'isolated-fixture-only'});
    assert.equal(player.status,200);assert.match(player.cookie,/; Secure/);
    const cookie=player.cookie.split(';')[0];
    const launch=async()=>{
      for(let n=0;n<100;n++){
        const response=await post('launch',{site_id:'site'},cookie);
        if(response.status!==202)return response;
        assert.equal(response.value.pending,true);
        await new Promise(resolve=>setTimeout(resolve,20));
      }
      throw new Error('Fixture launch did not complete');
    };
    const launched=await launch();
    assert.equal(launched.status,200);
    assert.equal(new URL(launched.value.url).origin,'https://remote-game-test.trycloudflare.com');
    const local=JSON.parse(await import('node:fs/promises').then(({readFile})=>readFile(targets,'utf8')));
    const script=await (await fetch(local+'/app.mjs')).text();
    const navigation=await (await fetch(local+'/world/1/scene3d/portal-navigation.json')).json();
    assert.ok(navigation.endpoint.startsWith('/api/'));
    const transitions=await (await fetch(local+'/world/1/scene3d/transitions.js')).text();
    assert.ok(transitions.includes('new URL(config.endpoint,location.origin)'));
    assert.ok(transitions.includes('endpoint.origin!==location.origin'));
    assert.ok(!transitions.includes("endpoint.protocol!=='http:'"));
    assert.ok(script.includes(origin));assert.ok(!script.includes('http://127.0.0.1:'));
    const snap=JSON.stringify({version:2,identity:'a'.repeat(64),sequence:3,engine:{current_scene_id:'investigate'},local:{},notebook:[5],positions:{},shotState:null});
    assert.equal((await post('save',{run:launched.value.run,revision:0,operation:crypto.randomUUID(),changes:{save:snap}},cookie)).status,200);
    const another=await launch();
    assert.equal(JSON.parse(another.value.save.entries.save).sequence,3);
  } finally {await stop();await rm(directory,{recursive:true,force:true});}
});

test('cancelling tunnel startup stops the connector immediately',async()=>{
  const controller=new AbortController();let child;
  const pending=QuickTunnel.open('http://127.0.0.1:12345',{signal:controller.signal,start:()=>{
    child=spawn(process.execPath,['-e','setInterval(()=>{},1000)'],{stdio:['ignore','pipe','pipe']});
    setTimeout(()=>controller.abort(),20);return child;
  }});
  await assert.rejects(pending,/cancelled/);
  assert.ok(child.exitCode!==null || child.signalCode!==null);
});
