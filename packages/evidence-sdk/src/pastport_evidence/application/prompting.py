"""Load explicit packaged policy versions for injected semantic adapters."""

from importlib.resources import files
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
        "photo_inspection": "v1",
        "pdf_matching": "v2",
        "evidence_association": "v2",
    }
    if profiles[kind] != version:
        raise ValueError("Unsupported semantic prompt binding")
    return (
        files("pastport_evidence")
        .joinpath("prompts", f"{kind}_{version}.txt")
        .read_text(encoding="utf-8")
    )
