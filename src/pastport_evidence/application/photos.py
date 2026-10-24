"""Register photos and identify repeated objects without interpreting them as panoramas."""

from __future__ import annotations

import hashlib
import io
import warnings
from pathlib import Path
from typing import Protocol

from PIL import Image, ImageOps, UnidentifiedImageError

from pastport_evidence.application.bootstrap import atomic_write
from pastport_evidence.domain.photos import (
    PhotoInspection,
    PhotoInspectionRequest,
    PhotoInventory,
    PhotoObservation,
    PhotoReference,
    ScenePhoto,
)
from pastport_evidence.ports.assets import AssetStore
from pastport_evidence.ports.identity import SceneRepository


class PhotoInputError(ValueError):
    """An ordinary photograph exceeds its declared format or resource bounds."""


class PhotoInspector(Protocol):
    def inspect_photos(self, request: PhotoInspectionRequest) -> PhotoInspection: ...


class PhotoRegistrar:
    def __init__(self, assets: AssetStore) -> None:
        self.assets = assets

    def register(self, project: str, paths: tuple[Path, ...]) -> tuple[ScenePhoto, ...]:
        if not 1 <= len(paths) <= 100:
            raise PhotoInputError("Supply between 1 and 100 photographs")
        if len(set(paths)) != len(paths) or any(p.is_symlink() or not p.is_file() for p in paths):
            raise PhotoInputError("Photographs must be unique regular files")
        if sum(p.stat().st_size for p in paths) > 200 * 1024 * 1024:
            raise PhotoInputError("Photographs exceed the 200 MiB total limit")
        photos: list[ScenePhoto] = []
        seen: set[str] = set()
        for path in paths:
            if path.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp"):
                raise PhotoInputError("Photographs must be JPEG, PNG or WebP")
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("error", Image.DecompressionBombWarning)
                    with Image.open(path) as raw:
                        if raw.format not in ("JPEG", "PNG", "WEBP"):
                            raise PhotoInputError("Unsupported photograph encoding")
                        if raw.width * raw.height > 40_000_000:
                            raise PhotoInputError("Photograph exceeds 40 megapixels")
                        media = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}[
                            raw.format
                        ]
                        original = self.assets.register_file(
                            project, path, media, 30 * 1024 * 1024
                        ).reference
                        if original.asset.sha256 in seen:
                            raise PhotoInputError("Duplicate photograph content")
                        seen.add(original.asset.sha256)
                        with (
                            ImageOps.exif_transpose(raw) as oriented,
                            oriented.convert("RGB") as image,
                        ):
                            image.thumbnail((2048, 2048))
                            buffer = io.BytesIO()
                            image.save(buffer, "JPEG", quality=88)
                            reference = self.assets.register_bytes(
                                project, buffer.getvalue(), "image/jpeg", 4 * 1024 * 1024
                            ).reference
                            photos.append(
                                ScenePhoto(
                                    photo_id="photo:" + original.asset.sha256,
                                    name=path.name,
                                    original=original,
                                    image=reference,
                                    width=image.width,
                                    height=image.height,
                                )
                            )
            except (
                OSError,
                UnidentifiedImageError,
                Image.DecompressionBombError,
                Image.DecompressionBombWarning,
            ) as error:
                raise PhotoInputError("Photograph cannot be safely decoded") from error
        return tuple(photos)


class PhotoRecognitionService:
    def __init__(
        self, repository: SceneRepository, inspector: PhotoInspector, assets: AssetStore
    ) -> None:
        self.repository, self.inspector, self.assets = repository, inspector, assets

    def run(
        self,
        project: str,
        photos: tuple[ScenePhoto, ...],
        artifacts: Path,
        grant: str,
        model: str,
        max_calls: int,
    ) -> PhotoInventory:
        target = artifacts / "photo-inventory.json"
        if target.exists():
            cached = PhotoInventory.model_validate_json(target.read_bytes())
            if cached.photos != photos:
                raise PhotoInputError("Cached photo inventory belongs to changed inputs")
            return cached
        observations: list[PhotoObservation] = []
        receipts: list[str] = []
        gaps: list[str] = []
        calls = 0
        # Persist each request before dispatch: resumption uses its original catalog, not
        # a later expanded catalog that would change the immutable execution-cache key.
        for phase in ("inventory", "recheck"):
            known_ids = {e.object_id for e in self.repository.list_entities(project)}
            pending = {
                p.photo_id
                for p in photos
                if any(
                    o.photo.photo_id == p.photo_id and o.identity_state == "uncertain"
                    for o in observations
                )
                or known_ids - {o.object_id for o in observations if o.photo.photo_id == p.photo_id}
            }
            for batch_number, offset in enumerate(range(0, len(photos), 4)):
                batch = photos[offset : offset + 4]
                if phase == "recheck" and not any(p.photo_id in pending for p in batch):
                    continue
                if calls >= max_calls:
                    gaps.append(f"photo_call_budget_exhausted:{phase}:{batch_number}")
                    continue
                request_path = artifacts / f"photo-request-{phase}-{batch_number}.json"
                if request_path.exists():
                    request = PhotoInspectionRequest.model_validate_json(request_path.read_bytes())
                    if (
                        request.photos != batch
                        or request.grant_ref != grant
                        or request.model_id != model
                    ):
                        raise PhotoInputError("Saved photo request differs from bound inputs")
                else:
                    references: dict[str, PhotoReference] = {}
                    for observation in observations:
                        if observation.identity_state == "confirmed":
                            references.setdefault(
                                observation.object_id,
                                PhotoReference(
                                    object_id=observation.object_id,
                                    image=observation.crop,
                                    basis=observation.basis,
                                ),
                            )
                    request = PhotoInspectionRequest(
                        photos=batch,
                        references=tuple(references.values())[:4],
                        catalog=self.repository.list_entities(project),
                        phase=phase,
                        grant_ref=grant,
                        model_id=model,
                    )
                    atomic_write(request_path, request.model_dump_json())
                result = self.inspector.inspect_photos(request)
                self.validate(request, result)
                calls += 1
                receipts.append(result.receipt_ref)
                binding = hashlib.sha256(request.model_dump_json().encode()).hexdigest()
                aliases = self.repository.resolve_proposals(project, binding, result.entities)
                ids = {e.object_id: e.object_id for e in request.catalog}
                ids.update({key: entity.object_id for key, entity in aliases.items()})
                for sighting in result.sightings:
                    oid = ids[sighting.target_ref]
                    photo = next(p for p in batch if p.photo_id == sighting.photo_id)
                    box = sighting.region
                    with Image.open(self.assets.resolve_path(photo.image)) as image:
                        with image.crop(
                            (
                                int(box.top_left.x),
                                int(box.top_left.y),
                                int(box.bottom_right.x + 0.999),
                                int(box.bottom_right.y + 0.999),
                            )
                        ) as crop:
                            buffer = io.BytesIO()
                            crop.save(buffer, "JPEG", quality=88)
                    crop_ref = self.assets.register_bytes(
                        project, buffer.getvalue(), "image/jpeg", 4 * 1024 * 1024
                    ).reference
                    observation = PhotoObservation(
                        object_id=oid,
                        photo=photo,
                        region=box,
                        crop=crop_ref,
                        identity_state=sighting.identity_state,
                        basis=sighting.basis,
                    )
                    observations = [
                        o
                        for o in observations
                        if (o.object_id, o.photo.photo_id) != (oid, photo.photo_id)
                    ]
                    observations.append(observation)
                gaps.extend(result.gaps)
        inventory = PhotoInventory(
            photos=photos,
            entities=self.repository.list_entities(project),
            observations=tuple(observations),
            receipt_refs=tuple(receipts),
            gaps=tuple(dict.fromkeys(gaps)),
        )
        atomic_write(target, inventory.model_dump_json())
        return inventory

    @staticmethod
    def validate(request: PhotoInspectionRequest, result: PhotoInspection) -> None:
        known = {e.object_id for e in request.catalog}
        proposals = [e.proposal_id for e in result.entities]
        if len(set(proposals)) != len(proposals) or known.intersection(proposals):
            raise PhotoInputError("Photo response changed proposal identities")
        if any(e.existing_object_id and e.existing_object_id not in known for e in result.entities):
            raise PhotoInputError("Photo response references an unknown existing object")
        if request.phase == "recheck" and result.entities:
            raise PhotoInputError("A focused recheck cannot allocate new identities")
        allowed = known | set(proposals)
        photos = {p.photo_id: p for p in request.photos}
        seen: set[tuple[str, str]] = set()
        for sighting in result.sightings:
            if sighting.target_ref not in allowed or sighting.photo_id not in photos:
                raise PhotoInputError("Photo sighting changed object/photo identity")
            photo = photos[sighting.photo_id]
            region = sighting.region
            if (
                region.top_left.x < 0
                or region.top_left.y < 0
                or region.bottom_right.x > photo.width
                or region.bottom_right.y > photo.height
            ):
                raise PhotoInputError("Photo selection exceeds its actual pixel dimensions")
            key = (sighting.target_ref, sighting.photo_id)
            if key in seen:
                raise PhotoInputError("Duplicate object sighting within one photograph")
            seen.add(key)
