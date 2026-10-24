"""Load and validate non-secret TOML project configuration."""

from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Final

from pydantic import ValidationError

from pastport_pdf_vr.domain.models import InputRepresentation, ProjectConfig

CONFIG_ENV_PREFIX: Final[str] = "PASTPORT_"


class ConfigurationError(ValueError):
    """Raised when a project configuration cannot be loaded or validated."""


def load_project_config(
    config_path: Path,
    environ: Mapping[str, str] | None = None,
) -> ProjectConfig:
    """Load TOML and apply the documented environment overrides without reading secrets."""
    if not config_path.is_file():
        raise ConfigurationError(f"Configuration file does not exist: {config_path}")
    try:
        with config_path.open("rb") as config_file:
            raw_config = tomllib.load(config_file)
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ConfigurationError(f"Cannot read TOML configuration: {config_path}") from error

    values = _apply_environment_overrides(raw_config, os.environ if environ is None else environ)
    _normalize_decimal_budget(values)
    try:
        return ProjectConfig.model_validate(values)
    except ValidationError as error:
        raise ConfigurationError("Project configuration failed validation") from error


def _apply_environment_overrides(
    config: dict[str, object], environ: Mapping[str, str]
) -> dict[str, object]:
    """Apply a small explicit override set, keeping nested limit parsing typed."""
    result = dict(config)
    allowed: Final[dict[str, tuple[str, ...]]] = {
        "PROJECT_ID": ("project_id",),
        "INPUT_REPRESENTATION": ("input_representation",),
        "PROVIDER": ("provider",),
        "MODEL_ID": ("model_id",),
        "PROMPT_VERSION": ("prompt_version",),
        "POLICY_VERSION": ("policy_version",),
        "MAX_MODEL_CALLS": ("limits", "max_model_calls"),
        "BUDGET_USD": ("limits", "budget_usd"),
    }
    for suffix, keys in allowed.items():
        value = environ.get(f"{CONFIG_ENV_PREFIX}{suffix}")
        if value is None:
            continue
        if len(keys) == 1:
            result[keys[0]] = _parse_environment_value(suffix, value)
            continue
        nested = result.get(keys[0])
        if not isinstance(nested, dict):
            nested = {}
        nested_values = dict(nested)
        nested_values[keys[1]] = _parse_environment_value(suffix, value)
        result[keys[0]] = nested_values
    representation = result.get("input_representation")
    if isinstance(representation, str):
        try:
            result["input_representation"] = InputRepresentation(representation)
        except ValueError as error:
            raise ConfigurationError(
                "input_representation must be real_site or synthetic_replay"
            ) from error
    return result


def _parse_environment_value(suffix: str, value: str) -> object:
    if suffix == "MAX_MODEL_CALLS":
        try:
            return int(value)
        except ValueError as error:
            raise ConfigurationError("PASTPORT_MAX_MODEL_CALLS must be an integer") from error
    return value


def _normalize_decimal_budget(values: dict[str, object]) -> None:
    """Parse TOML decimal strings exactly; reject binary floats for money values."""
    limits = values.get("limits")
    if not isinstance(limits, dict):
        return
    budget = limits.get("budget_usd")
    if isinstance(budget, str):
        try:
            parsed_budget = Decimal(budget)
        except InvalidOperation as error:
            raise ConfigurationError("limits.budget_usd must be a decimal string") from error
        updated_limits = dict(limits)
        updated_limits["budget_usd"] = parsed_budget
        values["limits"] = updated_limits
