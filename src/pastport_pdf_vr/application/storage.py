"""Durable atomic metadata writes shared by generation and job storage."""

import os
from pathlib import Path


def atomic_write(path: Path, content: str) -> None:
    temporary = path.with_name(path.name + ".pending")
    with temporary.open("w", encoding="utf-8") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)

