"""Source-bound review data; confirming input does not approve historical claims."""
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from pydantic import Field
from pastport.domain.common import Contract, Identifier, Sha256
from pastport.domain.story_inputs import EnvironmentPosition, SpatialObjectLocation

class OrganizerReviewBinding(Contract):
    root: Path
    worlds: tuple[Path, ...] = Field(min_length=1, max_length=2)
    import_sha256: Sha256

class ReviewChange(Contract):
    kind: Literal["review", "introduction"]
    expected_version: int = Field(ge=0)
    image: Literal["unreviewed", "suitable", "unsuitable", "uncertain"] = "unreviewed"
    text: Literal["unreviewed", "direct", "context_only", "unsuitable", "uncertain"] = "unreviewed"
    note: str = Field(default="", max_length=4000)
    content: str = Field(default="", max_length=1500)

class ReviewImage(Contract):
    asset_id: Identifier
    caption: str

class ObjectReviewHistory(Contract):
    image: str
    text: str
    note: str
    reviewer: str
    created_at: str

class OrganizerReviewObject(Contract):
    number: int
    stable_id: str
    name: str
    historical_id: str | None
    historical_title: str | None
    rationale: str
    image_review: str
    text_review: str
    pairing_version: int
    introduction: str | None
    introduction_version: int | None
    quote: str | None
    quote_page: int | None
    scope_warning: str
    photos: tuple[ReviewImage, ...]
    source_image: ReviewImage | None
    history: tuple[ObjectReviewHistory, ...]
    positions: tuple[EnvironmentPosition, ...]
    locations: tuple[SpatialObjectLocation, ...]

class OrganizerReviewView(Contract):
    source_format: Literal["pdf", "idml"] = "pdf"
    view_count: int = Field(default=2, ge=1, le=2)
    database_path: Path
    source_id: Identifier
    project_id: Identifier
    title: str
    revision: Sha256
    snapshot_current: bool
    objects: tuple[OrganizerReviewObject, ...]

class ReviewAcknowledgment(Contract):
    revision: Sha256

class NativeReviewWrite(Contract):
    object_id: int = Field(ge=1)
    version: int = Field(ge=0)
    image: Literal["unreviewed", "suitable", "unsuitable", "uncertain"]
    text: Literal["unreviewed", "direct", "context_only", "unsuitable", "uncertain"]
    note: str = Field(default="", max_length=4000)
    reviewer: str = Field(default="", max_length=100)

class NativeIntroductionWrite(Contract):
    object_id: int = Field(ge=1)
    version: int = Field(ge=0)
    content: str = Field(min_length=1, max_length=1500)
    editor: str = Field(default="", max_length=100)


@dataclass(frozen=True, slots=True)
class ReviewEnvironmentResource:
    body: bytes | None = None
    path: Path | None = None
    media_type: str | None = None
    status: int = 200
