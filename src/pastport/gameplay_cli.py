"""Prepare supported gameplay from a locked Story run, without model or build calls."""

import argparse
import hashlib
from pathlib import Path

from pastport.adapters.gameplay_catalog import load_gameplay_catalog
from pastport.adapters.gameplay_verifier import DemoGameplayVerifier
from pastport.adapters.runtime_resources import runtime_root
from pastport.application.gameplay_preparation import GameplayPreparer
from pastport.application.models import ServiceError
from pastport.application.story_authoring import StoryAuthoringCheck, StoryInputLock
from pastport.domain.common import CanonicalSerializer
from pastport.domain.evidence import SourceIndexDraft
from pastport.domain.modules import NarrativeDraft
from pastport.domain.story_inputs import EnvironmentSnapshot


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--story-run", type=Path, required=True)
    parser.add_argument("--guidance", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--host", choices=("pastport.demo.activities/1",), required=True)
    args = parser.parse_args()
    root = runtime_root()
    draft = NarrativeDraft.model_validate_json(
        (args.story_run / "narrative-draft.json").read_bytes()
    )
    lock = StoryInputLock.model_validate_json((args.story_run / "input-lock.json").read_bytes())
    check = StoryAuthoringCheck.model_validate_json(
        (args.story_run / "story-check.json").read_bytes()
    )
    raw_environment = (args.story_run / "environment-input.json").read_bytes()
    environment = EnvironmentSnapshot.model_validate_json(raw_environment)
    index = SourceIndexDraft.model_validate_json(
        (args.story_run / "source-index.json").read_bytes()
    )
    if (
        check.status != "ready"
        or check.story_draft_sha256 != CanonicalSerializer.digest(draft)
        or check.narrative_sha256 != CanonicalSerializer.digest(draft.package)
        or hashlib.sha256(raw_environment).hexdigest() != lock.environment_sha256
        or CanonicalSerializer.digest(index) != lock.source_index_sha256
    ):
        raise ServiceError(
            "GAMEPLAY_STORY_STALE", "Story check or its locked environment/source index changed"
        )
    guidance = args.guidance.read_bytes()
    if not guidance.startswith(b"---\nname: gameplay-preparation\n"):
        raise ServiceError(
            "GAMEPLAY_GUIDANCE_INVALID", "Expected the existing Gameplay Preparation Skill"
        )
    verifier = DemoGameplayVerifier(root)
    plan = GameplayPreparer(
        verifier,
        verifier.identity(),
        {"pastport.activity.tiling": verifier.identity("tiling")},
        capabilities=load_gameplay_catalog(),
    ).prepare(
        draft,
        CanonicalSerializer.reference(draft.package, "story-gameplay-input", "narrative"),
        environment,
        index,
        hashlib.sha256(guidance).hexdigest(),
    )
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "gameplay-plan.json").write_text(
        plan.model_dump_json(indent=2), encoding="utf-8"
    )
    (args.output / "environment-canonical.json").write_bytes(
        CanonicalSerializer.encode(environment)
    )
    print(f"Gameplay {plan.status}: {len(plan.bindings)} bindings, {len(plan.gaps)} gaps")
    if plan.status != "prepared":
        parser.exit(2, "Gameplay requirements are not executable; inspect the retained plan\n")


if __name__ == "__main__":
    main()
