"""Read a legacy demo DB as an explicit frozen replay counterpart; never migrate it in place."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

from pastport_pdf_vr.domain.editorial import ReplayEvidence
from pastport_pdf_vr.domain.models import DomainModel
from pastport_pdf_vr.ports.assets import AssetStore


class LegacyObject(DomainModel):
    object_number: int
    historical_subject_id: str | None
    ai_draft: str
    human_override: str | None
    background: str
    evidence: ReplayEvidence | None


class LegacyMaterials(DomainModel):
    mode: str = "explicit_legacy_replay"
    objects: tuple[LegacyObject, ...]


class LegacyReplayReader:
    def __init__(self, assets: AssetStore) -> None:
        self._assets = assets

    def read(self, project: str, path: Path) -> LegacyMaterials:
        if not path.is_file():
            raise ValueError("Legacy replay DB is missing")
        db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
        db.row_factory = sqlite3.Row
        try:
            db.execute("BEGIN")
            objects = []
            rows = db.execute("""SELECT p.modern_id,p.historical_id,v.ai_draft,v.human_override,
                v.historical_id AS content_subject FROM pairings p
                LEFT JOIN vr_display_contents v ON v.object_id=p.modern_id ORDER BY p.modern_id
                """).fetchall()
            for row in rows:
                subject = row["historical_id"]
                evidence = None
                background = ""
                if subject:
                    record = db.execute(
                        """SELECT h.title_zh,h.image_page,h.media_path,h.building_id,
                        a.translation_zh,a.coverage,a.limitation,p.pdf_page,p.start_offset,p.end_offset,
                        p.exact_text,s.normalized_text,s.printed_page,s.text_sha256
                        FROM historical_objects h
                        LEFT JOIN text_associations a ON a.historical_id=h.id
                        LEFT JOIN passages p ON p.id=a.passage_id
                        LEFT JOIN source_pages s ON s.pdf_page=p.pdf_page
                        WHERE h.id=?""",
                        (subject,),
                    ).fetchone()
                    if record and record["exact_text"] is not None:
                        raw = record["normalized_text"]
                        if (
                            raw[record["start_offset"] : record["end_offset"]]
                            != record["exact_text"]
                        ):
                            raise ValueError(
                                "Legacy exact quotation disagrees with its page selector"
                            )
                        if hashlib.sha256(raw.encode()).hexdigest() != record["text_sha256"]:
                            raise ValueError(
                                "Legacy extracted page hash disagrees with its stored text"
                            )
                        contexts = db.execute(
                            "SELECT summary_zh FROM narrative_contexts "
                            "WHERE building_id=? ORDER BY id",
                            (record["building_id"],),
                        ).fetchall()
                        background = "\n\n".join(context[0] for context in contexts)
                        image = None
                        if record["media_path"]:
                            media = (path.parent / record["media_path"]).resolve(strict=True)
                            if not media.is_relative_to(path.parent.resolve(strict=True)):
                                raise ValueError("Legacy media path escapes its material directory")
                            image = self._assets.register_file(
                                project, media, "image/jpeg", 16 * 1024 * 1024
                            ).reference
                        evidence = ReplayEvidence(
                            historical_subject_id=subject,
                            title=record["title_zh"],
                            pdf_page_number=record["pdf_page"],
                            printed_page=record["printed_page"],
                            original_quote=record["exact_text"],
                            translation=record["translation_zh"],
                            scope=record["coverage"],
                            limitation=record["limitation"],
                            source_page_sha256=record["text_sha256"],
                            source_image=image,
                            background=background,
                        )
                matched = row["content_subject"] == subject
                objects.append(
                    LegacyObject(
                        object_number=row["modern_id"],
                        historical_subject_id=subject,
                        ai_draft=(row["ai_draft"] or "") if matched else "",
                        human_override=row["human_override"] if matched else None,
                        background=background,
                        evidence=evidence,
                    )
                )
            return LegacyMaterials(objects=tuple(objects))
        finally:
            db.close()
