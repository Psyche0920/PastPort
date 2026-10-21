"""Ingest mock Turing Retro-Computing Lab IDML and panorama asset into test SQLite database."""
from __future__ import annotations

import hashlib
from pathlib import Path
import sqlite3
import xml.etree.ElementTree as ET
import zipfile


SCHEMA_SQL = """
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
"""


def compute_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def ingest_test_cluster(
    idml_path: Path,
    pano_path: Path,
    db_path: Path,
    project_id: str = "test-cluster",
) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")

    with conn:
        conn.executescript(SCHEMA_SQL)
        conn.execute(
            "INSERT OR REPLACE INTO projects (project_id, name, default_locale) VALUES (?, ?, ?)",
            (project_id, "Turing Computational Heritage Project", "en"),
        )

        # 1. Register Source
        idml_sha = compute_sha256(idml_path)
        source_id = f"src-{project_id}-idml"
        conn.execute(
            "INSERT OR REPLACE INTO sources (source_id, project_id, file_name, file_sha256, origin, uri) VALUES (?, ?, ?, ?, ?, ?)",
            (source_id, project_id, idml_path.name, idml_sha, "test_mock", str(idml_path.as_posix())),
        )

        # 2. Parse IDML Stories
        stories: dict[str, str] = {}
        with zipfile.ZipFile(idml_path) as z:
            for name in z.namelist():
                if name.startswith("Stories/"):
                    sid = name.split("/")[-1].replace("Story_", "").replace(".xml", "")
                    root = ET.fromstring(z.read(name))
                    texts = [e.text for e in root.iter() if e.tag.endswith("Content") and e.text]
                    stories[sid] = " ".join(texts).strip()

        site_id = f"{project_id}-turing-retro-computing-lab"
        name_tr = stories.get("st_tr_name", "Turing Retro-Hesaplama Laboratuvarı")
        name_en = stories.get("st_en_name", "Turing Retro-Computing Lab")
        desc_tr = stories.get("st_tr_desc", "")
        desc_en = stories.get("st_en_desc", "")
        district = stories.get("st_dist", "Osmangazi").title()
        category = stories.get("st_cat", "Computing Heritage")

        conn.execute(
            "INSERT OR REPLACE INTO sites (site_id, project_id, district, category, name_tr, name_en, description_tr, description_en, source_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (site_id, project_id, district, category, name_tr, name_en, desc_tr, desc_en, source_id),
        )

        # 3. Register Panorama Asset
        pano_sha = compute_sha256(pano_path)
        asset_id = "asset-turing-room-pano-360"
        conn.execute(
            "INSERT OR REPLACE INTO assets (asset_id, site_id, project_id, file_name, relative_path, sha256, media_type, district, category, rights_state, mapping_state) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                asset_id,
                site_id,
                project_id,
                pano_path.name,
                f"panoramas/{pano_path.name}",
                pano_sha,
                "image/jpeg",
                district,
                category,
                "permitted_for_scope",
                "verified",
            ),
        )

        # 4. Populate Claims
        claims_data = [
            (
                "claim-turing-style",
                site_id,
                project_id,
                stories.get("st_claim_style", "Built in 1987 in High-Tech Industrial style."),
                "historical_fact",
                "1987",
                "Story_st_claim_style",
                "supported",
                "Documented in architectural register",
            ),
            (
                "claim-turing-architect",
                site_id,
                project_id,
                stories.get("st_claim_architect", "Designed by Dr. Elena Vance and constructed by Ada Systems."),
                "historical_fact",
                "1987",
                "Story_st_claim_architect",
                "supported",
                "Verified building contractor manifest",
            ),
            (
                "claim-turing-tournament",
                site_id,
                project_id,
                stories.get("st_claim_event", "Hosted the historic Grandmaster AI Chess Blitz in 1996."),
                "historical_event",
                "1996",
                "Story_st_claim_event",
                "supported",
                "International Chess Federation archives",
            ),
            (
                "claim-turing-artifact-deepblue",
                site_id,
                project_id,
                stories.get("st_claim_artifact", "Preserves the DeepBlue-Prototype #4 terminal, an experimental computing artifact."),
                "historical_artifact",
                "1996-present",
                "Story_st_claim_artifact",
                "supported",
                "Museum catalog inventory record #4096",
            ),
        ]

        for claim in claims_data:
            conn.execute(
                "INSERT OR REPLACE INTO claims (claim_id, site_id, project_id, text, content_kind, time_scope, source_locator_ref, judgment, reason) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                claim,
            )

    conn.close()
    print(f"Successfully populated {db_path} with site, asset, and {len(claims_data)} claims.")


if __name__ == "__main__":
    idml = Path("var/sources/turing_lab.idml")
    pano = Path("var/sources/panoramas/turing_lab_room.jpg")
    db = Path("var/test_evidence.db")
    ingest_test_cluster(idml, pano, db)
