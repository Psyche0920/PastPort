"""Salted password derivation; plaintext passwords are never persisted."""

import hashlib
import hmac
import re
import secrets


class PasswordHasher:
    PREFIX = "scrypt$32768$8$1$"
    FORMAT = re.compile(r"^scrypt\$32768\$8\$1\$([0-9a-f]{32})\$([0-9a-f]{64})$")
    DUMMY = PREFIX + "0" * 32 + "$" + "0" * 64

    @classmethod
    def valid_hash(cls, value: str) -> bool:
        return cls.FORMAT.fullmatch(value) is not None

    @staticmethod
    def _derive(password: str, salt: bytes) -> bytes:
        return hashlib.scrypt(
            password.encode("utf-8"), salt=salt, n=32768, r=8, p=1, dklen=32, maxmem=64 * 1024**2
        )

    def hash(self, password: str) -> str:
        if not 12 <= len(password) <= 1024:
            raise ValueError("密码须为12至1024个字符。")
        salt = secrets.token_bytes(16)
        return self.PREFIX + salt.hex() + "$" + self._derive(password, salt).hex()

    def verify(self, password: str, encoded: str) -> bool:
        match = self.FORMAT.fullmatch(encoded)
        if match is None or not 1 <= len(password) <= 1024:
            return False
        actual = self._derive(password, bytes.fromhex(match[1]))
        return hmac.compare_digest(actual, bytes.fromhex(match[2]))
