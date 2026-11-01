"""Set an existing staff actor's password locally without exposing it in chat."""

import argparse
import fcntl
import getpass
import os
import tempfile
from pathlib import Path

from pastport.adapters.passwords import PasswordHasher
from pastport.api.settings import Accounts, Credential


class AccountPasswordCommand:
    def update(
        self, path: Path, actor_id: str, username: str, password: str, *, initial_only: bool = False
    ) -> None:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 1024**2:
            raise ValueError("请选择现有的私有账户配置文件。")
        with path.with_suffix(".update.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            accounts = Accounts.model_validate_json(path.read_bytes())
            if not any(account.actor.actor_id == actor_id for account in accounts.accounts):
                raise ValueError("找不到现有工作人员；此命令不会自动增加权限。")
            if initial_only and (
                len(accounts.accounts) != 1
                or any(account.password_hash is not None for account in accounts.accounts)
            ):
                raise ValueError("管理员已设置，不允许再次初始化。")
            encoded = PasswordHasher().hash(password)
            values = tuple(
                Credential.model_validate(
                    account.model_dump()
                    | {
                        "username": username,
                        "password_hash": encoded,
                    }
                )
                if account.actor.actor_id == actor_id
                else account
                for account in accounts.accounts
            )
            updated = Accounts(accounts=values)
            temporary: Path | None = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w", encoding="utf-8", dir=path.parent, delete=False
                ) as stream:
                    temporary = Path(stream.name)
                    os.fchmod(stream.fileno(), 0o600)
                    stream.write(updated.model_dump_json(indent=2))
                    stream.flush()
                    os.fsync(stream.fileno())
                temporary.replace(path)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--accounts", type=Path, required=True)
    parser.add_argument("--actor", required=True)
    args = parser.parse_args()
    print("首次设置工作人员登录。仅在本机保存密码哈希；现有角色和项目权限保持不变。", flush=True)
    username = input("账号名：").strip()
    password = getpass.getpass("密码（至少12个字符，输入不会显示）：")
    confirmation = getpass.getpass("再次输入密码：")
    if password != confirmation:
        parser.error("两次密码不一致；没有修改账户。")
    try:
        AccountPasswordCommand().update(args.accounts, args.actor, username, password)
    except (OSError, ValueError) as error:
        parser.exit(1, f"设置失败：{error}\n")
    print("设置完成。回到制作页，用刚才的账号密码登录即可。", flush=True)


if __name__ == "__main__":
    main()
