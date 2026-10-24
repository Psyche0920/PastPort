"""Explicit standalone composition; no SDK construction inside semantic business services."""

from pathlib import Path
from typing import Literal

from pydantic import TypeAdapter

from pastport_pdf_vr.adapters.assets import LocalAssetStore
from pastport_pdf_vr.adapters.codex_sdk import CodexSDKTransport
from pastport_pdf_vr.adapters.codex_semantics import CodexSemanticGateway, EvidenceImageBinding
from pastport_pdf_vr.adapters.execution import SubscriptionExecutor
from pastport_pdf_vr.application.bootstrap import atomic_write
from pastport_pdf_vr.domain.evidence import DraftRequest, EvidenceSelection
from pastport_pdf_vr.domain.execution import SubscriptionGrant
from pastport_pdf_vr.domain.models import DomainModel
from pastport_pdf_vr.domain.recognition import SceneInspectionRequest


def run_codex_request(
    kind: Literal["inspect", "associate", "draft"],
    request_path: Path,
    grant_path: Path,
    assets_path: Path,
    workspace: Path,
    output_path: Path,
    bindings_path: Path | None = None,
) -> None:
    for path in (request_path, grant_path, bindings_path):
        if path is not None and path.stat().st_size > 1024 * 1024:
            raise ValueError("Codex request/config exceeds the 1 MiB input bound")
    grant = SubscriptionGrant.model_validate_json(grant_path.read_bytes())
    transport = CodexSDKTransport(grant.effort)
    bindings = (
        TypeAdapter(tuple[EvidenceImageBinding, ...]).validate_json(bindings_path.read_bytes())
        if bindings_path
        else ()
    )
    gateway = CodexSemanticGateway(
        SubscriptionExecutor(workspace / "codex-executions.sqlite3", grant, transport),
        LocalAssetStore(assets_path),
        bindings,
    )
    raw = request_path.read_bytes()
    result: DomainModel
    if kind == "inspect":
        result = gateway.inspect(SceneInspectionRequest.model_validate_json(raw))
    elif kind == "associate":
        result = gateway.associate(EvidenceSelection.model_validate_json(raw))
    else:
        result = gateway.draft(DraftRequest.model_validate_json(raw))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(output_path, result.model_dump_json())
