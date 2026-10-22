"""PastPort Hotspot Studio: Unified Interactive Pipeline for Heritage Evidence Mapping.

Connects SQLite evidence databases (sites, assets, claims) directly to the 360 visual viewer
and 2D photo inspector, allowing curators to select claims, view AI-detected spots,
point-and-click to calibrate spots, and save validated Spots back into the database.

Usage:
    python tools/hotspot_studio.py [--port 8088] [--db var/bursa_evidence.db]
"""
from __future__ import annotations

import argparse
import http.server
import json
import os
from pathlib import Path
import re
import socketserver
import sqlite3
import sys
import time
import urllib.parse
import webbrowser

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
from tools.spot_converter import SphericalCoordinate


INIT_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS scene_hotspots (
    spot_id TEXT PRIMARY KEY,
    site_id TEXT NOT NULL REFERENCES sites(site_id),
    asset_id TEXT NOT NULL REFERENCES assets(asset_id),
    claim_id TEXT NOT NULL REFERENCES claims(claim_id),
    x INTEGER NOT NULL CHECK (x >= 0 AND x <= 10000),
    y INTEGER NOT NULL CHECK (y >= 0 AND y <= 10000),
    yaw REAL NOT NULL,
    pitch REAL NOT NULL,
    label TEXT NOT NULL,
    authoring_method TEXT NOT NULL DEFAULT 'manual_handclick',
    created_at REAL NOT NULL
);
"""


HTML_PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>PastPort · Hotspot Studio & Verification Viewer</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/pannellum@2.5.6/build/pannellum.css">
  <script src="https://cdn.jsdelivr.net/npm/pannellum@2.5.6/build/pannellum.js"></script>
  <style>
    :root {
      --bg: #141416;
      --surface: #1e1e24;
      --surface-border: #2e2e38;
      --primary: #3b82f6;
      --primary-hover: #2563eb;
      --accent: #10b981;
      --text: #f3f4f6;
      --text-muted: #9ca3af;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: var(--bg); color: var(--text); display: flex; flex-direction: column; height: 100vh; overflow: hidden; }
    header { background: var(--surface); padding: 10px 20px; border-bottom: 1px solid var(--surface-border); display: flex; align-items: center; justify-content: space-between; gap: 16px; }
    .header-left { display: flex; align-items: center; gap: 16px; }
    .header-left h1 { font-size: 15px; font-weight: 700; color: #fff; letter-spacing: -0.2px; }
    .header-left small { font-size: 10px; background: rgba(59, 130, 246, 0.15); color: #60a5fa; padding: 2px 8px; border-radius: 4px; font-weight: 600; text-transform: uppercase; }
    .controls-row { display: flex; align-items: center; gap: 10px; }
    select { background: #121215; color: #fff; border: 1px solid var(--surface-border); border-radius: 6px; padding: 6px 12px; font-size: 13px; outline: none; max-width: 380px; }
    select:focus { border-color: var(--primary); }
    .mode-switch { display: inline-flex; background: #121215; border: 1px solid var(--surface-border); border-radius: 6px; padding: 2px; gap: 2px; }
    .mode-btn { background: transparent; color: var(--text-muted); border: none; padding: 4px 10px; border-radius: 4px; font-size: 12px; font-weight: 600; cursor: pointer; transition: all 0.15s; }
    .mode-btn.active { background: var(--primary); color: #fff; }
    .btn { background: var(--primary); color: #fff; border: none; border-radius: 6px; padding: 6px 14px; font-size: 12px; font-weight: 600; cursor: pointer; display: inline-flex; align-items: center; gap: 6px; transition: background 0.15s; }
    .btn:hover { background: var(--primary-hover); }
    .btn-save { background: var(--accent); }
    .btn-save:hover { background: #059669; }
    #main { display: flex; flex: 1; overflow: hidden; position: relative; }
    #panel-claims { width: 340px; background: var(--surface); border-right: 1px solid var(--surface-border); display: flex; flex-direction: column; overflow: hidden; }
    #panel-viewer { flex: 1; height: 100%; position: relative; background: #0c0c0e; display: flex; align-items: center; justify-content: center; overflow: hidden; }
    #panel-spots { width: 340px; background: var(--surface); border-left: 1px solid var(--surface-border); display: flex; flex-direction: column; overflow: hidden; }
    .panel-header { padding: 12px 16px; border-bottom: 1px solid var(--surface-border); font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-muted); display: flex; justify-content: space-between; align-items: center; }
    .panel-content { flex: 1; overflow-y: auto; padding: 12px; display: flex; flex-direction: column; gap: 8px; }
    .claim-card { background: #18181d; border: 1px solid var(--surface-border); border-radius: 8px; padding: 12px; cursor: pointer; transition: all 0.15s; }
    .claim-card:hover { border-color: #4b5563; }
    .claim-card.selected { border-color: var(--primary); background: rgba(59, 130, 246, 0.08); }
    .claim-badge { font-size: 10px; font-weight: 600; text-transform: uppercase; padding: 2px 6px; border-radius: 4px; display: inline-block; margin-bottom: 6px; }
    .badge-arch { background: rgba(16, 185, 129, 0.15); color: #34d399; }
    .badge-hist { background: rgba(59, 130, 246, 0.15); color: #60a5fa; }
    .badge-date { background: rgba(245, 158, 11, 0.15); color: #fbbf24; }
    .claim-text { font-size: 12px; line-height: 1.4; color: #e5e7eb; }
    .spot-card { background: #18181d; border: 1px solid var(--surface-border); border-radius: 8px; padding: 12px; display: flex; flex-direction: column; gap: 6px; font-size: 12px; cursor: pointer; transition: all 0.15s; }
    .spot-card:hover { border-color: #4b5563; }
    .spot-card.selected { border-color: var(--accent); background: rgba(16, 185, 129, 0.08); }
    .spot-header { display: flex; justify-content: space-between; font-weight: 600; color: #fff; }
    .spot-meta { font-family: monospace; font-size: 11px; color: #60a5fa; }
    .spot-claim { font-size: 12px; color: var(--text-muted); line-height: 1.3; }
    .empty-state { text-align: center; color: var(--text-muted); font-size: 13px; padding: 40px 20px; }
    #toast { position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%); background: #10b981; color: #fff; padding: 10px 20px; border-radius: 8px; font-size: 13px; font-weight: 600; box-shadow: 0 4px 12px rgba(0,0,0,0.4); opacity: 0; pointer-events: none; transition: opacity 0.2s; z-index: 1000; }
    #toast.show { opacity: 1; }

    /* 2D Photo Mode Styles */
    #photo-view { width: 100%; height: 100%; position: absolute; top: 0; left: 0; overflow: auto; display: flex; align-items: center; justify-content: center; padding: 20px; }
    #photo-container { position: relative; display: inline-block; box-shadow: 0 10px 30px rgba(0,0,0,0.5); border-radius: 6px; overflow: visible; }
    #photo-img { max-width: 100%; max-height: calc(100vh - 120px); display: block; border-radius: 6px; cursor: crosshair; }
    .photo-pin { position: absolute; transform: translate(-50%, -50%); cursor: pointer; pointer-events: auto; z-index: 20; transition: transform 0.15s; }
    .photo-pin:hover, .photo-pin.selected { transform: translate(-50%, -50%) scale(1.2); z-index: 30; }
    .pin-dot { width: 14px; height: 14px; border-radius: 50%; border: 2px solid #fff; box-shadow: 0 0 8px rgba(0,0,0,0.8); }
    .pin-dot.ai { background: #8b5cf6; }
    .pin-dot.manual { background: #3b82f6; }
    .pin-label { position: absolute; left: 18px; top: -4px; background: rgba(0,0,0,0.85); backdrop-filter: blur(4px); color: #fff; font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 4px; white-space: nowrap; border: 1px solid rgba(255,255,255,0.15); pointer-events: none; }

    /* 360 Viewer */
    #viewer { width: 100%; height: 100%; }
    .viewer-tip { position: absolute; top: 12px; left: 50%; transform: translateX(-50%); background: rgba(0,0,0,0.75); backdrop-filter: blur(4px); border: 1px solid rgba(255,255,255,0.1); padding: 5px 14px; border-radius: 20px; font-size: 11px; color: #e5e7eb; pointer-events: none; z-index: 10; display: flex; align-items: center; gap: 8px; }
  </style>
</head>
<body>
  <header>
    <div class="header-left">
      <h1>PastPort · Hotspot Studio</h1>
      <small>Verification & Calibration Viewer</small>
      <div class="controls-row">
        <label style="font-size: 12px; color: var(--text-muted);">Site:</label>
        <select id="select-site"></select>
        <div class="mode-switch">
          <button id="mode-2d" class="mode-btn active" onclick="switchMode('2d')">🖼️ 2D Photo</button>
          <button id="mode-360" class="mode-btn" onclick="switchMode('360')">🌐 360 Sphere</button>
        </div>
      </div>
    </div>
    <div class="controls-row">
      <button id="btn-save" class="btn btn-save" onclick="saveHotspots()">💾 Save to SQLite</button>
      <button id="btn-export" class="btn" onclick="exportContract()">📋 Export Spot Contract</button>
    </div>
  </header>

  <div id="main">
    <!-- Left: Claims list -->
    <div id="panel-claims">
      <div class="panel-header">
        <span>Heritage Claims</span>
        <span id="claim-count" style="font-size: 11px; color: var(--text-muted);">0 claims</span>
      </div>
      <div id="claims-list" class="panel-content">
        <div class="empty-state">Loading claims from SQLite database...</div>
      </div>
    </div>

    <!-- Center: Visual Workspace -->
    <div id="panel-viewer">
      <div class="viewer-tip">
        <span id="tip-text"><span style="color: #60a5fa; font-weight: 600;">Click photo</span> to place/calibrate hotspot for selected claim</span>
      </div>

      <!-- 2D Photo Container -->
      <div id="photo-view">
        <div id="photo-container">
          <img id="photo-img" src="" alt="Asset" onclick="onPhotoClick(event)">
          <div id="photo-pins"></div>
        </div>
      </div>

      <!-- 360 Panorama Container -->
      <div id="viewer" style="display: none;"></div>
    </div>

    <!-- Right: Placed Hotspots -->
    <div id="panel-spots">
      <div class="panel-header">
        <span>Placed Hotspots</span>
        <span id="spot-count" style="font-size: 11px; color: var(--accent); font-weight: 700;">0 spots</span>
      </div>
      <div id="spots-list" class="panel-content">
        <div class="empty-state">Select a claim on the left, then click on the photo to place a spot.</div>
      </div>
    </div>
  </div>

  <div id="toast">Saved to SQLite successfully!</div>

  <script>
    let viewer = null;
    let currentSite = null;
    let selectedClaim = null;
    let selectedSpot = null;
    let placedSpots = [];
    let currentMode = '2d';

    async function api(path, options = {}) {
      const res = await fetch(path, options);
      return res.json();
    }

    function showToast(msg) {
      const t = document.getElementById('toast');
      t.textContent = msg;
      t.classList.add('show');
      setTimeout(() => t.classList.remove('show'), 2500);
    }

    function switchMode(mode) {
      currentMode = mode;
      document.getElementById('mode-2d').classList.toggle('active', mode === '2d');
      document.getElementById('mode-360').classList.toggle('active', mode === '360');

      const photoView = document.getElementById('photo-view');
      const panoView = document.getElementById('viewer');
      const tipText = document.getElementById('tip-text');

      if (mode === '2d') {
        photoView.style.display = 'flex';
        panoView.style.display = 'none';
        tipText.innerHTML = '<span style="color: #60a5fa; font-weight: 600;">Click photo</span> to place/calibrate hotspot for selected claim';
        renderPhotoPins();
      } else {
        photoView.style.display = 'none';
        panoView.style.display = 'block';
        tipText.innerHTML = '<span style="color: #60a5fa; font-weight: 600;">Drag</span> to look around &nbsp;·&nbsp; <span style="color: #34d399; font-weight: 600;">Double-click</span> to place hotspot';
        if (currentSite) {
          initPannellum(currentSite.panorama_url);
        }
      }
    }

    async function loadSites() {
      try {
        const sites = await api('/api/sites');
        const sel = document.getElementById('select-site');
        sel.innerHTML = '';
        sites.forEach(s => {
          const opt = document.createElement('option');
          opt.value = s.site_id;
          const spotBadge = s.spot_count > 0 ? ` [★ ${s.spot_count} spots]` : '';
          opt.textContent = `${s.name_en} (${s.district})${spotBadge}`;
          sel.appendChild(opt);
        });
        if (sites.length) {
          sel.value = sites[0].site_id;
          await loadSite(sites[0].site_id);
        } else {
          document.getElementById('claims-list').innerHTML = '<div class="empty-state">No sites found in database.</div>';
        }
        sel.onchange = () => loadSite(sel.value);
      } catch (err) {
        console.error('Failed to load sites:', err);
        showToast('Failed to load sites: ' + err.message);
      }
    }

    async function loadSite(siteId) {
      try {
        currentSite = await api(`/api/site/${encodeURIComponent(siteId)}`);
        placedSpots = currentSite.hotspots || [];
        renderClaims();
        renderSpots();

        // Load image into 2D view
        const img = document.getElementById('photo-img');
        img.src = currentSite.panorama_url;
        img.onload = () => {
          renderPhotoPins();
        };

        // Determine default view mode based on metadata
        if (currentSite.is_panorama) {
          switchMode('360');
        } else {
          switchMode('2d');
        }
      } catch (err) {
        console.error('Failed to load site:', err);
        showToast('Failed to load site: ' + err.message);
      }
    }

    function renderClaims() {
      const list = document.getElementById('claims-list');
      list.innerHTML = '';
      const claims = currentSite.claims || [];
      document.getElementById('claim-count').textContent = `${claims.length} claims`;

      if (!claims.length) {
        list.innerHTML = '<div class="empty-state">No claims found for this site.</div>';
        return;
      }

      claims.forEach((c) => {
        const card = document.createElement('div');
        card.id = `claim-card-${c.claim_id}`;
        card.className = 'claim-card' + (selectedClaim?.claim_id === c.claim_id ? ' selected' : '');
        const badgeClass = c.content_kind === 'architectural_feature' ? 'badge-arch' : (c.content_kind === 'historical_date' ? 'badge-date' : 'badge-hist');
        card.innerHTML = `
          <div class="claim-badge ${badgeClass}">${c.content_kind.replace('_', ' ')}</div>
          <div class="claim-text">${c.text}</div>
        `;
        card.onclick = () => {
          selectedClaim = c;
          document.querySelectorAll('.claim-card').forEach(el => el.classList.remove('selected'));
          card.classList.add('selected');
        };
        list.appendChild(card);
      });

      if (!selectedClaim && claims.length) {
        selectedClaim = claims[0];
        list.children[0]?.classList.add('selected');
      }
    }

    function renderSpots() {
      const list = document.getElementById('spots-list');
      list.innerHTML = '';
      document.getElementById('spot-count').textContent = `${placedSpots.length} spots`;

      if (!placedSpots.length) {
        list.innerHTML = '<div class="empty-state">Select a claim on the left, then click on the photo to place a spot.</div>';
        return;
      }

      placedSpots.forEach((s, idx) => {
        const card = document.createElement('div');
        card.id = `spot-card-${s.spot_id}`;
        card.className = 'spot-card' + (selectedSpot?.spot_id === s.spot_id ? ' selected' : '');
        const methodBadge = s.authoring_method === 'vision_llm' ? '<span style="font-size:10px; background:rgba(139,92,246,0.2); color:#a78bfa; padding:2px 6px; border-radius:4px; font-weight:600;">VISION AI</span>' : '<span style="font-size:10px; background:rgba(59,130,246,0.2); color:#60a5fa; padding:2px 6px; border-radius:4px; font-weight:600;">MANUAL</span>';
        card.innerHTML = `
          <div class="spot-header">
            <span>#${idx + 1} ${s.label || s.spot_id}</span>
            <button style="background:none; border:none; color:#ef4444; cursor:pointer;" onclick="deleteSpot(event, ${idx})">✕</button>
          </div>
          <div style="margin-bottom: 2px;">${methodBadge}</div>
          <div class="spot-meta">Spot(${s.x}, ${s.y}) · yaw=${s.yaw.toFixed(1)}°, pitch=${s.pitch.toFixed(1)}°</div>
          <div class="spot-claim">${s.claim_text || s.claim_id}</div>
        `;
        card.onclick = () => selectSpot(s);
        list.appendChild(card);
      });
    }

    function selectSpot(spot) {
      selectedSpot = spot;
      document.querySelectorAll('.spot-card').forEach(el => el.classList.remove('selected'));
      document.getElementById(`spot-card-${spot.spot_id}`)?.classList.add('selected');

      // Highlight claim
      if (spot.claim_id) {
        const claimObj = currentSite.claims.find(c => c.claim_id === spot.claim_id);
        if (claimObj) {
          selectedClaim = claimObj;
          document.querySelectorAll('.claim-card').forEach(el => el.classList.remove('selected'));
          const cCard = document.getElementById(`claim-card-${spot.claim_id}`);
          if (cCard) {
            cCard.classList.add('selected');
            cCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
          }
        }
      }

      // Highlight 2D Pin
      document.querySelectorAll('.photo-pin').forEach(el => el.classList.remove('selected'));
      document.getElementById(`pin-${spot.spot_id}`)?.classList.add('selected');

      // Rotate 360 viewer if active
      if (viewer && currentMode === '360') {
        viewer.lookAt(spot.pitch, spot.yaw, 80, 1000);
      }
    }

    function renderPhotoPins() {
      const container = document.getElementById('photo-pins');
      container.innerHTML = '';
      const img = document.getElementById('photo-img');
      if (!img.complete || img.naturalWidth === 0) return;

      placedSpots.forEach((s, idx) => {
        const pin = document.createElement('div');
        pin.id = `pin-${s.spot_id}`;
        pin.className = 'photo-pin' + (selectedSpot?.spot_id === s.spot_id ? ' selected' : '');
        pin.style.left = `${(s.x / 10000) * 100}%`;
        pin.style.top = `${(s.y / 10000) * 100}%`;
        const aiClass = s.authoring_method === 'vision_llm' ? 'ai' : 'manual';
        pin.innerHTML = `
          <div class="pin-dot ${aiClass}"></div>
          <div class="pin-label">#${idx + 1} ${s.label || s.spot_id}</div>
        `;
        pin.onclick = (e) => {
          e.stopPropagation();
          selectSpot(s);
        };
        container.appendChild(pin);
      });
    }

    function onPhotoClick(e) {
      if (!selectedClaim) {
        alert('Please select a claim from the left panel first.');
        return;
      }
      const img = document.getElementById('photo-img');
      const rect = img.getBoundingClientRect();
      const clickX = e.clientX - rect.left;
      const clickY = e.clientY - rect.top;

      const normX = Math.max(0, Math.min(10000, Math.round((clickX / rect.width) * 10000)));
      const normY = Math.max(0, Math.min(10000, Math.round((clickY / rect.height) * 10000)));

      // Convert to yaw/pitch
      const yaw = Number(((normX / 10000) * 360 - 180).toFixed(2));
      const pitch = Number(((normY / 10000) * 180 - 90).toFixed(2));

      const spotId = `spot-${currentSite.site_id.split('-').slice(-2).join('-')}-${Date.now().toString().slice(-4)}`;
      const newSpot = {
        spot_id: spotId,
        site_id: currentSite.site_id,
        asset_id: currentSite.asset_id,
        claim_id: selectedClaim.claim_id,
        claim_text: selectedClaim.text,
        x: normX,
        y: normY,
        yaw: yaw,
        pitch: pitch,
        label: selectedClaim.text.slice(0, 32) + '...',
        authoring_method: 'manual_handclick'
      };

      placedSpots.push(newSpot);
      renderSpots();
      renderPhotoPins();
      selectSpot(newSpot);
      showToast(`Placed spot for: ${selectedClaim.text.slice(0, 24)}...`);
    }

    window.deleteSpot = function(e, idx) {
      e.stopPropagation();
      placedSpots.splice(idx, 1);
      renderSpots();
      renderPhotoPins();
      refreshViewerHotspots();
    };

    function refreshViewerHotspots() {
      if (!viewer) return;
      const existing = viewer.getConfig().hotSpots || [];
      existing.forEach(hs => viewer.removeHotSpot(hs.id));
      placedSpots.forEach(s => {
        viewer.addHotSpot({
          id: s.spot_id,
          pitch: s.pitch,
          yaw: s.yaw,
          type: 'info',
          text: s.claim_text || s.label || s.spot_id
        });
      });
    }

    function initPannellum(panoUrl) {
      if (typeof pannellum === 'undefined') {
        showToast('Pannellum CDN library not available.');
        return;
      }
      if (viewer) {
        try { viewer.destroy(); } catch (e) {}
        viewer = null;
      }
      const initialHotspots = placedSpots.map(s => ({
        id: s.spot_id,
        pitch: s.pitch,
        yaw: s.yaw,
        type: 'info',
        text: s.claim_text || s.label || s.spot_id
      }));

      try {
        viewer = pannellum.viewer('viewer', {
          type: 'equirectangular',
          panorama: panoUrl,
          autoLoad: true,
          showZoomCtrl: true,
          mouseZoom: true,
          doubleClickZoom: false,
          hotSpots: initialHotspots
        });
      } catch (err) {
        console.error('Failed to init Pannellum:', err);
      }
    }

    window.saveHotspots = async function() {
      if (!currentSite) return;
      const payload = {
        site_id: currentSite.site_id,
        spots: placedSpots
      };
      const res = await api('/api/spots', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      if (res.ok) {
        showToast(`Saved ${res.saved_count} hotspots directly to SQLite!`);
      } else {
        alert('Failed to save: ' + res.error);
      }
    };

    window.exportContract = function() {
      const contractSpots = placedSpots.map(s => ({
        spot_id: s.spot_id,
        x: s.x,
        y: s.y,
        spherical: { yaw: s.yaw, pitch: s.pitch },
        text_key: `${s.spot_id}_text`,
        claim_ids: [s.claim_id]
      }));
      const jsonStr = JSON.stringify(contractSpots, null, 2);
      navigator.clipboard.writeText(jsonStr);
      showToast('Spot contracts copied to clipboard!');
      console.log('PastPort Spot Contracts:', contractSpots);
    };

    window.onload = loadSites;
  </script>
</body>
</html>
"""


class StudioHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, db_path: Path, **kwargs) -> None:
        self.db_path = db_path
        super().__init__(*args, **kwargs)

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = urllib.parse.unquote(parsed.path)

        if path == "/" or path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode("utf-8"))
            return

        if path == "/api/sites":
            conn = sqlite3.connect(self.db_path)
            conn.execute(INIT_TABLE_SQL)
            rows = conn.execute("""
                SELECT s.site_id, s.name_en, s.district, s.category,
                       (SELECT COUNT(*) FROM scene_hotspots h WHERE h.site_id = s.site_id) as spot_count
                FROM sites s
                ORDER BY spot_count DESC, s.name_en ASC
            """).fetchall()
            conn.close()
            payload = [
                {
                    "site_id": r[0],
                    "name_en": r[1],
                    "district": r[2],
                    "category": r[3],
                    "spot_count": r[4],
                }
                for r in rows
            ]
            self._send_json(payload)
            return

        if path.startswith("/api/site/"):
            site_id = path.replace("/api/site/", "").strip()
            conn = sqlite3.connect(self.db_path)
            site_row = conn.execute(
                "SELECT site_id, name_en, district, category FROM sites WHERE site_id = ?",
                (site_id,),
            ).fetchone()
            if not site_row:
                self.send_error(404, "Site not found")
                conn.close()
                return

            claims_rows = conn.execute(
                "SELECT claim_id, text, content_kind FROM claims WHERE site_id = ?",
                (site_id,),
            ).fetchall()

            conn.execute(INIT_TABLE_SQL)
            hotspots_rows = conn.execute(
                """SELECT h.spot_id, h.site_id, h.asset_id, h.claim_id, h.x, h.y, h.yaw, h.pitch, h.label, h.authoring_method, c.text
                   FROM scene_hotspots h
                   LEFT JOIN claims c ON h.claim_id = c.claim_id
                   WHERE h.site_id = ?""",
                (site_id,),
            ).fetchall()

            # Resolve image asset: first check if placed hotspots used a specific asset
            asset_row = None
            if hotspots_rows and hotspots_rows[0][2]:
                asset_row = conn.execute(
                    "SELECT asset_id, file_name, relative_path FROM assets WHERE asset_id = ? LIMIT 1",
                    (hotspots_rows[0][2],),
                ).fetchone()

            if not asset_row:
                asset_row = conn.execute(
                    "SELECT asset_id, file_name, relative_path FROM assets WHERE site_id = ? LIMIT 1",
                    (site_id,),
                ).fetchone()

            if not asset_row:
                asset_row = conn.execute(
                    "SELECT asset_id, file_name, relative_path FROM assets WHERE media_type = 'image/jpeg' LIMIT 1"
                ).fetchone()

            conn.close()

            pano_url = "/media/panoramas/turing_lab_room.jpg"
            asset_id = "asset-turing-room-pano-360"
            is_panorama = False
            if asset_row:
                asset_id = asset_row[0]
                clean_rel = asset_row[2]
                if clean_rel.startswith("media/"):
                    clean_rel = clean_rel[len("media/"):]
                pano_url = f"/media/{clean_rel}"
                if "panoramas" in clean_rel.lower() or "pano" in clean_rel.lower() or "360" in clean_rel.lower():
                    is_panorama = True

            payload = {
                "site_id": site_row[0],
                "name_en": site_row[1],
                "district": site_row[2],
                "category": site_row[3],
                "asset_id": asset_id,
                "panorama_url": pano_url,
                "is_panorama": is_panorama,
                "claims": [{"claim_id": c[0], "text": c[1], "content_kind": c[2]} for c in claims_rows],
                "hotspots": [
                    {
                        "spot_id": h[0],
                        "site_id": h[1],
                        "asset_id": h[2],
                        "claim_id": h[3],
                        "x": h[4],
                        "y": h[5],
                        "yaw": h[6],
                        "pitch": h[7],
                        "label": h[8],
                        "authoring_method": h[9] if len(h) > 9 else "manual_handclick",
                        "claim_text": h[10] if (len(h) > 10 and h[10]) else h[8],
                    }
                    for h in hotspots_rows
                ],
            }
            self._send_json(payload)
            return

        if path.startswith("/media/"):
            raw_rel = path[len("/media/"):].strip()
            if raw_rel.startswith("media/"):
                raw_rel = raw_rel[len("media/"):]

            candidates = [
                REPO_ROOT / "var/sources/media" / raw_rel,
                REPO_ROOT / "var/sources" / raw_rel,
                REPO_ROOT / "var/sources/media/bursa" / raw_rel,
                REPO_ROOT / "var/sources/panoramas" / raw_rel,
            ]
            if raw_rel.startswith("bursa/"):
                candidates.append(REPO_ROOT / "var/sources/media/bursa" / raw_rel[len("bursa/"):])

            # Also check file by basename in media/bursa
            basename = raw_rel.split("/")[-1]
            candidates.append(REPO_ROOT / "var/sources/media/bursa" / basename)

            target_file = next((c for c in candidates if c.is_file()), REPO_ROOT / "var/sources/panoramas/turing_lab_room.jpg")
            if target_file.is_file():
                self.send_response(200)
                mime = "image/png" if target_file.suffix.lower() == ".png" else "image/jpeg"
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(target_file.stat().st_size))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "*")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                self.wfile.write(target_file.read_bytes())
                return
            self.send_error(404, f"Media file '{raw_rel}' not found")
            return

        self.send_error(404, "Not Found")

    def do_POST(self) -> None:
        if self.path == "/api/spots":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            site_id = body.get("site_id")
            spots = body.get("spots", [])

            conn = sqlite3.connect(self.db_path)
            with conn:
                conn.execute(INIT_TABLE_SQL)
                conn.execute("DELETE FROM scene_hotspots WHERE site_id = ?", (site_id,))
                for s in spots:
                    conn.execute(
                        """INSERT OR REPLACE INTO scene_hotspots
                           (spot_id, site_id, asset_id, claim_id, x, y, yaw, pitch, label, authoring_method, created_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            s["spot_id"],
                            site_id,
                            s.get("asset_id", "asset-unknown"),
                            s["claim_id"],
                            int(s["x"]),
                            int(s["y"]),
                            float(s["yaw"]),
                            float(s["pitch"]),
                            s.get("label", s["spot_id"]),
                            s.get("authoring_method", "manual_handclick"),
                            time.time(),
                        ),
                    )
            conn.close()
            print(f"[Hotspot Studio] Saved {len(spots)} spots for site {site_id} to {self.db_path}")
            self._send_json({"ok": True, "saved_count": len(spots)})
            return

        self.send_error(404, "Not Found")

    def do_OPTIONS(self) -> None:
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Range")
        self.end_headers()

    def _send_json(self, data: object) -> None:
        body = json.dumps(data).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)


def open_browser(url: str) -> None:
    try:
        if Path("/proc/version").is_file() and "microsoft" in Path("/proc/version").read_text().lower():
            import subprocess
            subprocess.run(["cmd.exe", "/c", "start", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
    except Exception:
        pass
    try:
        webbrowser.open(url)
    except Exception:
        pass


def run_studio(port: int = 8088, db_path: Path = Path("var/bursa_evidence.db")) -> None:
    socketserver.TCPServer.allow_reuse_address = True
    handler = lambda *args, **kwargs: StudioHandler(*args, db_path=db_path, **kwargs)
    with socketserver.TCPServer(("0.0.0.0", port), handler) as httpd:
        url = f"http://localhost:{port}"
        print("=" * 70)
        print("PASTPORT HOTSPOT STUDIO & VERIFICATION VIEWER RUNNING")
        print("=" * 70)
        print(f"URL:      {url} (or http://127.0.0.1:{port})")
        print(f"Database: {db_path}")
        print("Press Ctrl+C in terminal to stop.")
        print("=" * 70)
        open_browser(url)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down Hotspot Studio.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PastPort Hotspot Studio & Verification Viewer")
    parser.add_argument("--port", type=int, default=8088, help="Local port to serve studio UI")
    default_db = "var/bursa_evidence.db" if Path("var/bursa_evidence.db").is_file() else "var/test_evidence.db"
    parser.add_argument("--db", default=default_db, help=f"SQLite database path (default: {default_db})")
    args = parser.parse_args()

    run_studio(port=args.port, db_path=Path(args.db))
