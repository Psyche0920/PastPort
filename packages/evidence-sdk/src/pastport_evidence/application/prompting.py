"""Load explicit packaged policy versions for injected semantic adapters."""

from importlib.resources import files
from pathlib import Path

from pastport_evidence.domain.models import DomainModel
from pastport_evidence.application.bootstrap import atomic_write
from typing import Literal


def load_semantic_prompt(
    kind: Literal[
        "evidence_association",
        "pdf_matching",
        "photo_inspection",
    ],
    version: str = "v1",
) -> str:
    profiles = {
        "photo_inspection": ("v1", "v2", "v3"),
        "pdf_matching": ("v2", "v3", "index-v1"),
        "evidence_association": ("v2", "v3"),
    }
    if version not in profiles[kind]:
        raise ValueError("Unsupported semantic prompt binding")
    return (
        files("pastport_evidence")
        .joinpath("prompts", f"{kind}_{version}.txt")
        .read_text(encoding="utf-8")
    )


class SemanticPromptProfile(DomainModel):
    """Pin new historical-content policy without changing existing run receipts."""

    photo: Literal["v1", "v2", "v3"] = "v1"
    mapping: Literal["v2", "v3"] = "v2"
    evidence: Literal["v2", "v3"] = "v3"


def resolve_prompt_profile(workspace: Path) -> SemanticPromptProfile:
    path = workspace / "semantic-policy.json"
    if path.exists():
        return SemanticPromptProfile.model_validate_json(path.read_bytes())
    legacy = (workspace / "codex-executions.sqlite3").exists() or (
        (workspace / "runs").is_dir() and any((workspace / "runs").iterdir())
    )
    profile = SemanticPromptProfile(photo="v1" if legacy else "v3", mapping="v2" if legacy else "v3", evidence="v2" if legacy else "v3")
    workspace.mkdir(parents=True, exist_ok=True)
    atomic_write(path, profile.model_dump_json())
    return profile
