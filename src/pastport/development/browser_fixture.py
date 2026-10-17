"""Dedicated synthetic localhost server for browser acceptance, never production data."""

import argparse
import hashlib
import os
from pathlib import Path

import uvicorn

from pastport.api.app import create_app
from pastport.api.settings import AppSettings, Credential
from pastport.application.models import Actor


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--port", type=int, required=True)
    options = parser.parse_args()
    token = os.environ["PASTPORT_BROWSER_TOKEN"]
    outsider = os.environ["PASTPORT_BROWSER_OUTSIDER"]
    fixture = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "reference"
    app = create_app(
        AppSettings(
            data_directory=options.directory,
            environment="test",
            fixture_directory=fixture,
            accounts=(
                Credential(
                    token_sha256=hashlib.sha256(token.encode()).hexdigest(),
                    actor=Actor(
                        actor_id="browser-reviewer",
                        roles=("editor", "evidence", "narrative", "publisher", "operator"),
                        project_ids=None,
                    ),
                ),
                Credential(
                    token_sha256=hashlib.sha256(outsider.encode()).hexdigest(),
                    actor=Actor(
                        actor_id="browser-outsider",
                        roles=("editor",),
                        project_ids=("other-project",),
                    ),
                ),
            ),
        )
    )
    uvicorn.run(app, host="127.0.0.1", port=options.port, log_level="warning", access_log=False)


if __name__ == "__main__":
    main()
