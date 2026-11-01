"""Organizer passwords reuse Main actors and reload private account configuration."""

import logging
from pathlib import Path

from pydantic import ValidationError

from pastport.account_cli import AccountPasswordCommand
from pastport.adapters.passwords import PasswordHasher
from pastport.api.settings import Accounts, Credential
from pastport.application.models import ServiceError
from pastport.domain.common import CanonicalSerializer

logger = logging.getLogger(__name__)


class OrganizerAccounts:
    def __init__(
        self,
        initial: tuple[Credential, ...],
        path: Path | None = None,
        *,
        allow_local_setup: bool = False,
    ) -> None:
        self.initial, self.path = initial, path
        self.allow_local_setup = allow_local_setup
        self.hasher = PasswordHasher()

    def credentials(self) -> tuple[Credential, ...]:
        if self.path is None:
            return self.initial
        try:
            if self.path.is_symlink() or self.path.stat().st_size > 1024**2:
                raise ValueError("Invalid private account file")
            return Accounts.model_validate_json(self.path.read_bytes()).accounts
        except (OSError, ValueError, ValidationError) as error:
            logger.error("Private account configuration unavailable: %s", type(error).__name__)
            raise ServiceError(
                "ACCOUNTS_UNAVAILABLE", "账户配置不可用，请联系维护者。", 503
            ) from error

    def setup_available(self) -> bool:
        accounts = self.credentials()
        return bool(
            self.allow_local_setup
            and self.path is not None
            and len(accounts) == 1
            and accounts[0].password_hash is None
            and {"editor", "operator"}.intersection(accounts[0].actor.roles)
        )

    def initialize_admin(self, password: str) -> Credential:
        if not self.setup_available() or self.path is None:
            raise ServiceError(
                "ADMIN_ALREADY_CONFIGURED", "管理员已设置或当前服务不允许初始化。", 409
            )
        account = self.credentials()[0]
        try:
            AccountPasswordCommand().update(
                self.path, account.actor.actor_id, "admin", password, initial_only=True
            )
        except ValueError as error:
            raise ServiceError(
                "ADMIN_SETUP_INVALID", "密码至少12个字符；管理员只能初始化一次。", 422
            ) from error
        return self.actor_account(account.actor.actor_id)

    def password(self, username: str, password: str) -> Credential:
        accounts = self.credentials()
        if not any(account.password_hash is not None for account in accounts):
            raise ServiceError("ACCOUNT_SETUP_REQUIRED", "维护者尚未设置工作人员账号密码。", 503)
        account = next(
            (account for account in accounts if account.username == username.strip().casefold()),
            None,
        )
        encoded = (
            account.password_hash
            if account is not None and account.password_hash is not None
            else PasswordHasher.DUMMY
        )
        valid = self.hasher.verify(password, encoded)
        if not valid or account is None:
            raise ServiceError("AUTHENTICATION_INVALID", "账号或密码不正确。", 401)
        return account

    def actor_account(self, actor_id: str) -> Credential:
        account = next(
            (account for account in self.credentials() if account.actor.actor_id == actor_id), None
        )
        if account is None:
            raise ServiceError("AUTHENTICATION_REQUIRED", "账户已停用，请重新登录。", 401)
        return account

    @staticmethod
    def version(account: Credential) -> str:
        return CanonicalSerializer.digest(account)
