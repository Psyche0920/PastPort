import { StoryEngine } from './engine.mjs';

const SAVE_KEY = 'pastport:muradiye:0.2.0';
const ui = {chapter:null, catalogue:null, engine:null, lastObservation:null, feedback:'', started:false};
const app = document.querySelector('#app');
const h = value => String(value).replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
let toastTimer;

async function load() {
  const urls = ['../data/muradiye-story.json','../data/muradiye.json','../data/task-overrides.json'];
  const responses = await Promise.all(urls.map(url => fetch(url)));
  if (responses.some(response => !response.ok)) throw new Error('Could not load all chapter files');
  const [chapter, catalogue, overrides] = await Promise.all(responses.map(response => response.json()));
  ui.chapter = resolveManualTasks(chapter, overrides);
  ui.catalogue = catalogue;
  let saved = null;
  try { saved = JSON.parse(localStorage.getItem(SAVE_KEY)); } catch (error) { console.warn('Session storage could not be read', error.name); }
  if (saved && !validSave(saved)) { saved = null; showToast('This save is out of date. A new case is ready.'); }
  ui.engine = new StoryEngine(ui.chapter, saved);
  ui.started = Boolean(saved);
  render();
}

function validSave(saved) {
  return saved.version === ui.chapter.version && Number.isInteger(saved.scene) && saved.scene >= 0 && saved.scene < ui.chapter.scenes.length && typeof saved.elapsed === 'number' && Array.isArray(saved.inventory) && Array.isArray(saved.completed) && Array.isArray(saved.caseboard) && saved.observed && saved.decisions && saved.assignments;
}

/** Only approved overrides using the same photo and evidence universe may replace tasks. */
function resolveManualTasks(chapter, bundle) {
  if (bundle.chapter_id !== chapter.chapter_id || !Array.isArray(bundle.overrides)) throw new Error('The task overrides belong to another chapter.');
  const copy = structuredClone(chapter);
  for (const override of bundle.overrides) {
    if (override.state !== 'published') continue;
    const scene = copy.scenes.find(item => item.id === override.scene_id);
    const task = override.task;
    if (!scene || !override.approved_by || !task || task.kind !== scene.task.kind || !Array.isArray(task.required) || !Array.isArray(override.claim_ids) || !override.claim_ids.length || override.claim_ids.some(id => !scene.claim_ids.includes(id))) throw new Error('The task override failed scene and evidence checks.');
    if (['inspect','inspect-sort'].includes(task.kind)) {
      if (!Array.isArray(task.hotspots) || !task.required.length || task.required.some(id => !task.hotspots.some(spot => spot.id === id)) || task.hotspots.some(spot => !scene.claim_ids.includes(spot.claim_id) || spot.x < 0 || spot.x > 100 || spot.y < 0 || spot.y > 100)) throw new Error('The task uses an unapproved photo area or source.');
    } else if (task.required.join('|') !== scene.task.required.join('|')) throw new Error('Editorial tasks cannot change evidence answers.');
    scene.task = task;
  }
  return copy;
}

function persist() {
  try { localStorage.setItem(SAVE_KEY, JSON.stringify(ui.engine.snapshot())); } catch (error) { showToast('Progress could not be saved. Keep this page open.'); console.warn('Session storage unavailable', error.name); }
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
  app.innerHTML = `<div class="game-shell"><div class="chapter-strip"><div><p class="eyebrow">The Last Two Sacks / ${h(scene.place)}</p><h1>${h(scene.title)}</h1><p>You are Yusuf · Probationary clerk · ${scene.id === 'arrival' ? 'Your first mistake is still unnamed.' : engine.friend === 'with_you' ? 'Cem is still with you.' : engine.friend === 'pending' ? 'Cem is waiting for your decision.' : 'Cem has been taken in for questioning.'}</p></div><div class="clock ${engine.remaining < 0 ? 'late' : ''}"><strong>${engine.remaining >= 0 ? engine.remaining : '+' + -engine.remaining}</strong><span>${engine.remaining >= 0 ? 'minutes · until the accounts are due' : 'minutes · past the deadline'}</span><span>Story time only · No real-time countdown</span></div></div><div class="scene-layout"><div class="visual-column"><figure class="photograph"><div class="photo-surface"><img class="scene-photo" src="${h(photo.file)}" alt="${h(photo.caption)}"><span class="photo-tag">Standing site · Photo taken today</span><button class="enlarge" id="enlarge-photo">View photo ↗</button>${(scene.task.hotspots || []).map((spot, index) => `<button class="hotspot ${seen.includes(spot.id) ? 'seen' : ''}" style="left:${spot.x}%;top:${spot.y}%" data-inspect="${h(spot.id)}" aria-label="Inspect area ${index+1}:${h(spot.label)}">${index+1}</button>`).join('')}</div><figcaption class="photo-caption">${h(photo.caption)} · Inventory · p. ${h(photo.printed_page)} · <a href="${sourceLink(photo)}" target="_blank" rel="noreferrer">Source page ↗</a></figcaption></figure>${renderTask(scene, complete, seen)}${renderSources(scene)}</div><section class="narrative" aria-live="polite"><div class="scene-intro"><p class="eyebrow">SCENE ${String(engine.state.scene+1).padStart(2,'0')} / 05</p><h2>${h(scene.title)}</h2><p class="scene-goal">${h(scene.goal)}</p>${renderBranch(scene)}${renderLines(scene.opening)}</div><div class="scene-consequence">${complete ? `<div class="after-story">${renderLines(scene.after)}${renderDecision(scene)}</div>` : `<p class="waiting">${h(scene.task.prompt)}<br>Complete this task to move the story forward.</p>`}${engine.canAdvance() && scene.next ? `<button class="primary advance" id="advance">${h(ui.chapter.scenes.find(item => item.id === scene.next).title)} <span>→</span></button>` : ''}</div></section></div><nav class="rail" aria-label="Case route">${ui.chapter.scenes.map((item,index) => `<div class="rail-step ${index === engine.state.scene ? 'current' : index < engine.state.scene ? 'done' : ''}"><b>${index < engine.state.scene ? '✓' : '0'+(index+1)}</b><span>${h(item.place.split(' · ')[0])}</span></div>`).join('')}</nav><p class="fiction-label">${h(ui.chapter.fiction_notice)}</p></div>`;
  bindScene(scene);
}
function renderIntro() {
  app.innerHTML = `<section class="hero"><img class="hero-photo" src="assets/aerial.jpg" alt="A modern photo of the Muradiye complex in Bursa"><div class="hero-content"><p class="eyebrow">PASTPORT / CASE 01 / BURSA</p><h1>The <em>Last Two Sacks</em></h1><p class="hook">Two sacks are missing.<br>The apprentice who vouched for you will be taken before the accounts close.<br>And your name is on the ledger.</p><p class="summary">You are Yusuf, a new clerk. Search Muradiye’s courtyard, fountain, and kitchen to find the sacks—and decide who pays for your mistake.</p><button class="primary" id="start">Open the ledger <span>→</span></button><p class="hero-meta">A five-scene mystery · Photo clues / witness choices / a hands-on stock check<br>An original story set in the 1430s · Modern site photos · Progress saved in this browser<br>Play from anywhere. No location access needed.</p></div></section>`;
  document.querySelector('#start').addEventListener('click', () => { ui.started = true; persist(); render(); window.scrollTo(0,0); });
}
function renderLines(lines) { return lines.map(line => `<div class="line ${line.speaker.startsWith('You') ? 'mine' : ''}"><span class="speaker">${h(line.speaker)}</span><p>${h(line.text)}</p></div>`).join(''); }
function renderBranch(scene) {
  const engine = ui.engine;
  if (scene.id === 'fountain') return `<div class="branch-note">${engine.friend === 'with_you' ? 'Cem walks with you. Halime recognizes him: “That is the boy. He has flour on his hands, not grain. I will sign if you help me explain what happened.”' : 'You reach the fountain alone. Halime hears Cem was taken away and sets down her cup: “You let them take him before asking me? The kitchen slip has no delivery name.”'}</div>`;
  if (scene.id === 'imaret') return `<div class="branch-note">${engine.hasWitness ? 'Halime comes with you. She can identify the carrier, giving you more than a count of the goods.' : 'Halime stays by the fountain. You have the loading slip, but no one will identify the carrier.'} ${engine.friend === 'with_you' ? 'Cem unfolds the loading slip for you.' : 'You unfold the slip Cem left behind. He cannot help you question the kitchen.'}</div>`;
  if (scene.id === 'reckoning') return `<div class="branch-note">${engine.hasWitness ? 'Halime lays her signed statement on the table. It identifies Cem as the delivery person.' : 'The kitchen receipt proves the flour arrived, but it does not name the carrier. You can account for the goods, but cannot fully prove Cem’s part.'} ${engine.remaining < 1 ? 'People waiting for the accounts are getting restless. A signed correction takes one more minute.' : 'There is still time to keep the original ledger and sign a correction.'}</div>`;
  return '';
}
function renderTask(scene, complete, seen) {
  if (scene.task.kind === 'document') return `<div class="inspection-panel"><h3>Your Ledger</h3><p>The steward brings out the morning ledger. Compare what arrived with what you recorded.</p>${complete ? renderTally() : '<button class="primary" id="open-tally" style="margin-top:14px">Open the delivery ledger →</button>'}</div>`;
  if (scene.task.kind === 'caseboard') {
    const cards = ui.engine.state.inventory;
    return `<div class="inspection-panel"><h3>Build the case</h3><p>Choose the original ledger, delivery list, and kitchen receipt. A witness can identify the carrier, but cannot replace a stock record.</p>${cards.map(id => {const item=ui.chapter.evidence.find(item=>item.id===id);return `<button class="case-card ${ui.engine.state.caseboard.includes(id)?'selected':''}" data-board="${h(id)}" ${complete?'disabled':''}><strong>${ui.engine.state.caseboard.includes(id)?'✓ ':''}${h(item.name)}</strong><span>${h(item.text)}</span></button>`;}).join('')}<button class="primary" id="check-board" ${complete?'disabled':''}>${complete?'Case complete':'Check these three records'}</button>${ui.feedback?`<p class="feedback">${h(ui.feedback)}</p>`:''}</div>`;
  }
  const inspected = scene.task.required.filter(id => seen.includes(id)).length;
  return `<div class="inspection-panel"><h3>Explore the photo</h3><p>${h(scene.task.prompt)}</p><details class="region-alternative"><summary>Choose a spot from the list</summary><div class="region-buttons">${scene.task.hotspots.map((spot,index) => `<button data-inspect="${h(spot.id)}" class="${seen.includes(spot.id)?'seen':''}">${index+1} · ${h(spot.label)}</button>`).join('')}</div></details><div class="inspection-progress">Clues found ${inspected} / ${scene.task.required.length}${complete?' · Task complete':''}</div>${ui.lastObservation?`<div class="observed-note"><h3>${h(ui.lastObservation.label)}</h3><p>${h(ui.lastObservation.text)}</p></div>`:''}</div>${scene.sorting && ui.engine.canSort()?renderSorting(scene,complete):''}`;
}
function renderTally() { return `<article class="paper"><span class="stamp">Fictional game prop · Not a historical document</span><h3>Morning delivery ledger</h3><div class="entry"><span>Delivered</span><strong>12 sacks</strong></div><div class="entry error"><span>Official entry</span><strong>12 sacks of grain</strong></div><p>Margin note: <u>check types of goods</u></p><p class="signature">Yusuf</p><p class="fine">Your signature is there. The note is not.</p></article>`; }
function renderSorting(scene,complete) { return `<div class="sorting"><h3>Sort the goods into the right records</h3><p class="feedback">This check takes 2 story minutes. Time counts when you confirm.</p><p class="fiction-label">Fictional game props · All figures and records are invented</p>${scene.sorting.cards.map(card=>`<div class="sorting-row"><label for="sort-${h(card.id)}">${h(card.label)}</label><select id="sort-${h(card.id)}" data-card="${h(card.id)}" ${complete?'disabled':''}><option value="">Choose a destination</option>${scene.sorting.destinations.map(item=>`<option value="${h(item.id)}" ${ui.engine.state.assignments[card.id]===item.id?'selected':''}>${h(item.label)}</option>`).join('')}</select></div>`).join('')}<button class="primary" id="check-sort" ${complete?'disabled':''}>${complete?'Records match':'Check the records →'}</button>${ui.feedback?`<p class="feedback">${h(ui.feedback)}</p>`:''}</div>`; }
function renderDecision(scene) {
  if (!scene.decision) return '';
  const decision = scene.decision;
  const selected = ui.engine.state.decisions[decision.id];
  return `<h3 class="choice-title">${h(decision.prompt)}</h3>${decision.options.map(option=>`<button class="choice ${selected===option.id?'selected':''}" data-choice="${h(option.id)}" ${selected?'disabled':''}><span class="cost">${option.cost?'Use '+option.cost+' min':'No extra time'}</span><strong>${selected===option.id?'✓ ':''}${h(option.label)}</strong><small>${h(option.detail)}</small></button>`).join('')}${selected?`<p class="feedback">${h(decisionConsequence(decision.id,selected))}</p>`:''}`;
}
function decisionConsequence(id,selected) {
  const messages = {'friend:vouch':'You vouched for Cem. He stays with you, and the steward records your guarantee.','friend:detain':'The guard takes Cem away. He says nothing; he only hands the loading slip back.','witness:help':'Halime signs and goes with you to the kitchen. Her statement is in your notes. It cost two minutes.','witness:hurry':'You hurry on. Halime does not follow or sign for the delivery person.'};
  return messages[id+':'+selected] || 'Your report has been submitted.';
}
function renderSources(scene) {
  return `<details class="sources"><summary>The real history behind this photo</summary>${scene.claim_ids.map(id=>{const claim=ui.catalogue.claims.find(item=>item.id===id);if(!claim)return '';return `<div class="claim">${h(claim.text)}${claim.caveat?`<br>${h(claim.caveat)}`:''}<br>${claim.source_ids.map(sourceId=>{const source=ui.catalogue.sources.find(item=>item.id===sourceId);return source?`<a href="${h(source.url)}" target="_blank" rel="noreferrer">${h(source.title)}</a>`:'';}).join(' · ')}</div>`;}).join('')}<p>The testimony, notes, meetings, and case figures are fictional. Photos show visible features and structures identified by the cited publication.</p></details>`;
}
function bindScene(scene) {
  document.querySelector('#enlarge-photo').addEventListener('click',()=>{const photo=photoFor(scene);document.querySelector('#large-photo').src=photo.file;document.querySelector('#large-photo').alt=photo.caption;document.querySelector('#large-caption').textContent=photo.caption+' · Inventory · p. '+photo.printed_page+' · Photo taken today';document.querySelector('#photo-dialog').showModal();});
  document.querySelectorAll('[data-inspect]').forEach(button=>button.addEventListener('click',()=>act(()=>{ui.lastObservation=scene.task.hotspots.find(item=>item.id===button.dataset.inspect);ui.engine.inspect(button.dataset.inspect);} )));
  document.querySelector('#open-tally')?.addEventListener('click',()=>act(()=>{ui.engine.openTally();showToast('The original ledger is now in your case notes.');}));
  document.querySelectorAll('[data-choice]').forEach(button=>button.addEventListener('click',()=>act(()=>{ui.engine.choose(button.dataset.choice);ui.feedback='';} )));
  document.querySelectorAll('[data-card]').forEach(select=>select.addEventListener('change',()=>{if(!select.value)return;act(()=>ui.engine.assign(select.dataset.card,select.value));}));
  document.querySelector('#check-sort')?.addEventListener('click',()=>act(()=>{ui.feedback=ui.engine.checkSorting()?scene.sorting.success:'The flour will not be in the grain store. Compare the delivery slip with the kitchen receipt.';}));
  document.querySelectorAll('[data-board]').forEach(button=>button.addEventListener('click',()=>act(()=>{ui.engine.toggleBoard(button.dataset.board);ui.feedback='';} )));
  document.querySelector('#check-board')?.addEventListener('click',()=>act(()=>{ui.feedback=ui.engine.checkBoard()?'The delivery slip, two receipts, and original ledger now show where the error began.':'Use all three original records. Your own calculation is not enough.';}));
  document.querySelector('#advance')?.addEventListener('click',()=>act(()=>{ui.engine.advance();ui.lastObservation=null;ui.feedback='';window.scrollTo(0,0);}));
}
function renderEnding() {
  const ending=ui.engine.state.ending;
  app.innerHTML=`<section class="ending"><p class="eyebrow">CASE COMPLETE / Whose name did you protect?</p><h1>${h(ending.title)}</h1><img class="ending-photo" src="assets/imaret-inside.jpg" alt="A modern photo of the imaret interior"><div class="outcomes">${[['Your job',ending.career],['Cem and the witness',ending.friend],['The meal',ending.service]].map(([name,text])=>`<article class="outcome"><h3>${h(name)}</h3><p>${h(text)}</p></article>`).join('')}</div><p class="growth">${h(ending.growth)}</p><div class="reflection"><h3>Why are these buildings connected?</h3><p>The madrasa supported learning, the fountain offered water, and the imaret served meals. Clerks, keepers, and kitchen staff each had a role. The case you solved is fiction; the connections between these places come from Muradiye’s real history.</p><p>This case used five photos from the inventory, three visual clues, and a traceable set of records. Revisit the ledger, slips, and testimony in your case notes.</p><a href="https://www.vakifkatilim.com.tr/tr/hakkimizda/medya-merkezi/yayinlarimiz" target="_blank" rel="noreferrer">Explore Bursa’s vakıf heritage ↗</a></div><button class="primary" id="replay">Return to the ledger and make another choice ↻</button><p class="fiction-label">${h(ui.chapter.fiction_notice)}</p></section>`;
  document.querySelector('#replay').addEventListener('click',restart);
  window.scrollTo(0,0);
}
function openNotebook() {
  if (!ui.engine) return;
  document.querySelector('#notebook-body').innerHTML=ui.engine.state.inventory.map(id=>{const item=ui.chapter.evidence.find(item=>item.id===id);return `<article class="note-card"><small>Fictional case prop</small><h3>${h(item.name)}</h3><p>${h(item.text)}</p></article>`;}).join('') || '<p class="waiting">You have not opened the ledger yet. Records and testimony you find will appear here.</p>';
  document.querySelector('#notebook').showModal();
}
function restart() { try {localStorage.removeItem(SAVE_KEY);} catch(error){console.warn('Could not remove session',error.name);}ui.engine=new StoryEngine(ui.chapter);ui.started=false;ui.lastObservation=null;ui.feedback='';render();window.scrollTo(0,0); }
function showToast(text) {const toast=document.querySelector('#toast');toast.textContent=text;toast.classList.add('show');clearTimeout(toastTimer);toastTimer=setTimeout(()=>toast.classList.remove('show'),3500);}
document.querySelector('#notebook-button').addEventListener('click',openNotebook);
document.querySelector('#close-notebook').addEventListener('click',()=>document.querySelector('#notebook').close());
document.querySelector('#close-photo').addEventListener('click',()=>document.querySelector('#photo-dialog').close());
document.querySelector('#restart-button').addEventListener('click',()=>{if(ui.chapter)restart();});
load().catch(error=>{app.innerHTML=`<div class="failure"><h1>The case did not load</h1><p>${h(error.message)}</p><p>Refresh the page or start the local server from the project folder.</p></div>`;console.error(error);});

function openMap() {
  const sites=ui.catalogue.spatial_context;
  document.querySelector('#map-body').innerHTML=`<p class="map-note">North is up · Relative layout only, not a survey map. Markers are not for navigation. GPS is off.</p><div class="site-schematic"><span class="north">N ↑</span>${sites.map(site=>`<button style="left:${site.x}%;top:${site.y}%" data-site="${h(site.id)}">${h(site.name)}</button>`).join('')}</div><div id="map-description" class="branch-note">Choose a building to see how it relates to the case.</div><p class="map-note">The tombs extend the site catalogue. The publication dates them to 1442–1573, so they do not appear in this 1430s story.</p>`;
  document.querySelectorAll('[data-site]').forEach(button=>button.addEventListener('click',()=>{const site=sites.find(item=>item.id===button.dataset.site);document.querySelector('#map-description').textContent=site.name+' · printed p. '+site.page+'：'+site.text;}));
  document.querySelector('#site-map').showModal();
}
let archiveAssets=null;
async function openArchive() {
  document.querySelector('#archive').showModal();
  document.querySelector('#archive-body').textContent='Loading the photo index…';
  try {
    if (!archiveAssets) {
      const responses=await Promise.all([fetch('../data/media_manifest.csv'),fetch('../data/drive_file_ids.csv')]);
      if(responses.some(response=>!response.ok))throw new Error('The photo archive is unavailable.');
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
  document.querySelector('#archive-body').innerHTML=`<p class="map-note">The five photos in this chapter come from one inventory and have been checked against the printed pages. The 93 original Drive photos below keep their individual location-review status.</p><p class="map-note">${matches.length} photos found</p>`+matches.map(asset=>`<article class="note-card"><small>${asset.mapping_state==='unmapped'?'Location unverified':'Possible match'}</small><h3><a href="${h(asset.url)}" target="_blank" rel="noreferrer">${h(asset.filename)} ↗</a></h3><p>${h(asset.observed_content)}</p></article>`).join('');
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
