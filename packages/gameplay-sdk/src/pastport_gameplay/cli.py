"""Local SDK commands; all generation calls remain in Story."""

import argparse
from pathlib import Path

from pastport_gameplay.client import GameplayClient, PreparationRequest, PresentationRequest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--story-run", type=Path, required=True)
    prepare.add_argument("--output", type=Path, required=True)
    present = commands.add_parser("present")
    present.add_argument("--story-run", type=Path, required=True)
    present.add_argument("--preparation", type=Path, required=True)
    present.add_argument("--museum", type=Path, required=True)
    present.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    client = GameplayClient()
    if args.command == "prepare":
        result = client.prepare(PreparationRequest(
            story_run=args.story_run, output_directory=args.output,
        ))
        print(result.plan_file)
    else:
        presentation = client.present(PresentationRequest(
            story_run=args.story_run, preparation_directory=args.preparation,
            museum_directory=args.museum, output_file=args.output,
        ))
        print(presentation.story_input)
