"""Load the one packaged capability catalog; malformed catalogs cannot authorize games."""

from importlib.resources import files

from pydantic import ValidationError

from pastport.application.models import ServiceError
from pastport.domain.mechanics import GameplayCapabilities


def load_gameplay_catalog() -> GameplayCapabilities:
    try:
        raw = files("pastport").joinpath("data/gameplay-capabilities.json").read_bytes()
        return GameplayCapabilities.model_validate_json(raw)
    except (OSError, ValidationError) as error:
        raise ServiceError(
            "GAMEPLAY_CATALOG_INVALID", "Cannot load verified capability catalog"
        ) from error
