"""Run the standalone reference-guided agent through the existing metered SDK."""

import argparse
import shutil
from pathlib import Path

from pastport_matched_environment.application.storage import atomic_write

from pastport_stylization.application.automatic_stylization import AutomaticStyleRun
from pastport_stylization.application.stylization_agent import EnvironmentStylizationAgent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    args = parser.parse_args()

    from pastport_matched_environment.adapters.codex_sdk import CodexSDKTransport

    from pastport_stylization.adapters.codex_image import CodexImageTransport

    request = AutomaticStyleRun.model_validate_json(args.request.read_bytes())
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        parser.error("FFmpeg is required before agent execution")
    agent = EnvironmentStylizationAgent(
        Path(ffmpeg),
        CodexSDKTransport(request.grant.effort),
        CodexImageTransport(request.grant.effort),
    )
    delivery = agent.run(request)
    atomic_write(
        Path(request.workspace).parent / "automatic-delivery.json",
        delivery.model_dump_json(indent=2),
    )
    print(delivery.model_dump_json())


if __name__ == "__main__":
    main()
