"""Export verified Evidence records directly, without rereading a human-layout PDF."""

from __future__ import annotations

import hashlib
import json
import shutil
import unicodedata
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING

from PIL import Image, ImageDraw, ImageFont

from pastport_evidence.adapters.report_layout import font_path
from pastport_evidence.application.evidence import CorpusIndex
from pastport_evidence.domain.models import DomainModel
from pastport_evidence.domain.pdf import RegisteredPDF
from pastport_evidence.ports.assets import AssetStore

if TYPE_CHECKING:
    from pastport_evidence.application.photo_mapping import PreparedDocuments


def normalized(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).split())


class _Observation(DomainModel):
    photo_number: int
    observation_status: str = "visible"
    region_normalized: tuple[float, float, float, float]
    basis: str


class _Object(DomainModel):
    number: int
    object_id: str
    name: str
    boundary: str
    history_id: str
    history: str
    parent: str = "Historical whole not established"
    page: int
    quote: str
    image_page: int | None = None
    image_box: tuple[float, float, float, float] | None = None
    image_role: str = "text_evidence"
    introduction: str
    explanation: str
    proxy: str = "Source-supported association; not an assertion of physical identity"
    limit: str
    observations: tuple[_Observation, ...]


class EvidenceEnvironmentHandoff:
    def __init__(self, assets: AssetStore) -> None:
        self.assets = assets

    def export(self, root: Path, bundle: PreparedDocuments, source: RegisteredPDF) -> Path:
        identity = hashlib.sha256(
            ("native-evidence-v1:" + bundle.model_dump_json() + source.model_dump_json()).encode()
        ).hexdigest()
        target = root / identity
        if target.exists():
            self.validate(target)
            return target
        root.mkdir(parents=True, exist_ok=True)
        corpus = CorpusIndex(source)
        with TemporaryDirectory(prefix=".native-evidence-", dir=root) as scratch:
            output = Path(scratch) / "handoff"
            media = output / "media"
            media.mkdir(parents=True)
            original = self.assets.resolve_path(source.source)
            with original.open("rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != source.source.asset.sha256:
                    raise ValueError("Native evidence source bytes changed")
            shutil.copyfile(original, output / "source.pdf")
            shutil.copyfile(original, output / "input.pdf")
            (output / "source-text.json").write_text(
                source.model_dump_json(indent=2), encoding="utf-8"
            )
            objects: list[_Object] = []
            quotes: list[dict[str, str | int]] = []
            photo_rows: list[dict[str, object]] = []
            photos: dict[str, int] = {}
            skipped: list[int] = []
            for item in bundle.objects:
                evidence = item.source_evidence
                sightings = tuple(
                    o for o in item.photo_observations if o.identity_state == "confirmed"
                )
                if evidence is None or not evidence.passages or not sightings:
                    skipped.append(item.entity.display_number)
                    continue
                for passage in evidence.passages:
                    corpus.validate_passage(passage)
                primary = next(
                    (p for p in evidence.passages if p.page_index + 1 == evidence.pdf_page_number),
                    evidence.passages[0],
                )
                page = source.pages[primary.page_index]
                context, quote = normalized(page.original_text), normalized(primary.quote)
                start = context.index(quote)
                observations: list[_Observation] = []
                for sighting in sightings:
                    photo = sighting.photo
                    if photo.photo_id not in photos:
                        number = len(photos) + 1
                        photos[photo.photo_id] = number
                        photo_file = media / f"photo-{number:02d}.jpg"
                        with Image.open(self.assets.resolve_path(photo.image)) as image:
                            with image.convert("RGB") as rgb:
                                rgb.save(photo_file, quality=95)
                            size = image.size
                        photo_rows.append(
                            {
                                "number": number,
                                "path": photo.name,
                                "sha256": hashlib.sha256(photo_file.read_bytes()).hexdigest(),
                                "oriented_size": list(size),
                                "source_kind": "registered_scene_observation",
                            }
                        )
                    observations.append(
                        _Observation(
                            photo_number=photos[photo.photo_id],
                            region_normalized=(
                                sighting.region.top_left.x / photo.width,
                                sighting.region.top_left.y / photo.height,
                                sighting.region.bottom_right.x / photo.width,
                                sighting.region.bottom_right.y / photo.height,
                            ),
                            basis=sighting.basis,
                        )
                    )
                with Image.open(self.assets.resolve_path(sightings[0].crop)) as crop:
                    crop.save(output / f"proxy-{item.entity.display_number}.png")
                objects.append(
                    _Object(
                        number=item.entity.display_number,
                        object_id=item.entity.object_id,
                        name=item.entity.label,
                        boundary="; ".join(item.entity.distinguishing_features),
                        history_id=evidence.historical_subject_id,
                        history=evidence.title,
                        page=primary.page_index + 1,
                        quote=quote,
                        introduction=primary.quote[:1300],
                        explanation=evidence.limitation,
                        limit=evidence.limitation,
                        observations=tuple(observations),
                    )
                )
                quotes.append(
                    {
                        "number": item.entity.display_number,
                        "page": primary.page_index + 1,
                        "normalized_text": context,
                        "start": start,
                        "end": start + len(quote),
                        "line_start": primary.line_start or 1,
                        "line_end": primary.line_end or len(page.original_text.splitlines()),
                    }
                )
                preview = media / f"source-page-{primary.page_index + 1:02d}.png"
                if not preview.exists():
                    self.text_preview(page.original_text, primary.page_index + 1, preview)
                shutil.copyfile(preview, media / f"history-{item.entity.display_number:02d}.png")
            if not objects:
                raise ValueError("No verified source-bound candidates with confirmed observations")
            (output / "objects.json").write_text(
                json.dumps(
                    {
                        "title": "Verified text evidence",
                        "objects": [o.model_dump(mode="json") for o in objects],
                    },
                    ensure_ascii=False,
                )
            )
            (output / "inputs.json").write_text(
                json.dumps(
                    {"input_page_count": source.page_count, "photos": photo_rows},
                    ensure_ascii=False,
                )
            )
            (output / "quote-regions.json").write_text(json.dumps(quotes, ensure_ascii=False))
            (output / "handoff-provenance.json").write_text(
                json.dumps(
                    {
                        "source_sha256": source.source.asset.sha256,
                        "input_binding": bundle.input_binding,
                        "objects_not_exported": skipped,
                        "history_images": "text previews, not photographs or source-page renders",
                        "model_calls": 0,
                        "historical_approval": False,
                    },
                    ensure_ascii=False,
                )
            )
            integrity = {
                p.relative_to(output).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in output.rglob("*")
                if p.is_file()
            }
            (output / ".integrity.json").write_text(json.dumps(integrity, sort_keys=True))
            output.rename(target)
        return target

    @staticmethod
    def text_preview(text: str, page: int, destination: Path) -> None:
        # UI compatibility card, never a rendering of the PDF page or a historical photograph.
        with Image.new("RGB", (1200, 1400), "white") as image:
            draw = ImageDraw.Draw(image)
            font = ImageFont.truetype(str(font_path()), 24)
            draw.text(
                (30, 20),
                f"TEXT PREVIEW | PDF page {page} | line numbers below",
                font=font,
                fill="black",
            )
            y = 70
            for index, line in enumerate(text.splitlines(), 1):
                for offset in range(0, max(1, len(line)), 70):
                    if y > 1320:
                        break
                    draw.text(
                        (30, y),
                        f"{index:03d}  " + line[offset : offset + 70],
                        font=font,
                        fill="black",
                    )
                    y += 32
                if y > 1320:
                    break
            image.save(destination)

    @staticmethod
    def validate(target: Path) -> None:
        entries: object = json.loads((target / ".integrity.json").read_text())
        if not isinstance(entries, dict):
            raise ValueError("Invalid handoff integrity")
        for name, sha in entries.items():
            if not isinstance(name, str) or not isinstance(sha, str):
                raise ValueError("Invalid handoff integrity")
            path = target / name
            if (
                path.is_symlink()
                or not path.resolve().is_relative_to(target.resolve())
                or hashlib.sha256(path.read_bytes()).hexdigest() != sha
            ):
                raise ValueError("Verified environment handoff changed")
