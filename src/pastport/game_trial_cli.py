"""Run Main's provider-disabled paired-SDK integration from one explicit manifest."""

import argparse
import asyncio
from pathlib import Path

from pydantic import ValidationError

from pastport.adapters.game_making import SDKGameMakingStages
from pastport.application.game_making import GameMakingWorkflow
from pastport.application.models import ServiceError
from pastport.domain.game_making import GameMakingRequest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True, type=Path)
    args = parser.parse_args()
    try:
        request = GameMakingRequest.model_validate_json(args.request.read_bytes())
        # Relative inputs resolve against the manifest, never the process working directory.
        request = request.model_copy(update={
            name: (args.request.resolve().parent / value).resolve()
            for name, value in request if isinstance(value, Path)
        })
        result = asyncio.run(GameMakingWorkflow(SDKGameMakingStages()).run(request))
    except (OSError, ValidationError, ServiceError) as error:
        parser.exit(2, f"Game production stopped: {error}\n")
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
