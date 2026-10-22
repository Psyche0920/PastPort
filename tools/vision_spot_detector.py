"""Vision LLM Spot Detector for 360 Panoramas (Branch B).

Takes an equirectangular panorama image and a target artifact claim text,
and predicts normalized Spot coordinates [x, y] in the range [0..10000].
Supports both live API calls (Gemini / OpenAI) and offline deterministic mock mode.
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import time
import urllib.request
import urllib.error


SYSTEM_PROMPT = """You are a spatial heritage vision grounding model. You are given an image (photograph or 360 panorama) of a historical monument or architectural site, and a description of a target physical architectural object or artifact.
Your task:
1. Determine if the target object is clearly visible in this specific image.
2. If visible, locate the center of the object and output normalized coordinates [x, y] in the range [0, 10000]:
   - x: 0 is left edge, 5000 is horizontal center, 10000 is right edge.
   - y: 0 is top edge (ceiling / upper structure), 5000 is eye-level center, 10000 is bottom edge (floor / ground).
3. If not visible (e.g. photo shows the exterior while the object is an interior mihrab), set "visible": false.

Output ONLY a JSON object with this exact schema:
{"visible": <bool>, "x": <int 0..10000>, "y": <int 0..10000>, "confidence": <float 0.0..1.0>, "label": "<concise title>"}
"""


def load_dotenv_if_present(env_path: Path) -> None:
    """Load simple KEY=VALUE pairs from a .env file into os.environ if not already present."""
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = val


def _encode_image_b64(image_path: Path, max_dim: int = 1600) -> str:
    """Read image, auto-resize in memory if large (>2MB or >max_dim) to avoid gateway 503 errors, and base64-encode."""
    try:
        from PIL import Image
        import io
        with Image.open(image_path) as im:
            if max(im.size) > max_dim or image_path.stat().st_size > 2 * 1024 * 1024:
                im.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
                buf = io.BytesIO()
                im.save(buf, format="JPEG", quality=85)
                return base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:
        pass
    return base64.b64encode(image_path.read_bytes()).decode("ascii")


ARCHITECTURAL_SEMANTICS: dict[str, dict[str, str]] = {
    "mihrab": {
        "noun": "Prayer Niche (Mihrab)",
        "adjectives": "concave semi-circular or polygonal wall niche with pointed arch or muqarnas hood, located on the interior Qibla wall",
        "context": "INTERIOR ONLY (strictly inside the main prayer hall)",
    },
    "minbar": {
        "noun": "Pulpit (Minbar)",
        "adjectives": "steep wooden or marble ceremonial staircase pulpit with handrails and conical kiosk roof",
        "context": "INTERIOR ONLY (located to the right of the interior Mihrab)",
    },
    "minaret": {
        "noun": "Minaret Tower",
        "adjectives": "tall, slender vertical masonry/brick cylindrical or polygonal tower, with projecting balcony (şerefe) and pointed conical cap",
        "context": "EXTERIOR ONLY (attached to building exterior, rising high above roofline)",
    },
    "dome": {
        "noun": "Roof Dome / Cupola",
        "adjectives": "curved hemispherical, segmented, or polygonal masonry dome resting on squinches or drum",
        "context": "EXTERIOR ROOF or INTERIOR CEILING",
    },
    "portal": {
        "noun": "Monumental Entrance Portal (Taçkapı)",
        "adjectives": "grand entrance doorway framed by carved stone borders, stalactite muqarnas vaulting, and wooden doors",
        "context": "EXTERIOR FACADE / PORCH (main entrance of building)",
    },
    "arch": {
        "noun": "Pointed / Horseshoe Arches & Columns",
        "adjectives": "structural pointed masonry arches resting on cylindrical marble/stone columns with carved capitals",
        "context": "PORTICO / COURTYARD ARCADE or INTERIOR NAVE",
    },
    "tile": {
        "noun": "Glazed Tile Revetment (Çini)",
        "adjectives": "colorful glazed ceramic decorative wall tiles (turquoise, cobalt blue, underglaze floral/geometric motifs)",
        "context": "WALL SURFACES (interior lower walls, spandrels, or mihrab surrounds)",
    },
    "inscription": {
        "noun": "Calligraphic Foundation Plaque (Kitabe)",
        "adjectives": "rectangular carved marble or limestone inscription panel featuring relief Ottoman/Arabic calligraphy",
        "context": "MOUNTED WALL / OVER-DOOR (typically above the entrance portal or windows)",
    },
    "sanduka": {
        "noun": "Cenotaph / Sarcophagus (Sanduka)",
        "adjectives": "raised rectangular wooden or marble burial chest/casket with peaked gabled ridge, draped with cloth or calligraphic tiles",
        "context": "INTERIOR TOMB CHAMBER ONLY (inside enclosed burial room)",
    },
    "tomb": {
        "noun": "Cenotaph / Sarcophagus (Sanduka)",
        "adjectives": "raised rectangular wooden or marble burial chest/casket with peaked gabled ridge, draped with cloth or calligraphic tiles",
        "context": "INTERIOR TOMB CHAMBER ONLY (inside enclosed burial room)",
    },
    "fountain": {
        "noun": "Ablution Fountain (Şadırvan)",
        "adjectives": "polygonal or circular central water basin surrounded by stone stools and covered by a domed canopy",
        "context": "EXTERIOR COURTYARD ONLY",
    },
    "courtyard": {
        "noun": "Courtyard & Fountain (Avlu / Şadırvan)",
        "adjectives": "open-air stone-paved enclosed quadrangle or colonnaded portico with central water fountain",
        "context": "EXTERIOR COURTYARD ONLY",
    },
    "window": {
        "noun": "Stained Glass / Plaster Grille Window",
        "adjectives": "arched window opening with decorative stone/plaster tracery, iron safety grilles, or colored glass",
        "context": "FACADE WALL or CLERESTORY",
    },
}


def _format_candidate_semantics(c: dict[str, str]) -> str:
    """Format candidate with physical noun, visual adjectives, and interior/exterior context."""
    text = f"{c['name']} {c.get('description', '')}".lower()
    matched_sem = None
    for key, sem in ARCHITECTURAL_SEMANTICS.items():
        if key in text:
            matched_sem = sem
            break
    if matched_sem:
        return (
            f"- [{c['object_id']}] {c['name']}:\n"
            f"  * Physical Noun: {matched_sem['noun']}\n"
            f"  * Visual Adjectives: {matched_sem['adjectives']}\n"
            f"  * Spatial Constraint: {matched_sem['context']}"
        )
    return f"- [{c['object_id']}] {c['name']} ({c.get('description', '')})"


class VisionSpotDetector:
    def __init__(self, mode: str = "auto") -> None:
        """Mode can be 'auto', 'gemini', 'openai', or 'mock'."""
        self.mode = mode
        repo_root = Path(__file__).resolve().parents[1]
        load_dotenv_if_present(repo_root / ".env")

        self.gemini_key = os.environ.get("GEMINI_API_KEY", "")
        self.openai_key = os.environ.get("OPENAI_API_KEY", "")

        self._last_call_time = 0.0
        self._min_interval = 4.2  # Gemini free tier limit is 15 RPM (4.0s/req); 4.2s guarantees safety

    def _rate_limit_wait(self) -> None:
        """Enforce inter-request delay to stay strictly under Gemini's 15 RPM ceiling."""
        elapsed = time.time() - self._last_call_time
        if elapsed < self._min_interval:
            wait_time = self._min_interval - elapsed
            time.sleep(wait_time)
        self._last_call_time = time.time()

    def detect(self, image_path: Path, claim_text: str) -> dict[str, object]:
        start = time.perf_counter()

        # Decide backend
        selected_mode = self.mode
        if selected_mode == "auto":
            if self.gemini_key:
                selected_mode = "gemini"
            elif self.openai_key:
                selected_mode = "openai"
            else:
                selected_mode = "mock"

        if selected_mode == "gemini":
            result = self._call_gemini(image_path, claim_text)
        elif selected_mode == "openai":
            result = self._call_openai(image_path, claim_text)
        else:
            result = self._call_mock(image_path, claim_text)

        elapsed_ms = (time.perf_counter() - start) * 1000.0
        result["latency_ms"] = round(elapsed_ms, 1)
        result["backend"] = selected_mode
        return result

    def detect_multi(self, image_path: Path, candidates: list[dict[str, str]]) -> list[dict[str, object]]:
        """Ground multiple architectural candidates on a single image in one unified API request."""
        start = time.perf_counter()
        selected_mode = self.mode
        if selected_mode == "auto":
            if self.gemini_key:
                selected_mode = "gemini"
            elif self.openai_key:
                selected_mode = "openai"
            else:
                selected_mode = "mock"

        if not candidates:
            return []

        if selected_mode == "gemini":
            results = self._call_gemini_multi(image_path, candidates)
        elif selected_mode == "openai":
            results = self._call_openai_multi(image_path, candidates)
        else:
            results = self._call_mock_multi(image_path, candidates)

        elapsed_ms = (time.perf_counter() - start) * 1000.0
        for r in results:
            r["latency_ms"] = round(elapsed_ms, 1)
            r["backend"] = selected_mode
        return results

    def _call_gemini_multi(self, image_path: Path, candidates: list[dict[str, str]]) -> list[dict[str, object]]:
        """Send 1 single image and candidate list to Gemini."""
        b64_img = _encode_image_b64(image_path)

        cand_text = "\n\n".join(_format_candidate_semantics(c) for c in candidates)
        prompt = (
            "You are an expert architectural historian and spatial visual grounding model.\n"
            "Analyze this heritage photograph.\n\n"
            "STEP 1: DETERMINE CAMERA PERSPECTIVE\n"
            "Identify if this photo is EXTERIOR (aerial drone, facade, street, garden) or INTERIOR (inside prayer hall, room, tomb chamber).\n\n"
            "STEP 2: ENFORCE SPATIAL EXCLUSIVITY & NOUN/ADJECTIVE ACCURACY\n"
            "- If the photo is EXTERIOR: Interior-only features (e.g. Mihrab prayer niche, interior sarcophagus/sanduka, minbar) are BEHIND SOLID WALLS and completely INVISIBLE. You MUST OMIT THEM!\n"
            "- If the photo is INTERIOR: Exterior-only features (e.g. minaret tower, aerial roof dome, outdoor courtyard fountain) are INVISIBLE. You MUST OMIT THEM!\n"
            "- A unique heritage object (like a single Mihrab, Minbar, or Inscription Plaque) exists in only ONE place. Do NOT tag it on multiple arbitrary walls.\n"
            "- Verify both the Physical Noun and the Visual Adjectives for each candidate. Only return an object if its exact physical features are genuinely identifiable in this specific photo.\n\n"
            f"Candidate Objects:\n{cand_text}\n\n"
            "Output ONLY a JSON array containing ONLY genuinely visible objects:\n"
            "[\n"
            '  {"object_id": "<exact object_id>", "name": "<name>", "x": <int 0..10000>, "y": <int 0..10000>, "confidence": <float 0..1>, "description": "<exact visual features seen>"}\n'
            "]\n"
            "If none of these specific objects are visible in this specific photo, return []."
        )

        models_to_try = [
            "gemini-2.5-flash",
            "gemini-flash-lite-latest",
            "gemini-3.5-flash",
            "gemini-flash-latest",
        ]
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {"inline_data": {"mime_type": "image/jpeg", "data": b64_img}}
                    ]
                }
            ],
            "generationConfig": {"response_mime_type": "application/json"}
        }

        for model_name in models_to_try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={self.gemini_key}"
            for attempt in range(1, 3):
                self._rate_limit_wait()
                req = urllib.request.Request(
                    url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                try:
                    with urllib.request.urlopen(req, timeout=45) as resp:
                        data = json.loads(resp.read().decode("utf-8"))
                        text = data["candidates"][0]["content"]["parts"][0]["text"]
                        parsed = json.loads(text)
                        if isinstance(parsed, list):
                            # Ensure matching candidate names/ids
                            valid_ids = {c["object_id"]: c for c in candidates}
                            valid_names = {c["name"].lower(): c for c in candidates}
                            cleaned = []
                            for item in parsed:
                                oid = item.get("object_id")
                                matched = valid_ids.get(oid) if oid else None
                                if not matched:
                                    item_name = str(item.get("name", "")).lower()
                                    matched = valid_names.get(item_name)
                                    if not matched:
                                        for cand_name, c in valid_names.items():
                                            if cand_name in item_name or item_name in cand_name:
                                                matched = c
                                                break
                                if matched:
                                    cleaned.append({
                                        "object_id": matched["object_id"],
                                        "name": matched["name"],
                                        "claim_id": matched.get("claim_id"),
                                        "category": matched.get("category", "Architecture"),
                                        "x": int(item.get("x", 5000)),
                                        "y": int(item.get("y", 5000)),
                                        "confidence": float(item.get("confidence", 0.9)),
                                        "description": str(item.get("description", matched.get("description", ""))),
                                        "cost_usd": 0.0004,
                                    })
                            return cleaned
                        return []
                except urllib.error.HTTPError as error:
                    if error.code == 429:
                        print(f"  [Quota 429 on {model_name}] Trying alternative model in pool...")
                        break
                    if error.code in (500, 502, 503, 504):
                        if attempt < 2:
                            print(f"  [HTTP {error.code}] Transient error on {model_name}. Retrying in 5s...")
                            time.sleep(5.0)
                            continue
                except Exception as error:
                    print(f"Gemini {model_name} call failed: {error}")
                    break

        if self.openai_key:
            print("All Gemini models exhausted; attempting OpenAI fallback...")
            return self._call_openai_multi(image_path, candidates)

        print("All vision LLM endpoints exhausted; falling back to mock.")
        return self._call_mock_multi(image_path, candidates)

    def _call_openai_multi(self, image_path: Path, candidates: list[dict[str, str]]) -> list[dict[str, object]]:
        """Send 1 single image and candidate list to OpenAI."""
        b64_img = _encode_image_b64(image_path)

        cand_text = "\n".join(f"- {c['object_id']}: {c['name']} ({c.get('description', '')})" for c in candidates)
        prompt = (
            "You are an expert spatial architectural vision grounding model.\n"
            "Analyze this heritage photograph and locate any of the following physical architectural objects if clearly visible:\n\n"
            f"Candidate Objects:\n{cand_text}\n\n"
            "Output ONLY a JSON array containing ONLY the objects that are actually VISIBLE in this image:\n"
            "[\n"
            '  {"object_id": "<exact object_id>", "name": "<name>", "x": <int 0..10000>, "y": <int 0..10000>, "confidence": <float 0..1>, "description": "<brief note>"}\n'
            "]\n"
            "If none of these specific objects are visible in this specific photo, return []."
        )

        url = "https://api.openai.com/v1/chat/completions"
        payload = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}}
                ]}
            ],
            "response_format": {"type": "json_object"}
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.openai_key}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                text = data["choices"][0]["message"]["content"]
                parsed = json.loads(text)
                items = parsed if isinstance(parsed, list) else parsed.get("objects", [])
                valid_ids = {c["object_id"]: c for c in candidates}
                cleaned = []
                for item in items:
                    oid = item.get("object_id")
                    if oid in valid_ids:
                        c = valid_ids[oid]
                        cleaned.append({
                            "object_id": c["object_id"],
                            "name": c["name"],
                            "claim_id": c.get("claim_id"),
                            "category": c.get("category", "Architecture"),
                            "x": int(item.get("x", 5000)),
                            "y": int(item.get("y", 5000)),
                            "confidence": float(item.get("confidence", 0.85)),
                            "description": str(item.get("description", "")),
                            "cost_usd": 0.0015,
                        })
                return cleaned
        except Exception as error:
            print(f"OpenAI multi-object API call failed: {error}; falling back to mock.")
            return self._call_mock_multi(image_path, candidates)

    def _call_mock_multi(self, image_path: Path, candidates: list[dict[str, str]]) -> list[dict[str, object]]:
        """Deterministic mock for offline testing."""
        time.sleep(0.05)
        # Select first 1-2 candidates
        results = []
        for c in candidates[:2]:
            results.append({
                "object_id": c["object_id"],
                "name": c["name"],
                "claim_id": c.get("claim_id"),
                "category": c.get("category", "Architecture"),
                "x": 5000,
                "y": 4500,
                "confidence": 0.85,
                "description": f"Mock detected: {c['name']}",
                "cost_usd": 0.0,
            })
        return results

    def _call_mock(self, image_path: Path, claim_text: str) -> dict[str, object]:
        """Deterministic mock for offline CI and testing."""
        time.sleep(0.08)  # simulate model inference latency
        low = claim_text.lower()
        if any(w in low for w in ["deepblue", "terminal", "computer", "prototype", "artifact"]):
            return {
                "x": 5350,
                "y": 4530,
                "confidence": 0.94,
                "label": "DeepBlue-Prototype #4 Mainframe Terminal",
                "cost_usd": 0.00,
            }
        if any(w in low for w in ["chess", "blitz", "tournament", "grandmaster", "1996"]):
            return {
                "x": 6800,
                "y": 4700,
                "confidence": 0.88,
                "label": "Grandmaster AI Chess Blitz Match Station",
                "cost_usd": 0.00,
            }
        if any(w in low for w in ["architect", "vance", "systems", "constructed", "designed"]):
            return {
                "x": 2200,
                "y": 5200,
                "confidence": 0.85,
                "label": "Dedication Plaque (Dr. Elena Vance)",
                "cost_usd": 0.00,
            }
        if any(w in low for w in ["style", "industrial", "high-tech", "1987", "built"]):
            return {
                "x": 5000,
                "y": 7200,
                "confidence": 0.91,
                "label": "High-Tech Industrial Architectural Structure",
                "cost_usd": 0.00,
            }

        # Deterministic coordinate generation based on content hash for generic heritage claims
        import hashlib
        h = int(hashlib.md5(claim_text.encode("utf-8")).hexdigest()[:8], 16)
        x = 1500 + (h % 7000)
        y = 3500 + ((h >> 4) % 3000)
        return {
            "x": x,
            "y": y,
            "confidence": 0.80,
            "label": claim_text[:32],
            "cost_usd": 0.00,
        }

    def _call_gemini(self, image_path: Path, claim_text: str) -> dict[str, object]:
        """Call Gemini Vision API via standard HTTPS."""
        b64_img = _encode_image_b64(image_path)

        models_to_try = ["gemini-3.5-flash", "gemini-flash-lite-latest", "gemini-flash-latest"]
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": f"{SYSTEM_PROMPT}\nTarget artifact to locate: {claim_text}"},
                        {
                            "inline_data": {
                                "mime_type": "image/jpeg",
                                "data": b64_img,
                            }
                        },
                    ]
                }
            ],
            "generationConfig": {"response_mime_type": "application/json"},
        }

        for model_name in models_to_try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={self.gemini_key}"
            for attempt in range(1, 3):
                self._rate_limit_wait()
                req = urllib.request.Request(
                    url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                try:
                    with urllib.request.urlopen(req, timeout=45) as resp:
                        data = json.loads(resp.read().decode("utf-8"))
                        text = data["candidates"][0]["content"]["parts"][0]["text"]
                        parsed = json.loads(text)
                        return {
                            "visible": bool(parsed.get("visible", True)),
                            "x": int(parsed.get("x", 5000)),
                            "y": int(parsed.get("y", 5000)),
                            "confidence": float(parsed.get("confidence", 0.8)),
                            "label": str(parsed.get("label", "detected_object")),
                            "cost_usd": 0.0004,
                        }
                except urllib.error.HTTPError as error:
                    if error.code == 429:
                        print(f"  [Quota 429 on {model_name}] Trying alternative model in pool...")
                        break
                    if error.code in (500, 502, 503, 504):
                        if attempt < 2:
                            time.sleep(5.0)
                            continue
                except Exception as error:
                    print(f"Gemini {model_name} call failed: {error}")
                    break

        if self.openai_key:
            return self._call_openai(image_path, claim_text)

        return self._call_mock(image_path, claim_text)

    def _call_openai(self, image_path: Path, claim_text: str) -> dict[str, object]:
        """Call OpenAI Vision API via standard HTTPS."""
        b64_img = _encode_image_b64(image_path)

        url = "https://api.openai.com/v1/chat/completions"
        payload = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"Target artifact: {claim_text}"},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}},
                    ],
                },
            ],
            "response_format": {"type": "json_object"},
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.openai_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                text = data["choices"][0]["message"]["content"]
                parsed = json.loads(text)
                return {
                    "visible": bool(parsed.get("visible", True)),
                    "x": int(parsed.get("x", 5000)),
                    "y": int(parsed.get("y", 5000)),
                    "confidence": float(parsed.get("confidence", 0.8)),
                    "label": str(parsed.get("label", "detected_object")),
                    "cost_usd": 0.0015,
                }
        except Exception as error:
            print(f"OpenAI API call failed: {error}; falling back to mock.")
            return self._call_mock(image_path, claim_text)


if __name__ == "__main__":
    detector = VisionSpotDetector(mode="mock")
    pano_file = Path("var/sources/panoramas/turing_lab_room.jpg")
    claim = "Preserves the DeepBlue-Prototype #4 terminal, an experimental computing artifact."
    res = detector.detect(pano_file, claim)
    print("Detector result:", res)
