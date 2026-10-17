"""Stable game field locks and declared targets, shared by manual and module revisions."""

import hashlib
import json

from pydantic import JsonValue

from pastport.application.models import ServiceError
from pastport.domain.modules import NarrativeDraft


def story_field_hash(story: NarrativeDraft, pointer: str) -> str:
    if not pointer.startswith("/package/game/"):
        raise ServiceError("LOCK_INVALID", "Only declared game fields can be locked", 422)
    current: JsonValue = story.model_dump(mode="json")
    try:
        for part in pointer[1:].split("/"):
            part = part.replace("~1", "/").replace("~0", "~")
            if isinstance(current, dict):
                current = current[part]
            elif isinstance(current, list):
                if not part.isdecimal():
                    raise ValueError("Invalid array index")
                current = current[int(part)]
            else:
                raise ValueError("Path traverses a scalar")
    except (KeyError, IndexError, ValueError) as error:
        raise ServiceError(
            "LOCK_INVALID", "Lock path does not identify a game field", 422
        ) from error
    return hashlib.sha256(
        json.dumps(
            current, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def story_target_ids(story: NarrativeDraft) -> set[str]:
    targets: set[str] = set()

    def visit(value: JsonValue) -> None:
        if isinstance(value, dict):
            for name, item in value.items():
                if name.endswith("_id") and isinstance(item, str):
                    targets.add(item)
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(story.package.game.model_dump(mode="json"))
    return targets
