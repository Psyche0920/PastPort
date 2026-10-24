"""Load explicit packaged policy versions for injected semantic adapters."""

from importlib.resources import files
from typing import Literal


def load_semantic_prompt(
    kind: Literal["scene_inspection", "evidence_association", "popup_draft", "pdf_matching"],
    version: str = "v1",
) -> str:
    if (
        kind not in ("scene_inspection", "evidence_association", "popup_draft", "pdf_matching")
        or version != "v1"
    ):
        raise ValueError("Unsupported semantic prompt binding")
    return (
        files("pastport_pdf_vr")
        .joinpath("prompts", f"{kind}_{version}.txt")
        .read_text(encoding="utf-8")
    )
