"""Read regular local package files without following a file symlink or blocking on a pipe."""

import os
import stat
from contextlib import ExitStack
from pathlib import Path

from pastport.domain.package_loading import PackageLoadError


class LocalPackageFileReader:
    def read(self, path: Path, maximum_bytes: int) -> bytes:
        if maximum_bytes <= 0:
            raise ValueError("Package byte limit must be positive")
        try:
            with ExitStack() as resources:
                descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                resources.callback(os.close, descriptor)
                metadata = os.fstat(descriptor)
                if not stat.S_ISREG(metadata.st_mode):
                    raise PackageLoadError(
                        "RUNTIME_PACKAGE_UNREADABLE", "Package input must be a regular file"
                    )
                if metadata.st_size > maximum_bytes:
                    raise PackageLoadError(
                        "RUNTIME_PACKAGE_TOO_LARGE", "Package exceeds the configured byte limit"
                    )
                with os.fdopen(descriptor, "rb", closefd=False) as stream:
                    content = stream.read(maximum_bytes + 1)
                if len(content) > maximum_bytes:
                    raise PackageLoadError(
                        "RUNTIME_PACKAGE_TOO_LARGE", "Package exceeds the configured byte limit"
                    )
                return content
        except OSError as error:
            raise PackageLoadError(
                "RUNTIME_PACKAGE_UNREADABLE", "Package file cannot be read"
            ) from error
