"""Revalidate immutable records rather than bypassing their boundary validators."""

from pastport.domain.common import Contract


def updated[Record: Contract](record: Record, **changes: object) -> Record:
    values = record.model_dump(mode="python")
    values.update(changes)
    return type(record).model_validate(values)
