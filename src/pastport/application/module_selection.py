"""Explicit composition choices; injected implementations never silently fall back."""

from collections.abc import Callable
from typing import Literal

ModuleMode = Literal["local", "injected", "disabled"]


def select_module[Port](
    name: str, mode: ModuleMode | None, supplied: Port | None, local: Callable[[], Port] | None
) -> tuple[Port | None, ModuleMode]:
    selected = mode or (
        "injected" if supplied is not None else "local" if local is not None else "disabled"
    )
    if selected not in ("local", "injected", "disabled"):
        raise ValueError(name + " has an unsupported selection mode")
    if selected != "injected" and supplied is not None:
        raise ValueError(name + " has an injected adapter but a different explicit mode")
    if selected == "injected":
        if supplied is None:
            raise ValueError(name + " requires an injected adapter")
        return supplied, selected
    if selected == "local":
        if local is None:
            raise ValueError(name + " local mode requires a configured directory")
        return local(), selected
    return None, selected
