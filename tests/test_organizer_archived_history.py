"""History archival must not break references from retained packages."""

from pathlib import Path

import pytest

from pastport.adapters.organizer_store import OrganizerStore
from pastport.application.models import ServiceError
from pastport.domain.common import Contract


class ArchivedValue(Contract):
    value: str


def test_archived_jobs_are_resolvable_but_not_listed(tmp_path: Path) -> None:
    store = OrganizerStore(tmp_path)
    old = ArchivedValue(value="preserved package dependency")
    store.save("archived_job_20261106-222742", "same-id", old)
    assert store.list("job", ArchivedValue) == ()
    assert store.get("job", "same-id", ArchivedValue) == old
    current = ArchivedValue(value="new active record")
    store.save("job", "same-id", current)
    assert store.get("job", "same-id", ArchivedValue) == current
    with pytest.raises(ServiceError):
        store.get("materials", "same-id", ArchivedValue)
