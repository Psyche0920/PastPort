"""PastPort Hotspot Studio: Unified Interactive Pipeline for 360 Panorama Evidence Mapping.

Connects SQLite evidence databases (sites, assets, claims) directly to the 360 visual viewer,
allowing curators to select claims, point-and-click on 360 panoramas, and save validated Spots
directly back into the database.

Usage:
    python tools/hotspot_studio.py [--port 8088] [--db var/test_evidence.db]
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

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
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
  <title>PastPort · 360 Hotspot Studio</title>
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
    header { background: var(--surface); padding: 12px 20px; border-bottom: 1px solid var(--surface-border); display: flex; align-items: center; justify-content: space-between; gap: 16px; }
    .header-left { display: flex; align-items: center; gap: 16px; }
    .header-left h1 { font-size: 16px; font-weight: 700; color: #fff; letter-spacing: -0.2px; }
    .header-left small { font-size: 11px; background: rgba(59, 130, 246, 0.15); color: #60a5fa; padding: 2px 8px; border-radius: 4px; font-weight: 600; text-transform: uppercase; }
    .controls-row { display: flex; align-items: center; gap: 12px; }
    select { background: #121215; color: #fff; border: 1px solid var(--surface-border); border-radius: 6px; padding: 6px 12px; font-size: 13px; outline: none; }
    select:focus { border-color: var(--primary); }
    .btn { background: var(--primary); color: #fff; border: none; border-radius: 6px; padding: 7px 14px; font-size: 13px; font-weight: 600; cursor: pointer; display: inline-flex; align-items: center; gap: 6px; transition: background 0.15s; }
    .btn:hover { background: var(--primary-hover); }
    .btn-save { background: var(--accent); }
    .btn-save:hover { background: #059669; }
    #main { display: flex; flex: 1; overflow: hidden; position: relative; }
    #panel-claims { width: 340px; background: var(--surface); border-right: 1px solid var(--surface-border); display: flex; flex-direction: column; overflow: hidden; }
    #panel-viewer { flex: 1; height: 100%; position: relative; }
    #panel-spots { width: 320px; background: var(--surface); border-left: 1px solid var(--surface-border); display: flex; flex-direction: column; overflow: hidden; }
    .panel-header { padding: 14px 16px; border-bottom: 1px solid var(--surface-border); font-size: 13px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-muted); display: flex; justify-content: space-between; align-items: center; }
    .panel-content { flex: 1; overflow-y: auto; padding: 12px; display: flex; flex-direction: column; gap: 8px; }
    .claim-card { background: #18181d; border: 1px solid var(--surface-border); border-radius: 8px; padding: 12px; cursor: pointer; transition: all 0.15s; }
    .claim-card:hover { border-color: #4b5563; }
    .claim-card.selected { border-color: var(--primary); background: rgba(59, 130, 246, 0.08); }
    .claim-badge { font-size: 10px; font-weight: 600; text-transform: uppercase; padding: 2px 6px; border-radius: 4px; display: inline-block; margin-bottom: 6px; }
    .badge-arch { background: rgba(16, 185, 129, 0.15); color: #34d399; }
    .badge-hist { background: rgba(59, 130, 246, 0.15); color: #60a5fa; }
    .badge-date { background: rgba(245, 158, 11, 0.15); color: #fbbf24; }
    .claim-text { font-size: 13px; line-height: 1.4; color: #e5e7eb; }
    .spot-card { background: #18181d; border: 1px solid var(--surface-border); border-radius: 8px; padding: 12px; display: flex; flex-direction: column; gap: 6px; font-size: 13px; }
    .spot-header { display: flex; justify-content: space-between; font-weight: 600; color: #fff; }
    .spot-meta { font-family: monospace; font-size: 12px; color: #60a5fa; }
    .spot-claim { font-size: 12px; color: var(--text-muted); }
    .empty-state { text-align: center; color: var(--text-muted); font-size: 13px; padding: 40px 20px; }
    #toast { position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%); background: #10b981; color: #fff; padding: 10px 20px; border-radius: 8px; font-size: 14px; font-weight: 600; box-shadow: 0 4px 12px rgba(0,0,0,0.4); opacity: 0; pointer-events: none; transition: opacity 0.2s; z-index: 1000; }
    #toast.show { opacity: 1; }
  </style>
</head>
<body>
  <header>
    <div class="header-left">
      <h1>PastPort · Hotspot Studio</h1>
      <small>Branch A Pipeline</small>
      <div class="controls-row">
        <label style="font-size: 13px; color: var(--text-muted);">Site:</label>
        <select id="select-site"></select>
      </div>
    </div>
    <div class="controls-row">
      <button id="btn-save" class="btn btn-save">💾 Save Hotspots to SQLite</button>
      <button id="btn-export" class="btn">📋 Export Spot Contract</button>
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

    <!-- Center: 360 viewer -->
    <div id="panel-viewer">
      <div id="viewer" style="width: 100%; height: 100%;"></div>
    </div>

    <!-- Right: Placed Hotspots -->
    <div id="panel-spots">
      <div class="panel-header">
        <span>Placed Hotspots</span>
        <span id="spot-count" style="font-size: 11px; color: var(--text-muted);">0 spots</span>
      </div>
      <div id="spots-list" class="panel-content">
        <div class="empty-state">Select a claim on the left, then click on the object in the 360 panorama to place a spot.</div>
      </div>
    </div>
  </div>

  <div id="toast">Saved to SQLite successfully!</div>

  <script>
    let viewer = null;
    let currentSite = null;
    let selectedClaim = null;
    let placedSpots = [];

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

    async function loadSites() {
      const sites = await api('/api/sites');
      const sel = document.getElementById('select-site');
      sel.innerHTML = '';
      sites.forEach(s => {
        const opt = document.createElement('option');
        opt.value = s.site_id;
        opt.textContent = `${s.name_en} (${s.district})`;
        sel.appendChild(opt);
      });
      if (sites.length) {
        sel.value = sites[0].site_id;
        loadSite(sites[0].site_id);
      }
      sel.onchange = () => loadSite(sel.value);
    }

    async function loadSite(siteId) {
      currentSite = await api(`/api/site/${encodeURIComponent(siteId)}`);
      placedSpots = currentSite.hotspots || [];
      renderClaims();
      renderSpots();
      initViewer(currentSite.panorama_url);
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

      claims.forEach((c, idx) => {
        const card = document.createElement('div');
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
        list.innerHTML = '<div class="empty-state">Select a claim on the left, then click on the object in the 360 panorama to place a spot.</div>';
        return;
      }

      placedSpots.forEach((s, idx) => {
        const card = document.createElement('div');
        card.className = 'spot-card';
        card.innerHTML = `
          <div class="spot-header">
            <span>#${idx + 1} ${s.label || s.spot_id}</span>
            <button style="background:none; border:none; color:#ef4444; cursor:pointer;" onclick="deleteSpot(${idx})">✕</button>
          </div>
          <div class="spot-meta">Spot(${s.x}, ${s.y}) · yaw=${s.yaw.toFixed(1)}°, pitch=${s.pitch.toFixed(1)}°</div>
          <div class="spot-claim">${s.claim_text || s.claim_id}</div>
        `;
        list.appendChild(card);
      });
    }

    window.deleteSpot = function(idx) {
      placedSpots.splice(idx, 1);
      renderSpots();
      refreshViewerHotspots();
    };

    function refreshViewerHotspots() {
      if (!viewer) return;
      // remove old spots
      const existing = viewer.getConfig().hotSpots || [];
      existing.forEach(hs => viewer.removeHotSpot(hs.id));
      // add current
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

    function initViewer(panoUrl) {
      if (viewer) viewer.destroy();
      const initialHotspots = placedSpots.map(s => ({
        id: s.spot_id,
        pitch: s.pitch,
        yaw: s.yaw,
        type: 'info',
        text: s.claim_text || s.label || s.spot_id
      }));

      viewer = pannellum.viewer('viewer', {
        type: 'equirectangular',
        panorama: panoUrl,
        autoLoad: true,
        showZoomCtrl: true,
        mouseZoom: true,
        hotSpots: initialHotspots
      });

      viewer.on('mousedown', function(event) {
        if (!selectedClaim) {
          alert('Please select a claim from the left panel first.');
          return;
        }
        const coords = viewer.mouseEventToCoords(event);
        if (!coords || isNaN(coords[0]) || isNaN(coords[1])) return;
        const pitch = Number(coords[0].toFixed(2));
        const yaw = Number(coords[1].toFixed(2));

        // Coordinate conversion formula
        const x = Math.max(0, Math.min(10000, Math.round(((yaw + 180) / 360) * 10000)));
        const y = Math.max(0, Math.min(10000, Math.round(((pitch + 90) / 180) * 10000)));

        const spotId = `spot-${currentSite.site_id.split('-').slice(-2).join('-')}-${Date.now().toString().slice(-4)}`;
        const newSpot = {
          spot_id: spotId,
          site_id: currentSite.site_id,
          asset_id: currentSite.asset_id,
          claim_id: selectedClaim.claim_id,
          claim_text: selectedClaim.text,
          x: x,
          y: y,
          yaw: yaw,
          pitch: pitch,
          label: selectedClaim.text.slice(0, 32) + '...',
          authoring_method: 'manual_handclick'
        };

        placedSpots.push(newSpot);
        renderSpots();
        refreshViewerHotspots();
        showToast(`Tagged: ${selectedClaim.text.slice(0, 28)}...`);
      });
    }

    document.getElementById('btn-save').onclick = async () => {
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

    document.getElementById('btn-export').onclick = () => {
      const contractSpots = placedSpots.map(s => ({
        spot_id: s.spot_id,
        x: s.x,
        y: s.y,
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
        path = parsed.path

        if path == "/" or path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode("utf-8"))
            return

        if path == "/api/sites":
            conn = sqlite3.connect(self.db_path)
            rows = conn.execute("SELECT site_id, name_en, district, category FROM sites ORDER BY site_id").fetchall()
            conn.close()
            payload = [{"site_id": r[0], "name_en": r[1], "district": r[2], "category": r[3]} for r in rows]
            self._send_json(payload)
            return

        if path.startswith("/api/site/"):
            site_id = urllib.parse.unquote(path.replace("/api/site/", ""))
            conn = sqlite3.connect(self.db_path)
            site_row = conn.execute("SELECT site_id, name_en, district, category FROM sites WHERE site_id = ?", (site_id,)).fetchone()
            if not site_row:
                self.send_error(404, "Site not found")
                conn.close()
                return

            claims_rows = conn.execute("SELECT claim_id, text, content_kind FROM claims WHERE site_id = ?", (site_id,)).fetchall()
            asset_row = conn.execute("SELECT asset_id, file_name, relative_path FROM assets WHERE site_id = ? OR media_type = 'image/jpeg' LIMIT 1", (site_id,)).fetchone()

            # Ensure scene_hotspots table exists
            conn.execute(INIT_TABLE_SQL)
            hotspots_rows = conn.execute(
                "SELECT spot_id, site_id, asset_id, claim_id, x, y, yaw, pitch, label FROM scene_hotspots WHERE site_id = ?",
                (site_id,),
            ).fetchall()
            conn.close()

            pano_url = "/media/panoramas/turing_lab_room.jpg"
            asset_id = "asset-turing-room-pano-360"
            if asset_row:
                asset_id = asset_row[0]
                pano_url = f"/media/{asset_row[2]}"

            payload = {
                "site_id": site_row[0],
                "name_en": site_row[1],
                "district": site_row[2],
                "category": site_row[3],
                "asset_id": asset_id,
                "panorama_url": pano_url,
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
                    }
                    for h in hotspots_rows
                ],
            }
            self._send_json(payload)
            return

        if path.startswith("/media/"):
            rel_path = path.replace("/media/", "")
            target_file = Path("var/sources") / rel_path
            if not target_file.exists():
                # Fallback to test panorama
                target_file = Path("var/sources/panoramas/turing_lab_room.jpg")
            if target_file.exists():
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(target_file.stat().st_size))
                self.end_headers()
                self.wfile.write(target_file.read_bytes())
                return
            self.send_error(404, "Media file not found")
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
                # Clear prior spots for this site to overwrite with updated list
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

    def _send_json(self, data: object) -> None:
        body = json.dumps(data).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
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


def run_studio(port: int = 8088, db_path: Path = Path("var/test_evidence.db")) -> None:
    handler = lambda *args, **kwargs: StudioHandler(*args, db_path=db_path, **kwargs)
    with socketserver.TCPServer(("127.0.0.1", port), handler) as httpd:
        url = f"http://127.0.0.1:{port}"
        print("=" * 70)
        print("PASTPORT 360 HOTSPOT STUDIO RUNNING")
        print("=" * 70)
        print(f"URL:      {url}")
        print(f"Database: {db_path}")
        print("Press Ctrl+C in terminal to stop.")
        print("=" * 70)
        open_browser(url)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down Hotspot Studio.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PastPort 360 Hotspot Studio")
    parser.add_argument("--port", type=int, default=8088, help="Local port to serve studio UI")
    parser.add_argument("--db", default="var/test_evidence.db", help="SQLite database path")
    args = parser.parse_args()

    run_studio(port=args.port, db_path=Path(args.db))
