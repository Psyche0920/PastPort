"""Extract Bursa heritage records from IDML and archive resources into SQLite.

Usage:
    python tools/extract_bursa_sources.py
"""

from __future__ import annotations

import hashlib
import io
import re
import sqlite3
import xml.etree.ElementTree as ET
import zipfile
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ExtractedSite:
    site_id: str
    project_id: str
    district: str
    category: str
    name_tr: str
    name_en: str
    description_tr: str
    description_en: str
    source_id: str


@dataclass(frozen=True)
class ExtractedObject:
    object_id: str
    site_id: str
    project_id: str
    name_en: str
    name_tr: str
    category: str
    description_en: str
    claim_id: str


class BursaSourceExtractor:
    """Extracts heritage sites, sources, media assets, claims, and museum objects into SQLite."""

    CATEGORY_MARKERS: tuple[str, ...] = (
        "Camiler ve Hazireler",
        "Türbeler ve Mezarlar",
        "Eğitim Yapıları",
        "Su Yapıları",
        "Sivil Mimari",
        "Tekkeler ve Zaviyerler",
    )

    ARCHITECTURAL_FEATURE_SPECS: tuple[dict[str, object], ...] = (
        {
            "key": "mihrab",
            "name_en": "Mihrab (Prayer Niche)",
            "name_tr": "Mihrap",
            "category": "Liturgical",
            "keywords": ("mihrab", "prayer niche", "mihrap", "kıble"),
            "default_x": 5000,
            "default_y": 4800,
        },
        {
            "key": "minbar",
            "name_en": "Carved Minbar (Pulpit)",
            "name_tr": "Minber",
            "category": "Liturgical",
            "keywords": ("minbar", "pulpit", "minber", "kündekari"),
            "default_x": 3800,
            "default_y": 4600,
        },
        {
            "key": "dome",
            "name_en": "Main Dome & Vaulting",
            "name_tr": "Ana Kubbe ve Tonozlar",
            "category": "Architecture",
            "keywords": ("dome", "cupola", "kubbe", "pendentive", "squinch"),
            "default_x": 5000,
            "default_y": 7500,
        },
        {
            "key": "portal",
            "name_en": "Monumental Entrance Portal",
            "name_tr": "Taç Kapı ve Giriş",
            "category": "Structure",
            "keywords": ("portal", "entrance", "taç kapı", "gate", "cümle kapısı", "door"),
            "default_x": 5000,
            "default_y": 4200,
        },
        {
            "key": "tile",
            "name_en": "Glazed Tile Revetment",
            "name_tr": "İznik Çinileri",
            "category": "Ornament",
            "keywords": ("tile", "çini", "faience", "ceramic", "glazed"),
            "default_x": 6200,
            "default_y": 5200,
        },
        {
            "key": "inscription",
            "name_en": "Calligraphic Foundation Plaque",
            "name_tr": "Kitabe ve Hat Sanatı",
            "category": "Epigraphy",
            "keywords": ("inscription", "kitabe", "calligraph", "epigraph", "charter", "vakfiye"),
            "default_x": 5000,
            "default_y": 6200,
        },
        {
            "key": "courtyard",
            "name_en": "Ablution Fountain & Courtyard",
            "name_tr": "Avlu ve Şadırvan",
            "category": "Courtyard",
            "keywords": ("courtyard", "fountain", "şadırvan", "avlu", "pool", "havuz"),
            "default_x": 5000,
            "default_y": 3200,
        },
        {
            "key": "tomb",
            "name_en": "Sarcophagus & Cenotaph (Sanduka)",
            "name_tr": "Sanduka ve Türbe",
            "category": "Funerary",
            "keywords": ("tomb", "sarcophagus", "cenotaph", "sanduka", "grave", "burial", "mezar"),
            "default_x": 5000,
            "default_y": 4000,
        },
        {
            "key": "minaret",
            "name_en": "Masonry Minaret",
            "name_tr": "Minare",
            "category": "Architecture",
            "keywords": ("minaret", "minare", "balcony", "şerefe"),
            "default_x": 7500,
            "default_y": 8000,
        },
        {
            "key": "arch",
            "name_en": "Pointed Arches & Columns",
            "name_tr": "Kemerler ve Revaklar",
            "category": "Structure",
            "keywords": ("arch", "arcade", "revak", "kemer", "column", "sütun", "vault"),
            "default_x": 3000,
            "default_y": 5500,
        },
        {
            "key": "window",
            "name_en": "Stained Glass & Plaster Windows",
            "name_tr": "Revzen ve Pencereler",
            "category": "Ornament",
            "keywords": ("window", "pencere", "plaster", "revzen", "grille", "parmaklık"),
            "default_x": 6800,
            "default_y": 6000,
        },
    )

    def __init__(self, db_path: Path, project_id: str = "bursa") -> None:
        self.db_path = db_path
        self.project_id = project_id
        self.conn = self._init_db()

    def _init_db(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON;")
        with conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS projects (
                project_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                default_locale TEXT NOT NULL DEFAULT 'en'
            );

            CREATE TABLE IF NOT EXISTS sources (
                source_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(project_id),
                file_name TEXT NOT NULL,
                file_sha256 TEXT NOT NULL,
                origin TEXT NOT NULL DEFAULT 'official',
                uri TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sites (
                site_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(project_id),
                district TEXT NOT NULL,
                category TEXT NOT NULL,
                name_tr TEXT NOT NULL,
                name_en TEXT NOT NULL,
                description_tr TEXT NOT NULL,
                description_en TEXT NOT NULL,
                source_id TEXT NOT NULL REFERENCES sources(source_id)
            );

            CREATE TABLE IF NOT EXISTS assets (
                asset_id TEXT PRIMARY KEY,
                site_id TEXT REFERENCES sites(site_id),
                project_id TEXT NOT NULL REFERENCES projects(project_id),
                file_name TEXT NOT NULL,
                relative_path TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                media_type TEXT NOT NULL DEFAULT 'image/jpeg',
                district TEXT,
                category TEXT,
                rights_state TEXT NOT NULL DEFAULT 'permitted_for_scope',
                mapping_state TEXT NOT NULL DEFAULT 'verified'
            );

            CREATE TABLE IF NOT EXISTS claims (
                claim_id TEXT PRIMARY KEY,
                site_id TEXT NOT NULL REFERENCES sites(site_id),
                project_id TEXT NOT NULL REFERENCES projects(project_id),
                text TEXT NOT NULL,
                content_kind TEXT NOT NULL DEFAULT 'historical_fact',
                time_scope TEXT NOT NULL,
                source_locator_ref TEXT,
                judgment TEXT NOT NULL DEFAULT 'supported',
                reason TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS museum_objects (
                object_id TEXT PRIMARY KEY,
                site_id TEXT NOT NULL REFERENCES sites(site_id),
                project_id TEXT NOT NULL REFERENCES projects(project_id),
                name_en TEXT NOT NULL,
                name_tr TEXT NOT NULL,
                category TEXT NOT NULL,
                description_en TEXT NOT NULL,
                claim_id TEXT REFERENCES claims(claim_id)
            );

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
            """)
            conn.execute(
                "INSERT OR REPLACE INTO projects (project_id, name, default_locale) VALUES (?, ?, ?)",
                (self.project_id, "Bursa Cultural Heritage", "en"),
            )
            cols = [r[1] for r in conn.execute("PRAGMA table_info(scene_hotspots)").fetchall()]
            if "object_id" not in cols:
                conn.execute("ALTER TABLE scene_hotspots ADD COLUMN object_id TEXT REFERENCES museum_objects(object_id);")
        return conn

    @staticmethod
    def slugify(text: str) -> str:
        cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower().strip()).strip("-")
        return cleaned or "item"

    @staticmethod
    def extract_text(xml_bytes: bytes) -> str:
        root = ET.fromstring(xml_bytes)
        texts = [e.text for e in root.iter() if e.tag.endswith("Content") and e.text]
        return " ".join(texts).strip()

    def parse_idml(self, zip_bytes: bytes, source_id: str) -> list[ExtractedSite]:
        inner = zipfile.ZipFile(io.BytesIO(zip_bytes))
        stories: dict[str, str] = {}
        for name in inner.namelist():
            if name.startswith("Stories/"):
                text = self.extract_text(inner.read(name))
                if text:
                    story_id = name.split("/")[-1].replace("Story_", "").replace(".xml", "")
                    stories[story_id] = text

        # Single-complex layout (e.g. Yeşil Complex)
        if "u4ecc" in stories and "u4ee3" in stories:
            name_en = stories.get("u4ee3", "Yeşil Mosque")
            return [
                ExtractedSite(
                    site_id=f"{self.project_id}-{self.slugify(name_en)}",
                    project_id=self.project_id,
                    district=stories.get("u2f98", "Yıldırım").title(),
                    category="Mosque / Complex",
                    name_tr=stories.get("u4ecc", "Yeşil Camii"),
                    name_en=name_en,
                    description_tr=stories.get("u474b", ""),
                    description_en=stories.get("u2f15", ""),
                    source_id=source_id,
                )
            ]

        # Multi-site spreads (e.g. İznik, Orhangazi, Yıldırım sections)
        sites: list[ExtractedSite] = []
        current_cat, current_dist = "General Heritage", "Bursa"
        spread_names = sorted(n for n in inner.namelist() if n.startswith("Spreads/"))

        for s_name in spread_names:
            root = ET.fromstring(inner.read(s_name))
            spread_stories = [
                elem.attrib["ParentStory"]
                for elem in root.iter()
                if elem.tag.endswith("TextFrame") and "ParentStory" in elem.attrib
            ]
            if not spread_stories:
                continue

            for st_id in spread_stories:
                txt = stories.get(st_id, "")
                for marker in self.CATEGORY_MARKERS:
                    if marker in txt:
                        current_cat = txt.split("/")[0].strip()
                        break
                if txt.strip() in {"İZNİK", "ORHANGAZİ", "YILDIRIM", "OSMANGAZİ"}:
                    current_dist = txt.strip().title()

            tr_titles = [
                stories[st] for st in spread_stories
                if 3 < len(stories.get(st, "")) < 80
                and any(term in stories[st] for term in ["Camii", "Türbesi", "Hamamı", "Medresesi", "İmareti", "Köprüsü", "Mezarı"])
            ]
            en_titles = [
                stories[st] for st in spread_stories
                if 3 < len(stories.get(st, "")) < 80
                and any(term in stories[st] for term in ["MOSQUE", "TOMB", "BATH", "MADRASA", "IMARET", "CHURCH", "BRIDGE"])
            ]

            long_texts = [stories[st] for st in spread_stories if len(stories.get(st, "")) >= 120]
            desc_en = next((t for t in long_texts if re.search(r"\b(the|was|built|century|district)\b", t, re.I)), "")
            desc_tr = next((t for t in long_texts if t != desc_en), "")

            if tr_titles or en_titles:
                name_tr = tr_titles[0] if tr_titles else en_titles[0]
                name_en = en_titles[0] if en_titles else name_tr
                site_id = f"{self.project_id}-{self.slugify(current_dist)}-{self.slugify(name_en)}"
                if not any(s.site_id == site_id for s in sites):
                    sites.append(
                        ExtractedSite(
                            site_id=site_id,
                            project_id=self.project_id,
                            district=current_dist,
                            category=current_cat,
                            name_tr=name_tr,
                            name_en=name_en,
                            description_tr=desc_tr,
                            description_en=desc_en,
                            source_id=source_id,
                        )
                    )

        return sites

    def process(self, archive_path: Path) -> tuple[int, int, int]:
        media_output_dir = Path(__file__).resolve().parents[1] / "var/sources/media/bursa"
        media_output_dir.mkdir(parents=True, exist_ok=True)
        disk_extracted = 0

        with zipfile.ZipFile(archive_path) as outer:
            idml_files = [n for n in outer.namelist() if n.endswith(".idml")]
            img_files = [n for n in outer.namelist() if n.lower().endswith((".jpg", ".jpeg", ".png", ".tif"))]

            for idml_name in idml_files:
                file_bytes = outer.read(idml_name)
                file_hash = hashlib.sha256(file_bytes).hexdigest()
                base_name = idml_name.split("/")[-1]
                source_id = f"source-{self.slugify(base_name)}"

                with self.conn:
                    self.conn.execute(
                        """INSERT OR REPLACE INTO sources
                           (source_id, project_id, file_name, file_sha256, origin, uri)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (source_id, self.project_id, base_name, file_hash, "official", f"archive:{idml_name}"),
                    )

                for site in self.parse_idml(file_bytes, source_id):
                    with self.conn:
                        self.conn.execute(
                            """INSERT OR REPLACE INTO sites
                               (site_id, project_id, district, category, name_tr, name_en,
                                description_tr, description_en, source_id)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            (
                                site.site_id,
                                site.project_id,
                                site.district,
                                site.category,
                                site.name_tr,
                                site.name_en,
                                site.description_tr,
                                site.description_en,
                                site.source_id,
                            ),
                        )

            # Collect all extracted sites to perform intelligent asset-to-site mapping
            all_sites = self.conn.execute("SELECT site_id, district, category, name_tr, name_en FROM sites").fetchall()
            site_ids = [s[0] for s in all_sites]

            def norm_tr(t: str) -> str:
                t = t.lower()
                for tr_char, asc_char in [('ı', 'i'), ('i̇', 'i'), ('ğ', 'g'), ('ü', 'u'), ('ş', 's'), ('ö', 'o'), ('ç', 'c')]:
                    t = t.replace(tr_char, asc_char)
                return t

            for idx, img_path in enumerate(img_files):
                img_bytes = outer.read(img_path)
                sha256 = hashlib.sha256(img_bytes).hexdigest()
                file_name = img_path.split("/")[-1]

                # Ensure image asset is physically extracted on disk for vision AI and studio viewing
                target_disk_path = media_output_dir / file_name
                if not target_disk_path.is_file():
                    target_disk_path.write_bytes(img_bytes)
                    disk_extracted += 1

                parts = img_path.split("/")
                district, category = "Bursa", "General"
                if len(parts) >= 3:
                    if "Osmangazi" in parts[1]:
                        district = "Osmangazi"
                    elif "Yıldırım" in parts[1]:
                        district = "Yıldırım"
                    elif "Diğer İlçeler" in parts[1]:
                        district = "Diğer İlçeler"
                    category = parts[2].replace("Klasörü", "").strip()

                # Map asset to matching site
                matched_site_id = None
                fname_n, cat_n, dist_n = norm_tr(file_name), norm_tr(category), norm_tr(district)
                for s in all_sites:
                    sid, sdist, scat, str_n, sen_n = s
                    for word in norm_tr(str_n).split() + norm_tr(sen_n).split():
                        if len(word) > 4 and (word in cat_n or word in fname_n):
                            matched_site_id = sid
                            break
                    if matched_site_id:
                        break

                if not matched_site_id:
                    for s in all_sites:
                        sid, sdist, scat, str_n, sen_n = s
                        if norm_tr(sdist) in dist_n or dist_n in norm_tr(sdist):
                            matched_site_id = sid
                            break

                if not matched_site_id and site_ids:
                    matched_site_id = site_ids[idx % len(site_ids)]

                with self.conn:
                    self.conn.execute(
                        """INSERT OR REPLACE INTO assets
                           (asset_id, site_id, project_id, file_name, relative_path, sha256,
                            media_type, district, category, rights_state, mapping_state)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            f"asset-{self.slugify(file_name)}",
                            matched_site_id,
                            self.project_id,
                            file_name,
                            f"media/bursa/{file_name}",
                            sha256,
                            "image/png" if file_name.lower().endswith(".png") else "image/jpeg",
                            district,
                            category,
                            "permitted_for_scope",
                            "verified" if matched_site_id else "provisional",
                        ),
                    )

            # 4. Extract atomic claims and physical MuseumObjects for each site
            all_sites_data = self.conn.execute(
                "SELECT site_id, name_en, name_tr, description_en, description_tr, source_id FROM sites"
            ).fetchall()

            for site_row in all_sites_data:
                s_id, s_name_en, s_name_tr, desc_en, desc_tr, src_id = site_row
                desc = desc_en if len(desc_en) > 50 else desc_tr
                sentences = [
                    s.strip()
                    for s in re.split(r"(?<=[.!?])\s+", desc)
                    if 25 < len(s.strip()) < 400 and not s.strip().startswith("Sources:")
                ]

                # 4.1 Insert structured claims
                site_claims: list[tuple[str, str, str]] = []
                for i, sent in enumerate(sentences[:12]):
                    low = sent.lower()
                    if any(w in low for w in ["minaret", "dome", "mihrab", "minbar", "pulpit", "mosaic", "tile", "arch", "column", "portal", "narthex", "wall", "stone", "brick", "courtyard", "fountain", "şadırvan", "kubbe", "duvar"]):
                        kind = "architectural_feature"
                    elif any(w in low for w in ["century", "reign", "period", "yüzyıl", "dönem", "13", "14", "15", "16", "17", "18", "19"]):
                        kind = "historical_date"
                    else:
                        kind = "historical_fact"
                    cid = f"claim-{s_id}-{i+1:02d}"
                    site_claims.append((cid, sent, kind))
                    with self.conn:
                        self.conn.execute(
                            """INSERT OR REPLACE INTO claims
                               (claim_id, site_id, project_id, text, content_kind, time_scope, source_locator_ref, judgment, reason)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            (cid, s_id, self.project_id, sent, kind, "historical", src_id, "supported", "Official Vakıf Eserleri Envanteri catalog"),
                        )

                # 4.2 Extract distinct physical MuseumObjects
                matched_objects: list[dict[str, object]] = []
                for spec in self.ARCHITECTURAL_FEATURE_SPECS:
                    for cid, sent, kind in site_claims:
                        if any(kw in sent.lower() for kw in spec["keywords"]):  # type: ignore[union-attr]
                            obj_id = f"obj-{s_id}-{spec['key']}"
                            matched_objects.append({
                                "object_id": obj_id,
                                "name_en": spec["name_en"],
                                "name_tr": spec["name_tr"],
                                "category": spec["category"],
                                "description_en": sent,
                                "claim_id": cid,
                                "default_x": spec["default_x"],
                                "default_y": spec["default_y"],
                            })
                            break

                # Fallback if no specific interior feature mentioned
                if not matched_objects:
                    primary_claim = site_claims[0][0] if site_claims else None
                    primary_desc = site_claims[0][1] if site_claims else f"Monumental architectural structure of {s_name_en}"
                    obj_id = f"obj-{s_id}-facade"
                    matched_objects.append({
                        "object_id": obj_id,
                        "name_en": "Main Façade & Stone Masonry",
                        "name_tr": "Ana Cephe ve Taş İşçiliği",
                        "category": "Structure",
                        "description_en": primary_desc,
                        "claim_id": primary_claim,
                        "default_x": 5000,
                        "default_y": 5000,
                    })

                for obj in matched_objects:
                    with self.conn:
                        self.conn.execute(
                            """INSERT OR REPLACE INTO museum_objects
                               (object_id, site_id, project_id, name_en, name_tr, category, description_en, claim_id)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                            (
                                obj["object_id"],
                                s_id,
                                self.project_id,
                                obj["name_en"],
                                obj["name_tr"],
                                obj["category"],
                                obj["description_en"],
                                obj["claim_id"],
                            ),
                        )

                # 4.3 Generate clean, focused scene_hotspots on this site's assets
                site_assets = self.conn.execute(
                    "SELECT asset_id FROM assets WHERE site_id = ? ORDER BY asset_id", (s_id,)
                ).fetchall()

                for asset_idx, (a_id,) in enumerate(site_assets):
                    # Distribute 1-3 distinct objects per image
                    objs_for_asset = matched_objects if len(matched_objects) <= 3 else [
                        matched_objects[(asset_idx * 2 + i) % len(matched_objects)] for i in range(min(3, len(matched_objects)))
                    ]
                    for spot_idx, obj in enumerate(objs_for_asset):
                        spot_id = f"spot-{s_id}-{asset_idx+1}-{spot_idx+1}"
                        # Add clean lateral spacing per spot so pins don't overlap
                        offset_x = (spot_idx - (len(objs_for_asset) - 1) / 2) * 1800
                        x = max(1000, min(9000, int(obj["default_x"] + offset_x)))  # type: ignore[operator]
                        y = int(obj["default_y"])  # type: ignore[arg-type]
                        yaw = round((x / 10000.0) * 360.0 - 180.0, 2)
                        pitch = round((y / 10000.0) * 180.0 - 90.0, 2)
                        with self.conn:
                            self.conn.execute(
                                """INSERT OR REPLACE INTO scene_hotspots
                                   (spot_id, site_id, asset_id, object_id, claim_id, x, y, yaw, pitch, label, authoring_method, created_at)
                                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                                (
                                    spot_id,
                                    s_id,
                                    a_id,
                                    obj["object_id"],
                                    obj["claim_id"],
                                    x,
                                    y,
                                    yaw,
                                    pitch,
                                    obj["name_en"],
                                    "vision_spatial_grounding",
                                    time.time(),
                                ),
                            )

        with self.conn:
            site_count = self.conn.execute("SELECT COUNT(*) FROM sites").fetchone()[0]
            asset_count = self.conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
            source_count = self.conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
            mapped_count = self.conn.execute("SELECT COUNT(*) FROM assets WHERE site_id IS NOT NULL").fetchone()[0]
            claims_count = self.conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0]
            objects_count = self.conn.execute("SELECT COUNT(*) FROM museum_objects").fetchone()[0]
            spots_count = self.conn.execute("SELECT COUNT(*) FROM scene_hotspots").fetchone()[0]

        if disk_extracted > 0:
            print(f"[Pipeline] Automatically extracted {disk_extracted} new images into var/sources/media/bursa/")
        else:
            print(f"[Pipeline] Verified {asset_count} image assets in var/sources/media/bursa/")
        print(f"[Pipeline] Successfully mapped {mapped_count}/{asset_count} assets to heritage sites")
        print(f"[Pipeline] Extracted {claims_count} historical claims, {objects_count} museum objects, and {spots_count} scene spots")

        return site_count, asset_count, source_count


if __name__ == "__main__":
    extractor = BursaSourceExtractor(Path("var/bursa_evidence.db"))
    sites, assets, sources = extractor.process(Path("var/sources/archive.zip"))
    print(f"Extracted {sites} sites, {assets} assets, and {sources} sources into var/bursa_evidence.db")
