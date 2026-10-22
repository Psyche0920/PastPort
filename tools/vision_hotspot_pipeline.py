"""PastPort Vision Hotspot Pipeline: Automated Multimodal Spatial AI Detector.

Uses multimodal vision models (Gemini / OpenAI / offline mock) to analyze 360 panoramas and 2D images,
locate target heritage artifacts described in SQLite claims, and generate PastPort Spot contracts.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import sys

import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.spot_converter import SphericalCoordinate
from tools.vision_spot_detector import VisionSpotDetector

INIT_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS scene_hotspots (
    spot_id TEXT PRIMARY KEY,
    site_id TEXT NOT NULL REFERENCES sites(site_id),
    asset_id TEXT NOT NULL REFERENCES assets(asset_id),
    object_id TEXT REFERENCES museum_objects(object_id),
    claim_id TEXT NOT NULL REFERENCES claims(claim_id),
    x INTEGER NOT NULL CHECK (x >= 0 AND x <= 10000),
    y INTEGER NOT NULL CHECK (y >= 0 AND y <= 10000),
    yaw REAL NOT NULL,
    pitch REAL NOT NULL,
    label TEXT NOT NULL,
    authoring_method TEXT NOT NULL DEFAULT 'vision_spatial_grounding',
    created_at REAL NOT NULL
);
"""


def create_vision_spot(
    db_path: Path,
    pano_path: Path,
    claim_id: str,
    mode: str = "auto",
    spot_id: str | None = None,
    asset_id: str = "asset-unknown",
) -> dict[str, object]:
    """Query claim, run Vision LLM detector on panorama, and produce Spot contract."""
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT claim_id, site_id, text, content_kind FROM claims WHERE claim_id = ?",
        (claim_id,),
    ).fetchone()
    conn.close()

    if not row:
        raise ValueError(f"Claim '{claim_id}' not found in database {db_path}")

    cid, site_id, claim_text, kind = row

    detector = VisionSpotDetector(mode=mode)
    detect_res = detector.detect(pano_path, claim_text)
    spot_x = int(detect_res["x"])
    spot_y = int(detect_res["y"])
    coord = SphericalCoordinate.from_spot(spot_x, spot_y)

    resolved_spot_id = spot_id or f"spot-vision-{claim_id}"

    contract = {
        "spot_id": resolved_spot_id,
        "site_id": site_id,
        "asset_id": asset_id,
        "claim_id": cid,
        "x": spot_x,
        "y": spot_y,
        "spherical": {"yaw": coord.yaw, "pitch": coord.pitch},
        "label": str(detect_res.get("label", claim_text[:32])),
        "text_key": f"{resolved_spot_id}_desc",
        "claim_ids": [cid],
        "authoring_method": "vision_llm",
        "vision_backend": detect_res.get("backend", mode),
        "confidence": detect_res.get("confidence", 0.0),
        "latency_ms": detect_res.get("latency_ms", 0.0),
        "cost_usd": detect_res.get("cost_usd", 0.0),
    }
    return contract


def run_vision_pipeline_for_site(
    db_path: Path,
    site_id: str | None = None,
    pano_path: Path | None = None,
    mode: str = "auto",
    save_to_db: bool = True,
) -> list[dict[str, object]]:
    """Batch pipeline: detect spots for all claims of a site and save to SQLite."""
    conn = sqlite3.connect(db_path)

    # 1. Resolve site
    if not site_id:
        site_row = conn.execute("SELECT site_id, name_en FROM sites LIMIT 1").fetchone()
        if not site_row:
            conn.close()
            raise ValueError(f"No sites found in database {db_path}")
        site_id = site_row[0]
        site_name = site_row[1]
    else:
        site_row = conn.execute("SELECT site_id, name_en FROM sites WHERE site_id = ?", (site_id,)).fetchone()
        if not site_row:
            conn.close()
            raise ValueError(f"Site '{site_id}' not found in database {db_path}")
        site_name = site_row[1]

    # 2. Resolve image assets for this site
    repo_root = Path(__file__).resolve().parents[1]
    asset_rows: list[tuple[str, str]] = []

    if pano_path and pano_path.is_file():
        asset_rows = [("asset-custom", str(pano_path))]
    else:
        db_assets = conn.execute(
            "SELECT asset_id, relative_path FROM assets WHERE site_id = ? ORDER BY asset_id",
            (site_id,),
        ).fetchall()
        asset_rows = [(r[0], r[1]) for r in db_assets]

    resolved_assets: list[tuple[str, Path]] = []
    for a_id, raw_path in asset_rows:
        candidates = [
            Path(raw_path),
            repo_root / "var/sources" / raw_path,
            repo_root / "var/sources/media" / raw_path,
            repo_root / "var/sources/media/bursa" / Path(raw_path).name,
            repo_root / "var/sources" / raw_path.replace("media/", ""),
        ]
        found_file = next((c for c in candidates if c.is_file()), None)
        if found_file:
            resolved_assets.append((a_id, found_file))

    if not resolved_assets:
        resolved_assets = [("asset-turing-room-pano-360", repo_root / "var/sources/panoramas/turing_lab_room.jpg")]

    # 3. Retrieve museum objects for this site (or fallback to architectural claims)
    objects = []
    try:
        objects = conn.execute(
            "SELECT object_id, name_en, category, description_en, claim_id FROM museum_objects WHERE site_id = ?",
            (site_id,),
        ).fetchall()
    except sqlite3.OperationalError:
        pass

    targets: list[tuple[str, str, str, str | None]] = []
    if objects:
        for obj_id, name_en, category, desc, cid in objects:
            targets.append((obj_id, f"{name_en}: {desc}", name_en, cid))
    else:
        claims = conn.execute(
            "SELECT claim_id, text, content_kind FROM claims WHERE site_id = ? AND content_kind = 'architectural_feature'",
            (site_id,),
        ).fetchall()
        if not claims:
            claims = conn.execute(
                "SELECT claim_id, text, content_kind FROM claims WHERE site_id = ? LIMIT 3",
                (site_id,),
            ).fetchall()
        for cid, text, kind in claims:
            targets.append((cid, text, text[:32], cid))

    if not targets:
        conn.close()
        print(f"[Vision Pipeline] No objects or claims found for site {site_id}")
        return []

    print("=" * 70)
    print("PASTPORT VISION LLM AUTOMATED PIPELINE")
    print("=" * 70)
    print(f"Site ID:     {site_id} ({site_name})")
    print(f"Assets:      {len(resolved_assets)} photographic views to scan")
    print(f"Targets:     {len(targets)} museum objects to ground")
    print(f"Backend:     {mode}")
    print(f"Save to DB:  {save_to_db} -> {db_path}")
    print("-" * 70)

    detector = VisionSpotDetector(mode=mode)
    results: list[dict[str, object]] = []

    if save_to_db:
        conn.execute(INIT_TABLE_SQL)

    candidates = [
        {
            "object_id": t[0],
            "name": t[2],
            "description": t[1],
            "claim_id": t[3],
        }
        for t in targets
    ]

    for a_idx, (asset_id, asset_path) in enumerate(resolved_assets, 1):
        print(f"\n--- Scanning Asset [{a_idx}/{len(resolved_assets)}]: {asset_path.name} ---")
        detected_items = detector.detect_multi(asset_path, candidates)
        if not detected_items:
            print(f"  No target objects detected in {asset_path.name}.")
            continue

        for det in detected_items:
            spot_x = int(det["x"])
            spot_y = int(det["y"])
            coord = SphericalCoordinate.from_spot(spot_x, spot_y)
            obj_id = det["object_id"]
            spot_id = f"spot-vision-{obj_id}-{asset_id[-6:]}"
            label = det["name"]
            is_obj = obj_id.startswith("obj-")

            spot_record = {
                "spot_id": spot_id,
                "site_id": site_id,
                "asset_id": asset_id,
                "object_id": obj_id if is_obj else None,
                "claim_id": det.get("claim_id") or "claim-general",
                "x": spot_x,
                "y": spot_y,
                "spherical": {"yaw": coord.yaw, "pitch": coord.pitch},
                "label": label,
                "text_key": f"{spot_id}_desc",
                "claim_ids": [det["claim_id"]] if det.get("claim_id") else [],
                "authoring_method": "vision_spatial_grounding",
                "vision_backend": det.get("backend", mode),
                "confidence": det.get("confidence", 0.0),
                "latency_ms": det.get("latency_ms", 0.0),
                "cost_usd": det.get("cost_usd", 0.0),
            }
            results.append(spot_record)

            if save_to_db:
                conn.execute(
                    """INSERT OR REPLACE INTO scene_hotspots
                       (spot_id, site_id, asset_id, object_id, claim_id, x, y, yaw, pitch, label, authoring_method, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        spot_id,
                        site_id,
                        asset_id,
                        obj_id if is_obj else None,
                        det.get("claim_id") or "claim-general",
                        spot_x,
                        spot_y,
                        coord.yaw,
                        coord.pitch,
                        label,
                        "vision_spatial_grounding",
                        time.time(),
                    ),
                )
                conn.commit()

            print(
                f"  VISIBLE: {label} -> Spot({spot_x}, {spot_y}) "
                f"yaw={coord.yaw:+.1f}°, pitch={coord.pitch:+.1f}° | conf={det.get('confidence', 0):.2f} "
                f"({det.get('description', '')[:40]})"
            )

    if save_to_db:
        conn.commit()
        print(f"\nSuccessfully saved {len(results)} spots directly to {db_path} (table: scene_hotspots)")

    conn.close()
    print("=" * 70)
    return results

def main() -> None:
    default_db = "var/bursa_evidence.db" if Path("var/bursa_evidence.db").is_file() else "var/test_evidence.db"
    parser = argparse.ArgumentParser(description="PastPort Vision LLM Spot Detection Pipeline")
    parser.add_argument("--db", default=default_db, help=f"Path to SQLite evidence database (default: {default_db})")
    parser.add_argument("--site", default=None, help="Site ID to batch process (default: all claims in first site)")
    parser.add_argument("--all", action="store_true", help="Process all sites across the entire database in batch")
    parser.add_argument("--claim", default=None, help="Process single target claim ID")
    parser.add_argument("--pano", default=None, help="Path to 360 panorama JPG (default: auto-detect from assets)")
    parser.add_argument("--mode", default="auto", choices=["auto", "gemini", "openai", "mock"], help="Detector backend")
    parser.add_argument("--no-save", action="store_true", help="Do not write results to SQLite scene_hotspots")
    parser.add_argument("--export", default=None, help="Optional output JSON path for Spot contracts")
    args = parser.parse_args()

    db_path = Path(args.db)
    pano_path = Path(args.pano) if args.pano else None

    if args.claim:
        # Single-claim mode
        resolved_pano = pano_path or Path("var/sources/panoramas/turing_lab_room.jpg")
        result = create_vision_spot(
            db_path=db_path,
            pano_path=resolved_pano,
            claim_id=args.claim,
            mode=args.mode,
        )
        print("=" * 60)
        print("PASTPORT: VISION LLM SINGLE SPOT RESULT")
        print("=" * 60)
        print(json.dumps(result, indent=2))
        spots = [result]
    elif args.all:
        # Process all sites in the database
        conn = sqlite3.connect(db_path)
        site_ids = [r[0] for r in conn.execute("SELECT site_id FROM sites ORDER BY site_id").fetchall()]
        conn.close()
        spots = []
        for s_id in site_ids:
            s_spots = run_vision_pipeline_for_site(
                db_path=db_path,
                site_id=s_id,
                pano_path=pano_path,
                mode=args.mode,
                save_to_db=not args.no_save,
            )
            spots.extend(s_spots)
        print(f"\n[Batch Complete] Processed {len(site_ids)} sites, generated {len(spots)} spots.")
    else:
        # Full site batch pipeline mode
        spots = run_vision_pipeline_for_site(
            db_path=db_path,
            site_id=args.site,
            pano_path=pano_path,
            mode=args.mode,
            save_to_db=not args.no_save,
        )

    if args.export:
        export_path = Path(args.export)
        export_path.parent.mkdir(parents=True, exist_ok=True)
        export_path.write_text(json.dumps(spots, indent=2), encoding="utf-8")
        print(f"Exported {len(spots)} spot contracts to {export_path}")


if __name__ == "__main__":
    main()
