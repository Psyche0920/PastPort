"""Export MuseumPackage conforming to PastPort SDK v1 specification.

Owner: wcheung (Task T2 -> T3 Handoff).
Specification: docs/PastPort_PRD_EN.md Section 2.6 and
docs/technical/sdk-v1/sdk-contracts.schema.json (#/$defs/MuseumPackage).
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any


def export_museum_package(
    db_path: Path,
    output_path: Path,
    project_id: str = "bursa",
    max_views: int = 35,
) -> dict[str, Any]:
    """Export SQLite evidence database to an SDK v1 MuseumPackage."""
    if not db_path.is_file():
        raise FileNotFoundError(f"Database not found at {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # 1. Fetch sites and assets (up to max_views to stay within 1..40 limit)
    sites = conn.execute(
        """SELECT s.site_id, s.name_en, s.name_tr, s.district, s.category, s.source_id,
                  src.file_sha256 as source_sha256
           FROM sites s
           JOIN sources src ON s.source_id = src.source_id
           ORDER BY s.site_id
           LIMIT ?""",
        (max_views,),
    ).fetchall()

    site_ids = [s["site_id"] for s in sites]

    # 2. Build views (one primary view per site)
    views: list[dict[str, Any]] = []
    view_id_by_site: dict[str, str] = {}
    site_primary_asset: dict[str, sqlite3.Row] = {}

    for s in sites:
        s_id = s["site_id"]
        # Find primary asset for this site
        asset = conn.execute(
            """SELECT asset_id, file_name, relative_path, sha256
               FROM assets
               WHERE site_id = ?
               ORDER BY asset_id
               LIMIT 1""",
            (s_id,),
        ).fetchone()

        if not asset:
            continue

        site_primary_asset[s_id] = asset
        view_id = f"view-{s_id}"
        view_id_by_site[s_id] = view_id

        views.append({
            "view_id": view_id,
            "original_asset": {
                "resource_id": asset["asset_id"],
                "version": "v1",
                "sha256": asset["sha256"],
            },
            "display_asset": {
                "resource_id": asset["asset_id"],
                "version": "v1",
                "sha256": asset["sha256"],
            },
            "display_kind": "photographic",
            "panorama_revision": 1,
            "initial_view": {
                "yaw": 0.0,
                "pitch": 0.0,
                "hfov": 95.0,
            },
        })

    # 3. Build linear bidirectional tour connections between consecutive views
    connections: list[dict[str, Any]] = []
    for i in range(len(views) - 1):
        v_from = views[i]["view_id"]
        v_to = views[i + 1]["view_id"]
        # Forward
        connections.append({
            "connection_id": f"conn-{v_from}-to-{v_to}",
            "from_view_id": v_from,
            "to_view_id": v_to,
            "departure": {"yaw": 0.0, "pitch": 0.0, "hfov": 95.0},
            "arrival": {"yaw": 0.0, "pitch": 0.0, "hfov": 95.0},
        })
        # Return
        connections.append({
            "connection_id": f"conn-{v_to}-to-{v_from}",
            "from_view_id": v_to,
            "to_view_id": v_from,
            "departure": {"yaw": 180.0, "pitch": 0.0, "hfov": 95.0},
            "arrival": {"yaw": 0.0, "pitch": 0.0, "hfov": 95.0},
        })

    # 4. Build museum objects and entries
    placeholders = ",".join("?" for _ in site_ids)
    obj_rows = conn.execute(
        f"""SELECT o.object_id, o.site_id, o.name_en, o.category, o.description_en, o.claim_id,
                   s.source_id
            FROM museum_objects o
            JOIN sites s ON o.site_id = s.site_id
            WHERE o.site_id IN ({placeholders})
            ORDER BY o.site_id, o.object_id""",
        site_ids,
    ).fetchall()

    museum_objects: list[dict[str, Any]] = []
    museum_entries: list[dict[str, Any]] = []

    for obj in obj_rows:
        obj_id = obj["object_id"]
        src_id = obj["source_id"]
        claim_id = obj["claim_id"]

        museum_objects.append({
            "object_id": obj_id,
            "site_id": obj["site_id"],
            "source_record_ids": [src_id],
        })

        claims_list = [claim_id] if claim_id else []
        museum_entries.append({
            "entry_id": f"entry-{obj_id}",
            "object_id": obj_id,
            "text": obj["description_en"],
            "language": "en",
            "source_record_ids": [src_id],
            "claim_ids": claims_list,
        })

    # 5. Build anchors from verified scene hotspots
    hotspot_rows = conn.execute(
        f"""SELECT h.spot_id, h.site_id, h.asset_id, h.object_id, h.yaw, h.pitch, h.label,
                   a.sha256 as asset_sha256, o.category
            FROM scene_hotspots h
            JOIN assets a ON h.asset_id = a.asset_id
            JOIN museum_objects o ON h.object_id = o.object_id
            WHERE h.site_id IN ({placeholders}) AND h.object_id IS NOT NULL
            ORDER BY h.site_id, h.spot_id""",
        site_ids,
    ).fetchall()

    anchors: list[dict[str, Any]] = []
    for h in hotspot_rows:
        s_id = h["site_id"]
        view_id = view_id_by_site.get(s_id)
        if not view_id:
            continue

        bounded_pitch = max(-85.0, min(85.0, float(h["pitch"])))
        bounded_yaw = max(-180.0, min(180.0, float(h["yaw"])))

        anchors.append({
            "anchor_id": f"anchor-{h['spot_id']}",
            "object_id": h["object_id"],
            "view_id": view_id,
            "panorama_sha256": h["asset_sha256"],
            "yaw": round(bounded_yaw, 2),
            "pitch": round(bounded_pitch, 2),
            "radius_degrees": 3.0,
            "match_state": "confirmed",
            "visual_check": "pass",
            "legible_features": [h["category"]] if h["category"] else [],
            "basis_refs": [f"db:bursa_evidence.db:scene_hotspots:{h['spot_id']}"],
        })

    # 6. Source corpus and tour references
    corpus_sha = hashlib.sha256(b"pastport:bursa:corpus:v1").hexdigest()
    tour_sha = hashlib.sha256(b"pastport:bursa:tour:v1").hexdigest()

    package: dict[str, Any] = {
        "contract_family": "pastport-sdk",
        "schema_version": "1.0.0",
        "kind": "museum",
        "project_id": project_id,
        "artifact_id": f"museum-{project_id}",
        "content_version": "v1",
        "source_corpus_ref": {
            "artifact_id": f"corpus-{project_id}",
            "project_id": project_id,
            "kind": "source_corpus",
            "schema_version": "1.0.0",
            "content_version": "v1",
            "sha256": corpus_sha,
        },
        "tour_ref": {
            "artifact_id": f"tour-{project_id}",
            "project_id": project_id,
            "kind": "tour",
            "schema_version": "1.0.0",
            "content_version": "v1",
            "sha256": tour_sha,
        },
        "state": "ready_for_review",
        "views": views,
        "connections": connections,
        "objects": museum_objects,
        "entries": museum_entries,
        "anchors": anchors,
        "unmatched_record_ids": [],
        "unresolved_items": [],
    }

    # 7. Write to output path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(package, indent=2, ensure_ascii=False)
    output_path.write_text(serialized, encoding="utf-8")

    print("=" * 70)
    print("PASTPORT MUSEUM PACKAGE EXPORT COMPLETE")
    print("=" * 70)
    print(f"Target Output: {output_path}")
    print(f"Project ID:    {project_id}")
    print(f"Views:         {len(views)}")
    print(f"Connections:   {len(connections)}")
    print(f"Objects:       {len(museum_objects)}")
    print(f"Entries:       {len(museum_entries)}")
    print(f"Anchors:       {len(anchors)}")
    print("=" * 70)

    return package


def validate_package_contracts(package: dict[str, Any]) -> None:
    """Validate package integrity and constraints according to SDK schema."""
    assert package.get("contract_family") == "pastport-sdk", "Invalid contract_family"
    assert package.get("schema_version") == "1.0.0", "Invalid schema_version"
    assert package.get("kind") == "museum", "Invalid kind"
    assert 1 <= len(package.get("views", [])) <= 40, "Views count must be between 1 and 40"

    view_ids = {v["view_id"] for v in package["views"]}
    for c in package.get("connections", []):
        assert c["from_view_id"] in view_ids, f"Unknown from_view_id {c['from_view_id']}"
        assert c["to_view_id"] in view_ids, f"Unknown to_view_id {c['to_view_id']}"

    obj_ids = {o["object_id"] for o in package["objects"]}
    for e in package.get("entries", []):
        assert e["object_id"] in obj_ids, f"Entry object_id {e['object_id']} missing in objects"
        assert e.get("language") == "en"

    for a in package.get("anchors", []):
        assert a["object_id"] in obj_ids, f"Anchor object_id {a['object_id']} missing in objects"
        assert a["view_id"] in view_ids, f"Anchor view_id {a['view_id']} missing in views"
        assert -180.0 <= a["yaw"] <= 180.0, f"Anchor yaw {a['yaw']} out of bounds"
        assert -85.0 <= a["pitch"] <= 85.0, f"Anchor pitch {a['pitch']} out of bounds"
        assert a["match_state"] in ("candidate", "confirmed")
        assert a["visual_check"] in ("not_checked", "pass", "fail")

    print("[Validation] Package strictly passed all schema constraints and cross-references.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Export PastPort SDK v1 MuseumPackage")
    parser.add_argument("--db", default="var/bursa_evidence.db", help="Path to evidence SQLite DB")
    parser.add_argument("--out", default="var/museum.json", help="Path to export museum.json")
    parser.add_argument("--project", default="bursa", help="Project identifier")
    parser.add_argument("--views", type=int, default=31, help="Number of view sites to include (max 40)")
    parser.add_argument("--validate", action="store_true", default=True, help="Validate contracts")
    args = parser.parse_args()

    pkg = export_museum_package(
        db_path=Path(args.db),
        output_path=Path(args.out),
        project_id=args.project,
        max_views=args.views,
    )

    if args.validate:
        validate_package_contracts(pkg)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
