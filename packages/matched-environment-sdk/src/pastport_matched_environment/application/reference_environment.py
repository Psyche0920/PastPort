"""Assemble a new, isolated review candidate from a hash-bound visual handoff."""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import json
import re
import shutil
import sqlite3
import subprocess
import sys
import unicodedata
import uuid
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from html import escape
from importlib.resources import files
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast

from PIL import Image, ImageDraw
from pypdf import PdfReader

from pastport_matched_environment.adapters.assets import LocalAssetStore
from pastport_matched_environment.adapters.tour import TourImporter
from pastport_matched_environment.application.environment_agent import offline_input_limits

type Json = None | bool | int | float | str | list[Json] | dict[str, Json]
type Record = dict[str, Json]


class ImportFailure(ValueError):
    """An input cannot safely be associated with this candidate."""


def record(value: Json) -> Record:
    if not isinstance(value, dict):
        raise ImportFailure("Expected a JSON record")
    return value


def sequence(value: Json) -> list[Json]:
    if not isinstance(value, list):
        raise ImportFailure("Expected a JSON array")
    return value


def string(value: Json) -> str:
    if not isinstance(value, str):
        raise ImportFailure("Expected a string")
    return value


def integer(value: Json) -> int:
    if type(value) is not int:
        raise ImportFailure("Expected an integer")
    return value


def read_json(path: Path) -> Json:
    return cast(Json, json.loads(path.read_text()))


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


@dataclass(frozen=True, slots=True)
class Observation:
    photo_number: int
    box: tuple[float, float, float, float]
    basis: str


@dataclass(frozen=True, slots=True)
class Entity:
    number: int
    stable_id: str
    name: str
    boundary: str
    historical_id: str
    historical_name: str
    parent: str
    text_page: int
    image_page: int
    image_box: str
    image_role: str
    explanation: str
    proxy: str
    limitation: str
    quote: str
    observations: tuple[Observation, ...]

    @classmethod
    def parse(cls, raw: Record) -> Entity:
        for field in ("object_id", "name", "boundary", "history_id", "history"):
            if not string(raw[field]).strip():
                raise ImportFailure(f"Entity field {field} cannot be empty")
        if not string(raw["quote"]).strip() and not raw["image_page"]:
            raise ImportFailure("A subject needs actual image evidence or a source quotation")
        views: list[Observation] = []
        for item in sequence(raw["observations"]):
            view = record(item)
            if view["observation_status"] != "visible":
                continue
            values = sequence(view["region_normalized"])
            if len(values) != 4 or any(type(v) not in (int, float) for v in values):
                raise ImportFailure("Invalid observation rectangle")
            coords = tuple(float(cast(float, v)) for v in values)
            box = (coords[0], coords[1], coords[2], coords[3])
            if not 0 <= box[0] < box[2] <= 1 or not 0 <= box[1] < box[3] <= 1:
                raise ImportFailure("Observation outside photo")
            views.append(Observation(integer(view["photo_number"]), box, string(view["basis"])))
        page = integer(raw["page"])
        return cls(
            integer(raw["number"]),
            string(raw["object_id"]),
            string(raw["name"]),
            string(raw["boundary"]),
            string(raw["history_id"]),
            string(raw["history"]),
            string(raw["parent"]),
            page,
            integer(raw["image_page"]) if raw["image_page"] else page,
            json.dumps(raw["image_box"], ensure_ascii=False),
            "object_image" if raw["image_page"] else "text_evidence",
            string(raw["explanation"]),
            string(raw["proxy"]),
            string(raw["limit"]),
            string(raw["quote"]),
            tuple(views),
        )

    def introduction(self) -> str:
        """Show source history; keep proxy reasoning in the editorial review record."""
        title = self.historical_name[:200]
        quote = self.quote.strip()
        if len(quote) > 1100:
            quote = quote[:1100].rsplit(" ", 1)[0] + "…"
        historical_content = f"史料原文：\n{quote}" if quote else "此条仅有来源图像，请查看原始资料。"
        return (
            f"{title}\n\n{historical_content}\n\n"
            f"来源：原始史料 PDF 第 {self.text_page} 页。\n"
            "展示说明：当前场景中的现代物件仅作交互入口，不是这件历史实物。"
        )


@dataclass(frozen=True, slots=True)
class MeasuredPosition:
    number: int
    source_scene: str
    panorama_hash: str
    x: int
    y: int
    basis: str

    @classmethod
    def parse(cls, value: Json) -> MeasuredPosition:
        row = record(value)
        xy = sequence(row["pixel_center"])
        if len(xy) != 2:
            raise ImportFailure("Expected a measured pixel center")
        return cls(
            integer(row["object_number"]),
            string(row["source_scene_id"]),
            string(row["panorama_sha256"]),
            integer(xy[0]),
            integer(xy[1]),
            string(row["basis"]),
        )


@dataclass(frozen=True, slots=True)
class RelationshipReview:
    whole: int
    part: int
    historical_relation: str
    modern_relation: str
    verdict: str
    reason: str

    @classmethod
    def parse(cls, value: Json) -> RelationshipReview:
        row = record(value)
        relation = cls(
            integer(row["whole_object_number"]),
            integer(row["part_object_number"]),
            string(row["historical_relation"]),
            string(row["modern_relation"]),
            string(row["verdict"]),
            string(row["reason"]),
        )
        allowed = {
            "fixed_part_of": {"within_whole", "attached_to_whole"},
            "contained_in": {"within_whole"},
        }
        if relation.whole == relation.part or relation.historical_relation not in allowed:
            raise ImportFailure("Invalid structural relation")
        if (
            relation.verdict not in {"verified", "rejected", "pending"}
            or not relation.reason.strip()
        ):
            raise ImportFailure("A structural review needs a verdict and evidence reason")
        if (
            relation.verdict == "verified"
            and relation.modern_relation not in allowed[relation.historical_relation]
        ):
            raise ImportFailure(
                "A verified mapping contradicts the whole/part spatial relationship"
            )
        return relation


class CandidateBuilder:
    def __init__(
        self, reference: Path, upstream: Path, pdf: Path, vr: Path, locations: Path, output: Path
    ) -> None:
        self.reference, self.upstream, self.pdf = reference, upstream, pdf
        self.vr, self.locations, self.output = vr, locations, output

    def build(self) -> None:
        if self.output.exists():
            raise ImportFailure(
                "Output already exists: choose a new directory; never overwrite human work"
            )
        source = record(read_json(self.upstream / "objects.json"))
        entities = tuple(Entity.parse(record(o)) for o in sequence(source["objects"]))
        if not entities:
            raise ImportFailure("No evidence-backed objects were supplied")
        if len({o.number for o in entities}) != len(entities) or len(
            {o.stable_id for o in entities}
        ) != len(entities):
            raise ImportFailure("Duplicate modern identity")
        if len({o.historical_id for o in entities}) != len(entities):
            raise ImportFailure("Historical identities need explicit upstream conflict review")
        if digest(self.pdf) != digest(self.upstream / "input.pdf"):
            raise ImportFailure("PDF and upstream evidence differ")
        measured = record(read_json(self.locations))
        if measured["input_html_sha256"] != digest(self.vr):
            raise ImportFailure("Coordinates belong to a different VR import")
        relations = tuple(
            RelationshipReview.parse(r) for r in sequence(measured.get("relationship_reviews", []))
        )
        numbers = {o.number for o in entities}
        if any(r.whole not in numbers or r.part not in numbers for r in relations):
            raise ImportFailure("Structural relation refers to an unknown identity")
        rejected = {r.part for r in relations if r.verdict != "verified"}
        positions = tuple(
            p
            for p in (MeasuredPosition.parse(p) for p in sequence(measured["locations"]))
            if p.number not in rejected
        )
        if len({(p.number, p.source_scene) for p in positions}) != len(positions):
            raise ImportFailure("Duplicate viewpoint position")
        self.output.mkdir(parents=True)
        (self.output / "vr_trial").mkdir()
        (self.output / "evidence").mkdir()
        shutil.copytree(self.upstream / "media", self.output / "media")
        for name in (
            "review_server.py",
            "vr_content.py",
            "vr_positions.py",
            "start_demo.py",
            "schema.sql",
        ):
            shutil.copy2(
                self.reference / (name + ".template" if name.endswith(".py") else name),
                self.output / name,
            )
        shutil.copy2(
            self.reference / "vr_position_editor.js", self.output / "vr_trial/vr_position_editor.js"
        )
        shutil.copy2(self.pdf, self.output / "mapping-demo.pdf")
        shutil.copy2(self.upstream / "source.pdf", self.output / "source.pdf")
        shutil.copy2(self.upstream / "objects.json", self.output / "evidence/upstream-objects.json")
        shutil.copy2(
            self.upstream / "quote-regions.json", self.output / "evidence/quote-regions.json"
        )
        shutil.copy2(self.locations, self.output / "evidence/fresh-locations.json")
        html = self.vr.read_text()
        match = re.search(
            r'<script id="tour-data" type="application/json">(.*?)</script>', html, re.S
        )
        if match is None:
            raise ImportFailure("Expected a panorama tour, not an unverified video import")
        tour = record(cast(Json, json.loads(match.group(1))))
        if tour.get("schemaVersion") != 4:
            raise ImportFailure("Only the verified schemaVersion 4 panorama import is supported")
        import_id = str(uuid.uuid4())
        scenes = [record(s) for s in sequence(tour["scenes"])]
        with TemporaryDirectory(prefix="pastport-environment-import-") as temporary:
            store = LocalAssetStore(Path(temporary))
            limits = offline_input_limits()
            admitted = TourImporter(store).import_html("environment-import", self.vr, limits)
            admitted_views = {view.view_id: view for view in admitted.views}
            total_bytes = 0
            for scene in scenes:
                view = admitted_views[string(scene["id"])]
                raw = store.resolve_path(view.panorama).read_bytes()
                total_bytes += len(raw)
                if total_bytes > limits.tour_max_expanded_bytes:
                    raise ImportFailure("Combined panorama bytes exceed the tour input limit")
                with Image.open(store.resolve_path(view.panorama)) as image:
                    media_type = Image.MIME[image.format or "JPEG"]
                pano = record(scene["panorama"])
                pano.update(
                    data=f"data:{media_type};base64," + base64.b64encode(raw).decode(),
                    width=view.width,
                    height=view.height,
                )
        ids = {
            string(s["id"]): str(uuid.uuid5(uuid.UUID(import_id), string(s["id"]))) for s in scenes
        }
        if not scenes or len(ids) != len(scenes):
            raise ImportFailure("Missing or duplicate imported viewpoints")
        entity_by_number = {o.number: o for o in entities}
        located: list[Record] = []
        for scene in scenes:
            old_id = string(scene["id"])
            pano = record(scene["panorama"])
            raw = base64.b64decode(string(pano["data"]).split(",", 1)[1], validate=True)
            sha = hashlib.sha256(raw).hexdigest()
            width, height = integer(pano["width"]), integer(pano["height"])
            if width < 1 or height < 1:
                raise ImportFailure("Invalid panorama dimensions")
            navigation: list[Json] = []
            for hot in sequence(scene["hotspots"]):
                item = record(hot)
                if item["type"] == "scene":
                    item["targetId"] = ids[string(item["targetId"])]
                    navigation.append(item)
            for position in positions:
                if position.source_scene != old_id:
                    continue
                if (
                    position.panorama_hash != sha
                    or not 0 <= position.x < width
                    or not 0 <= position.y < height
                ):
                    raise ImportFailure("Position is not valid for the imported panorama")
                obj = entity_by_number[position.number]
                yaw, pitch = position.x / width * 360 - 180, 90 - position.y / height * 180
                navigation.append(
                    {
                        "id": f"trial-object-{obj.number:02d}",
                        "type": "info",
                        "targetId": None,
                        "label": f"{obj.number:02d}",
                        "text": obj.introduction(),
                        "yaw": yaw,
                        "pitch": pitch,
                    }
                )
                located.append(
                    {
                        "object_id": obj.number,
                        "stable_object_id": obj.stable_id,
                        "scene_id": ids[old_id],
                        "source_scene_id": old_id,
                        "import_id": import_id,
                        "panorama_revision": 1,
                        "panorama_sha256": sha,
                        "panorama_hash_basis": "decoded JPEG bytes",
                        "pixel_center": [position.x, position.y],
                        "yaw": yaw,
                        "pitch": pitch,
                        "basis": position.basis,
                        "state": "executor_located_pending_user_review",
                    }
                )
            scene["sourceSceneId"], scene["id"], scene["hotspots"] = old_id, ids[old_id], navigation
            scene["panoramaRevision"] = 1
        if len(located) != len(positions):
            raise ImportFailure("Unknown measured viewpoint")
        tour["firstSceneId"] = ids[string(tour["firstSceneId"])]
        tour["id"], tour["title"] = (
            import_id,
            string(source.get("title", "PastPort · 匹配环境展示")),
        )
        for scene in scenes:
            if scene.get("view") is None:
                raise ImportFailure("Imported initial viewing direction is missing")
        tour["scenes"] = cast(list[Json], scenes)
        report = {
            "import_id": import_id,
            "input_html_sha256": digest(self.vr),
            "located": located,
            "source_panorama_bytes_preserved": True,
            "viewpoint_count": len(scenes),
            "hotspot_count": len(located),
            "located_object_count": len({p["object_id"] for p in located}),
            "acceptance": "candidate; no independent or user acceptance inferred",
        }
        write_json(self.output / "vr_trial/trial_report.json", report)
        self.render_viewer(tour, entities, located)
        self.database(entities, import_id, frozenset(rejected))
        with closing(sqlite3.connect(self.output / "pastport_matching.sqlite3")) as db, db:
            for relation in relations:
                if relation.verdict != "verified":
                    db.execute(
                        "UPDATE pairings SET proposal_state='invalid_structural_relation',"
                        "image_review='unsuitable',rationale=? WHERE modern_id=?",
                        (relation.reason, relation.part),
                    )
        self.render_review(len(entities) - len(rejected), len(located))
        subprocess.run(
            [
                sys.executable,
                "-c",
                "; ".join(
                    (
                        "from pathlib import Path",
                        "from vr_content import VRContentService",
                        "from vr_positions import VRPositionService",
                        "from review_server import ReviewRepository",
                        "db=Path('pastport_matching.sqlite3')",
                        "manifest=Path('vr_trial/trial_report.json')",
                        "VRContentService(db).initialize()",
                        "VRPositionService(db,manifest).initialize()",
                        "Path('expanded_dataset.json').write_text(ReviewRepository().dataset())",
                    )
                ),
            ],
            cwd=self.output,
            check=True,
            capture_output=True,
        )
        write_json(
            self.output / "import-manifest.json",
            {
                "import_id": import_id,
                "created_at": datetime.now(UTC).isoformat(),
                "input_pdf_sha256": digest(self.pdf),
                "input_vr_sha256": digest(self.vr),
                "source_pdf_sha256": digest(self.upstream / "source.pdf"),
                "upstream_objects_sha256": digest(self.upstream / "objects.json"),
                "reference_files": {
                    n: digest(self.reference / n)
                    for n in (
                        "review.html",
                        "viewer.html",
                        "review_server.py.template",
                        "vr_content.py.template",
                        "vr_positions.py.template",
                    )
                },
                "scene_ids": ids,
                "objects": len(entities),
                "hotspots": len(located),
                "eligible_candidate_count": len(entities) - len(rejected),
                "excluded_object_numbers": sorted(rejected),
                "review_state": "candidate_unreviewed",
                "reuse": "presentation/persistence code only; no reference database or positions",
            },
        )

    def database(
        self,
        entities: tuple[Entity, ...],
        import_id: str,
        excluded: frozenset[int] = frozenset(),
    ) -> None:
        quotes = {
            integer(record(q)["number"]): record(q)
            for q in sequence(read_json(self.upstream / "quote-regions.json"))
        }
        inputs = record(read_json(self.upstream / "inputs.json"))
        with closing(sqlite3.connect(self.output / "pastport_matching.sqlite3")) as db, db:
            db.executescript((self.output / "schema.sql").read_text())
            db.execute("ALTER TABLE modern_objects ADD COLUMN stable_id TEXT")
            db.execute("ALTER TABLE historical_objects ADD COLUMN image_role TEXT")
            db.execute("ALTER TABLE historical_objects ADD COLUMN image_printed_page INTEGER")
            db.execute("INSERT INTO metadata VALUES (?,?)", ("import_id", import_id))
            db.executemany(
                "INSERT INTO design_references VALUES (?,?,?)",
                (
                    (
                        "W3C Web Annotation",
                        "https://www.w3.org/TR/annotation-model/",
                        "Separate targets, bodies and selectors; exact text and context.",
                    ),
                    (
                        "IIIF region tagging",
                        "https://iiif.io/api/cookbook/recipe/0021-tagging/",
                        "Identify an object region rather than assume whole image scope.",
                    ),
                    (
                        "FiftyOne review UI",
                        "https://docs.voxel51.com/user_guide/app.html",
                        "Object patches with surrounding context; review tags and filters.",
                    ),
                ),
            )
            db.execute(
                "INSERT INTO documents VALUES (?,?,?,?,?)",
                (
                    "heritage",
                    "source.pdf",
                    digest(self.upstream / "source.pdf"),
                    _pdf_page_count(self.upstream / "source.pdf"),
                    "local_user_supplied; public distribution unconfirmed",
                ),
            )
            for photo in sequence(inputs["photos"]):
                row = record(photo)
                n = integer(row["number"])
                size = sequence(row["oriented_size"])
                db.execute(
                    "INSERT INTO photos VALUES (?,?,?,?,?,?,?)",
                    (
                        n,
                        Path(string(row["path"])).name,
                        f"media/photo-{n:02d}.jpg",
                        string(row["path"]),
                        integer(size[0]),
                        integer(size[1]),
                        string(row["sha256"]),
                    ),
                )
            page_contexts: dict[int, str] = {}
            for obj in entities:
                q = quotes[obj.number]
                context = string(q["normalized_text"])
                start, end = integer(q["start"]), integer(q["end"])
                if context[start:end] != obj.quote:
                    raise ImportFailure("Quotation scope disagrees with upstream")
                if obj.text_page in page_contexts and page_contexts[obj.text_page] != context:
                    raise ImportFailure("Conflicting page context")
                page_contexts[obj.text_page] = context
            pages = sorted(set(page_contexts) | {o.image_page for o in entities})
            printed: dict[int, int | None] = {}
            for page in pages:
                result = subprocess.run(
                    [
                        "pdftotext",
                        "-f",
                        str(page),
                        "-l",
                        str(page),
                        str(self.upstream / "source.pdf"),
                        "-",
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                first = result.stdout.strip().splitlines()[0].strip()
                normalized_page = _source_text(result.stdout)
                for obj in entities:
                    if obj.text_page == page and _source_text(obj.quote) not in normalized_page:
                        raise ImportFailure(
                            f"Quote for object {obj.number} is not present on source page {page}"
                        )
                printed[page] = int(first) if first.isdecimal() else None
                context = page_contexts.get(page, " ".join(result.stdout.split()))
                db.execute(
                    "INSERT INTO source_pages VALUES (?,?,?,?,?,?)",
                    (
                        page,
                        printed[page] or 0,
                        result.stdout,
                        context,
                        hashlib.sha256(context.encode()).hexdigest(),
                        "upstream English-column normalized context; original full page retained",
                    ),
                )
                subprocess.run(
                    [
                        "pdftoppm",
                        "-f",
                        str(page),
                        "-l",
                        str(page),
                        "-singlefile",
                        "-scale-to",
                        "1400",
                        "-png",
                        str(self.upstream / "source.pdf"),
                        str(self.output / f"media/source-page-{page:02d}"),
                    ],
                    check=True,
                    capture_output=True,
                )
            # Text-only evidence still needs a portable source image, never an invented
            # historical-object photograph. Existing upstream crops remain unchanged.
            for obj in entities:
                history = self.output / f"media/history-{obj.number:02d}.png"
                if not history.is_file():
                    if obj.image_role != "text_evidence":
                        raise ImportFailure(f"Missing historical image for object {obj.number}")
                    shutil.copyfile(self.output / f"media/source-page-{obj.image_page:02d}.png", history)
            observation_id = 0
            for obj in entities:
                q = quotes[obj.number]
                db.execute(
                    "INSERT OR IGNORE INTO buildings VALUES (?,?,?)",
                    (obj.parent, obj.parent, "Scope retained from selected upstream PDF"),
                )
                db.execute(
                    "INSERT INTO modern_objects VALUES (?,?,?,?,?,?)",
                    (obj.number, obj.name, "现代替代物", obj.boundary, None, obj.stable_id),
                )
                db.execute(
                    "INSERT INTO historical_objects VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        obj.historical_id,
                        obj.parent,
                        obj.parent,
                        obj.historical_name,
                        obj.historical_id,
                        obj.image_page,
                        obj.image_box,
                        f"media/history-{obj.number:02d}.png",
                        "按原文主体与部件范围（见适用限制）",
                        obj.limitation,
                        obj.image_role,
                        printed[obj.image_page],
                    ),
                )
                start, end = integer(q["start"]), integer(q["end"])
                context = string(q["normalized_text"])
                db.execute(
                    "INSERT OR IGNORE INTO passages("
                    "id,pdf_page,start_offset,end_offset,exact_text,prefix,suffix) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (
                        obj.number,
                        obj.text_page,
                        start,
                        end,
                        obj.quote,
                        context[max(0, start - 60) : start],
                        context[end : end + 60],
                    ),
                )
                passage = db.execute(
                    "SELECT id FROM passages WHERE pdf_page=? AND start_offset=? AND end_offset=?",
                    (obj.text_page, start, end),
                ).fetchone()
                if passage is None:
                    raise ImportFailure("Missing passage")
                db.execute(
                    "INSERT INTO text_associations VALUES (?,?,?,?,?,?,?)",
                    (
                        obj.historical_id,
                        passage[0],
                        obj.explanation,
                        "upstream scope retained",
                        obj.limitation,
                        "specified upstream PDF evidence",
                        "unreviewed",
                    ),
                )
                db.execute(
                    "INSERT INTO pairings VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (
                        obj.number,
                        obj.historical_id,
                        "candidate_unreviewed",
                        obj.proxy + "\n" + obj.limitation,
                        "specified upstream PDF; no rematching",
                        None,
                        None,
                        "unreviewed",
                        "unreviewed",
                        0,
                    ),
                )
                db.execute(
                    "INSERT INTO assistant_semantic_audit VALUES (?,?,?,?,?,?)",
                    (
                        obj.historical_id,
                        "候选·待独立验收",
                        obj.explanation,
                        obj.limitation,
                        "upstream execution",
                        "指定PDF与原文证据",
                    ),
                )
                for view in obj.observations:
                    observation_id += 1
                    db.execute(
                        "INSERT INTO observations VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (
                            observation_id,
                            view.photo_number,
                            obj.number,
                            *view.box,
                            "upstream_recorded",
                            view.basis,
                            "upstream_visual_evidence",
                        ),
                    )
                    with Image.open(
                        self.output / f"media/photo-{view.photo_number:02d}.jpg"
                    ) as photo_image:
                        w, h = photo_image.size
                        photo_image.crop(
                            (
                                round(view.box[0] * w),
                                round(view.box[1] * h),
                                round(view.box[2] * w),
                                round(view.box[3] * h),
                            )
                        ).save(
                            self.output / f"media/observation-{observation_id:03d}.jpg", quality=92
                        )
            if db.execute("PRAGMA foreign_key_check").fetchall():
                raise ImportFailure("Foreign key failure")
        with (self.output / "expanded_mapping.csv").open("w", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(
                (
                    "object_number",
                    "stable_id",
                    "modern_name",
                    "historical_id",
                    "historical_name",
                    "review_state",
                )
            )
            writer.writerows(
                (
                    o.number,
                    o.stable_id,
                    o.name,
                    o.historical_id,
                    o.historical_name,
                    "invalid_structural_relation"
                    if o.number in excluded
                    else "candidate_unreviewed",
                )
                for o in entities
            )

    def render_viewer(
        self, tour: Record, entities: tuple[Entity, ...], located: list[Record]
    ) -> None:
        template = (self.reference / "viewer.html").read_text()

        def insert_tour(match: re.Match[str]) -> str:
            payload = json.dumps(tour, ensure_ascii=False).replace("</", "<\\/")
            return match[1] + payload + match[2]

        template, count = re.subn(
            r'(<script id="tour-data" type="application/json">).*?(</script>)',
            insert_tour,
            template,
            flags=re.S,
        )
        if count != 1:
            raise ImportFailure("Missing reference tour slot")
        active = len({integer(p["object_id"]) for p in located})
        summary = (
            '<aside id="trial-summary">点击透明编号查看介绍 · '
            f"{active}项独立候选，{len(located)}处重新定位热点；"
            f"{len(entities) - active}项待修正。<br>"
            "现代物件承载历史信息；来源与替代设定分开。候选尚未独立验收。<br>"
            '<a href="comparison.html" target="_blank" '
            'style="color:white;pointer-events:auto">完整结果与定位依据</a></aside>'
        )
        template = re.sub(
            r'<aside id="trial-summary">.*?</aside>', lambda _: summary, template, flags=re.S
        )
        (self.output / "vr_trial/index.html").write_text(template)
        rows = "".join(
            f"<tr><td>{escape(str(p['object_id']))}</td>"
            f"<td>{escape(str(p['source_scene_id']))}</td>"
            f"<td>{escape(str(p['pixel_center']))}</td><td>{escape(str(p['basis']))}</td></tr>"
            for p in located
        )
        (self.output / "vr_trial/comparison.html").write_text(
            '<!doctype html><meta charset="utf-8"><title>定位依据</title><style>'
            "body{font:16px system-ui;margin:32px;background:#f4f2ed;color:#183b34}"
            "td,th{padding:12px;border:1px solid #bbb}table{border-collapse:collapse}"
            "</style><h1>本轮重新定位依据</h1><p>仅复用Demo展示代码。"
            "像素位置在本轮原全景上重新量取，不复制旧热点；均待独立验收。</p>"
            '<p><a href="/">审核后台</a> · <a href="index.html">VR</a> · '
            '<a href="trial_report.json">完整版本与坐标记录</a></p>'
            "<table><tr><th>编号</th><th>源视点</th><th>原图像素</th><th>识别依据</th></tr>"
            + rows
            + "</table>"
        )
        for scene in sequence(tour["scenes"]):
            sc = record(scene)
            pano = record(sc["panorama"])
            from io import BytesIO

            raw = base64.b64decode(string(pano["data"]).split(",", 1)[1])
            with Image.open(BytesIO(raw)) as source:
                im = source.copy()
            draw = ImageDraw.Draw(im)
            for row in located:
                if row["scene_id"] == sc["id"]:
                    xy = sequence(row["pixel_center"])
                    x, y = integer(xy[0]), integer(xy[1])
                    draw.ellipse((x - 14, y - 14, x + 14, y + 14), outline="yellow", width=3)
                    draw.text(
                        (x + 18, y - 15),
                        str(row["object_id"]),
                        fill="yellow",
                        stroke_width=2,
                        stroke_fill="black",
                        font_size=25,
                    )
            im.save(self.output / f"evidence/located-{string(sc['id'])}.jpg", quality=92)

    def render_review(self, count: int, hotspots: int) -> None:
        text = (self.reference / "review.html").read_text()
        upstream = record(read_json(self.upstream / "objects.json"))
        title = escape(string(upstream.get("title", "PastPort")))
        text = text.replace("<h2>PastPort · 图文配对复核</h2>", f"<h2>{title} · 图文配对复核</h2>")
        inputs = record(read_json(self.upstream / "inputs.json"))
        if any(
            record(photo).get("source_kind") == "matched_pdf_page_render_not_original_photo"
            for photo in sequence(inputs["photos"])
        ):
            text = text.replace("你的照片：同一对象的全部视角", "输入PDF中同一对象的全部照片选区")
            text = text.replace("照片 ${String(v.photo_id)", "PDF页 ${String(v.photo_id)")
            text = text.replace("查看完整照片", "查看完整PDF页视图")
        labels: dict[str, str] = {}
        for i, value in enumerate(sequence(upstream["objects"]), 1):
            obj = record(value)
            label = obj.get("history_key", f"H{i}")
            labels[string(obj["history_id"])] = (
                string(label) if isinstance(label, str) and 0 < len(label) <= 80 else f"H{i}"
            )
        payload = json.dumps(labels, ensure_ascii=False).replace("</", "<\\/")
        text = text.replace(
            "<script>",
            '<script id="source-labels" type="application/json">'
            + payload
            + "</script><script>\nconst sourceLabels=JSON.parse("
            + 'document.getElementById("source-labels").textContent);',
            1,
        )
        text = text.replace(
            "esc(o.historical_id||'未分配来源')",
            "esc(sourceLabels[o.historical_id]||o.historical_id||'未分配来源')",
        )
        text = text.replace(
            "esc(o.proposal_state)",
            "esc(o.proposal_state==='candidate_unreviewed'?'候选·待审核':o.proposal_state==='invalid_structural_relation'?'关系未确认或不成立·不计数':o.proposal_state)",
        )
        text = text.replace("' · '+esc(s.id)", "' · '+esc(sourceLabels[s.id]||s.id)")
        text = text.replace("<p>${esc(s.title_en)}</p>", "<p>${esc(s.parent_ref)}</p>")
        text = text.replace("||1;const $", "||0;const $")
        text = text.replace("))id=1;", "))id=data.objects[0].id;")
        text = text.replace(
            "叙事优先的合成演示：代理可以跨类别，但编号稳定、来源真实。图片关联与文字适用性分别复核。",
            "指定PDF的现代替代展示候选：编号与来源保留。尚未独立验收；图片关联与文字适用性分别复核。",
        )
        text = text.replace("${s.image_page+109}", "${s.image_printed_page??'未识别'}").replace(
            "${s.text_page+109}", "${s.text_printed_page??'未识别'}"
        )
        text = text.replace("中文译文（人工整理，未独立审校）", "中文说明（按上游英文原文整理）")
        text = text.replace(
            "展开完整文字页上下文及精确支持位置", "展开英文文字栏上下文及精确支持位置"
        )
        text = text.replace("下方展开文字页上下文", "下方展开英文文字栏上下文")
        text = text.replace("查看AI初始草稿", "查看初始内容草稿").replace(
            "AI草稿（尚未人工修改，默认展示）", "上游PDF内容草稿（尚未人工修改）"
        )
        text = text.replace(
            "历史映射已经变化，请先核对内容与新来源；当前禁止直接覆盖。",
            "历史绑定或整体与部件关系不成立，请先复核；当前禁止直接覆盖。",
        )
        text = text.replace(
            "这是中文改述，原文保留在下方；不是用户批准。",
            "这是上游中文说明，英文证据保留在下方；不是用户批准。",
        )
        text = text.replace(
            "当前独立重匹配提案：37个对象、66处热点；编号点击显示文字，人工拖拽后自动保存。05号背包及36号运动鞋未放置；身份疑点以VR页面说明为准。",
            f"本轮{count}个PDF候选物件、{hotspots}处重新定位热点。未在某视点确认的物件不补造热点；编号点击显示文字，人工拖拽后自动保存。候选尚未独立验收。",
        )
        text = text.replace("下载当前39项映射表", "下载生成时映射状态快照")
        text = re.sub(
            r"已撤下扶手椅→学生房.*?不能视为已拍到的实物。",
            f"原PDF记录保留；本轮{count}项候选可继续核验，结构关系不成立的项保留证据但不计数、不挂载。源文不可通过弹窗编辑改写。",
            text,
        )
        text = text.replace(
            "此对象当前没有放置VR热点，因此还没有弹窗内容。05号背包尚未定位；其他未纳入本轮的对象保持原状。",
            "此对象目前没有经本轮定位的热点，不补造位置；原文证据仍可在此审核。",
        )
        (self.output / "index.html").write_text(text)
        inputs = record(read_json(self.upstream / "inputs.json"))
        photo_count = len(sequence(inputs["photos"]))
        scene_count = integer(
            record(read_json(self.output / "vr_trial/trial_report.json"))["viewpoint_count"]
        )
        pdf_pages = integer(inputs["input_page_count"])
        landing = (self.reference / "landing.html").read_text()
        landing = landing.replace(
            "同一套原始成品快照：映射 PDF、图文配对复核和可编辑 VR。",
            "本轮指定PDF、图文配对复核和重新定位的可编辑VR。",
        )
        landing = (
            landing.replace(
                "原始52页",
                f"{pdf_pages}页",
            )
            .replace(
                "52页",
                f"{pdf_pages}页",
            )
            .replace(
                "39个对象、20张照片、93处出现位置",
                f"{count}个候选物件、{photo_count}张照片及全部已记录视角",
            )
        )
        landing = landing.replace(
            "2个点位、37个对象、66处热点",
            f"{scene_count}个本轮导入视点、{count}个候选物件、{hotspots}处重新定位热点",
        )
        landing = landing.replace(
            "这是人工辅助完成的演示参照，不代表自动化生产流程或所有历史与身份判断均已通过审核。",
            "本轮候选待用户独立验收。现代替代物不是历史文物；无付费调用、无发布。",
        )
        (self.output / "demo.html").write_text(landing)


def _source_text(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).replace("\u00ad", "").split())


def _pdf_page_count(path: Path) -> int:
    with path.open("rb") as stream:
        return len(PdfReader(stream, strict=True).pages)


def reference_assets() -> Path:
    """Resolve the packaged, data-free demonstrated presentation counterpart."""
    return Path(str(files("pastport_matched_environment").joinpath("reference_environment")))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, default=reference_assets())
    for name in ("upstream", "pdf", "vr", "locations", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    try:
        CandidateBuilder(
            args.reference, args.upstream, args.pdf, args.vr, args.locations, args.output
        ).build()
    except (OSError, sqlite3.Error, subprocess.CalledProcessError, ImportFailure) as error:
        raise SystemExit(
            f"Candidate import failed; partial directory retained for diagnosis: {error}"
        ) from error


if __name__ == "__main__":
    main()
