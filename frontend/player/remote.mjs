/** Foreground-only remote sharing. Ctrl+C stops only processes owned by this command. */
import {spawn} from 'node:child_process';
import {createServer} from 'node:net';
import {once} from 'node:events';
import {fileURLToPath} from 'node:url';
import {join} from 'node:path';
import {access} from 'node:fs/promises';
import {parseArgs} from 'node:util';
import {QuickTunnel,stopProcess} from './network.mjs';
import {OrganizerGateway,verifyOrganizerReady} from './organizer-gateway.mjs';
const {values}=parseArgs({options:{port:{type:'string',default:'18852'},'organizer-port':{type:'string',default:'18840'},'share-organizer':{type:'boolean',default:false}}});
const port=Number(values.port),organizerPort=Number(values['organizer-port']);
for(const value of [port,organizerPort])if(!Number.isSafeInteger(value)||value<1||value>65535)throw new Error('Use a port between 1 and 65535.');
const root=fileURLToPath(new URL('../../',import.meta.url));
const organizer=process.env.ORGANIZER_DATA??join(root,'var/organizer-integration/server/organizer');
const data=process.env.PLAYER_DATA??join(root,'frontend/player/.local');
const owned=[];let stopped=false;const lifecycle=new AbortController();
async function close(){
  if(stopped)return;stopped=true;lifecycle.abort();
  for(const resource of owned.reverse())await resource.close();
}
function lost(){if(!stopped){console.error('Remote sharing stopped: a tunnel or player service disconnected. Restart this command for new links.');process.exitCode=1;void close();}}
for(const signal of ['SIGINT','SIGTERM'])process.once(signal,()=>{void close();});
try {
  // Sharing must never initialize an empty deployment by a path typo.
  await access(join(data,'players.sqlite'));
  await access(organizer);
  const local='http://127.0.0.1:'+organizerPort;
  if(values['share-organizer'])await verifyOrganizerReady(local);
  const check=createServer();check.listen(port,'127.0.0.1');await once(check,'listening');
  await new Promise(resolve=>check.close(resolve));
  if(stopped)throw new Error('Sharing cancelled.');
  const target='http://127.0.0.1:'+port;
  console.log('Connecting temporary player access; existing local services stay running...');
  const platform=await QuickTunnel.open(target,{onExit:lost,signal:lifecycle.signal});
  owned.push(platform);
  if(stopped){await platform.close();throw new Error('Sharing cancelled.');}
  const child=spawn(process.execPath,[fileURLToPath(new URL('./server.mjs',import.meta.url))],{
    env:{...process.env,PLAYER_PORT:String(port),PLAYER_PUBLIC_ORIGIN:platform.url,PLAYER_GAME_TUNNELS:'quick',PLAYER_DATA:data,ORGANIZER_DATA:organizer},
    stdio:['ignore','pipe','inherit'],
  });
  owned.push({close:()=>stopProcess(child)});
  child.once('exit',lost);
  await new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>{cleanup();reject(new Error('Player service did not start.'));},10000);
    const ready=data=>{if(String(data).includes('PastPort player:')){cleanup();resolve();}};
    const fail=()=>{cleanup();reject(new Error('Player service could not start.'));};
    function cleanup(){clearTimeout(timer);child.stdout.off('data',ready);child.off('error',fail);child.off('exit',fail);}
    child.stdout.on('data',ready);child.once('error',fail);child.once('exit',fail);
  });
  if(stopped)throw new Error('Sharing cancelled.');
  console.log('Checking the temporary HTTPS address; DNS may take up to two minutes...');
  await platform.waitReady({signal:lifecycle.signal});
  console.log('\nPLAYER / 玩家入口: '+platform.url);
  if(values['share-organizer']){
    await verifyOrganizerReady(local);
    const gateway=new OrganizerGateway(local);owned.push(gateway);
    const target=await gateway.listen();
    const staff=await QuickTunnel.open(target,{onExit:lost,signal:lifecycle.signal});owned.push(staff);
    gateway.setOrigin(staff.url);
    await staff.waitReady({signal:lifecycle.signal,path:'/organizer/__pastport_ready'});
    if(stopped){await staff.close();throw new Error('Sharing cancelled.');}
    console.log('STAFF / Organizer 登录入口: '+staff.url+'/organizer/');
  }
  console.log('\nKeep this terminal and computer awake. Ctrl+C closes remote access; local services and data remain.\nGame links open on demand on separate temporary origins. Do not share your staff password publicly.');
} catch(error) {
  console.error('Remote sharing: '+error.message);
  process.exitCode=1;
  await close();
}
