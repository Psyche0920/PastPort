"""Create this computer's private Organizer administrator once; the password stays local."""

import argparse
import getpass
import json
import os
from pathlib import Path
from typing import Literal

from pastport.adapters.passwords import PasswordHasher
from pastport.api.settings import Accounts, Credential
from pastport.application.models import Actor

DEFAULT_ACCOUNTS = Path("var/organizer-integration/staff-accounts.json")
# The Organizer sign-in form always submits this username.
ADMIN_USERNAME = "admin"
Role = Literal["editor", "evidence", "narrative", "publisher", "operator"]
ADMIN_ROLES: tuple[Role, ...] = ("editor", "evidence", "narrative", "publisher", "operator")
MINIMUM_PASSWORD = 12


class OrganizerAdminInitializer:
    """Write a new single-administrator account file; never overwrite an existing one."""

    def create(self, path: Path, password: str) -> Credential:
        if path.is_symlink() or path.exists():
            raise ValueError(
                "账户配置已存在，未作修改；改密码请用 account-password。"
                " / An account file already exists and was left unchanged;"
                " use account-password to change the password."
            )
        if len(password) < MINIMUM_PASSWORD:
            raise ValueError(
                f"密码至少{MINIMUM_PASSWORD}个字符。"
                f" / The password needs at least {MINIMUM_PASSWORD} characters."
            )
        credential = Credential(
            actor=Actor(actor_id="organizer-admin", roles=ADMIN_ROLES, project_ids=None),
            username=ADMIN_USERNAME,
            password_hash=PasswordHasher().hash(password),
        )
        content = Accounts(accounts=(credential,)).model_dump_json(indent=2)
        path.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(path.parent, 0o700)
        # O_EXCL keeps a concurrent run from replacing a file created in the meantime.
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        return credential


def start_command(path: Path) -> str:
    """The portable start command for this account file, relative to the repository root."""
    return " ".join(
        (
            ".venv/bin/python -m pastport",
            f"--accounts {json.dumps(str(path))}",
            "--data-directory var/organizer-integration/server",
            "--evidence-mode disabled --narrative-mode disabled --resources-mode disabled",
            "--port 18840",
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--accounts", type=Path, default=DEFAULT_ACCOUNTS)
    args = parser.parse_args()
    print(
        "为本机创建 Organizer 管理员（账号固定为 admin）。密码只以哈希保存在本机。\n"
        "Creating this computer's Organizer administrator (username: admin)."
        " Only a password hash is stored locally.",
        flush=True,
    )
    password = getpass.getpass(f"密码 / Password (≥{MINIMUM_PASSWORD}): ")
    if getpass.getpass("再次输入 / Repeat: ") != password:
        parser.exit(1, "两次密码不一致，未作修改。 / Passwords differ; nothing changed.\n")
    try:
        OrganizerAdminInitializer().create(args.accounts, password)
    except (OSError, ValueError) as error:
        parser.exit(1, f"设置失败 / Setup failed: {error}\n")
    print(
        f"已创建 / Created {args.accounts}\n"
        f"启动 / Start: {start_command(args.accounts)}\n"
        "然后打开 / Then open http://127.0.0.1:18840/organizer/ (admin + your password)",
        flush=True,
    )


if __name__ == "__main__":
    main()
