"""Extract Bursa heritage records from IDML and archive resources into SQLite.

Usage:
    python tools/extract_bursa_sources.py
"""

from __future__ import annotations

import hashlib
import io
import re
import sqlite3
import urllib.parse
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


@dataclass(frozen=True)
class ExtractedAsset:
    asset_id: str
    site_id: str | None
    project_id: str
    file_name: str
    relative_path: str
    sha256: str
    media_type: str
    district: str
    category: str


def init_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
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
        """)
    return conn


def slugify(text: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower().strip())
    cleaned = cleaned.strip("-")
    return cleaned or "item"


def extract_text_from_story(xml_bytes: bytes) -> str:
    root = ET.fromstring(xml_bytes)
    texts: list[str] = []
    for elem in root.iter():
        if elem.tag.endswith("Content") and elem.text:
            texts.append(elem.text)
    return " ".join(texts).strip()


def parse_idml_monument(
    zip_bytes: bytes,
    source_id: str,
    project_id: str,
) -> list[ExtractedSite]:
    """Parse sites and descriptions from an IDML archive."""
    inner = zipfile.ZipFile(io.BytesIO(zip_bytes))
    stories: dict[str, str] = {}
    for name in inner.namelist():
        if name.startswith("Stories/"):
            try:
                text = extract_text_from_story(inner.read(name))
                if text:
                    story_id = name.split("/")[-1].replace("Story_", "").replace(".xml", "")
                    stories[story_id] = text
            except Exception:
                continue

    sites: list[ExtractedSite] = []
    
    # Check if this is the Yeşil Complex file
    if "u4ecc" in stories and "u4ee3" in stories:
        name_tr = stories.get("u4ecc", "Yeşil Camii")
        name_en = stories.get("u4ee3", "Yeşil Mosque")
        district = stories.get("u2f98", "Yıldırım").title()
        category = "Mosque / Complex"
        desc_tr = stories.get("u474b", "")
        desc_en = stories.get("u2f15", "")
        site_id = f"{project_id}-{slugify(name_en)}"
        sites.append(
            ExtractedSite(
                site_id=site_id,
                project_id=project_id,
                district=district,
                category=category,
                name_tr=name_tr,
                name_en=name_en,
                description_tr=desc_tr,
                description_en=desc_en,
                source_id=source_id,
            )
        )
        return sites

    # General pattern in İznik / Orhangazi / Yıldırım Kalan Bölümler
    # Spread mapping: inspect text frames on spreads to pair TR title, EN title, category, descriptions
    current_category = "General Heritage"
    current_district = "Bursa"

    # Sort stories by character length to identify titles vs descriptions
    short_stories = {k: v for k, v in stories.items() if len(v) < 120}
    long_stories = {k: v for k, v in stories.items() if len(v) >= 120}

    # Identify category markers
    cat_markers = [
        "Camiler ve Hazireler",
        "Türbeler ve Mezarlar",
        "Eğitim Yapıları",
        "Su Yapıları",
        "Sivil Mimari",
        "Tekkeler ve Zaviyerler",
    ]

    # Map spreads to find grouped stories
    for s_name in sorted(n for n in inner.namelist() if n.startswith("Spreads/")):
        try:
            root = ET.fromstring(inner.read(s_name))
        except Exception:
            continue
        spread_stories = [
            elem.attrib["ParentStory"]
            for elem in root.iter()
            if elem.tag.endswith("TextFrame") and "ParentStory" in elem.attrib
        ]
        if not spread_stories:
            continue

        # Check for category change
        for st_id in spread_stories:
            txt = stories.get(st_id, "")
            for marker in cat_markers:
                if marker in txt:
                    current_category = txt.split("/")[0].strip()
                    break
            if txt.strip() in {"İZNİK", "ORHANGAZİ", "YILDIRIM", "OSMANGAZİ"}:
                current_district = txt.strip().title()

        # Find monument titles on this spread
        # Usually: one story is TR name (mixed case or ALL CAPS), another is EN name (ALL CAPS with English terms)
        tr_titles = []
        en_titles = []
        for st_id in spread_stories:
            txt = stories.get(st_id, "")
            if 3 < len(txt) < 80:
                if any(m in txt for m in cat_markers) or txt.strip() in {"İZNİK", "ORHANGAZİ", "YILDIRIM"}:
                    continue
                if any(term in txt for term in ["MOSQUE", "TOMB", "BATH", "MADRASA", "IMARET", "CHURCH", "BRIDGE"]):
                    en_titles.append((st_id, txt))
                elif any(term in txt for term in ["Camii", "Türbesi", "Hamamı", "Medresesi", "İmareti", "Köprüsü", "Mezarı"]):
                    tr_titles.append((st_id, txt))

        # Find long texts (descriptions) on this spread
        spread_long_texts = [stories[st_id] for st_id in spread_stories if st_id in long_stories]
        desc_tr = ""
        desc_en = ""
        for lt in spread_long_texts:
            # Simple heuristic: English description usually contains words like 'the', 'was', 'century', 'built'
            if re.search(r"\b(the|was|built|century|located|district)\b", lt, re.IGNORECASE):
                desc_en = lt
            else:
                desc_tr = lt

        if tr_titles or en_titles:
            name_tr = tr_titles[0][1] if tr_titles else (en_titles[0][1] if en_titles else "Unknown")
            name_en = en_titles[0][1] if en_titles else name_tr
            site_slug = slugify(name_en)
            site_id = f"{project_id}-{slugify(current_district)}-{site_slug}"
            
            # Avoid duplicate sites
            if not any(s.site_id == site_id for s in sites):
                sites.append(
                    ExtractedSite(
                        site_id=site_id,
                        project_id=project_id,
                        district=current_district,
                        category=current_category,
                        name_tr=name_tr,
                        name_en=name_en,
                        description_tr=desc_tr,
                        description_en=desc_en,
                        source_id=source_id,
                    )
                )

    return sites


def process_archive(archive_path: Path, db_path: Path) -> None:
    print(f"Opening archive: {archive_path}")
    conn = init_db(db_path)
    project_id = "bursa"

    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO projects (project_id, name, default_locale) VALUES (?, ?, ?)",
            (project_id, "Bursa Cultural Heritage", "en"),
        )

    with zipfile.ZipFile(archive_path) as outer:
        namelist = outer.namelist()
        idml_files = [n for n in namelist if n.endswith(".idml")]
        image_files = [n for n in namelist if n.lower().endswith((".jpg", ".jpeg", ".png", ".tif"))]

        print(f"Found {len(idml_files)} IDML files and {len(image_files)} image files.")

        # 1. Register sources and extract sites
        all_sites: list[ExtractedSite] = []
        for idml_name in idml_files:
            file_bytes = outer.read(idml_name)
            file_hash = hashlib.sha256(file_bytes).hexdigest()
            base_name = idml_name.split("/")[-1]
            source_id = f"source-{slugify(base_name)}"

            with conn:
                conn.execute(
                    """INSERT OR REPLACE INTO sources
                       (source_id, project_id, file_name, file_sha256, origin, uri)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (source_id, project_id, base_name, file_hash, "official", f"archive:{idml_name}"),
                )

            sites = parse_idml_monument(file_bytes, source_id, project_id)
            all_sites.extend(sites)
            print(f"  Extracted {len(sites)} sites from {base_name}")

        with conn:
            for s in all_sites:
                conn.execute(
                    """INSERT OR REPLACE INTO sites
                       (site_id, project_id, district, category, name_tr, name_en, description_tr, description_en, source_id)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        s.site_id,
                        s.project_id,
                        s.district,
                        s.category,
                        s.name_tr,
                        s.name_en,
                        s.description_tr,
                        s.description_en,
                        s.source_id,
                    ),
                )

        # 2. Register photos / assets
        assets_inserted = 0
        with conn:
            for img_path in image_files:
                img_bytes = outer.read(img_path)
                sha256 = hashlib.sha256(img_bytes).hexdigest()
                file_name = img_path.split("/")[-1]
                asset_id = f"asset-{slugify(file_name)}"
                
                # Derive district and category from folder name
                # e.g. 'Vakıf Eserleri Envanteri - Bursa Fotoğraf Arşivi/I. ve II. Cilt - Osmangazi/Ulucamii Klasörü/Links/...'
                parts = img_path.split("/")
                district = "Bursa"
                category = "General"
                if len(parts) >= 3:
                    cilt_part = parts[1]
                    if "Osmangazi" in cilt_part:
                        district = "Osmangazi"
                    elif "Yıldırım" in cilt_part:
                        district = "Yıldırım"
                    elif "Diğer İlçeler" in cilt_part:
                        district = "Diğer İlçeler"

                    klasor_part = parts[2]
                    category = klasor_part.replace("Klasörü", "").strip()

                relative_path = f"media/bursa/{file_name}"
                media_type = "image/png" if file_name.lower().endswith(".png") else "image/jpeg"

                conn.execute(
                    """INSERT OR REPLACE INTO assets
                       (asset_id, site_id, project_id, file_name, relative_path, sha256, media_type, district, category, rights_state, mapping_state)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        asset_id,
                        None,  # Provisioanl mapping; can be linked to site_id based on name/category
                        project_id,
                        file_name,
                        relative_path,
                        sha256,
                        media_type,
                        district,
                        category,
                        "permitted_for_scope",
                        "provisional",
                    ),
                )
                assets_inserted += 1

        print(f"Registered {assets_inserted} assets into database.")

    # Print summary
    with conn:
        site_count = conn.execute("SELECT COUNT(*) FROM sites").fetchone()[0]
        asset_count = conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
        source_count = conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
        print(f"\nExtraction complete! Database saved to: {db_path}")
        print(f"Summary: {site_count} sites, {asset_count} assets, {source_count} sources.")


if __name__ == "__main__":
    archive = Path("var/sources/archive.zip")
    db = Path("var/bursa_evidence.db")
    process_archive(archive, db)
