/* Scene-specific drag review. A released marker is persisted automatically. */
window.PastPortPositionEditor = class PastPortPositionEditor {
  constructor(host) {
    this.host = host;
    this.records = new Map();
    this.enabled = false;
    this.drag = null;
    this.pending = 0;
    this.failed = null;
    this.root = document.createElement('aside');
    this.root.id = 'position-editor';
    this.root.innerHTML = '<button type="button" disabled aria-pressed="false">调整编号位置</button> <span role="status" aria-live="polite">正在读取位置…</span><button type="button" hidden>重试保存</button>';
    document.body.append(this.root);
    [this.toggle, this.retry] = this.root.querySelectorAll('button');
    this.status = this.root.querySelector('[role="status"]');
    this.toggle.onclick = () => {
      this.enabled = !this.enabled;
      this.toggle.setAttribute('aria-pressed', String(this.enabled));
      this.toggle.textContent = this.enabled ? '完成位置调整' : '调整编号位置';
      this.host.container.classList.toggle('position-editing', this.enabled);
      this.host.viewer.stopAutoRotate();
      this.message(this.enabled ? '拖动编号，松开即自动保存' : '点击编号查看介绍');
    };
    this.retry.onclick = () => {
      if (this.failed) {
        const job = this.failed;
        this.failed = null;
        this.retry.hidden = true;
        this.enqueue(job);
      }
    };
    const container = this.host.container;
    container.addEventListener('pointerdown', e => this.start(e), true);
    container.addEventListener('pointermove', e => this.move(e), true);
    container.addEventListener('pointerup', e => this.finish(e), true);
    container.addEventListener('pointercancel', e => this.cancel(e), true);
    for (const type of ['mousedown', 'touchstart', 'click']) {
      container.addEventListener(type, e => {
        if (this.enabled && e.target.closest?.('.trial-number')) {
          e.preventDefault();
          e.stopImmediatePropagation();
        }
      }, {capture: true, passive: false});
    }
    this.navigation = new window.PastPortNavigationEditor(host, this.root, this);
    this.navigation.initialize();
    this.host.viewer.on('scenechange', () => this.applyScene());
    this.host.viewer.on('load', () => this.applyScene());
    window.addEventListener('beforeunload', e => {
      if (this.pending || this.failed || this.drag?.moved) {
        e.preventDefault();
        e.returnValue = '';
      }
    });
  }

  message(text) { this.status.textContent = text; }

  async initialize() {
    if (location.protocol === 'file:') {
      this.message('请通过原本地VR网址打开，才能保存位置');
      return;
    }
    try {
      const response = await fetch('/api/vr-positions', {cache: 'no-store'});
      if (!response.ok) throw new Error('位置服务不可用');
      for (const value of await response.json()) {
        this.records.set(this.key(value.key.scene_id, value.key.object_id), {...value, chain: Promise.resolve(), sequence: 0});
      }
      this.applyScene();
      this.toggle.disabled = false;
      this.message('人工调整的位置会自动保存');
    } catch (error) {
      this.message('位置载入失败：' + error.message + '；请刷新重试');
    }
  }

  key(scene, object) { return scene + ':' + object; }

  applyScene() {
    const viewer = this.host.viewer;
    if (!viewer) return;
    const config = viewer.getConfig();
    for (const hotspot of config.hotSpots || []) {
      const object = Number(hotspot.id?.replace('trial-object-', ''));
      const record = this.records.get(this.key(viewer.getScene(), object));
      if (record) this.place(hotspot.id, record.yaw, record.pitch);
    }
    this.paint();
  }

  place(id, yaw, pitch) {
    const hotspot = this.host.viewer.getConfig().hotSpots?.find(h => h.id === id);
    if (hotspot) { hotspot.yaw = yaw; hotspot.pitch = pitch; }
    const scene = this.host.scenes.find(s => s.id === this.host.viewer.getScene());
    const source = scene?.hotspots.find(h => h.id === id);
    if (source) { source.yaw = yaw; source.pitch = pitch; }
  }

  paint() {
    if (!this.host.viewer?.isLoaded()) return;
    this.host.viewer.setUpdate(true);
    requestAnimationFrame(() => this.host.viewer?.setUpdate(false));
  }

  start(event) {
    const marker = event.target.closest?.('.trial-number');
    if (!this.enabled || !marker || event.button !== 0 || this.drag) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    const object = Number(marker.dataset.objectNumber);
    const scene = this.host.viewer.getScene();
    const record = this.records.get(this.key(scene, object));
    if (!record) { this.message('该编号的位置尚未载入，请刷新'); return; }
    const bounds = marker.getBoundingClientRect();
    this.host.viewer.stopMovement();
    this.drag = {
      marker, record, scene, id: 'trial-object-' + String(object).padStart(2, '0'),
      pointer: event.pointerId, startX: event.clientX, startY: event.clientY,
      offsetX: event.clientX - bounds.left - bounds.width / 2,
      offsetY: event.clientY - bounds.top - bounds.height / 2,
      yaw: record.yaw, pitch: record.pitch, moved: false
    };
    marker.setPointerCapture(event.pointerId);
  }

  move(event) {
    const drag = this.drag;
    if (!drag || drag.pointer !== event.pointerId) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    if (Math.hypot(event.clientX - drag.startX, event.clientY - drag.startY) < 3 && !drag.moved) return;
    drag.moved = true;
    const [pitch, yaw] = this.host.viewer.mouseEventToCoords(new MouseEvent('mousemove', {
      clientX: event.clientX - drag.offsetX, clientY: event.clientY - drag.offsetY
    }));
    drag.yaw = Math.max(-180, Math.min(180, yaw));
    drag.pitch = Math.max(-85, Math.min(85, pitch));
    drag.marker.classList.add('position-unsaved');
    this.place(drag.id, drag.yaw, drag.pitch);
    this.paint();
    this.message('松开编号即可自动保存');
  }

  finish(event) {
    const drag = this.drag;
    if (!drag || drag.pointer !== event.pointerId) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    this.drag = null;
    if (drag.marker.hasPointerCapture(event.pointerId)) drag.marker.releasePointerCapture(event.pointerId);
    if (!drag.moved) return;
    drag.record.sequence += 1;
    this.enqueue({...drag, sequence: drag.record.sequence, operation: crypto.randomUUID()});
  }

  cancel(event) {
    if (!this.drag || this.drag.pointer !== event.pointerId) return;
    const drag = this.drag;
    this.drag = null;
    this.place(drag.id, drag.record.yaw, drag.record.pitch);
    drag.marker.classList.remove('position-unsaved');
    this.paint();
    this.message('本次拖动已取消');
  }

  enqueue(job) {
    this.pending += 1;
    this.message('正在自动保存…');
    job.record.chain = job.record.chain.then(async () => {
      const response = await fetch('/api/vr-positions', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({...job.record.key, yaw: job.yaw, pitch: job.pitch,
          version: job.record.version, operation_id: job.operation})
      });
      if (response.status === 409) {
        const latest = await fetch('/api/vr-positions', {cache: 'no-store'});
        if (latest.ok) {
          const values = await latest.json();
          const current = values.find(p => p.key.object_id === job.record.key.object_id &&
            p.key.scene_id === job.scene && p.key.panorama_sha256 === job.record.key.panorama_sha256);
          if (current) Object.assign(job.record, current);
        }
        throw new Error('位置版本已变化，请核对后重试保存');
      }
      if (!response.ok) throw new Error('后台未确认保存，请重试');
      const [saved] = await response.json();
      Object.assign(job.record, saved);
      if (job.sequence === job.record.sequence) {
        job.marker.classList.remove('position-unsaved');
        if (this.failed?.record === job.record) { this.failed = null; this.retry.hidden = true; }
      }
      this.message('已自动保存 ' + String(job.record.key.object_id).padStart(2, '0') + ' 号；以人工位置为准');
    }).catch(error => {
      if (job.sequence === job.record.sequence) {
        this.failed = job;
        this.retry.hidden = false;
        this.message('尚未保存：' + error.message);
      }
    }).finally(() => { this.pending -= 1; });
  }
};

/* Navigation edits preserve identity; positions and arrival directions save separately per arrow. */
window.PastPortNavigationEditor = class PastPortNavigationEditor {
  constructor(host, panel, positionEditor) {
    this.host=host;this.panel=panel;this.positionEditor=positionEditor;this.links=[];
    this.enabled=false;this.drag=null;this.selected=null;this.arrivalEdit=null;this.pending=null;this.saving=false;
    this.controls=document.createElement('div');
    this.controls.innerHTML='<button type="button" disabled aria-pressed="false">调整导航箭头</button><button type="button" hidden>设置跳转后朝向</button><button type="button" hidden>保存当前朝向</button><button type="button" hidden>取消朝向调整</button><button type="button" hidden>重试导航保存</button><span role="status" aria-live="polite"></span>';
    panel.append(this.controls);
    [this.toggle,this.preview,this.arrivalSave,this.cancelButton,this.retry]=this.controls.querySelectorAll('button');
    this.status=this.controls.querySelector('[role="status"]');
    this.toggle.onclick=()=>{if(this.saving||this.pending||this.arrivalEdit||this.drag)return;this.enabled=!this.enabled;if(this.enabled&&positionEditor.enabled)positionEditor.toggle.click();this.toggle.setAttribute('aria-pressed',String(this.enabled));this.toggle.textContent=this.enabled?'完成导航调整':'调整导航箭头';this.preview.hidden=!this.enabled||!this.selected;this.say(this.enabled?'拖动箭头；点选箭头可设置跳转后的朝向':'');};
    positionEditor.toggle.addEventListener('click',()=>{if(positionEditor.enabled&&this.enabled)this.toggle.click();});
    this.preview.onclick=()=>{if(!this.selected||this.pending||this.saving)return;this.arrivalEdit=this.selected;this.preview.hidden=true;this.arrivalSave.hidden=false;this.cancelButton.hidden=false;this.host.go(this.selected.target_id);this.say('转动画面到进入此点位时希望看到的方向，再保存');};
    this.arrivalSave.onclick=()=>{if(!this.arrivalEdit||this.host.viewer.getScene()!==this.arrivalEdit.target_id){this.say('请留在目标点位再保存朝向');return;}const view=this.host.view();this.save({...this.arrivalEdit,arrival:{yaw:view.yaw,pitch:view.pitch}});};
    this.cancelButton.onclick=()=>{if(this.saving||this.pending)return;const link=this.arrivalEdit;this.arrivalEdit=null;this.arrivalSave.hidden=true;this.cancelButton.hidden=true;if(link)this.host.go(link.scene_id);this.preview.hidden=!this.enabled;this.say('已取消朝向调整');};
    this.retry.onclick=()=>{if(this.pending&&!this.saving)this.send();};
    const c=host.container;
    c.addEventListener('pointerdown',e=>this.start(e),true);
    c.addEventListener('pointermove',e=>this.move(e),true);
    c.addEventListener('pointerup',e=>this.finish(e),true);
    c.addEventListener('pointercancel',e=>this.cancelDrag(e),true);
    for(const type of ['mousedown','touchstart','click'])c.addEventListener(type,e=>{if(this.enabled&&this.arrow(e.target)){e.preventDefault();e.stopImmediatePropagation();}},{capture:true,passive:false});
    host.viewer.on('load',()=>this.apply());host.viewer.on('scenechange',()=>this.apply());
    addEventListener('beforeunload',e=>{if(this.pending||this.drag?.moved){e.preventDefault();e.returnValue='';}});
  }
  say(text){this.status.textContent=text;}
  arrow(target){const el=target.closest?.('.pnlm-hotspot-base');if(!el)return null;const scene=this.host.scenes.find(s=>s.id===this.host.viewer.getScene());const link=scene?.hotspots.find(h=>h.type==='scene'&&h.label===el.getAttribute('aria-label'));return link?{el,link}:null;}
  async initialize(){try{const response=await fetch('/api/vr-navigation',{cache:'no-store'});if(!response.ok)throw Error('导航服务尚未载入，请重新打开此成品');this.links=await response.json();this.apply();this.toggle.disabled=false;}catch(e){this.say(e.message);}}
  place(link){const scene=this.host.scenes.find(s=>s.id===link.scene_id),hot=scene?.hotspots.find(h=>h.id===link.hotspot_id);if(hot){hot.yaw=link.position.yaw;hot.pitch=link.position.pitch;if(link.arrival)hot.arrivalView=link.arrival;}if(this.host.viewer.getScene()===link.scene_id){const active=this.host.viewer.getConfig().hotSpots?.find(h=>h.id===link.hotspot_id);if(active){active.yaw=link.position.yaw;active.pitch=link.position.pitch;if(link.arrival){active.targetYaw=link.arrival.yaw;active.targetPitch=link.arrival.pitch;}}}this.positionEditor.paint();}
  apply(){for(const link of this.links)this.place(link);}
  start(e){const hit=this.arrow(e.target);if(!this.enabled||!hit||e.button!==0||this.arrivalEdit||this.pending||this.saving)return;e.preventDefault();e.stopImmediatePropagation();const link=this.links.find(l=>l.scene_id===this.host.viewer.getScene()&&l.hotspot_id===hit.link.id);if(!link)return;this.selected=link;this.preview.hidden=false;this.host.viewer.stopMovement();const b=hit.el.getBoundingClientRect();this.drag={el:hit.el,original:link,link, pointer:e.pointerId,x:e.clientX,y:e.clientY,dx:e.clientX-b.left-b.width/2,dy:e.clientY-b.top-b.height/2,moved:false};hit.el.setPointerCapture(e.pointerId);this.say('已选中导航箭头，可拖动或设置跳转后朝向');}
  move(e){const d=this.drag;if(!d||d.pointer!==e.pointerId)return;e.preventDefault();e.stopImmediatePropagation();if(!d.moved&&Math.hypot(e.clientX-d.x,e.clientY-d.y)<3)return;d.moved=true;const[pitch,yaw]=this.host.viewer.mouseEventToCoords(new MouseEvent('mousemove',{clientX:e.clientX-d.dx,clientY:e.clientY-d.dy}));d.link={...d.original,position:{yaw:Math.max(-180,Math.min(180,yaw)),pitch:Math.max(-85,Math.min(85,pitch))}};this.place(d.link);this.say('松开箭头自动保存位置');}
  finish(e){const d=this.drag;if(!d||d.pointer!==e.pointerId)return;e.preventDefault();e.stopImmediatePropagation();this.drag=null;if(d.el.hasPointerCapture(e.pointerId))d.el.releasePointerCapture(e.pointerId);if(d.moved)this.save(d.link);}
  cancelDrag(e){const d=this.drag;if(!d||d.pointer!==e.pointerId)return;this.drag=null;this.place(d.original);this.say('已取消箭头拖动');}
  save(link){if(this.pending||this.saving)return;this.pending={...link,operation_id:crypto.randomUUID()};this.send();}
  async send(){this.saving=true;this.retry.hidden=true;this.arrivalSave.disabled=true;this.say('正在保存导航…');try{const response=await fetch('/api/vr-navigation',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(this.pending)});if(response.status===409){this.pending=null;throw Error('导航已在其他页面改变，请刷新后重新调整');}if(!response.ok)throw Error('后台未确认保存');const saved=await response.json();this.links=this.links.map(l=>l.scene_id===saved.scene_id&&l.hotspot_id===saved.hotspot_id?saved:l);this.selected=saved;this.place(saved);this.pending=null;const arrival=this.arrivalEdit;this.arrivalEdit=null;this.arrivalSave.hidden=true;this.cancelButton.hidden=true;this.preview.hidden=!this.enabled;if(arrival)this.host.go(saved.scene_id);this.say('导航已保存，刷新后保留；反向箭头可单独调整');}catch(e){this.retry.hidden=!this.pending;this.say('尚未保存：'+e.message);}finally{this.saving=false;this.arrivalSave.disabled=false;}}
};
