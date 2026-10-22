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


class BursaSourceExtractor:
    """Extracts heritage sites, sources, and media assets into SQLite."""

    CATEGORY_MARKERS: tuple[str, ...] = (
        "Camiler ve Hazireler",
        "Türbeler ve Mezarlar",
        "Eğitim Yapıları",
        "Su Yapıları",
        "Sivil Mimari",
        "Tekkeler ve Zaviyerler",
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
            """)
            conn.execute(
                "INSERT OR REPLACE INTO projects (project_id, name, default_locale) VALUES (?, ?, ?)",
                (self.project_id, "Bursa Cultural Heritage", "en"),
            )
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

            for img_path in img_files:
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

                with self.conn:
                    self.conn.execute(
                        """INSERT OR REPLACE INTO assets
                           (asset_id, site_id, project_id, file_name, relative_path, sha256,
                            media_type, district, category, rights_state, mapping_state)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            f"asset-{self.slugify(file_name)}",
                            None,
                            self.project_id,
                            file_name,
                            f"media/bursa/{file_name}",
                            sha256,
                            "image/png" if file_name.lower().endswith(".png") else "image/jpeg",
                            district,
                            category,
                            "permitted_for_scope",
                            "provisional",
                        ),
                    )

        with self.conn:
            site_count = self.conn.execute("SELECT COUNT(*) FROM sites").fetchone()[0]
            asset_count = self.conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
            source_count = self.conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0]

        if disk_extracted > 0:
            print(f"[Pipeline] Automatically extracted {disk_extracted} new images into var/sources/media/bursa/")
        else:
            print(f"[Pipeline] Verified {asset_count} image assets in var/sources/media/bursa/")

        return site_count, asset_count, source_count


if __name__ == "__main__":
    extractor = BursaSourceExtractor(Path("var/bursa_evidence.db"))
    sites, assets, sources = extractor.process(Path("var/sources/archive.zip"))
    print(f"Extracted {sites} sites, {assets} assets, and {sources} sources into var/bursa_evidence.db")
