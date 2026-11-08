"""Run Story authoring only, using explicitly selected upstream outputs."""

import argparse
import asyncio
import fcntl
from pathlib import Path

from pastport.adapters.story_materials import StoryMaterialReader
from pastport.adapters.story_workflow import StoryAutomationWorkflow
from pastport.application.models import ServiceError


def main(*, default_skill_directory: Path | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--source-document", type=Path, required=True)
    parser.add_argument("--environment", type=Path, required=True)
    parser.add_argument("--media-directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--skills", type=Path, default=default_skill_directory or Path("skills"))
    parser.add_argument("--brief", required=True)
    parser.add_argument("--revalidate-saved-response", action="store_true")
    parser.add_argument("--accept-recorded-usage", action="store_true",
                        help="Accept existing settled token usage; requires provider-disabled replay")
    parser.add_argument(
        "--structure-profile",
        choices=("compiled_plan_v1", "compiled_branch_v1"),
        default="compiled_plan_v1",
    )
    args = parser.parse_args()
    if args.accept_recorded_usage and not args.revalidate_saved_response:
        parser.error("--accept-recorded-usage requires --revalidate-saved-response")
    args.output.mkdir(parents=True, exist_ok=True)
    with (args.output / ".story.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        materials = StoryMaterialReader().read(
            args.pdf, args.source_document, args.environment, args.media_directory
        )
        try:
            result = asyncio.run(
                StoryAutomationWorkflow(
                    materials,
                    args.output,
                    args.skills,
                    args.brief,
                    revalidate_saved_response=args.revalidate_saved_response,
                    accept_recorded_usage=args.accept_recorded_usage,
                    structure_profile=args.structure_profile,
                ).run()
            )
        except ServiceError as error:
            parser.exit(2, f"Story stopped [{error.code}]: {error}\nOutput: {args.output}\n")
        print("Story completed:", result)


if __name__ == "__main__":
    main()
