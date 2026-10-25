"""Attach an existing Marble world to a labelled environment without rematching."""

from __future__ import annotations

import base64
import hashlib
import json
import re
import shutil
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path

from pastport_pdf_vr.application.marble import MarbleImporter, load_scene
from pastport_pdf_vr.application.reference_environment import (
    digest,
    read_json,
    record,
    sequence,
    string,
    write_json,
)
from pastport_pdf_vr.application.storage import atomic_write
from pastport_pdf_vr.domain.models import DomainModel
from pastport_pdf_vr.workflow.graph import (
    FixedStage,
    FixedWorkflow,
    StageCommand,
    StageJournal,
    StageOutput,
)


class Scene3DDelivery(DomainModel):
    environment: str
    scene_binding: str
    source_scene_id: str
    status: str = "pending_alignment_and_manual_acceptance"
    new_model_calls: int = 0


class Scene3DAttachment:
    """Immutable per-workspace attachment; SQLite backup preserves human overrides."""

    def __init__(self, source: Path, world: Path, workspace: Path, source_scene: str) -> None:
        self.source, self.world, self.workspace = (
            source.resolve(),
            world.resolve(),
            workspace.resolve(),
        )
        self.source_scene = source_scene
        self.output = self.workspace / "result"

    def run(self) -> Scene3DDelivery:
        if self.source == self.workspace or self.source in self.workspace.parents:
            raise ValueError("Choose a workspace outside the source environment")
        if not self.world.is_file() or not (self.source / "import-manifest.json").is_file():
            raise ValueError("Provide world.json and an existing matched environment")
        binding = hashlib.sha256(
            (
                str(self.source)
                + digest(self.source / "import-manifest.json")
                + digest(self.source / "vr_trial/index.html")
                + digest(self.world)
                + self.source_scene
            ).encode()
        ).hexdigest()
        self.workspace.mkdir(parents=True, exist_ok=True)
        FixedWorkflow(
            StageJournal(self.workspace / "stages.sqlite3"),
            (
                FixedStage("marble_import", AttachmentStage(self, "import")),
                FixedStage("preserve_environment", AttachmentStage(self, "copy")),
                FixedStage("attach_3d", AttachmentStage(self, "attach")),
            ),
            "scene3d-attachment-v1",
        ).run("scene3d", "attach", binding)
        return Scene3DDelivery.model_validate_json((self.workspace / "delivery.json").read_bytes())

    def import_world(self) -> StageOutput:
        MarbleImporter().prepare(self.world, self.workspace / "marble")
        return StageOutput(references=("asset:existing-marble-world",))

    def preserve(self) -> StageOutput:
        if self.output.exists():
            raise ValueError("Never rebuild an existing review database")
        self.output.mkdir(parents=True)
        total = 0
        for source in self.source.rglob("*"):
            if source.is_symlink():
                raise ValueError("Source environment cannot contain symbolic links")
            if not source.is_file():
                continue
            relative = source.relative_to(self.source)
            if source.suffix in (".py", ".sqlite3") or source.name.endswith(("-wal", "-shm")):
                continue
            total += source.stat().st_size
            if total > 1024**3:
                raise ValueError("Source environment exceeds 1 GiB")
            target = self.output / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        with closing(
            sqlite3.connect(
                f"{(self.source / 'pastport_matching.sqlite3').as_uri()}?mode=ro", uri=True
            )
        ) as src:
            with closing(sqlite3.connect(self.output / "pastport_matching.sqlite3")) as dst:
                src.backup(dst)
        reference = Path(str(files("pastport_pdf_vr").joinpath("reference_environment")))
        for name in ("review_server", "vr_content", "vr_positions", "start_demo"):
            shutil.copy2(reference / f"{name}.py.template", self.output / f"{name}.py")
        return StageOutput(references=("artifact:consistent-environment-backup",))

    def attach(self) -> StageOutput:
        scene = load_scene(self.workspace / "marble")
        original = record(read_json(self.output / "vr_trial/trial_report.json"))
        located = [record(row) for row in sequence(original["located"])]
        choices = {string(row["scene_id"]) for row in located}
        selected = self.source_scene
        if not selected and len(choices) == 1:
            selected = next(iter(choices))
        if selected not in choices:
            raise ValueError(
                "Choose an existing --source-scene from trial_report.json; views "
                "cannot be merged implicitly"
            )
        scene_folder = self.output / "scene3d"
        shutil.copytree(
            self.workspace / "marble", scene_folder, ignore=shutil.ignore_patterns("index.html")
        )
        source_html = (self.output / "vr_trial/index.html").read_text()
        source_match = re.search(
            r'<script id="tour-data" type="application/json">(.*?)</script>', source_html, re.S
        )
        if source_match is None:
            raise ValueError("Missing source panorama data")
        source_tour = record(json.loads(source_match.group(1)))
        source_view = next(
            record(view)
            for view in sequence(source_tour["scenes"])
            if record(view)["id"] == selected
        )
        source_uri = string(record(source_view["panorama"])["data"])
        source_bytes = base64.b64decode(source_uri.split(",", 1)[1], validate=True)
        source_name = (
            "source-panorama.png" if source_bytes.startswith(b"\x89PNG") else "source-panorama.jpg"
        )
        (scene_folder / source_name).write_bytes(source_bytes)
        assets = Path(str(files("pastport_pdf_vr").joinpath("scene3d_assets")))
        for path in assets.iterdir():
            shutil.copy2(path, scene_folder / path.name)
        # Space binding includes the exact new world, frozen source DB and source viewpoint.
        binding = hashlib.sha256(
            (scene.binding + digest(self.output / "pastport_matching.sqlite3") + selected).encode()
        ).hexdigest()
        db_path = self.output / "pastport_matching.sqlite3"
        with closing(sqlite3.connect(db_path)) as db, db:
            db.executescript("""
                CREATE TABLE scene3d_anchors(object_id INTEGER PRIMARY KEY REFERENCES 
                modern_objects(id),
                    historical_id TEXT, version INTEGER NOT NULL DEFAULT 0, point_json TEXT,
                    editor TEXT NOT NULL DEFAULT '', identity_basis TEXT NOT NULL DEFAULT '',
                    relation_basis TEXT NOT NULL DEFAULT '');
                CREATE TABLE scene3d_events(operation_id TEXT PRIMARY KEY, request_sha256 TEXT
                 NOT NULL,
                    object_id INTEGER NOT NULL, previous_version INTEGER NOT NULL,
                    response_json TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE scene3d_alignment(id INTEGER PRIMARY KEY CHECK(id=1),
                    version INTEGER NOT NULL, payload_json TEXT NOT NULL);
            """)
            db.execute(
                "INSERT INTO scene3d_alignment VALUES (1,0,?)",
                (
                    json.dumps(
                        {
                            "confirmed": False,
                            "origin": {"x": 0.0, "y": 1.6, "z": 0.0},
                            "yaw_degrees": 0.0,
                            "pitch_degrees": 0.0,
                            "roll_degrees": 0.0,
                            "editor": "",
                            "basis": "",
                        }
                    ),
                ),
            )
            db.execute(
                "INSERT INTO scene3d_anchors(object_id,historical_id) SELECT "
                "modern_id,historical_id FROM pairings"
            )
            # Snapshot current human positions, never merely the original model report.
            db.row_factory = sqlite3.Row
            rows = [
                dict(row)
                for row in db.execute(
                    """SELECT v.object_id,v.scene_id,
                COALESCE(v.human_yaw,v.model_yaw) AS yaw,
                COALESCE(v.human_pitch,v.model_pitch) AS pitch,
                v.panorama_sha256,v.version FROM vr_positions v JOIN pairings p ON 
                p.modern_id=v.object_id
                WHERE v.scene_id=? AND p.image_review!='unsuitable' AND p.text_review!='unsuitable'
                AND p.proposal_state!='invalid_structural_relation' """,
                    (selected,),
                )
            ]
            db.execute("INSERT OR REPLACE INTO metadata VALUES ('scene3d_binding',?)", (binding,))
        # No conversion is authoritative until the user aligns cameras and confirms identity.
        payload = {
            "scene": json.loads(scene.model_dump_json()),
            "binding": binding,
            "source_scene_id": selected,
            "source_hotspots": rows,
            "source_panorama": source_name,
            "source_import_sha256": digest(self.source / "import-manifest.json"),
            "created_at": datetime.now(UTC).isoformat(),
            "notice": "Generated geometry is not historical evidence. Ray "
            "intersections are unverified candidates.",
        }
        write_json(scene_folder / "attachment.json", payload)
        review = self.output / "index.html"
        review.write_text(
            review.read_text().replace(
                "<body>", '<body><p><a href="/scene3d/index.html">打开 3D 场景与热点校准</a></p>', 1
            )
        )
        atomic_write(
            self.output / "start_3d.py",
            "from pathlib import Path\nfrom "
            "pastport_pdf_vr.application.reference_preview import serve\n"
            "serve(Path(__file__).resolve().parent, port=8796)\n",
        )
        delivery = Scene3DDelivery(
            environment=str(self.output), scene_binding=binding, source_scene_id=selected
        )
        atomic_write(self.workspace / "delivery.json", delivery.model_dump_json())
        return StageOutput(
            references=("artifact:3d-review-environment",),
            gaps=("3d_alignment_and_identity_review_pending",),
        )


class AttachmentStage:
    def __init__(self, owner: Scene3DAttachment, action: str) -> None:
        self.owner, self.action = owner, action

    def execute(self, command: StageCommand) -> StageOutput:
        if self.action == "import":
            return self.owner.import_world()
        if self.action == "copy":
            return self.owner.preserve()
        return self.owner.attach()
