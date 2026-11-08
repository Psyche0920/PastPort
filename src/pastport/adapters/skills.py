"""Read only server-approved Skill paths and fingerprint every included file."""

import hashlib
import re
from pathlib import Path
from typing import Literal

from pastport.adapters.package_files import LocalPackageFileReader
from pastport.application.execution_models import ModelPolicy, SkillBundle, SkillFile
from pastport.application.models import ServiceError
from pastport.domain.package_loading import PackageLoadError


class SkillLoader:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def load(self, policy: ModelPolicy) -> SkillBundle:
        name: Literal["evidence-review", "narrative"] = (
            "evidence-review" if policy.role == "research" else "narrative"
        )
        directory = self.root / name
        files = []
        for relative in ("SKILL.md", *policy.references):
            if relative != "SKILL.md" and not relative.startswith("references/"):
                raise ServiceError("SKILL_PATH_INVALID", "Only approved references may be included")
            path = directory / relative
            if (
                any(p in ("", ".", "..") for p in relative.split("/"))
                or "\\" in relative
                or ":" in relative
                or "%" in relative
                or not path.resolve().is_relative_to(directory)
                or path.is_symlink()
                or directory.is_symlink()
                or any(p.is_symlink() for p in path.parents if p.is_relative_to(directory))
            ):
                raise ServiceError("SKILL_PATH_INVALID", "Skill path is outside its approved scope")
            try:
                content = LocalPackageFileReader().read(path, 128 * 1024)
                text = content.decode("utf-8")
            except (PackageLoadError, UnicodeError) as error:
                raise ServiceError("SKILL_UNAVAILABLE", "Approved Skill cannot be read") from error
            files.append(
                SkillFile(
                    path=name + "/" + relative,
                    sha256=hashlib.sha256(content).hexdigest(),
                    text=text,
                )
            )
        entry = files[0].text
        version = re.search(r'^\s+version: "([a-zA-Z0-9_.:-]+)"\s*$', entry, re.MULTILINE)
        if not entry.startswith("---\nname: " + name + "\n") or version is None:
            raise ServiceError("SKILL_INVALID", "Skill identity and version are required")
        return SkillBundle(name=name, version=version[1], files=tuple(files))


    @staticmethod
    def restore(bundles: tuple[SkillBundle, ...], destination: Path) -> Path:
        """Materialize the original trusted snapshots so replay never adopts edited Skills."""
        for bundle in bundles:
            for item in bundle.files:
                parts = item.path.split("/")
                if parts[0] != bundle.name or any(part in ("", ".", "..") for part in parts) or "\\" in item.path:
                    raise ServiceError("SKILL_PATH_INVALID", "Pinned Skill path is invalid")
                data = item.text.encode()
                if hashlib.sha256(data).hexdigest() != item.sha256:
                    raise ServiceError("SKILL_INVALID", "Pinned Skill content changed")
                path = destination.joinpath(*parts)
                if path.is_symlink() or not path.resolve().is_relative_to(destination.resolve()):
                    raise ServiceError("SKILL_PATH_INVALID", "Pinned Skill leaves its destination")
                if path.exists():
                    if path.is_symlink() or path.read_bytes() != data:
                        raise ServiceError("SKILL_INVALID", "Materialized Skill content changed")
                else:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(data)
        return destination
