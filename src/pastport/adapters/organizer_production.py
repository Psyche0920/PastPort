"""Real SDK composition for registered mounted environments and saved Story runs."""

import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory

from pastport.adapters.game_making import SDKGameMakingStages
from pastport.adapters.runtime_resources import skill_root
from pastport.adapters.story_materials import StoryMaterialReader
from pastport.application.game_making import GameMakingWorkflow
from pastport.application.models import ServiceError
from pastport.domain.common import CanonicalSerializer
from pastport.domain.game_making import GameMakingRequest
from pastport.domain.organizer import OrganizerStart


class SDKOrganizerProduction:
    def validate(self, request: GameMakingRequest) -> None:
        StoryMaterialReader().read(
            request.original_pdf,
            request.source_document,
            request.environment,
            request.media_directory,
        )
        # Reuse native identity/resource checks without mutating the registered inputs.
        with TemporaryDirectory(prefix="pastport-organizer-check-") as directory:
            SDKGameMakingStages().validate_inputs(
                request.model_copy(update={"output_directory": Path(directory)})
            )

    async def run(
        self,
        request: GameMakingRequest,
        start: OrganizerStart,
        output: Path,
        *,
        resume: bool = False,
    ) -> None:
        self.validate(request)
        production = request.model_copy(update={"output_directory": output})
        if start.mode == "regenerate":
            if not start.authorize_model:
                raise ServiceError(
                    "MODEL_AUTHORIZATION_REQUIRED", "请先确认本次生成会调用模型。", 422
                )
            story = output / "fresh-story"
            skills = skill_root()
            production = production.model_copy(update={"skills_directory": skills})
            if story.exists() and not resume:
                # A dispatched request may still have effects. Never redispatch on resume.
                raise ServiceError(
                    "STORY_RECONCILIATION_REQUIRED",
                    "已存在生成记录，请先核对回执，不能直接再次调用。",
                    409,
                )
            brief = (start.brief or request.brief) + (
                f"\nTarget player experience: approximately {start.target_minutes} minutes; "
                "this is a pacing objective, not a guaranteed duration."
            )
            await SDKGameMakingStages().author_story(
                request,
                story,
                brief=brief,
                skills_directory=skills,
                revalidate_saved_response=resume,
            )
            production = production.model_copy(update={"saved_story_run": story, "brief": brief})
        # A code update gets a new local build attempt, while the already charged
        # Story run stays pinned and is only revalidated. Never alter old locks.
        stages = SDKGameMakingStages()
        build_identity = hashlib.sha256(
            (CanonicalSerializer.digest(production) + stages.identity()).encode()
        ).hexdigest()
        production = production.model_copy(
            update={
                "output_directory": output / "builds" / build_identity,
            }
        )
        pointer = output / "organizer-production-request.json"
        temporary = pointer.with_suffix(".pending")
        temporary.write_text(production.model_dump_json(indent=2))
        temporary.replace(pointer)
        # Story preparation stops before gameplay, presentation and assembly.
        if start.stop_after == "story":
            production.output_directory.mkdir(parents=True, exist_ok=True)
            await stages.story(production)
            return
        # Saved-response revalidation has no provider dispatch, including after fresh generation.
        await GameMakingWorkflow(stages).run(production)
        # Do not copy, rebuild or edit the registered review database here.
