import {SaveSynchronizer} from './save-sync.mjs';
import {sites} from './sites.mjs';
import {illustration} from './illustrations.mjs';

const $ = selector => document.querySelector(selector);
let locale = localStorage.getItem('pastport:map-language') === 'en' ? 'en' : 'zh';
const t = (zh,en) => locale === 'en' ? en : zh;
const originalText = new Map([...document.querySelectorAll('[data-en], [data-en-label]')]
  .map(el => [el,el.hasAttribute('data-en') ? el.textContent : el.getAttribute(el.matches('iframe') ? 'title' : 'aria-label')]));
const errors = {
  '未找到':'Not found.',
  '存档会话已失效，请返回地图重新打开游戏':'Your save session expired. Return to the map and reopen the game.',
  '此游戏尚未支持账号存档':'This game does not support account saves yet.',
  '另一设备已更新存档，请返回地图重新打开，避免覆盖':'Another device has a newer save. Return to the map and reopen to avoid overwriting it.',
  '存档格式不符合此游戏要求':'This game snapshot could not be accepted.',
  '此地点尚未发布试玩。':'This place does not have a published game yet.',
  '来源不符':'Request origin does not match.',
  '远程游戏入口尚未连通，请检查网络或 DNS 后重试。':'Remote game access could not connect. Check network/DNS and retry.',
  '账号用 3–32 位字母、数字、下划线或连字符。密码至少 8 位。':'Use 3–32 letters, digits, underscores or hyphens for the username. Use at least 8 characters for the password.',
  '账号已存在':'That username is already taken.',
  '请输入 1–40 字的昵称':'Enter a display name between 1 and 40 characters.',
  '账号或密码错误':'Incorrect username or password.',
  '请先登录，才能领取护照印章':'Sign in to earn passport stamps.',
  '本次通关回执无效':'This completion receipt is invalid.',
  '请求无法处理':'The request could not be processed.',
};
function renderLanguage() {
  document.documentElement.lang = t('zh-Hans','en');
  document.title = t('PastPort · Bursa 遗址地图','PastPort · Bursa Heritage Map');
  $('#language').textContent = t('English','中文');
  $('#language').lang = t('en','zh-Hans');
  for (const [el,zh] of originalText) {
    if (el.hasAttribute('data-en')) el.textContent = t(zh,el.dataset.en);
    else el.setAttribute(el.matches('iframe') ? 'title' : 'aria-label',t(zh,el.dataset.enLabel));
  }
  for (const stamp of document.querySelectorAll('.map-stamp')) stamp.textContent=t('通关','Cleared');
  retrySave.textContent=t('重试保存','Retry save');
  exportSave.textContent=t('下载未同步存档','Export unsynced save');
}
const node = (tag, text, className) => {
  const el = document.createElement(tag);
  el.textContent = text;
  if (className) el.className = className;
  return el;
};
async function api(route, data) {
  const response = await fetch('/api/'+route, data === undefined ? {} : {
    method:'POST',keepalive:route==='save' && JSON.stringify(data).length<60000,headers:{'Content-Type':'application/json'},body:JSON.stringify(data),
  });
  const value = await response.json();
  if (!response.ok) {const error=new Error(t(value.error,errors[value.error] ?? value.error));error.code=value.code;throw error;}
  return value;
}
let current = null;
let active = null;
let pendingLaunch = null;
let launchRequest=0;
let claiming = false;
const modal = $('#profile-dialog');
const frame = $('#game iframe');
let saveSync=null;
const retrySave=node('button',t('重试保存','Retry save'));
const exportSave=node('button',t('下载未同步存档','Export unsynced save'));
retrySave.hidden=true;exportSave.hidden=true;
$('#game-status').after(retrySave,exportSave);
function saveStatus(state,error) {
  retrySave.hidden=state!=='failed' || error?.code==='SAVE_CONFLICT';
  exportSave.hidden=state!=='failed';
  $('#game-status').textContent=state==='failed' ? t('尚未同步：','Not synced: ')+error.message
    : state==='saved' ? t('进度已保存到账号','Progress saved to your account')
    : t('正在保存进度…','Saving progress…');
}
retrySave.onclick=()=>{void saveSync?.retry().then(()=>{if(active?.endingPending)void claimEnding(active);}).catch(()=>{});};
exportSave.onclick=()=>{
  if(!active?.save)return;
  const url=URL.createObjectURL(new Blob([JSON.stringify({site:selectedSite.id,version:active.version,entries:active.save.entries},null,2)],{type:'application/json'}));
  const link=node('a','');link.href=url;link.download='pastport-unsynced-save.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
};
window.addEventListener('pagehide',()=>{void saveSync?.flush().catch(()=>{});});
window.addEventListener('beforeunload',event=>{if(saveSync?.dirty){event.preventDefault();event.returnValue='';}});
let selectedSite = null;
const mapPoints = sites.map((site,index)=>({
  site,index,mobileX:12.5+(index%4)*25,mobileY:19+Math.floor(index/4)*22,
}));
function medal(site) {
  const badge = node('span','','medal-art');
  badge.innerHTML = illustration(site.art,sites.indexOf(site));
  badge.setAttribute('aria-hidden','true');
  return badge;
}
function medalLabel(site) {
  const item = node('span','','rank-medal');
  item.append(medal(site),node('span',site.name));
  return item;
}
const sampleTravelers = [
  {name:'Deniz',stops:[14,3,4]},
  {name:'Ece',stops:[14,1]},
  {name:'Emir',stops:[9]},
];
async function showPlace(site) {
  let available = false;
  if (site.game) {
    try {
      available = (await api('publications')).some(publication=>publication.site_id===site.game);
    } catch (error) {
      console.error(error.message);
    }
  }
  const dialog = $('#place-dialog');
  const content = $('#place-content');
  const earned = current?.stamps.some(stamp=>stamp.game===site.game);
  content.replaceChildren(medal(site),node('h2',site.name),node('p',
    earned ? t('已获得此地点的奖章。','You earned this place’s medal.')
    : available ? t('完成试玩即可获得此地点的奖章。','Complete the game to earn this place’s medal.')
    : t('此地点暂未开放试玩。','This place can be explored on the map. Its game is not available yet.')));
  if (available) {
    const play = node('button',t('进入试玩','Play game'));
    play.onclick=()=>{dialog.close();void launch(site);};
    content.append(play);
  }
  dialog.showModal();
}
let boardRequest = 0;
async function loadLeaderboard() {
  const request = ++boardRequest;
  const list = $('#rankings');
  list.replaceChildren(node('p',t('正在读取排名…','Loading rankings…')));
  try {
    const entries = await api('leaderboard');
    if (request !== boardRequest) return;
    const sample = !entries.length;
    const rows = sample ? sampleTravelers.map((person,index)=>({
      name:person.name,rank:index+1,places:person.stops.map(stop=>sites[stop]),
    })) : entries.map(entry=>({
      ...entry,places:entry.games.map(game=>sites.find(place=>place.game===game)).filter(Boolean),
    }));
    const ranking = node('ol','','rank-list');
    for (const entry of rows) {
      const row = node('li','','rank-row');
      const medals = node('div','','rank-medals');
      for (const site of entry.places) medals.append(medalLabel(site));
      row.append(node('strong',String(entry.rank)),node('span',entry.name),medals);
      ranking.append(row);
    }
    list.replaceChildren(ranking);
    if (sample) list.prepend(node('p',t('示例排名 · 虚构旅人及奖章','Sample rankings · Fictional travelers and medals'),'sample-note'));
  } catch {
    if (request === boardRequest) list.replaceChildren(node('p',t('暂时无法读取排行榜。','The leaderboard is temporarily unavailable.')));
  }
}
function showPage() {
  const page = ['#map','#leaderboard'].includes(location.hash) ? location.hash.slice(1) : 'home';
  for (const id of ['home','map','leaderboard']) document.getElementById(id).hidden=id!==page;
  $('.site-menu').open = false;
  if (page==='map') void refreshPublications().catch(console.error);
  if (page==='leaderboard') void loadLeaderboard();
}
window.addEventListener('hashchange',showPage);
$('.site-menu nav').addEventListener('click',()=>{$('.site-menu').open=false;});
function syncStamps() {
  for (const site of sites) {
    const marker=document.querySelector('[data-site-id="'+site.id+'"]');
    marker.querySelector('.map-stamp').hidden=!current?.stamps.some(entry=>entry.game===site.id);
  }
}
async function refreshPublications() {
  const published=await api('publications');
  for (const site of sites) {
    document.querySelector('[data-site-id="'+site.id+'"]').classList.toggle('unavailable',
      !published.some(publication=>publication.site_id===site.id));
  }
}
mapPoints.forEach(({site,index,mobileX,mobileY}) => {
  const marker = node('button','','marker');
  marker.type = 'button';
  marker.style.setProperty('--x',site.x+'%');
  marker.style.setProperty('--y',site.y+'%');
  marker.style.setProperty('--mobile-x', mobileX+'%');
  marker.style.setProperty('--mobile-y', mobileY+'%');
  marker.title = site.id==='42heilbronn' ? 'Heilbronn · Deutschland' : site.name;
  const thumb = node('span','','thumb');
  thumb.innerHTML = illustration(site.art,index);
  marker.append(node('span',site.name,'marker-label'),thumb);
  marker.dataset.siteId=site.id;
  {
    if (site.id==='42heilbronn') marker.id='launch';
    const stamp = node('span','通关','map-stamp');
    stamp.hidden = true;
    marker.append(stamp);
  }
  marker.classList.add('unavailable');
  marker.onclick=()=>showPlace(site);
  $('#markers').append(marker);
});
function showProfile(mode='login') {
  syncStamps();
  const content = $('#profile-content');
  const notice = $('#notice');
  notice.textContent = '';
  if (current) {
    const passport = node('div','','document');
    passport.append(node('p',t('PASTPORT · 通关文书','PASTPORT · TRAVEL PASSPORT'),'eyebrow'),node('h2',current.name),node('p','@'+current.username,'muted'));
    const stamps = node('div','','stamps');
    if (!current.stamps.length) stamps.append(node('p',t('完成已开放地点的游戏，即可领取对应的印章。','Complete a published game to earn its place’s stamp.')));
    for (const stamp of current.stamps) {
      const seal = node('div','','seal');
      const site = sites.find(place=>place.game===stamp.game);
      if (site) seal.append(medal(site));
      seal.append(node('b',site?.name ?? stamp.game),node('span',t('通关','Cleared')),node('small',new Date(stamp.awarded).toLocaleDateString(t('zh-CN','en'))));
      stamps.append(seal);
    }
    passport.append(stamps);
    const logout = node('button',t('退出登录','Sign out'),'secondary');
    logout.onclick = async()=>{
      try {
        await saveSync?.flush();
        current=await api('logout',{});
        frame.src='about:blank';$('#game').hidden=true;active=null;saveSync=null;
        showProfile();
      } catch(error){notice.textContent=error.message;}
    };
    content.replaceChildren(passport,logout);
  } else {
    const register = mode==='register';
    const form = node('form','');
    for (const [name,label,type] of [
      ...(register ? [['name',t('昵称','Display name'),'text']] : []),
      ['username',t('账号','Username'),'text'],['password',t('密码','Password'),'password'],
    ]) {
      const field = node('label',label);
      const input = node('input','');
      Object.assign(input,{name,type,required:true,maxLength:name==='password'?128:name==='name'?40:32});
      input.autocomplete = name==='password' ? (register?'new-password':'current-password') : name==='name'?'nickname':'username';
      field.append(input);
      form.append(field);
    }
    const submit = node('button',register?t('创建账号','Create account'):t('登录','Sign in'));
    const switchMode = node('button',register?t('已有账号，去登录','Already have an account? Sign in'):t('没有账号，去注册','New here? Create an account'),'secondary');
    switchMode.type='button';
    switchMode.onclick=()=>showProfile(register?'login':'register');
    form.append(submit,switchMode);
    form.onsubmit=async event=>{
      event.preventDefault();
      submit.disabled=true;
      try {
        current=await api(mode,Object.fromEntries(new FormData(form)));
        showProfile();
        if (pendingLaunch) {const site=pendingLaunch;pendingLaunch=null;await launch(site);}
      } catch(error) {notice.textContent=error.message;} finally {submit.disabled=false;}
    };
    content.replaceChildren(node('h2',register?t('创建旅人档案','Create your traveler profile'):t('登录通关文书','Sign in to your passport')),form);
  }
  if (!modal.open) modal.showModal();
}
async function launch(site) {
  const request=++launchRequest;
  selectedSite=site;
  if (!current) {pendingLaunch=site;showProfile();return;}
  try {
    $('#game strong').textContent=site.name;
    $('#game-status').textContent=t('正在连接远程游戏入口…','Connecting the remote game…');
    frame.src='about:blank';$('#game').hidden=false;
    let launch;
    for(let attempt=0;attempt<240;attempt++){
      launch=await api('launch',{site_id:site.id});
      if(request!==launchRequest)return;
      if(!launch.pending)break;
      await new Promise(resolve=>setTimeout(resolve,1000));
      if(request!==launchRequest || $('#game').hidden)return;
    }
    if(launch.pending)throw new Error(t('远程入口尚未就绪，请稍后重试','Remote access is not ready. Please retry shortly.'));
    if(request!==launchRequest || $('#game').hidden)return;
    active=launch;
    const launched=active;
    saveSync=active.save ? new SaveSynchronizer({revision:active.save.revision,
      persist:batch=>api('save',{run:launched.run,...batch}),status:saveStatus}) : null;
    retrySave.hidden=true;exportSave.hidden=true;
    $('#game strong').textContent=site.name;
    frame.title=site.name;
    if (modal.open) modal.close();
    $('#game-status').textContent=active.save ? t('正在恢复账号进度…','Restoring your account progress…') : t('此游戏仅支持本机存档','This game only supports local saves');
    const url = new URL(active.url);
    url.searchParams.set('lang',locale);
    frame.src=url.href;
    $('#game').hidden=false;
    $('#back').focus();
  } catch (error) {
    if(request!==launchRequest)return;
    $('#game').hidden=true;
    showProfile();
    $('#notice').textContent=error.message;
  }
}
renderLanguage();
showPage();
$('#language').onclick=()=>{
  locale=t('en','zh');
  localStorage.setItem('pastport:map-language',locale);
  renderLanguage();
  if (!$('#leaderboard').hidden) void loadLeaderboard();
};
$('#passport').onclick=()=>showProfile();
modal.addEventListener('close',()=>{pendingLaunch=null;});
$('#back').onclick=async()=>{
  $('#back').disabled=true;
  try {
    try {await saveSync?.flush();}
    catch {if(!confirm(t('进度尚未同步。建议先下载未同步存档。仍然返回地图并放弃本次未同步进度？','Progress is not synced. Export your unsynced save first. Return to the map and discard these unsynced changes?')))return;}
    ++launchRequest;
    $('#game').hidden=true;
    frame.src='about:blank';
    active=null;saveSync=null;
    if(selectedSite)document.querySelector(`[data-site-id="${selectedSite.id}"]`)?.focus();
  } finally {$('#back').disabled=false;}
};
window.addEventListener('message',async event=>{
  if (!active || event.source!==frame.contentWindow || event.origin!==new URL(active.url).origin || event.data?.run!==active.run) return;
  const launched=active;
  if(event.data.type==='pastport:save-ready' && active.save){
    frame.contentWindow.postMessage({type:'pastport:save-state',run:active.run,namespace:active.namespace,entries:active.save.entries},event.origin);
    $('#game-status').textContent=active.save.revision ? t('已恢复账号进度','Account progress restored') : t('新游戏 · 进度将自动保存','New game · Progress saves automatically');
    return;
  }
  if(event.data.type==='pastport:save-error'){
    $('#game-status').textContent=t('账号进度载入失败，请返回地图重试','Account save could not be loaded. Return to the map and retry.');return;
  }
  if(event.data.type==='pastport:save-change' && saveSync){
    const {key,value}=event.data;
    if(typeof key!=='string' || (value!==null && typeof value!=='string'))return;
    if(value===null)delete active.save.entries[key];else active.save.entries[key]=value;
    saveSync.queue(key,value);return;
  }
  if(event.data.type!=='pastport:ending' || claiming || active.stamped)return;
  active.endingPending=true;
  await claimEnding(launched);
});
async function claimEnding(launched) {
  if(active!==launched || claiming || launched.stamped)return;
  claiming=true;
  try {
    await saveSync?.flush();
    current=await api('stamp',{run:launched.run});
    if(active!==launched)return;
    active.stamped=true;
    $('#game-status').textContent=t('已在通关文书盖章','Passport stamped');
    showProfile();
  } catch(error) {$('#game-status').textContent=error.message;}
  finally {claiming=false;}
}
try {current=await api('profile');syncStamps();await refreshPublications();} catch (error) {console.error(error.message);}
