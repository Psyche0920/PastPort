"""Portable side-by-side photo mapping report with independent source evidence pages."""

from __future__ import annotations

import io
from importlib.resources import files
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image, ImageDraw
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Flowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus import (
    Image as PDFImage,
)

from pastport_pdf_vr.domain.editorial import PreviewObject
from pastport_pdf_vr.domain.models import ProjectAssetRef
from pastport_pdf_vr.domain.photos import PhotoInventory, ScenePhoto
from pastport_pdf_vr.ports.assets import AssetStore


class MappingPDFExporter:
    """Only validated evidence enters direct introductions; omitted content remains explicit."""

    def __init__(self, assets: AssetStore) -> None:
        self.assets = assets
        pdfmetrics.registerFont(
            TTFont(
                "PastPortSans",
                str(files("pastport_pdf_vr").joinpath("fonts", "NotoSansSC-Regular.ttf")),
            )
        )
        self.body = ParagraphStyle(
            "body",
            fontName="PastPortSans",
            fontSize=10,
            leading=16,
            textColor=colors.HexColor("#203c35"),
            wordWrap="CJK",
        )
        self.heading = ParagraphStyle(
            "heading", parent=self.body, fontSize=18, leading=25, spaceAfter=12
        )

    def paragraph(self, text: str, *, heading: bool = False) -> Paragraph:
        return Paragraph(
            escape(text).replace("\n", "<br/>"), self.heading if heading else self.body
        )

    def image(self, reference: ProjectAssetRef, width: float, height: float) -> PDFImage:
        path = self.assets.resolve_path(reference)
        with Image.open(path) as raw:
            scale = min(width / raw.width, height / raw.height)
            return PDFImage(str(path), width=raw.width * scale, height=raw.height * scale)

    def annotated(
        self, photo: ScenePhoto, inventory: PhotoInventory, objects: tuple[PreviewObject, ...]
    ) -> PDFImage:
        numbers = {o.entity.object_id: o.entity.display_number for o in objects}
        with Image.open(self.assets.resolve_path(photo.image)) as raw, raw.convert("RGB") as image:
            draw = ImageDraw.Draw(image)
            for observation in inventory.observations:
                if observation.photo.photo_id != photo.photo_id:
                    continue
                box = observation.region
                colour = "#db9c3c" if observation.identity_state == "uncertain" else "#178a70"
                draw.rectangle(
                    (box.top_left.x, box.top_left.y, box.bottom_right.x, box.bottom_right.y),
                    outline=colour,
                    width=max(2, image.width // 350),
                )
                label = str(numbers[observation.object_id]) + (
                    "?" if observation.identity_state == "uncertain" else ""
                )
                draw.text(
                    (box.top_left.x + 4, box.top_left.y + 4),
                    label,
                    fill="white",
                    stroke_width=2,
                    stroke_fill=colour,
                    font_size=28,
                )
            stream = io.BytesIO()
            image.save(stream, "PNG")
            stream.seek(0)
            scale = min(350 / image.width, 420 / image.height)
            return PDFImage(stream, width=image.width * scale, height=image.height * scale)

    def write(
        self,
        destination: Path,
        inventory: PhotoInventory,
        objects: tuple[PreviewObject, ...],
        gaps: tuple[str, ...],
    ) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(".pending.pdf")
        story: list[Flowable] = [
            self.paragraph("PastPort · 替代物照片映射", heading=True),
            self.paragraph(
                f"{len(inventory.photos)} 张照片 / {len(objects)} 个固定对象 / "
                f"{len(inventory.observations)} 处出现位置"
            ),
            Spacer(1, 14),
            self.paragraph(
                "这是现实物品承载历史信息的演示映射，不代表同一件真实文物。问号表示身份待确认。没有依据的内容保持空缺；图像证据和文字适用范围分别记录。"
            ),
        ]
        lookup = {o.entity.object_id: o for o in objects}
        for photo_number, photo in enumerate(inventory.photos, 1):
            visible = list(
                dict.fromkeys(
                    o.object_id
                    for o in inventory.observations
                    if o.photo.photo_id == photo.photo_id
                )
            )
            batches = [visible[n : n + 2] for n in range(0, len(visible), 2)] or [[]]
            for part, ids in enumerate(batches, 1):
                story += [
                    PageBreak(),
                    self.paragraph(
                        f"照片 {photo_number:02d} · {photo.name} · {part}/{len(batches)}",
                        heading=True,
                    ),
                ]
                cards: list[Flowable] = []
                for oid in ids:
                    obj = lookup[oid]
                    evidence = obj.replay_evidence
                    cards.append(
                        self.paragraph(f"{obj.entity.display_number:02d} · {obj.entity.label[:70]}")
                    )
                    if evidence:
                        cards.append(
                            self.paragraph(
                                f"→ {evidence.title[:100]} · "
                                f"来源 PDF 第 {evidence.pdf_page_number} 页"
                            )
                        )
                        if evidence.source_image:
                            cards.append(self.image(evidence.source_image, 160, 65))
                        cards.append(
                            self.paragraph(
                                obj.draft.introduction[:140]
                                if obj.draft
                                else "无直接适用的介绍；详见对象证据页。"
                            )
                        )
                    else:
                        cards.append(self.paragraph("未分配历史来源，保留空值。"))
                    cards.append(Spacer(1, 10))
                if not cards:
                    cards = [self.paragraph("本照片未确认可编号的物品。")]
                table = Table(
                    [[self.annotated(photo, inventory, objects), cards]], colWidths=[370, 380]
                )
                table.setStyle(
                    TableStyle(
                        [("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 4)]
                    )
                )
                story.append(table)
        for obj in objects:
            story += [
                PageBreak(),
                self.paragraph(
                    f"对象 {obj.entity.display_number:02d} · {obj.entity.label}", heading=True
                ),
            ]
            story.append(
                self.paragraph("身份特征：" + "；".join(obj.entity.distinguishing_features))
            )
            evidence = obj.replay_evidence
            if evidence:
                story.append(
                    self.paragraph(
                        f"历史对象：{evidence.title} · PDF 第 {evidence.pdf_page_number} 页"
                    )
                )
                story.append(self.paragraph("映射依据与限制：" + evidence.limitation))
                if evidence.source_image:
                    story.append(self.image(evidence.source_image, 480, 220))
                story.append(
                    self.paragraph(
                        "直接介绍：" + (obj.draft.introduction if obj.draft else "暂无直接介绍")
                    )
                )
                story.append(
                    self.paragraph(
                        "相关背景："
                        + (
                            obj.draft.background
                            if obj.draft and obj.draft.background
                            else "暂无经校验的背景"
                        )
                    )
                )
                story.append(self.paragraph("原文证据（可能来自不同页）："))
                for passage in evidence.passages:
                    story.append(
                        self.paragraph(
                            f"PDF 第 {passage.page_index + 1} 页 · "
                            f"字符位置 {passage.start}-{passage.end}\n{passage.quote}"
                        )
                    )
                    story.append(Spacer(1, 8))
            else:
                story.append(self.paragraph("未找到可确认的历史映射。"))
        if gaps:
            story += [PageBreak(), self.paragraph("待确认与未覆盖内容", heading=True)]
            story.extend(self.paragraph(gap) for gap in gaps)
        try:
            SimpleDocTemplate(
                str(temporary),
                pagesize=landscape(A4),
                leftMargin=40,
                rightMargin=40,
                topMargin=32,
                bottomMargin=32,
                title="PastPort photo mapping",
            ).build(story)
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
