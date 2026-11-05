/** Explicit browser origins and supervised temporary tunnels; local services stay loopback-only. */
import {spawn} from 'node:child_process';
import {mkdtemp,writeFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {once} from 'node:events';

export function browserOrigin(value) {
  const url=new URL(value);
  const local=url.protocol==='http:' && ['127.0.0.1','localhost','[::1]'].includes(url.hostname);
  if (url.origin!==value || url.username || url.password || (!local && url.protocol!=='https:')) {
    throw new Error('Use an HTTPS origin, or an HTTP loopback origin, without a path.');
  }
  return url.origin;
}

export async function stopProcess(child) {
  if (!child || !child.pid || child.exitCode!==null || child.signalCode!==null) return;
  const done=once(child,'exit').catch(()=>{});
  child.kill('SIGTERM');
  const timer=setTimeout(()=>child.kill('SIGKILL'),4000);
  try {await done;} finally {clearTimeout(timer);}
}

/** Only expose an explicitly supplied loopback service, without reading account tunnel credentials. */
export class QuickTunnel {
  static async open(target,{binary='cloudflared',timeout=60000,onExit=()=>{},start=spawn,signal}={}) {
    signal?.throwIfAborted();
    const url=new URL(target);
    if (url.protocol!=='http:' || url.hostname!=='127.0.0.1' || !url.port || url.origin!==target) {
      throw new Error('A tunnel target must be an explicit HTTP loopback origin.');
    }
    const directory=await mkdtemp(join(tmpdir(),'pastport-quick-tunnel-'));
    let child;
    try {
      const config=join(directory,'config.yml');
      await writeFile(config,'{}\n',{mode:0o600});
      child=start(binary,['tunnel','--config',config,'--no-autoupdate','--protocol','http2',
        '--url',target,'--metrics','127.0.0.1:0','--grace-period','1s'],{
        stdio:['ignore','pipe','pipe'],
        env:Object.fromEntries(['PATH','HOME','TMPDIR','SYSTEMROOT','SSL_CERT_FILE'].filter(key=>process.env[key]).map(key=>[key,process.env[key]])),
      });
      const tunnel=new QuickTunnel(child,directory,onExit);
      tunnel.url=await new Promise((resolve,reject)=>{
        let output='',publicUrl=null,connected=false;
        const finish=()=>{if(publicUrl && connected){cleanup();resolve(publicUrl);}};
        const read=chunk=>{
          output=(output+String(chunk)).slice(-16000);
          publicUrl=/https:\/\/[a-z0-9]+(?:-[a-z0-9]+)*\.trycloudflare\.com(?=[\s|"'\x60]|$)/.exec(output)?.[0]??publicUrl;
          connected=connected || output.includes('Registered tunnel connection');
          finish();
        };
        const aborted=()=>{cleanup();reject(new Error('Remote sharing cancelled.'));};
        const failed=()=>{cleanup();reject(new Error('The temporary tunnel stopped before connecting. Check your network and cloudflared installation.'));};
        const timer=setTimeout(()=>{cleanup();reject(new Error('The temporary tunnel could not connect within one minute.'));},timeout);
        function cleanup(){clearTimeout(timer);child.stdout.off('data',read);child.stderr.off('data',read);child.off('error',failed);child.off('exit',failed);signal?.removeEventListener('abort',aborted);}
        child.stdout.on('data',read);child.stderr.on('data',read);child.once('error',failed);child.once('exit',failed);
        signal?.addEventListener('abort',aborted,{once:true});if(signal?.aborted)aborted();
      });
      child.stdout.resume();child.stderr.resume();
      if(child.exitCode!==null || child.signalCode!==null)throw new Error('The temporary tunnel disconnected.');
      return tunnel;
    } catch(error) {
      await stopProcess(child);
      await rm(directory,{recursive:true,force:true});
      throw error;
    }
  }
  constructor(child,directory,onExit) {
    this.child=child;this.directory=directory;this.closing=false;
    child.once('exit',()=>{
      void rm(directory,{recursive:true,force:true});
      if(!this.closing)onExit();
    });
  }
  async waitReady({signal,timeout=120000,path='/__pastport_ready'}={}) {
    const deadline=Date.now()+timeout;
    while(Date.now()<deadline){
      signal?.throwIfAborted();
      try{
        const response=await fetch(this.url+path,{signal:AbortSignal.any([AbortSignal.timeout(5000),...(signal?[signal]:[])])});
        if(response.ok && await response.text()==='pastport-remote-ready')return;
      }catch(error){if(signal?.aborted)throw error;}
      await new Promise((resolve,reject)=>{
        const done=()=>{signal?.removeEventListener('abort',cancel);resolve();};
        const timer=setTimeout(done,2000);
        const cancel=()=>{clearTimeout(timer);signal?.removeEventListener('abort',cancel);reject(new Error('Remote sharing cancelled.'));};
        signal?.addEventListener('abort',cancel,{once:true});if(signal?.aborted)cancel();
      });
    }
    throw new Error('The temporary address is connected but not reachable. Check network/DNS and retry.');
  }
  async close() {
    this.closing=true;
    await stopProcess(this.child);
    await rm(this.directory,{recursive:true,force:true});
  }
}
