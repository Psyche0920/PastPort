"""Versioned user-approved visual standard shared by generation and criticism."""

import hashlib
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

from pastport_pdf_vr.domain.models import DomainModel, Sha256


class AnimationStandard(DomainModel):
    profile_id: str
    reference: str
    reference_sha256: Sha256
    policy: str
    policy_sha256: Sha256
    criteria: tuple[str, ...]
    approval: str


@dataclass(frozen=True, slots=True)
class BoundAnimationStyle:
    reference: Path
    policy: Path
    standard: AnimationStandard | None


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def approved_animation_style(workspace: Path | None = None) -> BoundAnimationStyle:
    """A resumed run keeps its frozen style rather than silently adopting v2."""
    if workspace is not None and (workspace / "run-binding.json").is_file():
        reference, policy = workspace / "style.png", workspace / "prompt.txt"
        if not reference.is_file() or not policy.is_file():
            raise ValueError("Saved style/policy is missing; no reset or fallback")
        return BoundAnimationStyle(reference, policy, None)
    root = Path(str(files("pastport_pdf_vr").joinpath("animation_assets")))
    standard = AnimationStandard.model_validate_json((root / "approved-style-v2.json").read_bytes())
    if standard.reference != "approved-style-v2.png" or standard.policy != "policy-v2.txt":
        raise ValueError("Unexpected approved style asset paths")
    reference, policy = root / standard.reference, root / standard.policy
    if sha256(reference) != standard.reference_sha256 or sha256(policy) != standard.policy_sha256:
        raise ValueError("Approved visual standard changed")
    return BoundAnimationStyle(reference, policy, standard)
