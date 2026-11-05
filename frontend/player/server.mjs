import {browserOrigin,QuickTunnel,stopProcess} from './network.mjs';
import {PlayerSaveRepository, SaveConflict, InvalidSave} from './cloud-saves.mjs';
import {completionAdapter} from '../../tools/game-package/player-completion.mjs';
import {verifyDataIdentity} from './data-identity.mjs';
import {createServer} from 'node:http';
import {createHash, randomBytes, scryptSync, timingSafeEqual} from 'node:crypto';
import {DatabaseSync} from 'node:sqlite';
import {cp, mkdir, mkdtemp, readFile, realpath, rm, writeFile} from 'node:fs/promises';
import {spawn} from 'node:child_process';
import {tmpdir} from 'node:os';
import {fileURLToPath} from 'node:url';
import {join, relative} from 'node:path';

const root = fileURLToPath(new URL('.', import.meta.url));
const platformPort = Number(process.env.PLAYER_PORT ?? 18851);
const origin = browserOrigin(process.env.PLAYER_PUBLIC_ORIGIN ?? `http://127.0.0.1:${platformPort}`);
const lifecycle=new AbortController();
const remoteGames=process.env.PLAYER_GAME_TUNNELS==='quick';
if(process.env.PLAYER_GAME_TUNNELS && !remoteGames)throw new Error('Unsupported game tunnel mode.');
const secureCookie=origin.startsWith('https:') ? '; Secure' : '';
const cookieName = `pastport_player_${platformPort}`;
const data = process.env.PLAYER_DATA ?? join(root, '.local');
const repository = fileURLToPath(new URL('../../', import.meta.url));
const organizerData = process.env.ORGANIZER_DATA ?? join(repository,'var/organizer-integration/server/organizer');
// Never replace a known player database with a new empty one after a path change or data loss.
try {await verifyDataIdentity(data,organizerData);}
catch(error){console.error('Player data: '+error.message);process.exit(1);}
await mkdir(data, {recursive:true,mode:0o700});
const db = new DatabaseSync(join(data, 'players.sqlite'));
db.exec(`PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS player (id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL, name TEXT NOT NULL, salt TEXT NOT NULL, hash TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS session (token TEXT PRIMARY KEY, player TEXT REFERENCES player(id), expires INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS stamp (player TEXT REFERENCES player(id), game TEXT NOT NULL, awarded TEXT NOT NULL, PRIMARY KEY(player,game));`);
db.exec('PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000;');
const saves = new PlayerSaveRepository(db);
const launcherPath = process.env.GAME_LAUNCHER ?? join(repository,'tools/game-package/serve3d.mjs');
const publications = new Map();
const siteCatalog = process.env.SITE_CATALOG ?? join(root,'sites.json');
const mapSites = JSON.parse(await readFile(siteCatalog,'utf8'));
const siteIds = new Set(mapSites.map(site=>site.id));
async function resolvePublication(siteId,value) {
  if (value?.site_id !== siteId || !/^[a-f0-9]{64}$/.test(value.version)
    || !/^[a-f0-9]{32}$/.test(value.job_id)) throw new Error('Invalid Organizer publication');
  const job = await realpath(join(organizerData,'jobs',value.job_id));
  const directory = await realpath(join(organizerData,value.game_directory));
  const scope = relative(job,directory);
  if (!scope || scope.startsWith('..')) throw new Error('Invalid published game directory');
  return {...value,directory};
}
async function readPublication(siteId) {
  if (!siteIds.has(siteId)) return null;
  try {
    return await resolvePublication(siteId,JSON.parse(await readFile(join(organizerData,'player-map-'+siteId+'.json'),'utf8')));
  } catch (error) {
    if (error.code==='ENOENT') return null;
    throw error;
  }
}
/** Only versions that were actually published to this site can be resumed. */
async function publishedVersion(siteId,version) {
  if (!siteIds.has(siteId) || !/^[a-f0-9]{64}$/.test(version ?? '')) return null;
  let history=[];
  try {history=JSON.parse(await readFile(join(organizerData,'player-map-'+siteId+'.history.json'),'utf8'));}
  catch(error){if(error.code!=='ENOENT')throw error;}
  const current=await readPublication(siteId);
  if (current?.version===version) return current;
  for (const entry of [...(Array.isArray(history)?history:[])].reverse()) {
    if (entry?.version!==version) continue;
    try {return await resolvePublication(siteId,entry);}
    catch(error){if(error.code==='ENOENT')return null;throw error;}
  }
  return null;
}
const endingMessage = `
  const passportRun = new URL(location.href).searchParams.get('passportRun');
  if (passportRun && window.parent !== window &&
      (typeof continuationPending === 'undefined' || !continuationPending)) {
    window.parent.postMessage({type:'pastport:ending',run:passportRun}, ${JSON.stringify(origin)});
  }
`;
async function startPublishedGame(publication) {
  const game = await realpath(await mkdtemp(join(tmpdir(),'pastport-map-game-')));
  let child,tunnel;
  try {
    await cp(publication.directory,game,{recursive:true});
    let staticPlayer=null;
    try {staticPlayer=JSON.parse(await readFile(join(game,'pastport-player.json'),'utf8'));}
    catch(error){if(error.code!=='ENOENT')throw error;}
    let saveFormat=null;
    const input = staticPlayer ? {worlds:[]} : JSON.parse(await readFile(join(game,'data/scene3d-input.json'),'utf8'));
    for (const world of input.worlds) {
      const worldRoot = await realpath(join(game,world.root));
      const scope = relative(game,worldRoot);
      if (scope.startsWith('..')) throw new Error('Published world escapes the game directory');
    }
    const saveKeys=[];
    try {
      const sessionCode=await readFile(join(game,'session.mjs'),'utf8');
      if (sessionCode.includes('export class GameSession') && sessionCode.includes('snapshot()')) {
        const presentation=JSON.parse(await readFile(join(game,'data/presentation.json'),'utf8'));
        saveKeys.push(presentation.saveKey ?? 'pastport:murat-story-demo:save:3d-v1');
        if (presentation.continuation) {
          const manifestPath=await realpath(join(game,presentation.continuation.manifest));
          if (relative(game,manifestPath).startsWith('..')) throw new Error('Continuation escapes published game');
          const manifest=JSON.parse(await readFile(manifestPath,'utf8'));
          saveKeys.push(manifest.previous.presentation.saveKey);
        }
        if (saveKeys.some(key=>typeof key!=='string' || !key.length || key.length>512 || ['__proto__','constructor','prototype'].includes(key))) throw new Error('Invalid game save keys');
        await cp(join(root,'game-save-bridge.mjs'),join(game,'pastport-save-bridge.mjs'));
        saveFormat='gamesession-v2';
      }
    } catch (error) {if(error.code!=='ENOENT')throw error;}
    if (staticPlayer) {
      // Known legacy runtimes are pinned by digest; their own engine replays the event log.
      const adapter=await completionAdapter(game);
      if (adapter.saveKeys.length) {saveKeys.push(...adapter.saveKeys);saveFormat=adapter.id;}
    }
    const app = join(game,'app.mjs');
    try {
      const script = await readFile(app,'utf8');
      const locale = "(new URL(location.href).searchParams.get('lang') === 'en' ? 'en' : 'zh')";
      const endingHook = 'function renderEnding(root){';
      const bootstrap=saveKeys.length ? `import {connectPlayerSave} from './pastport-save-bridge.mjs';
await connectPlayerSave(${JSON.stringify(origin)},${JSON.stringify(saveKeys)}).catch(error=>{
window.parent.postMessage({type:'pastport:save-error',run:new URL(location.href).searchParams.get('passportRun')},${JSON.stringify(origin)});throw error;});\n` : '';
      await writeFile(app,bootstrap+script
        .replace(/let locale=(?:preferredLocale|'zh'),/,`let locale=${locale},`)
        .replace(endingHook,endingHook+endingMessage));
    } catch (error) {
      if (error.code!=='ENOENT') throw error;
    }
    const recording = join(game,'recording.mjs');
    try {
      const code = await readFile(recording,'utf8');
      const hook = 'function showEnding(title, copy, file) {';
      await writeFile(recording,code.replace(hook,hook+endingMessage));
    } catch (error) {
      if (error.code!=='ENOENT') throw error;
    }
    // Use the repository's trusted preview launcher. The imported launcher is data.
    child = spawn(process.execPath,[launcherPath],{
      stdio:['ignore','pipe','inherit'],
      env:{PATH:process.env.PATH,PASTPORT_PORT:'0',PASTPORT_HOST_ROOT:game,PASTPORT_LOCAL_DEMO:game,PASTPORT_PLAYER_ORIGIN:origin},
    });
    child.once('exit',()=>{
      void tunnel?.close();
      void rm(game,{recursive:true,force:true});
    });
    const url = await new Promise((resolve,reject)=>{
      const timer=setTimeout(()=>reject(new Error('Published game startup timed out')),10000);
      child.stdout.once('data',data=>{
        clearTimeout(timer);
        const match=/http:\/\/127\.0\.0\.1:\d+/.exec(String(data));
        if (match) resolve(match[0]);
        else reject(new Error('Published game did not report a URL'));
      });
      child.once('error',error=>{clearTimeout(timer);reject(error);});
      child.once('exit',()=>{clearTimeout(timer);reject(new Error('Published game stopped'));});
    });
    if(remoteGames){
      tunnel=await QuickTunnel.open(url,{onExit:()=>child.kill(),signal:lifecycle.signal});
      await tunnel.waitReady({signal:lifecycle.signal});
      if(child.exitCode!==null || child.signalCode!==null)throw new Error('Game stopped before remote access was ready.');
    }
    return {url:tunnel?.url??url,child,saveKeys,saveFormat,close:async()=>{await tunnel?.close();await stopProcess(child);}};
  } catch (error) {
    await tunnel?.close();
    await stopProcess(child);
    await rm(game,{recursive:true,force:true});
    throw error;
  }
}
function publishedGame(publication) {
  const key=publication.job_id+':'+publication.version;
  if (!publications.has(key)) {
    if (publications.size >= 16) throw new Error('Too many open games. Restart the player service after closing games.');
    const pending=startPublishedGame(publication);
    publications.set(key,pending);
    void pending.then(game=>{pending.game=game;game.child.once('exit',()=>{
      if (publications.get(key)===pending) publications.delete(key);
    });},error=>{
      pending.failure=error;
      if (!remoteGames && publications.get(key)===pending) publications.delete(key);
    });
  }
  return publications.get(key);
}
const runs = new Map();
const opaque = () => randomBytes(32).toString('hex');
const assets = new Map([['/','index.html'],['/style.css','style.css'],['/app.mjs','app.mjs'],['/save-sync.mjs','save-sync.mjs'],['/sites.mjs','sites.mjs'],['/illustrations.mjs','illustrations.mjs']]);
const types = {html:'text/html',css:'text/css',mjs:'text/javascript'};
const sessionLifetime = 7*24*60*60*1000;
const ends = () => Date.now()+sessionLifetime;
const runEnds = () => Date.now()+12*60*60*1000;
function send(res, status, value, headers={}) {
  res.writeHead(status, {'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store', ...headers});
  res.end(JSON.stringify(value));
}
async function body(req, limit=4096) {
  let bytes=0;
  const chunks = [];
  for await (const chunk of req) {
    bytes += chunk.length;
    if (bytes > limit) throw new Error('Request too large');
    chunks.push(chunk);
  }
  return JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}');
}
function session(req) {
  const token = new RegExp(`(?:^|;\\s*)${cookieName}=([a-f0-9]{64})(?:;|$)`).exec(req.headers.cookie ?? '')?.[1];
  const account = token && db.prepare('SELECT id,username,name FROM player JOIN session ON id=player WHERE token=? AND expires>?').get(token, Date.now());
  return {token,account};
}
function profile(account) {
  return {username:account.username,name:account.name,stamps:db.prepare('SELECT game,awarded FROM stamp WHERE player=?').all(account.id)};
}
const leaderboard = db.prepare(`
  WITH totals AS (
    SELECT player.id, player.name, COUNT(*) AS medals, json_group_array(stamp.game ORDER BY stamp.game) AS games
    FROM stamp JOIN player ON player.id=stamp.player
    GROUP BY player.id
  )
  SELECT name, games, DENSE_RANK() OVER (ORDER BY medals DESC) AS rank
  FROM totals ORDER BY medals DESC, name COLLATE NOCASE, id LIMIT 100
`);
const server = createServer(async (req,res) => {
  try {
    if(process.env.PLAYER_PUBLIC_ORIGIN && req.headers.host!==new URL(origin).host)return send(res,403,{error:'来源不符'});
    const route = new URL(req.url, origin).pathname;
    if(req.method==='GET' && route==='/__pastport_ready') {res.writeHead(200,{'Cache-Control':'no-store'});res.end('pastport-remote-ready');return;}
    if (req.method === 'GET' && route === '/sites.json') return send(res,200,mapSites);
    if (req.method === 'GET' && assets.has(route)) {
      const file = assets.get(route);
      res.writeHead(200, {'Content-Type':types[file.split('.').pop()]+'; charset=utf-8','Cache-Control':'no-store'});
      res.end(await readFile(join(root,file)));
      return;
    }
    if (req.method === 'GET' && route === '/api/publications') {
      const all=await Promise.all([...siteIds].map(siteId=>readPublication(siteId).catch(error=>{console.error(error.message);return null;})));
      return send(res,200,all.filter(Boolean).map(({site_id,version,published_at})=>({site_id,version,published_at:published_at??null})));
    }
    if (req.method === 'GET' && route === '/api/leaderboard') {
      return send(res,200,leaderboard.all().map(row=>({rank:row.rank,name:row.name,games:JSON.parse(row.games)})));
    }
    const {token,account} = session(req);
    if (req.method === 'GET' && route === '/api/profile') return send(res,200,account ? profile(account) : null);
    if (req.method === 'GET' && route === '/api/launch-options') {
      if (!account) return send(res,401,{error:'请先登录，才能领取护照印章'});
      const siteId=new URL(req.url,origin).searchParams.get('site_id');
      const current=await readPublication(siteId);
      if (!current) return send(res,409,{error:'此地点尚未发布试玩。'});
      const listed=[];
      for (const save of saves.list(account.id,siteId)) {
        listed.push({version:save.version,updated:save.updated,current:save.version===current.version,
          available:!!(await publishedVersion(siteId,save.version))});
      }
      return send(res,200,{current:{version:current.version,published_at:current.published_at??null},saves:listed});
    }
    if (req.method !== 'POST') return send(res,404,{error:'未找到'});
    if (req.headers.origin !== origin) return send(res,403,{error:'来源不符'});
    const input = await body(req,route==='/api/save' ? 600*1024 : 4096);
    if (route === '/api/register' || route === '/api/login') {
      const username = typeof input.username === 'string' ? input.username.trim().toLowerCase() : '';
      const password = input.password;
      if (!/^[a-z0-9_-]{3,32}$/.test(username) || typeof password !== 'string' || password.length < 8 || password.length > 128) return send(res,400,{error:'账号用 3–32 位字母、数字、下划线或连字符。密码至少 8 位。'});
      let player = db.prepare('SELECT * FROM player WHERE username=?').get(username);
      if (route === '/api/register') {
        if (player) return send(res,409,{error:'账号已存在'});
        const name = typeof input.name === 'string' ? input.name.trim() : '';
        if (!name || name.length > 40) return send(res,400,{error:'请输入 1–40 字的昵称'});
        const salt = opaque();
        const hash = scryptSync(password,salt,64).toString('hex');
        player = {id:opaque(),username,name,salt,hash};
        db.prepare('INSERT INTO player VALUES (?,?,?,?,?)').run(player.id,username,name,salt,hash);
      } else if (!player || !timingSafeEqual(scryptSync(password,player.salt,64),Buffer.from(player.hash,'hex'))) {
        return send(res,401,{error:'账号或密码错误'});
      }
      if (token) db.prepare('DELETE FROM session WHERE token=?').run(token);
      const next = opaque();
      db.prepare('INSERT INTO session VALUES (?,?,?)').run(next,player.id,ends());
      return send(res,200,profile(player),{'Set-Cookie':`${cookieName}=${next}; Path=/; HttpOnly; SameSite=Strict; Max-Age=${sessionLifetime/1000}${secureCookie}`});
    }
    if (!account) return send(res,401,{error:'请先登录，才能领取护照印章'});
    if (route === '/api/logout') {
      db.prepare('DELETE FROM session WHERE token=?').run(token);
      for (const [id,entry] of runs) if(entry.token===token)runs.delete(id);
      return send(res,200,null,{'Set-Cookie':`${cookieName}=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0${secureCookie}`});
    }
    if (route === '/api/launch') {
      const current=await readPublication(input.site_id);
      if (!current) return send(res,409,{error:'此地点尚未发布试玩。'});
      if (!['continue','latest',undefined].includes(input.resume_mode)) return send(res,400,{error:'请求无法处理'});
      let publication=current;
      if (input.resume_mode!=='latest') {
        // Continue the requested (or most recent) saved release; a newer map release never replaces it.
        const candidates=input.version ? [input.version] : saves.list(account.id,current.site_id).map(save=>save.version);
        for (const version of candidates) {
          const found=await publishedVersion(current.site_id,version);
          if (found) {publication=found;break;}
          if (input.version) return send(res,410,{error:'此存档对应的旧版本已不可用。'});
        }
      }
      const pending=publishedGame(publication);
      if(remoteGames){
        if(pending.failure){
          publications.delete(publication.job_id+':'+publication.version);
          console.error(pending.failure.message);
          return send(res,503,{error:'远程游戏入口尚未连通，请检查网络或 DNS 后重试。'});
        }
        if(!pending.game)return send(res,202,{pending:true});
      }
      const {url,saveKeys,saveFormat} = await pending;
      const run = opaque();
      for (const [key, entry] of runs) if (entry.expires < Date.now()) runs.delete(key);
      runs.set(run,{token,siteId:publication.site_id,version:publication.version,saveKeys,saveFormat,expires:runEnds()});
      const save=saveKeys.length ? saves.read(account.id,publication.site_id,publication.version) : null;
      const namespace=createHash('sha256').update(JSON.stringify([account.id,publication.site_id,publication.version])).digest('hex');
      return send(res,200,{url:`${url}/?scene=3d&passportRun=${run}&passportScope=${namespace}`,run,version:publication.version,
        current_version:current.version,latest:publication.version===current.version,save_format:saveFormat,save,namespace});
    }
    if (route === '/api/save') {
      const issued=runs.get(input.run);
      if (!issued || issued.token!==token || issued.expires<Date.now()) return send(res,403,{error:'存档会话已失效，请返回地图重新打开游戏'});
      if (!issued.saveKeys.length) return send(res,409,{error:'此游戏尚未支持账号存档'});
      try {
        const saved=saves.write(account.id,issued.siteId,issued.version,input,issued.saveKeys,issued.saveFormat);
        return send(res,200,{revision:saved.revision,updated:saved.updated});
      } catch(error) {
        if(error instanceof SaveConflict)return send(res,409,{error:'另一设备已更新存档，请返回地图重新打开，避免覆盖',code:'SAVE_CONFLICT'});
        if(error instanceof InvalidSave)return send(res,422,{error:'存档格式不符合此游戏要求'});
        throw error;
      }
    }
    if (route === '/api/stamp') {
      const issued = runs.get(input.run);
      if (!issued || issued.token !== token || issued.expires < Date.now()) return send(res,403,{error:'本次通关回执无效'});
      db.prepare('INSERT OR IGNORE INTO stamp VALUES (?,?,?)').run(account.id,issued.siteId,new Date().toISOString());
      return send(res,200,profile(account));
    }
    send(res,404,{error:'未找到'});
  } catch (error) {
    console.error(error.message);
    if (!res.headersSent) send(res,400,{error:'请求无法处理'});
    else res.end();
  }
});
server.listen(platformPort,'127.0.0.1',()=>console.log(`PastPort player: ${origin}`));
for (const signal of ['SIGINT','SIGTERM']) process.on(signal,()=>{
  lifecycle.abort();
  server.close();
  for (const pending of publications.values()) void pending.then(game=>game.close(),()=>{});
  server.closeAllConnections();
});
