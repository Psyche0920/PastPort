"""Read and verify a source-bound appearance manifest without executing stylization."""

from pathlib import Path

from pastport_matched_environment.application.reference_environment import digest, read_json, record
from pastport_matched_environment.domain.appearance import Style3DVariant
from pastport_matched_environment.domain.scene3d import MarbleScene


def current_style(root: Path) -> Style3DVariant | None:
    path = root / "scene3d/style-variant.json"
    if not path.is_file():
        return None
    variant = Style3DVariant.model_validate_json(path.read_bytes())
    attachment = record(read_json(root / "scene3d/attachment.json"))
    scene = MarbleScene.model_validate(attachment["scene"])
    if variant.scene_binding != attachment["binding"] or variant.world_id != scene.scene_id:
        raise ValueError("Styled asset belongs to another scene")
    folder = root / "scene3d"
    if (
        digest(folder / variant.splat) != variant.splat_sha256
        or digest(folder / variant.base_splat) != variant.base_splat_sha256
        or digest(folder / variant.panorama) != variant.panorama_sha256
    ):
        raise ValueError("Styled asset bytes changed")
    return variant
