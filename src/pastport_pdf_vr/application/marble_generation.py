"""One explicitly authorized panorama generation; resume only polls its saved operation."""

from __future__ import annotations

import base64
import fcntl
import hashlib
import io
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image

from pastport_pdf_vr.application.marble import NoRedirect
from pastport_pdf_vr.application.reference_environment import (
    Record,
    digest,
    read_json,
    record,
    sequence,
    string,
    write_json,
)
from pastport_pdf_vr.application.scene3d import Scene3DAttachment
from pastport_pdf_vr.application.storage import atomic_write


class MarbleHTTP:
    """Fixed API origin, bounded responses, no credentials in files or diagnostics."""

    def __init__(self, key: str) -> None:
        if not key:
            raise ValueError(
                "Set WORLDLABS_API_KEY locally; credentials are never copied into output"
            )
        self.key = key

    def request(self, method: str, path: str, payload: Record | None = None) -> Record:
        request = urllib.request.Request(
            "https://api.worldlabs.ai/marble/v1/" + path,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers={"WLT-Api-Key": self.key, "Content-Type": "application/json"},
            method=method,
        )
        try:
            with urllib.request.build_opener(NoRedirect()).open(request, timeout=60) as response:
                raw = response.read(4 * 1024**2 + 1)
            if len(raw) > 4 * 1024**2:
                raise ValueError("Marble response exceeds the bounded profile")
            return record(json.loads(raw))
        except urllib.error.URLError as error:
            raise RuntimeError(
                "Marble request failed; dispatch state retained, no automatic retry"
            ) from error


class MarbleGeneration:
    """Single-view input, one dispatch, source-bound receipt and explicit finite authorization."""

    def run(
        self,
        environment: Path,
        workspace: Path,
        source_scene: str,
        model: str,
        credit_budget: int,
        authorized: bool,
    ) -> str:
        expected = {"marble-1.1": 1500, "marble-1.0-draft": 150}.get(model)
        if not authorized or expected is None or credit_budget < expected:
            raise ValueError(
                "Authorize exactly one supported generation with sufficient credit budget"
            )
        environment, workspace = environment.resolve(), workspace.resolve()
        if environment == workspace or environment in workspace.parents:
            raise ValueError("Choose a generation workspace outside the source environment")
        html = (environment / "vr_trial/index.html").read_text()
        match = re.search(
            r'<script id="tour-data" type="application/json">(.*?)</script>', html, re.S
        )
        if match is None:
            raise ValueError("Missing registered source tour")
        tour = record(json.loads(match.group(1)))
        views = [record(v) for v in sequence(tour["scenes"])]
        if not source_scene and len(views) == 1:
            source_scene = string(views[0]["id"])
        selected = next((v for v in views if v["id"] == source_scene), None)
        if selected is None:
            raise ValueError("Select the source viewpoint explicitly")
        uri = string(record(selected["panorama"])["data"])
        if not uri.startswith(("data:image/jpeg;base64,", "data:image/png;base64,")):
            raise ValueError("Expected a registered embedded source panorama")
        raw = base64.b64decode(uri.split(",", 1)[1], validate=True)
        if not 0 < len(raw) <= 10 * 1024**2:
            raise ValueError("Inline panorama must fit the 10 MiB provider profile")
        with Image.open(io.BytesIO(raw)) as image:
            if image.width != image.height * 2:
                raise ValueError("Expected a complete equirectangular sphere")
            extension = "png" if image.format == "PNG" else "jpg"
            image.verify()
        binding: Record = {
            "source_import_sha256": digest(environment / "import-manifest.json"),
            "panorama_sha256": hashlib.sha256(raw).hexdigest(),
            "source_scene_id": source_scene,
            "model": model,
            "credit_budget": credit_budget,
            "max_calls": 1,
            "estimated_credits": expected,
            "pricing_reference": "https://docs.worldlabs.ai/api/pricing",
        }
        workspace.mkdir(parents=True, exist_ok=True)
        with (workspace / "generation.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            request_path = workspace / "request.json"
            if request_path.exists():
                if read_json(request_path) != binding:
                    raise ValueError(
                        "Cannot change inputs or authorization within a generation job"
                    )
            else:
                write_json(request_path, binding)
            frozen = workspace / "frozen/result"
            freeze_receipt = workspace / "frozen.json"
            if not freeze_receipt.exists():
                if frozen.exists():
                    raise RuntimeError(
                        "Interrupted source backup needs reconciliation; it will not be rebuilt"
                    )
                Scene3DAttachment(
                    environment, workspace / "world.json", workspace / "frozen", source_scene
                ).preserve()
                write_json(
                    freeze_receipt,
                    {
                        "database_sha256": digest(frozen / "pastport_matching.sqlite3"),
                        "tour_sha256": digest(frozen / "vr_trial/index.html"),
                    },
                )
            frozen_receipt = record(read_json(freeze_receipt))
            if (
                digest(frozen / "pastport_matching.sqlite3") != frozen_receipt["database_sha256"]
                or digest(frozen / "vr_trial/index.html") != frozen_receipt["tour_sha256"]
            ):
                raise ValueError("Frozen source changed; original job cannot be resumed")
            world_path = workspace / "world.json"
            if not world_path.exists():
                client = MarbleHTTP(os.environ.get("WORLDLABS_API_KEY", ""))
                operation_path = workspace / "operation.json"
                if operation_path.exists():
                    operation = record(read_json(operation_path))
                    operation = client.request(
                        "GET",
                        "operations/"
                        + urllib.parse.quote(string(operation["operation_id"]), safe=""),
                    )
                    write_json(operation_path, operation)
                else:
                    marker = workspace / "dispatched.json"
                    if marker.exists():
                        raise RuntimeError(
                            "Prior submission has unknown status. Reconcile it; no "
                            "redispatch allowed"
                        )
                    balance = client.request("GET", "credits")
                    available = balance.get("remaining_credits")
                    if not isinstance(available, (int, float)) or available < expected:
                        raise ValueError("Insufficient known credits; generation was not submitted")
                    write_json(workspace / "credits-before.json", balance)
                    write_json(marker, binding)
                    operation = client.request(
                        "POST",
                        "worlds:generate",
                        {
                            "display_name": "PastPort source-bound scene",
                            "model": model,
                            "permission": {"public": False},
                            "seed": 0,
                            "world_prompt": {
                                "type": "image",
                                "is_pano": True,
                                "disable_recaption": True,
                                "text_prompt": "Preserve the provided scene, "
                                "visible object identities, layout, "
                                "materials and details. Do not "
                                "replace, add or remove objects. "
                                "This guidance is not a fidelity "
                                "guarantee.",
                                "image_prompt": {
                                    "source": "data_base64",
                                    "extension": extension,
                                    "data_base64": base64.b64encode(raw).decode(),
                                },
                            },
                        },
                    )
                    write_json(operation_path, operation)
                if operation.get("error"):
                    raise RuntimeError("Marble operation failed; error and unknown usage retained")
                if not operation.get("done"):
                    return (
                        "pending: resume the same command to poll; "
                        "it will not submit another generation"
                    )
                world = record(operation["response"])
                if "assets" not in world:
                    world = client.request(
                        "GET", "worlds/" + urllib.parse.quote(string(world["world_id"]), safe="")
                    )
                cost = operation.get("cost")
                write_json(workspace / "settled-cost.json", cost)
                if cost is None:
                    raise RuntimeError(
                        "Completed operation has unknown settled credits; retained "
                        "for reconciliation"
                    )
                write_json(world_path, world)
                atomic_write(
                    workspace / "cost-note.txt",
                    "Provider cost is authoritative. The local budget admits one "
                    "estimated-cost job; it is not a provider-enforced hard credit "
                    "cap. No automatic retry or HQ mesh export.\n",
                )
            delivery = Scene3DAttachment(
                frozen, world_path, workspace / "attachment", source_scene
            ).run()
            return delivery.model_dump_json()
