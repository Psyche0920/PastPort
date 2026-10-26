"""Typed decisions for one initial generation and at most one repair round."""

from typing import Literal

from pastport_matched_environment.domain.models import DomainModel
from pydantic import Field


class StylizationPlan(DomainModel):
    action: Literal["generate", "needs_input"]
    scene_ids: tuple[str, ...]
    art_direction: str = Field(min_length=1, max_length=2000)
    consistency_notes: str = Field(max_length=1500)
    reason: str = Field(max_length=1000)


class StylizationIssue(DomainModel):
    severity: Literal["critical", "minor"]
    category: Literal["blur", "cross_view_conflict", "identity_or_structure", "style_deviation"]
    scene_ids: tuple[str, ...] = Field(min_length=1, max_length=2)
    observation: str = Field(min_length=1, max_length=320)
    correction: str = Field(min_length=1, max_length=320)


class StylizationReview(DomainModel):
    scene_ids: tuple[str, ...]
    issues: tuple[StylizationIssue, ...] = Field(max_length=2)
    summary: str = Field(min_length=1, max_length=2000)


class StylizationAgentReport(DomainModel):
    profile_id: str
    plan: StylizationPlan
    initial_reviews: tuple[StylizationReview, ...]
    repair_rounds: Literal[0, 1]
    final_reviews: tuple[StylizationReview, ...]
    status: Literal["model_review_pass", "needs_human_review"]
    reviewed_scope: Literal["panorama_imagery_only"] = "panorama_imagery_only"
    geometry_repair: Literal["not_performed"] = "not_performed"
    human_acceptance: Literal["pending"] = "pending"
