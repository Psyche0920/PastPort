import { GameSession } from './adventure-session.mjs';
import { WalkMesh, Walker } from './walkmesh.mjs';
import { ObservationMatch } from './observation-match.mjs';
import { ProximityTriggers } from './proximity-trigger.mjs';

const $ = selector => document.querySelector(selector);
const escape = value => String(value).replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const asset = path => {
  if (!/^assets\/[a-zA-Z0-9_./-]+\.(jpg|png)$/.test(path) || path.includes('..')) throw new Error('素材地址未通过校验');
  return path;
};
const distance = (a, b) => Math.hypot((a[0] - b[0]) * 16, (a[1] - b[1]) * 9);
const ICONS = {tally:'▤', 'loading-slip':'✉', witness:'✍', 'kitchen-slip':'▧', reconciliation:'≡'};

class ChapterRepository {
  async json(path) {
    const response = await fetch(path, {signal: AbortSignal.timeout(12000)});
    if (!response.ok) throw new Error(`章节文件读取失败：${response.status}`);
    return response.json();
  }

  async load() {
    const [chapter, world, catalogue, overrides] = await Promise.all([
      this.json('../data/locales/zh/muradiye-story.json'), this.json('../data/adventure.zh.json'),
      this.json('../data/locales/zh/muradiye.json'), this.json('../data/task-overrides.json'),
    ]);
    if (chapter.chapter_id !== world.chapter_id || chapter.chapter_id !== overrides.chapter_id) throw new Error('章节与场景不属于同一内容包');
    for (const override of overrides.overrides) {
      if (override.state !== 'published') continue;
      const scene = chapter.scenes.find(item => item.id === override.scene_id), task = override.task;
      if (!scene || !override.approved_by || !task || task.kind !== scene.task.kind || !Array.isArray(task.required) ||
          !override.claim_ids?.length || override.claim_ids.some(id => !scene.claim_ids.includes(id))) throw new Error('已发布任务与本章证据不兼容');
      if (['inspect', 'inspect-sort'].includes(task.kind)) {
        if (!task.hotspots?.length || !task.required.length || task.required.some(id => !task.hotspots.some(spot => spot.id === id)) ||
            task.hotspots.some(spot => !scene.claim_ids.includes(spot.claim_id) || !Number.isFinite(spot.x) || !Number.isFinite(spot.y) || spot.x < 0 || spot.x > 100 || spot.y < 0 || spot.y > 100)) throw new Error('观察任务缺少有效照片区域');
      } else if (task.required.join('|') !== scene.task.required.join('|')) throw new Error('已发布任务改变了证据要求');
      scene.task = task;
    }
    for (const scene of chapter.scenes) {
      const layout = world.scenes.find(item => item.scene_id === scene.id);
      if (!layout || !new WalkMesh(layout.boundary, layout.obstacles).allows(layout.spawn)) throw new Error('场景缺少可用的出生位置');
      if (!chapter.photos.some(photo => photo.id === scene.photo_id)) throw new Error('场景缺少观察照片');
      for (const object of layout.objects) {
        if (!new WalkMesh(layout.boundary, layout.obstacles).allows(object.approach)) throw new Error(`交互位置不可达：${object.id}`);
        if (object.action === 'inspect' && !scene.task.hotspots?.some(spot => spot.id === object.observation)) throw new Error('游戏构件与观察任务不匹配');
      }
    }
    return {chapter, world, catalogue};
  }
}


class Adventure {
  constructor(content) {
    Object.assign(this, content);
    this.session = new GameSession(this.chapter, this.world.version, {getItem: key => localStorage.getItem(key), setItem: (key, value) => localStorage.setItem(key, value)});
    this.keys = new Set();
    this.pending = null;
    this.conversation = null;
    this.frame = 0;
    this.previousTime = 0;
    this.savedTime = 0;
    this.disposed = false;
    this.toastTimer = 0;
    this.transitioning = false;
    this.storageReported = false;
    this.observationMatches = new Map();
  }

  get objects() { return this.layout.objects.filter(object => !object.when || this.engine.state.decisions[object.when.decision] === object.when.value); }

  get engine() { return this.session.engine; }
  get scene() { return this.engine.scene; }
  get complete() { return this.engine.state.completed.includes(this.scene.id); }
  get busy() { return $('#panel').open || !$('#dialogue').hidden || !$('#loading').hidden || this.transitioning; }

  start() {
    this.bind();
    try { this.session.restore(); }
    catch (error) { this.loadingError(error.message); return; }
    this.enterScene(false);
    if (this.session.started) {
      $('#loading').hidden = true;
      if (this.engine.state.ending) this.showEnding();
      else this.speak(this.complete ? this.scene.after : this.scene.opening, () => this.sceneReady());
    } else this.intro();
    this.frame = requestAnimationFrame(time => this.tick(time));
    if (this.session.storageWarning) this.toast('本浏览器无法保存；请保持此页面打开。');
  }

  bind() {
    $('#world').addEventListener('click', event => {
      if (this.busy) return;
      const objectButton = event.target.closest('[data-object]');
      if (objectButton) return this.approach(this.objects.find(item => item.id === objectButton.dataset.object));
      const rect = $('#world').getBoundingClientRect();
      this.walkTo([(event.clientX - rect.left) / rect.width * 100, (event.clientY - rect.top) / rect.height * 100]);
    });
    $('#close-panel').addEventListener('click', () => $('#panel').close());
    $('#panel').addEventListener('close', () => { this.keys.clear(); const callback = this.panelClosed; this.panelClosed = null; callback?.(); });
    $('#notes-toggle').addEventListener('click', () => this.notes());
    $('#source-toggle').addEventListener('click', () => this.sources());
    $('#map-toggle').addEventListener('click', () => this.map());
    $('#settings-toggle').addEventListener('click', () => this.settings());
    this.keyDown = event => {
      if ($('#panel').open || !$('#loading').hidden) return;
      const key = event.key.toLowerCase();
      if (!$('#dialogue').hidden) {
        if (key === ' ' && !event.repeat) { event.preventDefault(); $('#dialogue [data-next]')?.click(); }
        return;
      }
      if (['arrowup','arrowdown','arrowleft','arrowright','w','a','s','d'].includes(key)) {
        event.preventDefault(); this.keys.add(key); this.pending = null;
      }
      if (key === 'e' && !event.repeat) {
        const nearest = this.objects.filter(item => distance(this.walker.position, item.approach) < 135)
          .sort((a, b) => distance(this.walker.position, a.approach) - distance(this.walker.position, b.approach))[0];
        if (nearest) this.interact(nearest); else this.toast('先走近人物或标记，再按 E。');
      }
      if (key === 'escape') { this.walker.stop(); this.pending = null; }
    };
    this.keyUp = event => this.keys.delete(event.key.toLowerCase());
    this.onBlur = () => { this.keys.clear(); this.previousTime = 0; };
    this.onPageHide = event => { this.rememberPosition(); if (!event.persisted) this.dispose(); };
    window.addEventListener('keydown', this.keyDown);
    window.addEventListener('keyup', this.keyUp);
    window.addEventListener('blur', this.onBlur);
    window.addEventListener('pagehide', this.onPageHide);
    document.addEventListener('visibilitychange', this.onBlur);
  }

  dispose() {
    this.disposed = true; cancelAnimationFrame(this.frame); clearTimeout(this.toastTimer);
    window.removeEventListener('keydown', this.keyDown); window.removeEventListener('keyup', this.keyUp);
    window.removeEventListener('blur', this.onBlur); window.removeEventListener('pagehide', this.onPageHide);
    document.removeEventListener('visibilitychange', this.onBlur);
  }

  loadingError(message) {
    $('#loading').hidden = false;
    $('#loading').innerHTML = `<p class="eyebrow">PASTPORT / SAVE RECOVERY</p><h1>这一页暂未打开</h1><p>${escape(message)}</p><button id="recover">清除此游戏版本的存档，重新开始</button><p class="fine">照片版的原存档不受影响。</p>`;
    $('#recover').onclick = () => { this.session.reset(); this.enterScene(false); this.intro(); this.frame = requestAnimationFrame(time => this.tick(time)); };
  }

  intro() {
    $('#loading').hidden = false;
    $('#loading').innerHTML = `<p class="eyebrow">PASTPORT / BURSA / 1430s</p><h1>最后两袋</h1><p>粮仓少了两袋。<br>替你担保的学徒，将在交账前被带走。<br>而那张账上的签名，是你的。</p><button class="primary" id="begin">${this.session.started ? '继续调查' : '走进穆拉迪耶'} →</button><p class="fine">点击地面走动 · 方向键 / WASD · 走近人物与线索自动交互<br>五幕完整案件 · 自动保存 · 无真实倒计时<br>建筑为资料启发的艺术化演绎，非精确历史复原。</p>`;
    $('#begin').onclick = () => {
      this.session.started = true; this.session.persist(); $('#loading').hidden = true;
      this.speak(this.scene.opening, () => this.sceneReady());
    };
  }

  enterScene(withDialogue = true) {
    this.layout = this.world.scenes.find(item => item.scene_id === this.scene.id);
    const mesh = new WalkMesh(this.layout.boundary, this.layout.obstacles);
    const saved = this.session.positions[this.scene.id];
    const position = Array.isArray(saved) && saved.length === 2 && saved.every(Number.isFinite) && mesh.allows(saved) ? saved : this.layout.spawn;
    this.walker = new Walker(mesh, position);
    this.proximity = new ProximityTriggers();
    this.proximity.suppress(position,this.objects);
    this.pending = null; this.keys.clear();
    const background = this.layout.atlas.map(value => `${value}%`).join(' ');
    $('#landscape').style.backgroundPosition = background;
    $('#occlusion').style.backgroundPosition = background;
    $('#occlusion').hidden = !this.layout.occlusion;
    if (this.layout.occlusion) $('#occlusion').style.clipPath = `polygon(${this.layout.occlusion.map(point => point.map(value => `${value}%`).join(' ')).join(',')})`;
    this.renderObjects(); this.renderHUD(); this.paint();
    if (withDialogue) this.speak(this.complete ? this.scene.after : this.scene.opening, () => this.sceneReady());
  }

  renderObjects() {
    $('#objects').innerHTML = this.objects.map(object => {
      if (object.kind === 'npc') return `<button class="actor" data-object="${escape(object.id)}" aria-label="走近${escape(object.label)}交谈" style="left:${object.point[0]*16}px;top:${object.point[1]*9}px;z-index:${Math.round(object.point[1]*10)};transform:translate(-50%,-92%) scale(.78)"><div class="shadow"></div><div class="sprite" style="background-position-x:${object.sprite*100/3}%"></div><span class="actor-label">${escape(object.label)}</span></button>`;
      const seen = object.observation && (this.engine.state.observed[this.scene.id] || []).includes(object.observation);
      const locked = object.kind === 'exit' && !this.engine.canAdvance();
      return `<button class="object ${escape(object.kind)} ${seen?'seen':''} ${locked?'locked':''}" data-object="${escape(object.id)}" data-label="${escape(object.label)}" aria-label="${escape(object.label)}${locked?'（完成本幕后开放）':''}" style="left:${object.point[0]}%;top:${object.point[1]}%">${object.kind==='exit'?'➜':seen?'✓':object.glyph || '◇'}</button>`;
    }).join('');
  }

  renderHUD() {
    $('#location').textContent = this.layout.label;
    $('#quest').textContent = `◇ ${this.scene.goal.replace('用照片','通过建筑线索')}`;
    $('#status').textContent = `第 ${this.engine.state.scene+1} / ${this.chapter.scenes.length} 幕 · ${this.scene.title} · ${this.engine.friend === 'with_you'?'杰姆与你同行':this.engine.friend === 'detained'?'杰姆正被扣留':'调查尚未具名'}`;
    $('#count').textContent = this.engine.state.inventory.length;
    $('#time').textContent = this.engine.remaining >= 0 ? `还剩 ${this.engine.remaining} 刻钟 · 行动计时` : `超过约定 ${-this.engine.remaining} 刻钟 · 行动计时`;
    $('#inventory').innerHTML = this.engine.state.inventory.slice(-4).map(id => {
      const evidence = this.chapter.evidence.find(item => item.id === id);
      return `<button class="inventory-item" title="${escape(evidence.name)}" aria-label="查看${escape(evidence.name)}" data-evidence="${escape(id)}">${ICONS[id]}<span>${escape(evidence.name.slice(0,5))}</span></button>`;
    }).join('') + (this.engine.state.inventory.length ? '' : '<div class="inventory-empty" title="证据将保存在这里"></div>');
    $('#inventory').querySelectorAll('button').forEach(button => button.onclick = () => this.notes(button.dataset.evidence));
  }

  tick(time) {
    if (this.disposed) return;
    const dt = this.previousTime ? (time-this.previousTime)/1000 : 0;
    this.previousTime = time;
    if (!this.busy) {
      const axis = [Number(this.keys.has('d')||this.keys.has('arrowright'))-Number(this.keys.has('a')||this.keys.has('arrowleft')),
        Number(this.keys.has('s')||this.keys.has('arrowdown'))-Number(this.keys.has('w')||this.keys.has('arrowup'))];
      this.walker.tick(dt, axis);
      if (this.pending && !this.walker.route.length) {
        const target = this.pending; this.pending = null;
        if (distance(this.walker.position,target.approach) < 12) this.interact(target);
      }
      if (!this.busy && !this.pending) {
        const target = this.proximity.poll(this.walker.position,this.objects,object => this.autoEligible(object));
        if (target) this.interact(target);
      }
      if (time-this.savedTime > 4000) { this.rememberPosition(); this.savedTime = time; }
    } else { this.keys.clear(); this.walker.moving = false; }
    this.paint();
    this.frame = requestAnimationFrame(next => this.tick(next));
  }

  paint() {
    if (!this.walker) return;
    const [x,y] = this.walker.position, viewport = $('#viewport');
    const scale = Math.max(viewport.clientWidth/1600,viewport.clientHeight/900);
    const cameraX = Math.max(viewport.clientWidth-1600*scale, Math.min(0,viewport.clientWidth*.43-x*16*scale));
    const cameraY = Math.max(viewport.clientHeight-900*scale, Math.min(0,viewport.clientHeight*.8-y*9*scale));
    $('#world').style.transform = `translate(${cameraX}px,${cameraY}px) scale(${scale})`;
    const player = $('#player');
    player.style.left = `${x*16}px`; player.style.top = `${y*9}px`;
    player.style.zIndex = Math.round(y*10);
    const depth = .66+(y-75)/100;
    player.style.transform = `translate(-50%,-92%) scale(${depth}) scaleX(${this.walker.facing})`;
    player.classList.toggle('walking', this.walker.moving);
    $('#map-dot').setAttribute('cx', String(7+x*.86)); $('#map-dot').setAttribute('cy', String(10+(y-70)*1.3));
    $('#destination').hidden = !this.walker.route.length;
    if (this.walker.route.length) { const target = this.walker.route.at(-1); $('#destination').style.left=`${target[0]}%`; $('#destination').style.top=`${target[1]}%`; }
    $('#objects').querySelectorAll('.object').forEach(button => {
      const object = this.objects.find(item => item.id === button.dataset.object);
      button.classList.toggle('near', distance(this.walker.position,object.approach) < 100);
    });
  }

  rememberPosition() {
    if (!this.walker || !this.session.started) return;
    this.session.positions[this.scene.id] = [...this.walker.position]; this.session.persist(); this.reportStorage();
  }

  reportStorage() {
    if (this.session.storageWarning && !this.storageReported) { this.storageReported = true; this.toast('当前浏览器无法保存进度；请保持此页面打开。'); }
  }

  walkTo(point, object = null) {
    this.keys.clear(); this.pending = null;
    if (!this.walker.goTo(point)) { this.toast('这里不是可通行地面，请点击石板路。'); return; }
    this.pending = object;
  }

  approach(object) { this.walkTo(object.approach, object); }

  autoEligible(object) {
    if (!this.walker.mesh.clear(this.walker.position,object.approach)) return false;
    if (object.action === 'advance') return this.engine.canAdvance();
    if (object.action === 'sorting') return this.engine.canSort() && !this.complete;
    if (object.action === 'document' || object.action === 'caseboard') return !this.complete;
    if (object.action === 'inspect') return !this.scene.task.hotspots.every(spot => (this.engine.state.observed[this.scene.id] || []).includes(spot.id));
    return object.action === 'talk';
  }

  interact(object) {
    this.walker.stop(); this.pending = null; this.rememberPosition();
    if (distance(this.walker.position,object.approach) > 135) return this.toast('请先走近再交互。');
    this.proximity.suppress(this.walker.position,this.objects);
    if (object.action === 'talk') this.speak(object.lines || (this.complete ? this.scene.after : this.scene.opening), () => { if (!object.lines) this.sceneReady(); });
    if (object.action === 'inspect') this.inspect(object.observation);
    if (object.action === 'document') this.document();
    if (object.action === 'sorting') this.sorting();
    if (object.action === 'caseboard') this.caseboard();
    if (object.action === 'advance') {
      if (!this.engine.canAdvance()) this.toast(this.complete?'先完成本幕的人物选择。':'先完成本幕任务，再离开这里。');
      else this.advance();
    }
  }

  speakerSprite(speaker) {
    if (speaker.includes('杰姆')) return {column:0,row:100};
    if (speaker.includes('哈丽梅')) return {column:1,row:100};
    if (speaker.includes('厨房')) return {column:3,row:100};
    if (speaker.includes('管事')) return {column:2,row:100};
    return {column:1,row:0};
  }

  speak(lines, done = () => {}) {
    this.walker.stop(); this.pending = null; this.keys.clear();
    this.conversation = {lines, index:0, done};
    this.renderLine();
  }

  renderLine() {
    const conversation = this.conversation, line = conversation.lines[conversation.index];
    if (!line) { $('#dialogue').hidden = true; this.conversation = null; conversation.done(); return; }
    const sprite = this.speakerSprite(line.speaker);
    $('#dialogue').hidden = false;
    $('#dialogue').innerHTML = `<div class="portrait" aria-hidden="true"><div class="sprite" style="background-position:${sprite.column*100/3}% ${sprite.row}%"></div></div><div class="speaker">${escape(line.speaker)}</div><div class="dialogue-text">${escape(line.text)}</div><div class="dialogue-actions"><button data-next>继续 ▾</button></div>`;
    $('#dialogue [data-next]').onclick = () => { conversation.index++; this.renderLine(); };
  }

  sceneReady() {
    if (!this.complete) return this.toast('走近人物或 ◇ 标记，会自动交谈或打开任务。');
    if (this.scene.decision && !this.engine.state.decisions[this.scene.decision.id]) return this.decision();
    if (this.engine.state.ending) return this.showEnding();
    if (this.scene.next) {
      $('#dialogue').hidden = false;
      $('#dialogue').innerHTML = `<div class="speaker">调查笔记</div><div class="dialogue-text">本幕的线索与选择已保存。你可以继续观察，或沿出口前往下一处。</div><div class="dialogue-actions"><button id="keep-exploring">继续探索</button><button class="primary" id="walk-exit">走向出口 →</button></div>`;
      $('#keep-exploring').onclick = () => { $('#dialogue').hidden = true; };
      $('#walk-exit').onclick = () => { $('#dialogue').hidden = true; this.approach(this.objects.find(item => item.action === 'advance')); };
    }
  }

  decision() {
    const decision = this.scene.decision;
    $('#dialogue').hidden = false;
    $('#dialogue').innerHTML = `<div class="speaker">你的决定</div><div class="dialogue-text">${escape(decision.prompt)}</div><div class="decision-options">${decision.options.map(option => `<button data-choice="${escape(option.id)}">${escape(option.label)}<small>${escape(option.detail)} · ${option.cost} 刻钟</small></button>`).join('')}</div>`;
    $('#dialogue').querySelectorAll('[data-choice]').forEach(button => button.onclick = () => {
      this.act('choose',button.dataset.choice); this.renderHUD(); this.renderObjects(); $('#dialogue').hidden = true;
      this.sceneReady();
    });
  }

  act(kind, ...args) {
    try { const result = this.session.dispatch(kind,...args); this.renderHUD(); this.renderObjects(); this.reportStorage(); return result; }
    catch (error) { this.toast(error.message); console.error('Adventure action rejected',kind,error.name); return null; }
  }

  modal(html, closed = null) {
    this.walker.stop(); this.keys.clear(); this.pending = null;
    this.panelClosed = closed; $('#panel-body').innerHTML = html;
    if (!$('#panel').open) $('#panel').showModal();
  }

  inspect() {
    const photo = this.chapter.photos.find(item => item.id === this.scene.photo_id);
    const spots = this.scene.task.hotspots || [];
    const wasComplete = this.complete;
    if (!this.observationMatches.has(this.scene.id)) this.observationMatches.set(this.scene.id,new ObservationMatch(spots));
    const puzzle = this.observationMatches.get(this.scene.id);
    let passed = spots.every(spot => (this.engine.state.observed[this.scene.id] || []).includes(spot.id));
    if (passed) for (const option of puzzle.options) puzzle.assign(option.id,puzzle.markers.find(marker => marker.spotId === option.id).label);
    let selected = puzzle.options[0].id;
    this.modal(`<p class="eyebrow">LOOK CLOSELY / 建筑观察</p><h2>把构件与照片位置对应起来</h2><p class="match-instructions">先选下方的 1、2、3 号说明，再点击照片里的字母位置。全部配对后提交；位置字母已打乱，选错可以修改。</p><div class="photo-evidence matching-photo"><div class="photo-map"><img src="${asset(photo.file)}" alt="${escape(photo.caption)}">${puzzle.markers.map(marker => `<button class="photo-marker match-marker" data-marker="${marker.label}" aria-label="照片位置 ${marker.label}" style="left:${marker.x}%;top:${marker.y}%">${marker.label}</button>`).join('')}</div></div><div class="inspection-actions match-options" aria-label="编号构件说明">${puzzle.options.map(option => `<button data-option="${option.number}" aria-pressed="false"><strong>${option.number}</strong><span>${escape(option.label)}<small class="assignment"></small></span></button>`).join('')}</div><p id="match-feedback" role="status"></p><div class="match-controls"><button class="primary" id="check-match">提交配对</button><button id="return-world">稍后继续 · 回到场景</button></div><div id="observed"></div><p class="fine">库存出版物印刷页 ${escape(photo.printed_page)} · ${escape(photo.source_id)}<br>照片为当代实拍；现代设施不能证明故事年代。人物与案情为原创。</p>`, () => {
      if (!wasComplete && this.complete) this.speak(this.scene.after, () => this.sceneReady());
    });
    const render = () => {
      for (const option of puzzle.options) {
        const button = $(`[data-option="${option.number}"]`), assigned = puzzle.assignments.get(option.id);
        button.setAttribute('aria-pressed',String(!passed && option.id === selected));
        button.disabled = passed;
        button.querySelector('.assignment').textContent = assigned ? `→ 位置 ${assigned}` : '→ 等待选择位置';
      }
      for (const marker of puzzle.markers) {
        const button = $(`[data-marker="${marker.label}"]`), option = puzzle.options.find(item => puzzle.assignments.get(item.id) === marker.label);
        button.textContent = option ? `${marker.label} · ${option.number}` : marker.label;
        button.classList.toggle('assigned',Boolean(option)); button.disabled = passed;
        button.setAttribute('aria-label',`照片位置 ${marker.label}${option?`，已配对选项 ${option.number}`:''}`);
      }
      $('#check-match').disabled = passed;
      $('#check-match').textContent = passed ? '✓ 全部对应正确' : '提交配对';
      $('#match-feedback').textContent = passed ? '配对正确，建筑观察已记入笔记。' : `当前选择：${puzzle.options.find(option => option.id === selected).number} 号说明。点击照片中的字母位置；已配对 ${puzzle.assignments.size} / ${spots.length}。`;
      if (passed) {
        $('#return-world').textContent = this.scene.sorting ? '回到院子 · 操作分账台' : '线索已记入笔记 · 继续对话';
        $('#observed').innerHTML = puzzle.options.map(option=>`<p><strong>${option.number} · ${escape(option.label)}</strong><br>${escape(option.text)}</p>`).join('');
      }
    };
    $('#return-world').onclick = () => $('#panel').close();
    $('#panel-body').querySelectorAll('[data-option]').forEach(button => button.onclick = () => {
      selected = puzzle.options.find(option => option.number === Number(button.dataset.option)).id; render();
    });
    $('#panel-body').querySelectorAll('[data-marker]').forEach(button => button.onclick = () => {
      puzzle.assign(selected,button.dataset.marker);
      selected = puzzle.options.find(option => !puzzle.assignments.has(option.id))?.id || selected;
      render();
    });
    $('#check-match').onclick = () => {
      const result = puzzle.check();
      if (!result.complete) {
        $('#match-feedback').textContent = result.missing ? `还有 ${result.missing} 个说明未配对，请为每个编号选择照片位置。` : '还没有全部对应正确。请重新观察照片，修改后再次提交；线索尚未记录。';
        return;
      }
      try { this.session.submitObservationMatch(puzzle); passed = true; this.renderHUD(); this.renderObjects(); this.reportStorage(); render(); }
      catch (error) { this.toast(error.message); }
    };
    render();
  }

  document() {
    const wasComplete = this.complete;
    this.modal(`<p class="eyebrow">YOUR SIGNATURE / 原创案件道具</p><h2>早晨的签收账页</h2><article class="paper"><p>送达清点</p><strong>12 袋货物</strong><hr><p>正式入库誊写</p><strong class="wrong">麦粒 12 袋</strong><p>纸角备注：<u>品类待核</u></p><p>Yusuf / 优素福</p></article><p>你的签名仍在，备注却没有进入正式账。</p><button class="primary" id="read-ledger">${this.complete?'已记入笔记 · 返回':'确认账目，保留原账 →'}</button>`, () => {
      if (!wasComplete && this.complete) this.speak(this.scene.after, () => this.sceneReady());
    });
    $('#read-ledger').onclick = () => { if (!this.complete) this.act('openTally'); $('#panel').close(); };
  }

  sorting() {
    if (!this.engine.canSort()) return this.toast('先检查窗楣的星形砖饰，找到厨房收料单。');
    const wasComplete = this.complete;
    this.modal(`<p class="eyebrow">AT THE RECEIPT TABLE / 原创案件道具</p><h2>把货物分回两本账</h2><p>装车单：10 袋麦粒、2 袋面粉。厨房收料单：收到面粉 2 袋。</p>${this.scene.sorting.cards.map(card => `<div class="sort-row"><label for="sort-${escape(card.id)}">${escape(card.label)}</label><select id="sort-${escape(card.id)}" data-sort="${escape(card.id)}" ${this.complete?'disabled':''}><option value="" disabled>选择去向</option>${this.scene.sorting.destinations.map(item => `<option value="${escape(item.id)}" ${this.engine.state.assignments[card.id]===item.id?'selected':''}>${escape(item.label)}</option>`).join('')}</select></div>`).join('')}<p id="sorting-feedback">核账需要 2 刻钟，确认成功后计入。</p><button class="primary" id="check-sort">${this.complete?'已完成 · 回到场景':'核对分类 →'}</button>`, () => {
      if (!wasComplete && this.complete) this.speak(this.scene.after, () => this.sceneReady());
    });
    $('#panel-body').querySelectorAll('[data-sort]').forEach(select => select.onchange = () => { if (select.value) this.act('assign',select.dataset.sort,select.value); });
    $('#check-sort').onclick = () => {
      if (this.complete) return $('#panel').close();
      if (this.act('checkSorting')) { this.toast(this.scene.sorting.success); $('#panel').close(); }
      else $('#sorting-feedback').textContent = '分类还没对上：请核对哪种货物进粮仓、哪种货物进厨房。';
    };
  }

  caseboard() {
    const wasComplete = this.complete;
    const render = () => {
      this.modal(`<p class="eyebrow">FOLLOW THE RECORD / 原创案件道具</p><h2>把三份材料摆到核账桌上</h2><p>找出原账、装车分类和实际收料，解释 12 袋的去向。证词证明搬运者，不能代替数量记录。</p>${this.engine.state.inventory.map(id => {
        const item = this.chapter.evidence.find(item => item.id === id), selected = this.engine.state.caseboard.includes(id);
        return `<button class="evidence-card ${selected?'selected':''}" aria-pressed="${selected}" data-board="${escape(id)}" ${this.complete?'disabled':''}>${selected?'✓ ':''}${escape(item.name)}<span>${escape(item.text)}</span></button>`;
      }).join('')}<p id="board-feedback"></p><button class="primary" id="check-board">${this.complete?'材料已闭合 · 返回':'核对三份材料 →'}</button>`, () => {
        if (!wasComplete && this.complete) this.speak(this.scene.after, () => this.sceneReady());
      });
      $('#panel-body').querySelectorAll('[data-board]').forEach(button => button.onclick = () => { this.act('toggleBoard',button.dataset.board); render(); });
      $('#check-board').onclick = () => {
        if (this.complete) return $('#panel').close();
        if (this.act('checkBoard')) $('#panel').close();
        else $('#board-feedback').textContent = '还没有形成三份材料的核账链。请分别证明最初怎么记、装了什么、实际收了什么。';
      };
    };
    render();
  }

  notes(selected = null) {
    this.modal(`<p class="eyebrow">FIELD NOTES / 原创案件道具</p><h2>你保留下来的东西</h2>${this.engine.state.inventory.map(id => {
      const evidence = this.chapter.evidence.find(item => item.id === id);
      return `<article class="evidence-card ${selected===id?'selected':''}"><strong>${ICONS[id]} ${escape(evidence.name)}</strong><p>${escape(evidence.text)}</p></article>`;
    }).join('') || '<p>走近核账桌，先保留那张有你签名的原账。</p>'}<p class="fine">单据、证词、数量与人物事件均为游戏原创，不是历史原件。</p>`);
  }

  map() {
    this.modal(`<p class="eyebrow">A CONNECTED INVESTIGATION</p><h2>这一次调查的路线</h2><p>${escape(this.world.route_notice)}</p><ol class="route-list">${this.chapter.scenes.map((scene,index) => `<li class="${index===this.engine.state.scene?'current':''}">${index<this.engine.state.scene?'✓':String(index+1).padStart(2,'0')} · ${escape(scene.place)}<small>${escape(scene.title)}${index===this.engine.state.scene?' · 你在这里':''}${index>this.engine.state.scene?' · 尚未抵达':''}</small></li>`).join('')}</ol><p class="fine">故事年代采用 1430 年代。后建陵墓没有加入本案路线；转场代表游戏中的地点衔接，不是经测绘的实地步行路线。</p>`);
  }

  sources() {
    const photo = this.chapter.photos.find(item => item.id === this.scene.photo_id);
    this.modal(`<p class="eyebrow">EVIDENCE & INTERPRETATION</p><h2>画面从哪里来</h2><p>${escape(this.world.art_notice)}</p><p>当前建筑观察参考：${escape(photo.caption)}，库存出版物印刷页 ${escape(photo.printed_page)}。真实照片用于核对构件；游戏场景不能替代测绘或考古证据。</p><img src="${asset(photo.file)}" style="width:100%;max-height:42dvh;object-fit:contain" alt="${escape(photo.caption)}"><details><summary>本幕引用的历史记录</summary>${this.scene.claim_ids.map(id => {
      const claim = this.catalogue.claims.find(item => item.id === id);
      return claim ? `<p>${escape(claim.text)}</p><p class="fine">${escape(claim.caveat || '')}</p>` : '';
    }).join('')}</details><p>人物、账单、证词与案件由现有章节提供。背景和人物立绘由图像生成工具依据已确认的画风创作，未使用市政府全景瓦片。</p><p class="fine">已去除明显的现代玻璃顶、餐厅招牌与电灯；室内陈设、灯具和未经测绘的建筑细节仍含艺术推断，不能宣称已全面复原 1430 年代。</p><a class="source-link" href="https://islamansiklopedisi.org.tr/muradiye-kulliyesi--bursa" target="_blank" rel="noreferrer">建筑相对关系与年代的补充资料 ↗</a><a class="source-link" href="https://drive.google.com/drive/folders/18rlNGjpMhGuazgqqOUkJRDNbPEBIcTbh" target="_blank" rel="noreferrer">项目原始资料目录 ↗</a>`);
  }

  settings() {
    this.modal(`<p class="eyebrow">YOUR VISIT</p><h2>游玩设置</h2><p>点击地面或使用方向键 / WASD 移动。走近人物和任务点会自动交互；本幕完成后，走到出口会自动进入下一幕。离开附近再回来可重新触发。也可点击目标走近，或用 E 手动交互。Esc：停下。空格：继续对话。</p><p>手机可以点击地面与标记；竖屏会跟随角色移动镜头。</p><button id="motion">${document.body.classList.contains('reduced-motion')?'开启动画':'减少环境与角色动画'}</button><button id="restart">重新开始本次调查</button><p class="fine">故事时间只由行动扣除。走路和阅读不会消耗刻钟。此版本单独保存，照片版原进度保留。</p><a class="source-link" href="index.zh.html">打开原照片版 ↗</a>`);
    $('#motion').onclick = () => { document.body.classList.toggle('reduced-motion'); this.settings(); };
    $('#restart').onclick = () => {
      this.modal('<h2>重新开始调查？</h2><p>将清除此可行走版本的证据、选择和位置。照片版存档保留。</p><button id="confirm-restart" class="primary">重新开始</button><button id="cancel-restart">继续当前调查</button>');
      $('#cancel-restart').onclick = () => $('#panel').close();
      $('#confirm-restart').onclick = () => { this.panelClosed = null; $('#panel').close(); $('#dialogue').hidden = true; this.session.reset(); this.observationMatches.clear(); this.enterScene(false); this.intro(); };
    };
  }

  async advance() {
    if (this.transitioning) return;
    this.transitioning = true; this.rememberPosition(); $('#scene-curtain').classList.add('visible');
    await new Promise(resolve => setTimeout(resolve,230));
    const result = this.act('advance');
    if (result !== null) this.enterScene();
    $('#scene-curtain').classList.remove('visible'); this.transitioning = false;
  }

  showEnding() {
    const ending = this.engine.state.ending;
    $('#dialogue').hidden = true;
    this.modal(`<p class="eyebrow">THE LAST TWO SACKS / 调查结束</p><h2>${escape(ending.title)}</h2><div class="ending-grid">${[['你的职位',ending.career],['杰姆与证人',ending.friend],['公共服务',ending.service],['你的名字',ending.growth]].map(([title,text])=>`<article><h3>${escape(title)}</h3><p>${escape(text)}</p></article>`).join('')}</div><p class="fine">本案共消耗 ${this.engine.state.elapsed} 刻钟。人物、事件、数量与后果为原创虚构；这是一场关于证据与责任的游戏。</p><button class="primary" id="ending-notes">查看保留的证据</button><button id="ending-settings">重新开始 / 设置</button>`);
    $('#ending-notes').onclick = () => this.notes(); $('#ending-settings').onclick = () => this.settings();
  }

  toast(message) {
    $('#toast').textContent = message; $('#toast').classList.add('show'); clearTimeout(this.toastTimer);
    this.toastTimer = setTimeout(()=>$('#toast').classList.remove('show'),3500);
  }
}

async function boot() {
  const repository = new ChapterRepository();
  const content = await repository.load();
  await Promise.all(['assets/adventure/worlds.png','assets/adventure/cast.png'].map(path => new Promise((resolve,reject) => {
    const image = new Image(); image.onload=resolve; image.onerror=()=>reject(new Error('场景美术未完整载入，请刷新重试')); image.src=path;
  })));
  new Adventure(content).start();
}

boot().catch(error => {
  console.error('Adventure initialization failed',error.name,error.message);
  $('#load-message').textContent = `暂时无法开始：${error.message}。请刷新页面重试。`;
});
