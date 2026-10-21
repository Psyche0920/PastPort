"""Extract equirectangular panorama JPG from VR Studio exported tour zip."""
from __future__ import annotations

import base64
import json
from pathlib import Path
import re
import zipfile


def extract_panorama(zip_path: Path, output_file: Path) -> Path:
    with zipfile.ZipFile(zip_path) as z:
        html = z.read("index.html").decode("utf-8", errors="ignore")

    match = re.search(r'<script id="tour-data" type="application/json">(.*?)</script>', html, re.DOTALL)
    if not match:
        raise ValueError("Could not find <script id='tour-data'> inside tour index.html")

    data = json.loads(match.group(1))
    scenes = data.get("scenes", [])
    if not scenes:
        raise ValueError("No scenes found in tour-data")

    scene = scenes[0]
    pano_obj = scene.get("panorama", {})
    if isinstance(pano_obj, dict):
        pano_uri = pano_obj.get("data") or pano_obj.get("panorama", "")
        width = pano_obj.get("width", scene.get("width"))
        height = pano_obj.get("height", scene.get("height"))
    else:
        pano_uri = str(pano_obj)
        width = scene.get("width")
        height = scene.get("height")

    if not pano_uri.startswith("data:image/jpeg;base64,"):
        raise ValueError(f"Unexpected panorama format: {type(pano_obj)} {str(pano_uri)[:50]}")

    header, b64_data = pano_uri.split(",", 1)
    raw_bytes = base64.b64decode(b64_data)

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_bytes(raw_bytes)
    print(f"Extracted panorama to {output_file} ({len(raw_bytes):,} bytes, dimensions: {width}x{height})")
    return output_file


if __name__ == "__main__":
    src_zip = Path("../PastPort-VR-Studio/output/pastport-tour.zip")
    dst_img = Path("var/sources/panoramas/turing_lab_room.jpg")
    extract_panorama(src_zip, dst_img)
