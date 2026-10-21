"""Branch B: Vision LLM Automated Spot Detection Tool.

Uses multimodal vision models (Gemini / OpenAI / offline mock) to analyze a 360 panorama,
locate the target artifact described in a SQLite claim, and generate a PastPort Spot.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.spot_converter import SphericalCoordinate
from tools.vision_spot_detector import VisionSpotDetector


def create_vision_spot(
    db_path: Path,
    pano_path: Path,
    claim_id: str,
    mode: str = "auto",
    spot_id: str | None = None,
) -> dict[str, object]:
    """Query claim, run Vision LLM detector on panorama, and produce Spot contract."""
    # 1. Fetch claim from SQLite
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT claim_id, site_id, text, content_kind FROM claims WHERE claim_id = ?",
        (claim_id,),
    ).fetchone()
    conn.close()

    if not row:
        raise ValueError(f"Claim '{claim_id}' not found in database {db_path}")

    cid, site_id, claim_text, kind = row

    # 2. Run Vision LLM Detector
    detector = VisionSpotDetector(mode=mode)
    detect_res = detector.detect(pano_path, claim_text)
    spot_x = int(detect_res["x"])
    spot_y = int(detect_res["y"])
    coord = SphericalCoordinate.from_spot(spot_x, spot_y)

    resolved_spot_id = spot_id or f"spot-vision-{claim_id}"

    # 3. Assemble Spot Contract
    contract = {
        "spot_id": resolved_spot_id,
        "site_id": site_id,
        "x": spot_x,
        "y": spot_y,
        "spherical": {"yaw": coord.yaw, "pitch": coord.pitch},
        "text_key": f"{resolved_spot_id}_desc",
        "claim_ids": [cid],
        "authoring_method": "vision_llm",
        "vision_backend": detect_res.get("backend", mode),
        "confidence": detect_res.get("confidence", 0.0),
        "latency_ms": detect_res.get("latency_ms", 0.0),
        "cost_usd": detect_res.get("cost_usd", 0.0),
    }
    return contract


def main() -> None:
    parser = argparse.ArgumentParser(description="Branch B: Vision LLM Spot Detection")
    parser.add_argument("--db", default="var/test_evidence.db", help="Path to SQLite evidence database")
    parser.add_argument("--pano", default="var/sources/panoramas/turing_lab_room.jpg", help="Path to 360 panorama JPG")
    parser.add_argument("--claim", default="claim-turing-artifact-deepblue", help="Target claim ID")
    parser.add_argument("--mode", default="auto", choices=["auto", "gemini", "openai", "mock"], help="Detector backend")
    args = parser.parse_args()

    result = create_vision_spot(
        db_path=Path(args.db),
        pano_path=Path(args.pano),
        claim_id=args.claim,
        mode=args.mode,
    )
    print("=" * 60)
    print("BRANCH B: VISION LLM SPOT DETECTION RESULT")
    print("=" * 60)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
