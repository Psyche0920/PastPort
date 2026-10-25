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
