"""Initialize and start a portable local Organizer from the current checkout."""

import argparse
import errno
import getpass
import shutil
import socket
import sys
from pathlib import Path

from pastport.api.settings import Accounts
from pastport.organizer_data import DataIdentity, DeploymentBackup
from pastport.organizer_init import OrganizerAdminInitializer


class OrganizerLauncher:
    def __init__(self, directory: Path) -> None:
        self.directory = directory.resolve()
        self.accounts = self.directory / "staff-accounts.json"

    def initialize(self) -> None:
        if self.accounts.exists():
            Accounts.model_validate_json(self.accounts.read_bytes())
            print(f"Existing accounts retained: {self.accounts}")
            return
        password = getpass.getpass("New admin password (at least 12 characters): ")
        if len(password) < 12:
            raise ValueError("Use at least 12 characters.")
        if password != getpass.getpass("Confirm password: "):
            raise ValueError("Passwords do not match.")
        OrganizerAdminInitializer().create(self.accounts, password)
        print(f"Created admin account: {self.accounts}")

    def arguments(self, port: int, assets: Path | None) -> list[str]:
        if not self.accounts.is_file():
            raise ValueError("Run: python -m pastport organizer-init")
        Accounts.model_validate_json(self.accounts.read_bytes())
        if shutil.which("node") is None:
            raise ValueError("Install Node.js 22 or later, then reopen your terminal.")
        DataIdentity(self.directory).verify()
        with socket.socket() as listener:
            try:
                listener.bind(("127.0.0.1", port))
            except OSError as error:
                if error.errno == errno.EADDRINUSE:
                    raise ValueError(
                        f"Port {port} is occupied. Open the existing service or choose --port."
                    ) from error
                raise ValueError(f"Cannot open local port {port}: {error.strerror}") from error
        result = [
            "pastport",
            "--accounts",
            str(self.accounts),
            "--data-directory",
            str(self.directory / "server"),
            "--evidence-mode",
            "disabled",
            "--narrative-mode",
            "disabled",
            "--resources-mode",
            "disabled",
            "--port",
            str(port),
        ]
        catalog = self.directory / "catalog.json"
        if catalog.is_file():
            result.extend(("--organizer-catalog", str(catalog)))
        if assets is not None:
            if not assets.is_dir():
                raise ValueError("The player assets directory does not exist.")
            result.extend(("--organizer-player-assets", str(assets.resolve())))
        return result


def backup() -> None:
    parser = argparse.ArgumentParser(description="Back up Organizer and player data consistently")
    parser.add_argument("--directory", type=Path, default=Path("var/organizer-integration"))
    parser.add_argument("--player-data", type=Path, default=Path("frontend/player/.local"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        summary = DeploymentBackup(args.directory, args.player_data).create(args.output)
    except (OSError, ValueError) as error:
        parser.exit(2, f"Backup failed: {error}\n")
    print(f"Backup written: {args.output}\n{summary}", flush=True)


def main(*, initialize: bool = False) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path("var/organizer-integration"))
    parser.add_argument("--port", type=int, default=18840)
    parser.add_argument("--player-assets", type=Path)
    args = parser.parse_args()
    launcher = OrganizerLauncher(args.directory)
    try:
        if initialize:
            launcher.initialize()
            return
        if not 1 <= args.port <= 65535:
            raise ValueError("Port must be between 1 and 65535.")
        arguments = launcher.arguments(args.port, args.player_assets)
    except (OSError, ValueError) as error:
        parser.exit(2, f"Organizer configuration: {error}\n")
    from pastport.__main__ import main as server_main

    print(f"Organizer: http://127.0.0.1:{args.port}/organizer/", flush=True)
    sys.argv = arguments
    server_main()


if __name__ == "__main__":
    main()
