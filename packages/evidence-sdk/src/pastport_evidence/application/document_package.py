"""Atomically complete both human documents without exposing a downstream data interface."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, Literal

from pastport_evidence.adapters.document_export import IDMLRenderer, PDFRenderer
from pastport_evidence.adapters.report_layout import ReportLayout, font_path
from pastport_evidence.domain.models import DomainModel
from pastport_evidence.domain.pdf import RegisteredPDF
from pastport_evidence.ports.assets import AssetStore

if TYPE_CHECKING:
    from pastport_evidence.application.photo_mapping import PreparedDocuments


class OutputPaths(DomainModel):
    pdf: str
    idml: str
    status: Literal["completed", "completed_with_gaps"]
    gaps: tuple[str, ...]


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


class DocumentPackageExporter:
    def __init__(self, assets: AssetStore) -> None:
        self.assets = assets

    def write(self, root: Path, bundle: PreparedDocuments, source: RegisteredPDF) -> Path:
        root.mkdir(parents=True, exist_ok=True)
        fingerprint = hashlib.sha256(
            ("document-layout-v4-linked-jpeg:" + digest(font_path()) + bundle.model_dump_json()).encode()
        ).hexdigest()
        target = root / fingerprint
        if target.exists():
            self.validate(target)
            return target
        with TemporaryDirectory(prefix=".pending-", dir=root) as temporary:
            staging = Path(temporary) / "documents"
            staging.mkdir()
            report = ReportLayout(self.assets).build(bundle.inventory, bundle.objects, bundle.gaps)
            PDFRenderer().write(staging / "mapping.pdf", report)
            IDMLRenderer().write(staging / "mapping.idml", report)
            shutil.copyfile(self.assets.resolve_path(source.source), staging / "source.pdf")
            license_source = Path(__file__).parents[1] / "fonts" / "OFL.txt"
            if license_source.exists():
                shutil.copyfile(license_source, staging / "Document fonts" / "OFL.txt")
            (staging / "READ_ME.txt").write_text(
                "自动生成图文映射草稿 / Automatically generated draft\n"
                "mapping.pdf 和 mapping.idml 使用同一份图文布局。\n"
                "请保留 Links、Document fonts 和 source.pdf，避免图片或出处失效。\n"
                "IDML 的文字和图片可分别编辑；尚待 Adobe InDesign 原生打开和版面验收。\n"
                "此导出不授予资料的公开传播权，也不表示史料已人工审核。\n"
                f"Source SHA-256: {source.source.asset.sha256}\n",
                encoding="utf-8",
            )
            if sum(p.stat().st_size for p in staging.rglob("*") if p.is_file()) > 1024**3:
                raise ValueError("Document package exceeds the 1 GiB output limit")
            integrity = {
                p.relative_to(staging).as_posix(): digest(p)
                for p in staging.rglob("*")
                if p.is_file()
            }
            (staging / ".integrity.json").write_text(
                json.dumps(integrity, sort_keys=True), encoding="utf-8"
            )
            self.validate(staging)
            staging.rename(target)
        return target

    @staticmethod
    def validate(folder: Path) -> None:
        data: object = json.loads((folder / ".integrity.json").read_text())
        if (
            not isinstance(data, dict)
            or not {"mapping.pdf", "mapping.idml", "source.pdf"} <= data.keys()
        ):
            raise ValueError("Incomplete document package")
        for name, expected in data.items():
            if not isinstance(name, str) or not isinstance(expected, str):
                raise ValueError("Invalid document package integrity record")
            path = folder / name
            if (
                path.is_symlink()
                or not path.resolve().is_relative_to(folder.resolve())
                or digest(path) != expected
            ):
                raise ValueError(
                    "Completed document package was changed; original result preserved"
                )
