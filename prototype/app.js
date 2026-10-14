import { StoryEngine } from './engine.mjs';

const SAVE_KEY = 'pastport:muradiye:0.2.0';
const ui = {chapter:null, catalogue:null, engine:null, lastObservation:null, feedback:'', started:false};
const app = document.querySelector('#app');
const h = value => String(value).replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
let toastTimer;

async function load() {
  const urls = ['../data/muradiye-story.json','../data/muradiye.json','../data/task-overrides.json'];
  const responses = await Promise.all(urls.map(url => fetch(url)));
  if (responses.some(response => !response.ok)) throw new Error('章节或资料文件没有完整载入');
  const [chapter, catalogue, overrides] = await Promise.all(responses.map(response => response.json()));
  ui.chapter = resolveManualTasks(chapter, overrides);
  ui.catalogue = catalogue;
  let saved = null;
  try { saved = JSON.parse(localStorage.getItem(SAVE_KEY)); } catch (error) { console.warn('Session storage could not be read', error.name); }
  if (saved && !validSave(saved)) { saved = null; showToast('旧存档无法继续，已打开新一轮调查。'); }
  ui.engine = new StoryEngine(ui.chapter, saved);
  ui.started = Boolean(saved);
  render();
}

function validSave(saved) {
  return saved.version === ui.chapter.version && Number.isInteger(saved.scene) && saved.scene >= 0 && saved.scene < ui.chapter.scenes.length && typeof saved.elapsed === 'number' && Array.isArray(saved.inventory) && Array.isArray(saved.completed) && Array.isArray(saved.caseboard) && saved.observed && saved.decisions && saved.assignments;
}

/** Only approved overrides using the same photo and evidence universe may replace tasks. */
function resolveManualTasks(chapter, bundle) {
  if (bundle.chapter_id !== chapter.chapter_id || !Array.isArray(bundle.overrides)) throw new Error('人工任务文件不属于当前章节');
  const copy = structuredClone(chapter);
  for (const override of bundle.overrides) {
    if (override.state !== 'published') continue;
    const scene = copy.scenes.find(item => item.id === override.scene_id);
    const task = override.task;
    if (!scene || !override.approved_by || !task || task.kind !== scene.task.kind || !Array.isArray(task.required) || !Array.isArray(override.claim_ids) || !override.claim_ids.length || override.claim_ids.some(id => !scene.claim_ids.includes(id))) throw new Error('人工任务未通过场景与证据校验');
    if (['inspect','inspect-sort'].includes(task.kind)) {
      if (!Array.isArray(task.hotspots) || !task.required.length || task.required.some(id => !task.hotspots.some(spot => spot.id === id)) || task.hotspots.some(spot => !scene.claim_ids.includes(spot.claim_id) || spot.x < 0 || spot.x > 100 || spot.y < 0 || spot.y > 100)) throw new Error('人工观察任务引用了未批准的区域或证据');
    } else if (task.required.join('|') !== scene.task.required.join('|')) throw new Error('人工任务不可改写证据答案');
    scene.task = task;
  }
  return copy;
}

function persist() {
  try { localStorage.setItem(SAVE_KEY, JSON.stringify(ui.engine.snapshot())); } catch (error) { showToast('本浏览器无法保存进度；请在当前页面继续。'); console.warn('Session storage unavailable', error.name); }
}
function act(operation) {
  try { operation(); persist(); render(); } catch (error) { showToast(error.message); }
}
function photoFor(scene) { return ui.chapter.photos.find(photo => photo.id === scene.photo_id); }
function sourceLink(photo) { return `../sources/inventory/4-II.%20Murat%20K%C3%BClliyesi.pdf#page=${photo.pdf_page}`; }
function render() {
  document.querySelector('#evidence-count').textContent = ui.engine.state.inventory.length;
  if (!ui.started) return renderIntro();
  if (ui.engine.state.ending) return renderEnding();
  const engine = ui.engine;
  const scene = engine.scene;
  const photo = photoFor(scene);
  const complete = engine.state.completed.includes(scene.id);
  const seen = engine.state.observed[scene.id] || [];
  app.innerHTML = `<div class="game-shell"><div class="chapter-strip"><div><p class="eyebrow">最后两袋 / ${h(scene.place)}</p><h1>${h(scene.title)}</h1><p>你是优素福 · 试任文书员 · ${scene.id === 'arrival' ? '你的第一笔错误，还没有名字。' : engine.friend === 'with_you' ? '杰姆仍与你同行。' : engine.friend === 'pending' ? '杰姆正等待你的决定。' : '杰姆已被带走核查。'}</p></div><div class="clock ${engine.remaining < 0 ? 'late' : ''}"><strong>${engine.remaining >= 0 ? engine.remaining : '+' + -engine.remaining}</strong><span>${engine.remaining >= 0 ? '刻钟 · 距交账时限' : '刻钟 · 已超过时限'}</span><span>故事计时；不按现实时间倒数</span></div></div><div class="scene-layout"><div class="visual-column"><figure class="photograph"><div class="photo-surface"><img class="scene-photo" src="${h(photo.file)}" alt="${h(photo.caption)}"><span class="photo-tag">现存遗址 · 当代实拍</span><button class="enlarge" id="enlarge-photo">查看大图 ↗</button>${(scene.task.hotspots || []).map((spot, index) => `<button class="hotspot ${seen.includes(spot.id) ? 'seen' : ''}" style="left:${spot.x}%;top:${spot.y}%" data-inspect="${h(spot.id)}" aria-label="检查区域 ${index+1}：${h(spot.label)}">${index+1}</button>`).join('')}</div><figcaption class="photo-caption">${h(photo.caption)} · 库存卷印刷页 ${h(photo.printed_page)} · <a href="${sourceLink(photo)}" target="_blank" rel="noreferrer">原始页与说明 ↗</a></figcaption></figure>${renderTask(scene, complete, seen)}${renderSources(scene)}</div><section class="narrative" aria-live="polite"><div class="scene-intro"><p class="eyebrow">SCENE ${String(engine.state.scene+1).padStart(2,'0')} / 05</p><h2>${h(scene.title)}</h2><p class="scene-goal">${h(scene.goal)}</p>${renderBranch(scene)}${renderLines(scene.opening)}</div><div class="scene-consequence">${complete ? `<div class="after-story">${renderLines(scene.after)}${renderDecision(scene)}</div>` : `<p class="waiting">${h(scene.task.prompt)}<br>完成本幕的调查行动，才能推进这一幕。</p>`}${engine.canAdvance() && scene.next ? `<button class="primary advance" id="advance">${h(ui.chapter.scenes.find(item => item.id === scene.next).title)} <span>→</span></button>` : ''}</div></section></div><nav class="rail" aria-label="调查路线">${ui.chapter.scenes.map((item,index) => `<div class="rail-step ${index === engine.state.scene ? 'current' : index < engine.state.scene ? 'done' : ''}"><b>${index < engine.state.scene ? '✓' : '0'+(index+1)}</b><span>${h(item.place.split(' · ')[0])}</span></div>`).join('')}</nav><p class="fiction-label">${h(ui.chapter.fiction_notice)}</p></div>`;
  bindScene(scene);
}
function renderIntro() {
  app.innerHTML = `<section class="hero"><img class="hero-photo" src="assets/aerial.jpg" alt="穆拉迪耶建筑群及柏萨山城实拍"><div class="hero-content"><p class="eyebrow">PASTPORT / 第一案 / BURSA</p><h1>最后<em>两袋</em></h1><p class="hook">粮仓少了两袋。<br>替你担保的学徒，将在交账前被带走。<br>而那张账上的签名，是你的。</p><p class="summary">你是刚上任的文书员优素福。在 Muradiye 的庭院、喷泉和施食所里，找到货物去了哪里，也决定谁为这笔错误付出代价。</p><button class="primary" id="start">打开那张账 <span>→</span></button><p class="hero-meta">五幕短篇 · 真实照片观察 / 证词取舍 / 分账操作<br>1430 年代原创故事 · 当前遗址实拍 · 进度自动保存在本浏览器<br>无需到场，也无需定位权限。</p></div></section>`;
  document.querySelector('#start').addEventListener('click', () => { ui.started = true; persist(); render(); window.scrollTo(0,0); });
}
function renderLines(lines) { return lines.map(line => `<div class="line ${line.speaker.startsWith('你') ? 'mine' : ''}"><span class="speaker">${h(line.speaker)}</span><p>${h(line.text)}</p></div>`).join(''); }
function renderBranch(scene) {
  const engine = ui.engine;
  if (scene.id === 'fountain') return `<div class="branch-note">${engine.friend === 'with_you' ? '杰姆陪你走到喷泉。哈丽梅认出他：‘就是这个孩子。他手上沾的是面粉，不是麦粒。要我具名，你得陪我把话说清楚。’' : '你独自走到喷泉。哈丽梅听见杰姆已被带走，停下了手里的杯子：‘你让他们先抓人，再来问我？厨房那张单没有写送货人的名字。’'}</div>`;
  if (scene.id === 'imaret') return `<div class="branch-note">${engine.hasWitness ? '哈丽梅跟你走来。她可以辨认搬运者；你终于有了一份不只证明数量的证词。' : '哈丽梅留在喷泉旁。你有装车单，但还没有人愿意为搬运者具名。'} ${engine.friend === 'with_you' ? '杰姆把装车单展开在你面前。' : '你展开杰姆留下的装车单。他没法替你问厨房的人。'}</div>`;
  if (scene.id === 'reckoning') return `<div class="branch-note">${engine.hasWitness ? '哈丽梅把具名证词放在桌上，证明杰姆是送货者。' : '厨房收料单证明两袋面粉到达，却没有搬运者的名字。你现在能解释物资，尚不能完整证明杰姆的行动。'} ${engine.remaining < 1 ? '等候交账的人已经开始催促。署名更正仍需要一刻钟。' : '你仍有时间保留原账并补记更正。'}</div>`;
  return '';
}
function renderTask(scene, complete, seen) {
  if (scene.task.kind === 'document') return `<div class="inspection-panel"><h3>一张属于你的账</h3><p>管事拿出了早晨那张原账。看清送达品类与誊写品类的区别。</p>${complete ? renderTally() : '<button class="primary" id="open-tally" style="margin-top:14px">展开签收账页 →</button>'}</div>`;
  if (scene.task.kind === 'caseboard') {
    const cards = ui.engine.state.inventory;
    return `<div class="inspection-panel"><h3>把三份材料摆到核账板上</h3><p>选出原账、装车分类和实际收料。证词用于核对搬运者，不能代替货物数量。</p>${cards.map(id => {const item=ui.chapter.evidence.find(item=>item.id===id);return `<button class="case-card ${ui.engine.state.caseboard.includes(id)?'selected':''}" data-board="${h(id)}" ${complete?'disabled':''}><strong>${ui.engine.state.caseboard.includes(id)?'✓ ':''}${h(item.name)}</strong><span>${h(item.text)}</span></button>`;}).join('')}<button class="primary" id="check-board" ${complete?'disabled':''}>${complete?'核账链已闭合':'核对这三份材料'}</button>${ui.feedback?`<p class="feedback">${h(ui.feedback)}</p>`:''}</div>`;
  }
  const inspected = scene.task.required.filter(id => seen.includes(id)).length;
  return `<div class="inspection-panel"><h3>观察遗址，推动调查</h3><p>${h(scene.task.prompt)}</p><details class="region-alternative"><summary>用文字检查照片区域</summary><div class="region-buttons">${scene.task.hotspots.map((spot,index) => `<button data-inspect="${h(spot.id)}" class="${seen.includes(spot.id)?'seen':''}">${index+1} · ${h(spot.label)}</button>`).join('')}</div></details><div class="inspection-progress">已找到关键构件 ${inspected} / ${scene.task.required.length}${complete?' · 调查行动完成':''}</div>${ui.lastObservation?`<div class="observed-note"><h3>${h(ui.lastObservation.label)}</h3><p>${h(ui.lastObservation.text)}</p></div>`:''}</div>${scene.sorting && ui.engine.canSort()?renderSorting(scene,complete):''}`;
}
function renderTally() { return `<article class="paper"><span class="stamp">原创游戏道具 · 非历史文献</span><h3>早晨的签收账页</h3><div class="entry"><span>送达清点</span><strong>12 袋货物</strong></div><div class="entry error"><span>正式入库誊写</span><strong>麦粒 12 袋</strong></div><p>纸角备注：<u>品类待核</u></p><p class="signature">Yusuf / 优素福</p><p class="fine">你的签名仍在，备注却没有进入正式账。</p></article>`; }
function renderSorting(scene,complete) { return `<div class="sorting"><h3>拆开总数，把货物分回两本账</h3><p class="feedback">完整核账需 2 刻钟；确认分账后计入。</p><p class="fiction-label">游戏道具模拟 · 数字与单据均为虚构</p>${scene.sorting.cards.map(card=>`<div class="sorting-row"><label for="sort-${h(card.id)}">${h(card.label)}</label><select id="sort-${h(card.id)}" data-card="${h(card.id)}" ${complete?'disabled':''}><option value="">选择记录去向</option>${scene.sorting.destinations.map(item=>`<option value="${h(item.id)}" ${ui.engine.state.assignments[card.id]===item.id?'selected':''}>${h(item.label)}</option>`).join('')}</select></div>`).join('')}<button class="primary" id="check-sort" ${complete?'disabled':''}>${complete?'两本账已对上':'合并核对 →'}</button>${ui.feedback?`<p class="feedback">${h(ui.feedback)}</p>`:''}</div>`; }
function renderDecision(scene) {
  if (!scene.decision) return '';
  const decision = scene.decision;
  const selected = ui.engine.state.decisions[decision.id];
  return `<h3 class="choice-title">${h(decision.prompt)}</h3>${decision.options.map(option=>`<button class="choice ${selected===option.id?'selected':''}" data-choice="${h(option.id)}" ${selected?'disabled':''}><span class="cost">${option.cost?'用 '+option.cost+' 刻钟':'不额外用时'}</span><strong>${selected===option.id?'✓ ':''}${h(option.label)}</strong><small>${h(option.detail)}</small></button>`).join('')}${selected?`<p class="feedback">${h(decisionConsequence(decision.id,selected))}</p>`:''}`;
}
function decisionConsequence(id,selected) {
  const messages = {'friend:vouch':'你具名担保。杰姆留在你身边；管事把这次担保也记到了你名下。','friend:detain':'看守带走了杰姆。他没有责骂你，只把装车单推回你的手里。','witness:help':'哈丽梅具名并跟你一起去厨房。证词已经收入笔记，你付出了两刻钟。','witness:hurry':'你走得很快。哈丽梅没有跟上来，也没有替送货人签字。'};
  return messages[id+':'+selected] || '你的报告已经提交。';
}
function renderSources(scene) {
  return `<details class="sources"><summary>这张照片和遗址的真实依据</summary>${scene.claim_ids.map(id=>{const claim=ui.catalogue.claims.find(item=>item.id===id);if(!claim)return '';return `<div class="claim">${h(claim.text)}${claim.caveat?`<br>${h(claim.caveat)}`:''}<br>${claim.source_ids.map(sourceId=>{const source=ui.catalogue.sources.find(item=>item.id===sourceId);return source?`<a href="${h(source.url)}" target="_blank" rel="noreferrer">${h(source.title)}</a>`:'';}).join(' · ')}</div>`;}).join('')}<p>证词、纸片、会面与案件数量为原创，不由照片证明。照片只支持可见构件及经出版物确认的建筑身份。</p></details>`;
}
function bindScene(scene) {
  document.querySelector('#enlarge-photo').addEventListener('click',()=>{const photo=photoFor(scene);document.querySelector('#large-photo').src=photo.file;document.querySelector('#large-photo').alt=photo.caption;document.querySelector('#large-caption').textContent=photo.caption+' · 库存卷印刷页 '+photo.printed_page+' · 当代实拍';document.querySelector('#photo-dialog').showModal();});
  document.querySelectorAll('[data-inspect]').forEach(button=>button.addEventListener('click',()=>act(()=>{ui.lastObservation=scene.task.hotspots.find(item=>item.id===button.dataset.inspect);ui.engine.inspect(button.dataset.inspect);} )));
  document.querySelector('#open-tally')?.addEventListener('click',()=>act(()=>{ui.engine.openTally();showToast('原账已经保存在调查笔记中。');}));
  document.querySelectorAll('[data-choice]').forEach(button=>button.addEventListener('click',()=>act(()=>{ui.engine.choose(button.dataset.choice);ui.feedback='';} )));
  document.querySelectorAll('[data-card]').forEach(select=>select.addEventListener('change',()=>{if(!select.value)return;act(()=>ui.engine.assign(select.dataset.card,select.value));}));
  document.querySelector('#check-sort')?.addEventListener('click',()=>act(()=>{ui.feedback=ui.engine.checkSorting()?scene.sorting.success:'两袋面粉不会出现在麦粒库里。再把装车品类和厨房收料对照一次。';}));
  document.querySelectorAll('[data-board]').forEach(button=>button.addEventListener('click',()=>act(()=>{ui.engine.toggleBoard(button.dataset.board);ui.feedback='';} )));
  document.querySelector('#check-board')?.addEventListener('click',()=>act(()=>{ui.feedback=ui.engine.checkBoard()?'装车分类、两处收料与原账并列，错误的来源可以追溯。':'这条链需要三份原始材料，不能只交你自己算出的结论。';}));
  document.querySelector('#advance')?.addEventListener('click',()=>act(()=>{ui.engine.advance();ui.lastObservation=null;ui.feedback='';window.scrollTo(0,0);}));
}
function renderEnding() {
  const ending=ui.engine.state.ending;
  app.innerHTML=`<section class="ending"><p class="eyebrow">一案结束 / 你保留了谁的名字</p><h1>${h(ending.title)}</h1><img class="ending-photo" src="assets/imaret-inside.jpg" alt="施食所当代室内照片"><div class="outcomes">${[['你的职位',ending.career],['杰姆与证人',ending.friend],['这一餐',ending.service]].map(([name,text])=>`<article class="outcome"><h3>${h(name)}</h3><p>${h(text)}</p></article>`).join('')}</div><p class="growth">${h(ending.growth)}</p><div class="reflection"><h3>这些建筑为什么在一起？</h3><p>庭院让学习发生，喷泉承担饮水，施食所组织供餐。文书、保管与厨房各负其责，才能让同一批物资成为一项服务。你刚才查到的是原创案件；留下的空间关系，来自 Muradiye 的真实遗产。</p><p>本案用了五张出版物实拍、三组构件观察和一条可追溯的核账链。你可以在笔记里回看原账、单据与证词。</p><a href="https://www.vakifkatilim.com.tr/tr/hakkimizda/medya-merkezi/yayinlarimiz" target="_blank" rel="noreferrer">继续了解 Bursa 的 vakıf 遗产 ↗</a></div><button class="primary" id="replay">回到那张账，作出另一个选择 ↻</button><p class="fiction-label">${h(ui.chapter.fiction_notice)}</p></section>`;
  document.querySelector('#replay').addEventListener('click',restart);
  window.scrollTo(0,0);
}
function openNotebook() {
  if (!ui.engine) return;
  document.querySelector('#notebook-body').innerHTML=ui.engine.state.inventory.map(id=>{const item=ui.chapter.evidence.find(item=>item.id===id);return `<article class="note-card"><small>原创案件道具</small><h3>${h(item.name)}</h3><p>${h(item.text)}</p></article>`;}).join('') || '<p class="waiting">你还没有展开原账。进入调查后，单据与证词会保存在这里。</p>';
  document.querySelector('#notebook').showModal();
}
function restart() { try {localStorage.removeItem(SAVE_KEY);} catch(error){console.warn('Could not remove session',error.name);}ui.engine=new StoryEngine(ui.chapter);ui.started=false;ui.lastObservation=null;ui.feedback='';render();window.scrollTo(0,0); }
function showToast(text) {const toast=document.querySelector('#toast');toast.textContent=text;toast.classList.add('show');clearTimeout(toastTimer);toastTimer=setTimeout(()=>toast.classList.remove('show'),3500);}
document.querySelector('#notebook-button').addEventListener('click',openNotebook);
document.querySelector('#close-notebook').addEventListener('click',()=>document.querySelector('#notebook').close());
document.querySelector('#close-photo').addEventListener('click',()=>document.querySelector('#photo-dialog').close());
document.querySelector('#restart-button').addEventListener('click',()=>{if(ui.chapter)restart();});
load().catch(error=>{app.innerHTML=`<div class="failure"><h1>这份案件没有完整打开</h1><p>${h(error.message)}</p><p>请刷新页面，或从项目目录启动本地服务。</p></div>`;console.error(error);});

function openMap() {
  const sites=ui.catalogue.spatial_context;
  document.querySelector('#map-body').innerHTML=`<p class="map-note">北向上 · 相对关系示意，非测绘平面；标记不能用于现场定位。GPS 尚未启用。</p><div class="site-schematic"><span class="north">N ↑</span>${sites.map(site=>`<button style="left:${site.x}%;top:${site.y}%" data-site="${h(site.id)}">${h(site.name)}</button>`).join('')}</div><div id="map-description" class="branch-note">选择建筑查看与本案的关系。</div><p class="map-note">陵墓群属于当代遗址目录的扩展内容；出版物所列年代为 1442–1573 年，本章不把这些后建建筑放入 1430 年代的案情。</p>`;
  document.querySelectorAll('[data-site]').forEach(button=>button.addEventListener('click',()=>{const site=sites.find(item=>item.id===button.dataset.site);document.querySelector('#map-description').textContent=site.name+' · 印刷页 '+site.page+'：'+site.text;}));
  document.querySelector('#site-map').showModal();
}
let archiveAssets=null;
async function openArchive() {
  document.querySelector('#archive').showModal();
  document.querySelector('#archive-body').textContent='正在读取照片索引…';
  try {
    if (!archiveAssets) {
      const responses=await Promise.all([fetch('../data/media_manifest.csv'),fetch('../data/drive_file_ids.csv')]);
      if(responses.some(response=>!response.ok))throw new Error('照片档案暂时无法读取');
      const [manifest,ids]=await Promise.all(responses.map(response=>response.text()));
      const idMap=new Map(parseCsv(ids).map(row=>[row.filename,row.drive_file_id]));
      archiveAssets=parseCsv(manifest).map(row=>({...row,url:'https://drive.google.com/file/d/'+idMap.get(row.filename)+'/view'}));
    }
    renderArchive();
  } catch(error) {document.querySelector('#archive-body').textContent=error.message;console.error(error);}
}
function renderArchive() {
  const query=document.querySelector('#photo-search').value.toLowerCase();
  const matches=archiveAssets.filter(asset=>asset.filename.toLowerCase().includes(query));
  document.querySelector('#archive-body').innerHTML=`<p class="map-note">本章嵌入的五张实拍来自同一库存出版物，并已按页核对建筑身份。下列 93 张 Drive 原片仍保留各自的定位审核状态。</p><p class="map-note">找到 ${matches.length} 张</p>`+matches.map(asset=>`<article class="note-card"><small>${asset.mapping_state==='unmapped'?'位置未核':'暂定对应'}</small><h3><a href="${h(asset.url)}" target="_blank" rel="noreferrer">${h(asset.filename)} ↗</a></h3><p>${h(asset.observed_content)}</p></article>`).join('');
}
function parseCsv(text) {
  const rows=[];let row=[],field='',quoted=false;
  for(let index=0;index<text.length;index+=1){const ch=text[index];if(quoted && ch==='"' && text[index+1]==='"'){field+='"';index+=1;}else if(ch==='"')quoted=!quoted;else if(ch===',' && !quoted){row.push(field);field='';}else if((ch==='\n'||ch==='\r')&&!quoted){if(ch==='\r'&&text[index+1]==='\n')index+=1;row.push(field);if(row.some(item=>item))rows.push(row);row=[];field='';}else field+=ch;}
  if(field||row.length){row.push(field);rows.push(row);}const[headers,...records]=rows;
  return records.map(values=>Object.fromEntries(headers.map((header,index)=>[header,values[index]||''])));
}
document.querySelector('#map-button').addEventListener('click',()=>{if(ui.catalogue)openMap();});
document.querySelector('#close-map').addEventListener('click',()=>document.querySelector('#site-map').close());
document.querySelector('#archive-button').addEventListener('click',()=>{if(ui.catalogue)openArchive();});
document.querySelector('#close-archive').addEventListener('click',()=>document.querySelector('#archive').close());
document.querySelector('#photo-search').addEventListener('input',()=>{if(archiveAssets)renderArchive();});
