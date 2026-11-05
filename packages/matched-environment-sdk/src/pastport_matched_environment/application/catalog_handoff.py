"""Admit numbered, two-column exhibit catalogs as direct visual references."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import shutil
import subprocess
from tempfile import TemporaryDirectory

from PIL import Image
from pypdf.errors import PdfReadError

from pastport_matched_environment.application.candidate_source import PDFCandidateSource
from pastport_matched_environment.application.environment_build import normalized
from pastport_matched_environment.application.reference_environment import digest


@dataclass(frozen=True, slots=True)
class CatalogEntry:
    code: str
    name: str
    page: int
    observation: str
    usage: str
    provenance: str


class CatalogHandoff:
    """Keep each numbered exhibit and its photo panel bound to the original PDF."""

    _observation = re.compile(
        r"(?m)^(PP-[0-9]{3})\n([^\n]+)\n现场所见\n(.+?)\n用途与来源\n(.+?)"
        r"(?=\n(?:照片来自|展品来历|$))",
        re.S,
    )
    _supplement = re.compile(r"(?m)^(PP-[0-9]{3}) +([^\n]+)\n([\s\S]+?)(?=^PP-[0-9]{3} +|\Z)")

    def prepare(self, pdf: Path, destination: Path) -> None:
        if destination.exists():
            if digest(destination / "source.pdf") != digest(pdf):
                raise ValueError("展签来源已变更，请提交新任务。")
            return
        destination.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(dir=destination.parent) as scratch:
            root = Path(scratch) / "handoff"
            root.mkdir()
            shutil.copyfile(pdf, root / "source.pdf")
            shutil.copyfile(pdf, root / "input.pdf")
            try:
                self._extract(PDFCandidateSource(root, content_order=True), root)
                (root / "catalog-text-order").touch()
            except (PdfReadError, subprocess.SubprocessError) as exc:
                raise ValueError("展签 PDF 无法解析或渲染。") from exc
            root.rename(destination)

    def _extract(self, source: PDFCandidateSource, root: Path) -> None:
        count = source.count
        if not 1 <= count <= 200:
            raise ValueError("展签图录需要 1 至 200 页。")
        pages = {page: source.text(page) for page in range(1, count + 1)}
        supplement: dict[str, str] = {}
        for page_text in pages.values():
            if "展签补遗" in page_text and "均为虚构" in page_text:
                for appendix in self._supplement.finditer(page_text):
                    supplement[appendix[1]] = "".join(appendix[3].splitlines()).strip()
        media = root / "media"
        media.mkdir()
        objects: list[dict[str, object]] = []
        photos: list[dict[str, object]] = []
        quotes: list[dict[str, object]] = []
        seen: set[str] = set()
        for page, page_text in pages.items():
            match = self._observation.search(page_text)
            if match is None:
                continue
            code, name, observation, usage = match.groups()
            if code in seen:
                raise ValueError(f"同一编号出现在多个主展签：{code}")
            seen.add(code)
            usage_text = "".join(usage.splitlines())
            entry = CatalogEntry(code, name, page, "".join(observation.splitlines()),
                                 usage_text, supplement.get(code, ""))
            number = int(code[3:])
            context = normalized(page_text)
            quote = normalized(observation)
            start = context.find(quote)
            if start < 0:
                raise ValueError(f"展签 {code} 的描述无法定位到原文。")
            photo_number = len(photos) + 1
            photos.append(self._images(source, root, entry, number, photo_number))
            introduction = f"{entry.observation}\n\n{entry.usage}"
            if entry.provenance:
                introduction += f"\n\n展品来历（虚构）\n{entry.provenance}"
            objects.append({
                "number": number, "object_id": f"catalog:{digest(source.path)[:16]}:{code}",
                "name": entry.name, "boundary": entry.observation, "history_id": code,
                "history": entry.name, "parent": "展签图录", "page": page, "quote": quote,
                "image_page": page, "image_box": [0.045, 0.20, 0.495, 0.63],
                "image_role": "object_image", "introduction": introduction,
                "explanation": "以现场照片和可见特征识别同一件实物。",
                "proxy": "same_physical_object", "limit": "展品来历为虚构设定，仅用于展陈。",
                "observations": [{
                    "photo_number": photo_number, "observation_status": "visible",
                    "region_normalized": [0.0, 0.0, 1.0, 1.0],
                    "basis": "左栏照片中的同编号标框指向目标实物。",
                }],
            })
            quotes.append({"number": number, "page": page, "normalized_text": context,
                           "start": start, "end": start + len(quote)})
        if not objects:
            raise ValueError("需要有 PP-编号、现场所见和用途与来源的双栏展签。")
        for name, payload in (
            ("objects.json", {"title": "现场物件图录", "objects": objects}),
            ("inputs.json", {"input_page_count": count, "photos": photos}),
            ("quote-regions.json", quotes),
        ):
            (root / name).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    @staticmethod
    def _images(source: PDFCandidateSource, root: Path, entry: CatalogEntry, number: int,
                photo_number: int) -> dict[str, object]:
        page_image = root / "page.png"
        source.render(entry.page, page_image)
        photo = root / "media" / f"photo-{photo_number:02d}.jpg"
        with Image.open(page_image) as page:
            width, height = page.size
            with page.crop((round(width * .045), round(height * .20),
                            round(width * .495), round(height * .63))) as panel:
                panel.save(root / f"proxy-{number}.png")
                panel.save(root / "media" / f"history-{number:02d}.png")
                panel.save(photo, quality=95)
                size = panel.size
        page_image.unlink()
        return {"number": photo_number, "path": f"{entry.code}-catalog-photos",
                "sha256": digest(photo), "oriented_size": size}
