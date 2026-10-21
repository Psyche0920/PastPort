"""Branch A: Manual Hand-Click Hotspot Authoring Tool.

Allows human operators to define interactive Spot coordinates from VR Studio / 360 viewer
angles (yaw, pitch) or normalized (x, y), linking them directly to SQLite claims.
Zero external AI or cloud API dependencies.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.spot_converter import SphericalCoordinate


def create_handclick_spot(
    db_path: Path,
    claim_id: str,
    yaw: float | None = None,
    pitch: float | None = None,
    x: int | None = None,
    y: int | None = None,
    spot_id: str | None = None,
) -> dict[str, object]:
    """Resolve coordinates, verify against SQLite claim, and return Spot contract."""
    # 1. Resolve coordinates
    if yaw is not None and pitch is not None:
        coord = SphericalCoordinate(yaw=yaw, pitch=pitch)
        spot_x, spot_y = coord.to_spot()
    elif x is not None and y is not None:
        spot_x, spot_y = max(0, min(10000, x)), max(0, min(10000, y))
        coord = SphericalCoordinate.from_spot(spot_x, spot_y)
    else:
        raise ValueError("Must provide either (yaw, pitch) or (x, y)")

    # 2. Verify against SQLite claim
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT claim_id, site_id, text, content_kind FROM claims WHERE claim_id = ?",
        (claim_id,),
    ).fetchone()
    conn.close()

    if not row:
        raise ValueError(f"Claim '{claim_id}' not found in database {db_path}")

    cid, site_id, claim_text, kind = row
    resolved_spot_id = spot_id or f"spot-manual-{claim_id}"

    # 3. Assemble Spot Contract
    contract = {
        "spot_id": resolved_spot_id,
        "site_id": site_id,
        "x": spot_x,
        "y": spot_y,
        "spherical": {"yaw": coord.yaw, "pitch": coord.pitch},
        "text_key": f"{resolved_spot_id}_desc",
        "claim_ids": [cid],
        "authoring_method": "manual_handclick",
    }
    return contract


def main() -> None:
    parser = argparse.ArgumentParser(description="Branch A: Manual Hotspot Authoring")
    parser.add_argument("--db", default="var/test_evidence.db", help="Path to SQLite evidence database")
    parser.add_argument("--claim", default="claim-turing-artifact-deepblue", help="Target claim ID")
    parser.add_argument("--yaw", type=float, default=12.0, help="Viewer yaw in degrees (-180 to 180)")
    parser.add_argument("--pitch", type=float, default=-8.0, help="Viewer pitch in degrees (-90 to 90)")
    parser.add_argument("--x", type=int, default=None, help="Direct spot x (0..10000)")
    parser.add_argument("--y", type=int, default=None, help="Direct spot y (0..10000)")
    args = parser.parse_args()

    result = create_handclick_spot(
        db_path=Path(args.db),
        claim_id=args.claim,
        yaw=args.yaw,
        pitch=args.pitch,
        x=args.x,
        y=args.y,
    )
    print("=" * 60)
    print("BRANCH A: MANUAL HAND-CLICK SPOT RESULT")
    print("=" * 60)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
