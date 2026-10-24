from typing import Literal

from pastport_pdf_vr.domain.geometry import EquirectangularTransform, PixelPoint
from pastport_pdf_vr.domain.models import AssetRef, ProjectAssetRef
from pastport_pdf_vr.domain.recognition import (
    MatchingImage,
    PanoramaView,
    PixelRegion,
    SightingProposal,
)


def asset(name: str = "source", project: str = "test") -> ProjectAssetRef:
    import hashlib

    digest = hashlib.sha256(name.encode()).hexdigest()
    return ProjectAssetRef(
        project_id=project, asset=AssetRef(resource_id="sha256:" + digest, version=1, sha256=digest)
    )


def view(name: str) -> PanoramaView:
    panorama = asset(name)
    levels: tuple[Literal["overview", "detail"], ...] = ("overview", "detail")
    return PanoramaView(
        view_id=name,
        panorama=panorama,
        panorama_revision=1,
        images=tuple(
            MatchingImage(
                image_id=f"{name}:{level}",
                view_id=name,
                image=asset(f"{name}:{level}"),
                panorama=panorama,
                panorama_revision=1,
                inspection_level=level,
                transform=EquirectangularTransform(
                    source_width=800, source_height=400, image_width=400, image_height=200
                ),
            )
            for level in levels
        ),
    )


def sight(target: str, image: str, x: float = 200.0, role: str = "environment") -> SightingProposal:
    return SightingProposal.model_validate(
        {
            "target_ref": target,
            "image_id": image,
            "role": role,
            "disposition": "located",
            "point": PixelPoint(x=x, y=100.0),
            "region": PixelRegion(
                top_left=PixelPoint(x=max(0.0, x - 0.1), y=90.0),
                bottom_right=PixelPoint(x=min(400.0, x + 0.1), y=110.0),
            ),
            "basis": ("Distinctive visible feature inside the selected region",),
        }
    )
