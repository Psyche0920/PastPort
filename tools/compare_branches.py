"""Compare Branch A (Hand-Click) vs Branch B (Vision LLM) on 360 Panoramas."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.branch_a_handclick import create_handclick_spot
from tools.branch_b_vision import create_vision_spot
from tools.spot_converter import spot_angular_distance


def run_comparison(
    db_path: Path,
    pano_path: Path,
    claim_id: str = "claim-turing-artifact-deepblue",
    hand_yaw: float = 12.0,
    hand_pitch: float = -8.0,
    vision_mode: str = "auto",
    threshold_degrees: float = 15.0,
) -> dict[str, object]:
    print("=" * 70)
    print("PASTPORT 360 HOTSPOT MATCHING BENCHMARK")
    print("=" * 70)
    print(f"Database:    {db_path}")
    print(f"Pano Asset:  {pano_path} ({pano_path.stat().st_size:,} bytes)")
    print(f"Claim ID:    {claim_id}")
    print("-" * 70)

    # 1. Execute Branch A (Hand-Click Ground Truth)
    res_a = create_handclick_spot(
        db_path=db_path,
        claim_id=claim_id,
        yaw=hand_yaw,
        pitch=hand_pitch,
        spot_id="spot-branch-a-manual",
    )
    spot_a = (int(res_a["x"]), int(res_a["y"]))
    time_a_ms = 4500.0  # human observation & click latency

    print("BRANCH A: Manual Hand-Click (Ground Truth in VR Studio / Viewer)")
    print(f"  Spot(x, y):  ({spot_a[0]}, {spot_a[1]})")
    print(f"  Spherical:   (yaw={res_a['spherical']['yaw']}°, pitch={res_a['spherical']['pitch']}°)")
    print(f"  Latency:     {time_a_ms:.0f} ms (human UI interaction)")
    print(f"  Cost:        $0.00")
    print("-" * 70)

    # 2. Execute Branch B (Vision LLM)
    res_b = create_vision_spot(
        db_path=db_path,
        pano_path=pano_path,
        claim_id=claim_id,
        mode=vision_mode,
        spot_id="spot-branch-b-vision",
    )
    spot_b = (int(res_b["x"]), int(res_b["y"]))

    print(f"BRANCH B: Vision LLM Auto-Detector ({res_b['vision_backend']})")
    print(f"  Spot(x, y):  ({spot_b[0]}, {spot_b[1]})")
    print(f"  Spherical:   (yaw={res_b['spherical']['yaw']}°, pitch={res_b['spherical']['pitch']}°)")
    print(f"  Confidence:  {res_b['confidence']}")
    print(f"  Latency:     {res_b['latency_ms']} ms")
    print(f"  Cost:        ${res_b['cost_usd']:.4f}")
    print("-" * 70)

    # 3. Calculate Angular Error on Sphere
    angular_error = spot_angular_distance(spot_a, spot_b)
    passed = angular_error <= threshold_degrees

    print("COMPARISON & VERIFICATION RESULTS")
    print(f"  Great-Circle Angular Error: {angular_error:.2f}° (Threshold <= {threshold_degrees}°)")
    print(f"  Evaluation Verdict:         {'PASSED' if passed else 'FAILED'}")
    speedup = time_a_ms / max(1.0, float(res_b['latency_ms']))
    print(f"  Execution Speed:            Branch B is {speedup:.1f}x faster than human authoring")
    print("=" * 70)

    return {
        "branch_a": res_a,
        "branch_b": res_b,
        "angular_error_degrees": round(angular_error, 2),
        "passed": passed,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare Branch A vs Branch B")
    parser.add_argument("--db", default="var/test_evidence.db")
    parser.add_argument("--pano", default="var/sources/panoramas/turing_lab_room.jpg")
    parser.add_argument("--claim", default="claim-turing-artifact-deepblue")
    parser.add_argument("--yaw", type=float, default=12.0)
    parser.add_argument("--pitch", type=float, default=-8.0)
    parser.add_argument("--vision-mode", default="auto", choices=["auto", "gemini", "openai", "mock"])
    parser.add_argument("--threshold", type=float, default=15.0)
    args = parser.parse_args()

    results = run_comparison(
        db_path=Path(args.db),
        pano_path=Path(args.pano),
        claim_id=args.claim,
        hand_yaw=args.yaw,
        hand_pitch=args.pitch,
        vision_mode=args.vision_mode,
        threshold_degrees=args.threshold,
    )


if __name__ == "__main__":
    main()
