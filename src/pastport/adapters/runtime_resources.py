"""Resolve the single shared host distribution without requiring a checkout."""

from importlib.resources import files
from pathlib import Path

from pastport.application.models import ServiceError


def runtime_root() -> Path:
    """Prefer installed resources; use source counterparts only during development."""
    installed = Path(str(files("pastport").joinpath("runtime_assets")))
    if (installed / "tools/gameplay_lifecycle.mjs").is_file():
        return installed
    checkout = Path(__file__).resolve().parents[3]
    if (checkout / "tools/gameplay_lifecycle.mjs").is_file():
        return checkout
    raise ServiceError("GAMEPLAY_HOST_MISSING", "Shared gameplay host resources are missing")


def skill_root() -> Path:
    """Support both wheel resources and the editable monorepo installation."""
    installed = Path(str(files("pastport").joinpath("bundled_skills")))
    if (installed / "narrative/SKILL.md").is_file():
        return installed
    checkout = Path(__file__).resolve().parents[3] / "skills"
    if (checkout / "narrative/SKILL.md").is_file():
        return checkout
    raise ServiceError("GAMEPLAY_SKILLS_MISSING", "Canonical shared Skills are missing")
