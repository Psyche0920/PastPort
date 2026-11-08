"""Lay out supported text beside target and source images without truncating quotations."""

import io
import re
from importlib.resources import files
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from pastport_evidence.domain.mapping import MappedObject
from pastport_evidence.domain.photos import PhotoInventory
from pastport_evidence.domain.report import ImageFrame, ReportDocument, ReportPage, TextFrame
from pastport_evidence.ports.assets import AssetStore

FONT_NAME = "PastPortEvidence"
SCOPE_LABELS = {
    "direct": "直接描述",
    "parent_background": "所属整体背景",
    "general_context": "一般历史背景",
}


def font_path() -> Path:
    return Path(str(files("pastport_evidence").joinpath("fonts", "NotoSansSC-Regular.ttf")))


def register_font() -> None:
    if FONT_NAME not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(FONT_NAME, str(font_path())))


class ReportLayout:
    def __init__(self, assets: AssetStore) -> None:
        self.assets = assets
        register_font()

    @staticmethod
    def wrap(text: str, width: float, font_size: float = 10.0) -> tuple[str, ...]:
        lines: list[str] = []
        for paragraph in text.split("\n"):
            current = ""
            for char in paragraph:
                if current and pdfmetrics.stringWidth(current + char, FONT_NAME, font_size) > width:
                    lines.append(current)
                    current = ""
                current += char
            lines.append(current)
        return tuple(lines)

    def build(
        self, inventory: PhotoInventory, objects: tuple[MappedObject, ...], gaps: tuple[str, ...]
    ) -> ReportDocument:
        pages: list[ReportPage] = []
        intro = (
            "PastPort · 替代物图文映射\n\n"
            f"{len(inventory.photos)} 张照片 · {len(objects)} 个对象 · "
            f"{len(inventory.observations)} 处照片记录\n\n"
            "现实物品是承载历史信息的演示替代物，不是同一件真实文物。\n"
            "机器生成草稿，尚未人工确认。原始引文与改写介绍分别标注。\n"
            "对象编号跨照片保持一致；未确认的身份和无依据的内容保持空缺。\n"
            "图片及文字出处在对象页分别注明，点击出处可查看随附原 PDF。\n"
            "PDF 与 IDML 使用同一份图文和页面布局。IDML 的图片位于随附 Links 文件夹。"
        )
        lines = self.wrap(intro, 730)
        pages.append(
            ReportPage(tuple(TextFrame(t, 40, 45 + i * 17, 730, 17) for i, t in enumerate(lines)))
        )
        for photo in inventory.photos:
            with (
                Image.open(self.assets.resolve_path(photo.image)) as raw,
                raw.convert("RGB") as image,
            ):
                draw = ImageDraw.Draw(image)
                labels = {o.entity.object_id: o.entity.display_number for o in objects}
                for sighting in inventory.observations:
                    if sighting.photo.photo_id != photo.photo_id:
                        continue
                    box = sighting.region
                    color = "#b36b11" if sighting.identity_state == "uncertain" else "#14755e"
                    draw.rectangle(
                        (box.top_left.x, box.top_left.y, box.bottom_right.x, box.bottom_right.y),
                        outline=color,
                        width=3,
                    )
                    draw.text(
                        (box.top_left.x + 3, box.top_left.y + 3),
                        str(labels[sighting.object_id]),
                        fill="white",
                        stroke_width=2,
                        stroke_fill=color,
                        font=ImageFont.truetype(str(font_path()), 28),
                    )
                buffer = io.BytesIO()
                image.save(buffer, "JPEG", quality=90)
            annotated = self.assets.register_bytes(
                photo.original.project_id, buffer.getvalue(), "image/jpeg", 8 * 1024 * 1024
            )
            photo_title = "照片总览 · " + photo.name
            pages.append(
                ReportPage(
                    (
                        TextFrame(photo_title[:75], 32, 24, 778, 24, 14),
                        TextFrame(
                            "同一编号代表同一物品；橙色框为身份待确认。", 32, 550, 778, 18, 10
                        ),
                    ),
                    (
                        ImageFrame(
                            self.assets.resolve_path(annotated.reference),
                            32,
                            75,
                            778,
                            450,
                            photo_title,
                        ),
                    ),
                )
            )
        for obj in objects:
            sightings = tuple(
                o for o in inventory.observations if o.object_id == obj.entity.object_id
            )
            evidence = obj.source_evidence
            title = f"{obj.entity.display_number:02d} · {obj.entity.label[:40]}"
            indexed = bool(evidence and evidence.original_quote.strip() and sightings)
            bookmark = f"evidence-{obj.entity.display_number}" if indexed else None
            header = f"{obj.entity.display_number} -> {obj.historical_subject_id}" if indexed else title
            history = evidence.title if evidence else "未找到合适的历史对象"
            content = [
                f"现场物品：{obj.entity.label}",
                f"历史对象：{history}",
                "",
                "对应介绍（依据原文生成）",
            ]
            content.append(
                obj.draft.introduction
                if obj.draft and obj.draft.introduction
                else "暂无直接适用的介绍。"
            )
            if obj.draft and obj.draft.background:
                content.extend(("", "相关背景（不视为替代物自身经历）", obj.draft.background))
            if evidence:
                content.extend(("", "映射依据与限制", evidence.limitation, "", "原文摘录"))
                if evidence.passages:
                    for passage in evidence.passages:
                        locator = f"原 PDF 第 {passage.page_index + 1} 页"
                        if passage.line_start is not None:
                            locator += f"，第 {passage.line_start}–{passage.line_end} 行"
                        content.append(f"[{locator}] {passage.quote}")
                else:
                    content.append("无已验证的文字依据；不补写介绍。")
                for claim in evidence.claims:
                    content.extend(
                        (
                            "",
                            f"适用范围：{SCOPE_LABELS[claim.scope.value]}",
                            claim.statement,
                        )
                    )
            else:
                content.append("保持未分配，不以无关建筑背景填充。")
            wrapped = self.wrap("\n".join(content), 430)
            chunks = [wrapped[i : i + 27] for i in range(0, len(wrapped), 27)] or [()]
            # Every original sighting gets its own left-hand image page, including angles
            # that would otherwise be lost behind a single representative crop.
            count = max(len(chunks), len(sightings), 1)
            for index in range(count):
                texts = [TextFrame(header if index == 0 else title, 32, 24, 778, 24, 16)]
                texts.append(
                    TextFrame(
                        f"对象图文对照 · {index + 1}/{count} · 自动生成草稿", 32, 550, 778, 16, 9
                    )
                )
                images: list[ImageFrame] = []
                if sightings:
                    sighting = sightings[index % len(sightings)]
                    caption = f"替代物照片：{sighting.photo.name}"
                    if sighting.identity_state == "uncertain":
                        caption += "（跨视角身份待确认）"
                    images.append(
                        ImageFrame(
                            self.assets.resolve_path(sighting.crop), 32, 75, 300, 190, caption, bookmark
                        )
                    )
                    texts.append(TextFrame(caption, 32, 55, 300, 18, 9))
                image_caption = "原 PDF 文物图片（对照）"
                if evidence and evidence.source_image_role != "object_image":
                    image_caption = (
                        "原 PDF 场景背景图"
                        if evidence.source_image_role == "context_image"
                        else "原 PDF 文字证据（非实物照片）"
                    )
                if evidence and evidence.image_association_state != "linked":
                    image_caption += " · 关联待确认"
                if evidence and evidence.source_image:
                    images.append(
                        ImageFrame(
                            self.assets.resolve_path(evidence.source_image),
                            32,
                            310,
                            300,
                            190,
                            image_caption,
                        )
                    )
                    texts.append(TextFrame(image_caption, 32, 285, 300, 18, 9))
                else:
                    texts.append(
                        TextFrame("无独立文物图片，不使用无关图片替代", 32, 300, 300, 18, 9)
                    )
                if evidence:
                    page = evidence.pdf_page_number
                    texts.append(
                        TextFrame(
                            f"资料出处：原 PDF 第 {page} 页",
                            32,
                            515,
                            300,
                            18,
                            9,
                            f"source.pdf#page={page}",
                        )
                    )
                for line_number, line in enumerate(chunks[index] if index < len(chunks) else ()):
                    texts.append(
                        TextFrame(
                            line,
                            365,
                            65 + line_number * 17,
                            430,
                            17,
                            link=(
                                f"source.pdf#page={match.group(1)}"
                                if (match := re.search(r"\[原 PDF 第 (\d+) 页\]", line))
                                else None
                            ),
                        )
                    )
                pages.append(ReportPage(tuple(texts), tuple(images), bookmark if index == 0 else None))
        if gaps:
            gap_lines = self.wrap("待确认或未完成事项\n\n" + "\n".join(dict.fromkeys(gaps)), 750)
            for start in range(0, len(gap_lines), 27):
                pages.append(
                    ReportPage(
                        tuple(
                            TextFrame(t, 40, 45 + i * 17, 750, 17)
                            for i, t in enumerate(gap_lines[start : start + 27])
                        )
                    )
                )
        if len(pages) > 1500:
            raise ValueError("Document exceeds the 1500-page output limit")
        return ReportDocument(tuple(pages))
