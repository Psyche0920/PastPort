"""Start one authenticated local editorial service."""

import argparse
import os
import sys
from pathlib import Path

import uvicorn
from pydantic import ValidationError

from pastport.adapters.codex_provider import CodexStoryProvider
from pastport.adapters.model_narrative import ModelNarrativeAdapter
from pastport.adapters.model_provider import OpenAIResponsesProvider
from pastport.api.app import create_app
from pastport.api.settings import Accounts, AppSettings
from pastport.application.execution_models import ExecutionSettings, ProviderRegistration
from pastport.observability import LoggingConfiguration


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "gameplay-prepare":
        from pastport.gameplay_cli import main as gameplay_main

        sys.argv.pop(1)
        gameplay_main()
        return
    if len(sys.argv) > 1 and sys.argv[1] == "story":
        from pastport.story_cli import main as story_main

        sys.argv.pop(1)
        story_main()
        return
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--accounts",
        type=Path,
        required=True,
        help="Private JSON file containing actor permissions and SHA-256 token digests",
    )
    parser.add_argument("--data-directory", type=Path, default=Path("var/editorial"))
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--test-fixture-directory", type=Path)
    source.add_argument(
        "--content-directory",
        type=Path,
        help="Explicit authored-content files; does not run a model",
    )
    parser.add_argument(
        "--resource-directory", type=Path, help="Registered local resources.json and files"
    )
    parser.add_argument("--evidence-mode", choices=("local", "disabled"))
    parser.add_argument("--narrative-mode", choices=("local", "disabled"))
    parser.add_argument("--resources-mode", choices=("local", "disabled"))
    parser.add_argument(
        "--execution-config", type=Path, help="Pinned shared model/tool configuration"
    )
    parser.add_argument("--skill-directory", type=Path, help="Approved project Skill directory")
    parser.add_argument("--story-3d-preparation-directory", type=Path)
    parser.add_argument("--story-3d-museum-directory", type=Path)
    parser.add_argument("--story-3d-output-directory", type=Path)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--log-level", choices=("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"), default="INFO"
    )
    arguments = parser.parse_args()
    try:
        accounts = Accounts.model_validate_json(arguments.accounts.read_bytes())
        execution = (
            ExecutionSettings.model_validate_json(arguments.execution_config.read_bytes())
            if arguments.execution_config
            else ExecutionSettings()
        )
        providers: tuple[ProviderRegistration, ...] = ()
        if any(m.provider == "fake" for m in execution.models):
            raise ValueError("Use explicit Python injection for fake providers")
        if any(m.provider == "openai" for m in execution.models):
            providers = (
                ProviderRegistration(
                    "openai", OpenAIResponsesProvider(os.environ.get("PASTPORT_OPENAI_API_KEY", ""))
                ),
            )
        if any(m.provider == "codex" for m in execution.models):
            providers = (*providers, ProviderRegistration("codex", CodexStoryProvider()))
        settings = AppSettings(
            data_directory=arguments.data_directory,
            accounts=accounts.accounts,
            environment="test" if arguments.test_fixture_directory else "production",
            fixture_directory=arguments.test_fixture_directory,
            content_directory=arguments.content_directory,
            resource_directory=arguments.resource_directory,
            evidence_mode=arguments.evidence_mode,
            narrative_mode=arguments.narrative_mode,
            resources_mode=arguments.resources_mode,
            execution=execution,
            skill_directory=arguments.skill_directory,
            story_3d_preparation_directory=arguments.story_3d_preparation_directory,
            story_3d_museum_directory=arguments.story_3d_museum_directory,
            story_3d_output_directory=arguments.story_3d_output_directory,
        )
    except (OSError, ValidationError, ValueError) as error:
        parser.exit(2, "Configuration failed: " + type(error).__name__ + "\n")
    with LoggingConfiguration(arguments.log_level):
        narrative_factory = (
            ModelNarrativeAdapter
            if any(model.role == "story" for model in settings.execution.models)
            and settings.narrative_mode not in ("local", "disabled")
            else None
        )
        uvicorn.run(
            create_app(settings, providers=providers, narrative_factory=narrative_factory),
            host="127.0.0.1",
            port=arguments.port,
            workers=1,
            log_config=None,
            access_log=False,
        )


if __name__ == "__main__":
    main()
