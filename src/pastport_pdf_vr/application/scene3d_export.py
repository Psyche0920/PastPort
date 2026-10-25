"""Portable scene assets and source-bound game data from one consistent review snapshot."""

from __future__ import annotations

import json
import sqlite3
import zipfile
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from pastport_pdf_vr.application.reference_environment import digest, read_json, record
from pastport_pdf_vr.domain.scene3d import SceneRenderVariant


def export_scene(root: Path, archive: Path) -> None:
    """Export current edits without rebuilding or mutating their database."""
    attachment = record(read_json(root / "scene3d/attachment.json"))
    scene = record(attachment["scene"])
    render_name = "scene.spz"
    render_hash = scene["splat_sha256"]
    tier = "registered"
    variant_path = root / "scene3d/render-variant.json"
    if variant_path.is_file():
        variant = SceneRenderVariant.model_validate_json(variant_path.read_bytes())
        if variant.scene_binding != attachment["binding"] or variant.world_id != scene["scene_id"]:
            raise ValueError("Render variant belongs to a different scene")
        render_name, render_hash, tier = variant.splat, variant.splat_sha256, variant.tier
    if digest(root / "scene3d" / render_name) != render_hash:
        raise ValueError("Render asset bytes changed")
    with TemporaryDirectory(prefix="pastport-3d-export-") as temporary:
        snapshot = Path(temporary) / "review.sqlite3"
        with closing(
            sqlite3.connect(f"{(root / 'pastport_matching.sqlite3').as_uri()}?mode=ro", uri=True)
        ) as source:
            with closing(sqlite3.connect(snapshot)) as destination:
                source.backup(destination)
        with closing(sqlite3.connect(snapshot)) as db:
            db.row_factory = sqlite3.Row
            objects = [
                dict(row)
                for row in db.execute("""
                SELECT o.id,o.stable_id,o.name,o.parent_id,p.historical_id,
                p.proposal_state,p.image_review,p.text_review,p.version AS pairing_version,
                COALESCE(v.human_override,v.ai_draft) AS introduction,
                v.version AS introduction_version,h.title_en AS historical_title,
                h.media_path AS historical_image,h.image_page AS historical_image_page,
                psg.exact_text,psg.pdf_page AS text_page,t.translation_zh,t.limitation,
                a.point_json,a.version AS anchor_version,a.identity_basis,a.relation_basis
                FROM modern_objects o JOIN pairings p ON p.modern_id=o.id
                LEFT JOIN historical_objects h ON h.id=p.historical_id
                LEFT JOIN text_associations t ON t.historical_id=h.id
                LEFT JOIN passages psg ON psg.id=t.passage_id
                LEFT JOIN vr_display_contents v ON v.object_id=o.id
                    AND v.historical_id IS p.historical_id
                LEFT JOIN scene3d_anchors a ON a.object_id=o.id
                    AND a.historical_id IS p.historical_id
            """)
            ]
            photos = [
                dict(row)
                for row in db.execute("SELECT id,media_path,width,height,sha256 FROM photos")
            ]
            observations = [
                dict(row)
                for row in db.execute(
                    "SELECT photo_id,object_id,x0,y0,x1,y1,identity_state,identity_basis "
                    "FROM observations"
                )
            ]
            alignment = json.loads(
                db.execute("SELECT payload_json FROM scene3d_alignment WHERE id=1").fetchone()[0]
            )

            candidates = {}
            candidate_method = None
            if db.execute("SELECT 1 FROM sqlite_master WHERE name='scene3d_candidates'").fetchone():
                alignment_version = db.execute(
                    "SELECT version FROM scene3d_alignment WHERE id=1"
                ).fetchone()[0]
                candidates = {
                    row[0]: json.loads(row[1]) if row[1] else None
                    for row in db.execute(
                        "SELECT object_id,point_json FROM scene3d_candidates "
                        "WHERE binding=? AND alignment_version=?",
                        (attachment["binding"], alignment_version),
                    )
                }
                method = db.execute(
                    "SELECT payload_json FROM scene3d_candidate_batches "
                    "WHERE binding=? AND alignment_version=?",
                    (attachment["binding"], alignment_version),
                ).fetchone()
                candidate_method = json.loads(method[0]) if method else None

        def eligible(row: dict[str, object]) -> bool:
            return bool(
                row["historical_id"]
                and row["proposal_state"] != "invalid_structural_relation"
                and row["image_review"] != "unsuitable"
                and row["text_review"] != "unsuitable"
            )

        by_id = {row["id"]: row for row in objects}
        for row in objects:
            point = row.pop("point_json")
            parent = by_id.get(row["parent_id"])
            visible = eligible(row) and bool(alignment["confirmed"])
            if parent is not None:
                visible = (
                    visible
                    and eligible(parent)
                    and bool(parent.get("point_json") or parent.get("anchor"))
                )
            row["anchor"] = json.loads(point) if point and visible else None
            row["candidate_anchor"] = (
                candidates.get(row["id"])
                if eligible(row)
                and row["anchor_version"] == 0
                and (parent is None or parent.get("anchor") or parent.get("point_json"))
                else None
            )
            row["candidate_state"] = "ray_projection_unverified"
            row["anchor_state"] = "human_confirmed" if row["anchor"] else "withheld_or_unconfirmed"
        data = {
            "schema_version": "pastport.scene3d/1.0",
            "scene_binding": attachment["binding"],
            "coordinate_frame": "three_metric_y_up",
            "units": "metres",
            "objects": objects,
            "photos": photos,
            "observations": observations,
            "alignment": alignment,
            "candidate_method": candidate_method,
            "source_viewpoint": attachment["source_scene_id"],
            "source_pdf": "source.pdf",
            "matched_pdf": "mapping-demo.pdf",
        }
        manifest = {
            "schema_version": "pastport.scene3d/1.0",
            "scene_binding": attachment["binding"],
            "units": "metres",
            "coordinate_frame": "right_handed_threejs_y_up",
            "render_asset": {
                "path": "scene/" + render_name,
                "quality_tier": tier,
                "kind": "gaussian_splat_spz",
                "sha256": render_hash,
                "requires_splat_renderer": True,
            },
            "collision_asset": {
                "path": "scene/collider.glb",
                "kind": "glTF_2_binary_collision_only",
                "sha256": scene["collider_sha256"],
                "full_visual_mesh": False,
            },
            "asset_to_world": {
                "uniform_scale": scene["metric_scale_factor"],
                "rotation_quaternion_xyzw": [1, 0, 0, 0],
                "translation_xyz": [0, scene["ground_plane_offset"], 0],
            },
            "game_data": "game-data.json",
            "audit_database": "review.sqlite3",
            "rights_and_acceptance": "source rights retained; manual acceptance pending",
            "note": "Generated appearance is not historical evidence. No paid HQ mesh export.",
        }
        paths = [
            root / "scene3d" / render_name,
            root / "scene3d/collider.glb",
            root / "scene3d/panorama.jpg",
            root / "source.pdf",
            root / "mapping-demo.pdf",
        ]
        media = root / "media"
        paths.extend(path for path in media.rglob("*") if path.is_file())
        if (
            any(path.is_symlink() for path in paths)
            or sum(path.stat().st_size for path in paths) > 1024**3
        ):
            raise ValueError("Export assets are unsafe or exceed 1 GiB")
        with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_STORED) as bundle:
            bundle.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
            bundle.writestr("game-data.json", json.dumps(data, ensure_ascii=False, indent=2))
            bundle.write(snapshot, "review.sqlite3")
            for path in paths:
                relative = path.relative_to(root)
                name = (
                    "scene/" + path.name if relative.parts[0] == "scene3d" else relative.as_posix()
                )
                bundle.write(path, name)
            bundle.writestr(
                "README.txt",
                "PastPort portable scene package v1\n"
                "Read manifest.json and game-data.json. Keep object IDs and source evidence.\n"
                "GLB is collision geometry, not a complete textured visual model.\n"
                "SPZ needs a splat renderer.\n"
                "Apply asset_to_world before using metric anchors.\n"
                "Unity/Blender need their own axis adapter.\n"
                "Use original PDFs/photos for evidence.\n"
                "Generated geometry does not establish history.\n",
            )
