"""Load explicit packaged policy versions for injected semantic adapters."""

from importlib.resources import files
from typing import Literal


def load_semantic_prompt(
    kind: Literal[
        "scene_inspection",
        "evidence_association",
        "popup_draft",
        "pdf_matching",
        "photo_inspection",
    ],
    version: str = "v1",
) -> str:
    if kind not in (
        "scene_inspection",
        "evidence_association",
        "popup_draft",
        "pdf_matching",
        "photo_inspection",
    ) or (
        version != "v1"
        and not (version == "v2" and kind in ("pdf_matching", "evidence_association"))
    ):
        raise ValueError("Unsupported semantic prompt binding")
    return (
        files("pastport_pdf_vr")
        .joinpath("prompts", f"{kind}_{version}.txt")
        .read_text(encoding="utf-8")
    )
