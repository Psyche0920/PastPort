"""A provider-independent resource boundary; implementations enforce their own storage scope."""

from typing import Protocol

from pastport.domain.resources import ResourceData, ResourceReference


class ResourceReader(Protocol):
    def read(self, reference: ResourceReference, maximum_bytes: int) -> ResourceData: ...
