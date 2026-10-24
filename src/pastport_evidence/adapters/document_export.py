"""Render one layout as a PDF and an editable IDML package with relative image links."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

from PIL import Image
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas

from pastport_evidence.adapters.report_layout import FONT_NAME, font_path, register_font
from pastport_evidence.domain.report import ImageFrame, ReportDocument, TextFrame

PKG = "http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging"
ET.register_namespace("idPkg", PKG)


class PDFRenderer:
    def write(self, destination: Path, document: ReportDocument) -> None:
        register_font()
        canvas = Canvas(str(destination), pagesize=(document.width, document.height))
        canvas.setTitle("PastPort - Photo Evidence Mapping (Draft)")
        canvas.setAuthor("wehan")
        for page_number, page in enumerate(document.pages, 1):
            for image in page.images:
                with Image.open(image.path) as raw:
                    scale = min(image.width / raw.width, image.height / raw.height)
                    width, height = raw.width * scale, raw.height * scale
                    canvas.drawImage(
                        ImageReader(raw),
                        image.x,
                        document.height - image.y - height,
                        width=width,
                        height=height,
                    )
            for frame in page.texts:
                canvas.setFont(FONT_NAME, frame.font_size)
                canvas.drawString(frame.x, document.height - frame.y - frame.font_size, frame.text)
                if frame.link:
                    canvas.linkURL(
                        frame.link,
                        (
                            frame.x,
                            document.height - frame.y - frame.height,
                            frame.x + frame.width,
                            document.height - frame.y,
                        ),
                        relative=0,
                    )
            canvas.setFont(FONT_NAME, 9)
            canvas.drawRightString(
                document.width - 32, 16, f"{page_number} / {len(document.pages)}"
            )
            canvas.showPage()
        canvas.save()


class IDMLRenderer:
    """Write independently authored IDML; no source-template content or metadata is copied."""

    @staticmethod
    def _xml(root: ET.Element) -> bytes:
        result = ET.tostring(root, encoding="utf-8", xml_declaration=True)
        if not isinstance(result, bytes):
            raise ValueError("XML serialization did not produce bytes")
        return result

    @staticmethod
    def _geometry(parent: ET.Element, width: float, height: float) -> None:
        props = ET.SubElement(parent, "Properties")
        geometry = ET.SubElement(props, "PathGeometry")
        path = ET.SubElement(geometry, "GeometryPathType", PathOpen="false")
        points = ET.SubElement(path, "PathPointArray")
        for x, y in ((0, 0), (0, height), (width, height), (width, 0)):
            point = f"{x} {y}"
            ET.SubElement(
                points, "PathPointType", Anchor=point, LeftDirection=point, RightDirection=point
            )

    def _story(self, name: str, text: TextFrame) -> ET.Element:
        package = ET.Element(f"{{{PKG}}}Story", DOMVersion="6.0")
        story = ET.SubElement(
            package, "Story", Self=name, AppliedTOCStyle="n", TrackChanges="false", StoryTitle=name
        )
        paragraph = ET.SubElement(
            story, "ParagraphStyleRange", AppliedParagraphStyle="ParagraphStyle/Body"
        )
        run = ET.SubElement(
            paragraph,
            "CharacterStyleRange",
            AppliedCharacterStyle="CharacterStyle/$ID/[No character style]",
            PointSize=str(text.font_size),
            FontStyle="Regular",
            FillColor="Color/Black",
        )
        props = ET.SubElement(run, "Properties")
        ET.SubElement(props, "AppliedFont", type="string").text = "Noto Sans SC"
        ET.SubElement(props, "Leading", type="unit").text = str(text.font_size * 1.4)
        ET.SubElement(run, "Content").text = text.text or " "
        return package

    def _image(self, spread: ET.Element, name: str, frame: ImageFrame, linked: str) -> None:
        with Image.open(frame.path) as raw:
            width, height = raw.size
        scale = min(frame.width / width, frame.height / height)
        rectangle = ET.SubElement(
            spread,
            "Rectangle",
            Self=name,
            ContentType="GraphicType",
            ItemLayer="layer",
            AppliedObjectStyle="ObjectStyle/$ID/[None]",
            FillColor="Swatch/None",
            StrokeColor="Swatch/None",
            ItemTransform=f"1 0 0 1 {frame.x} {frame.y}",
        )
        self._geometry(rectangle, width * scale, height * scale)
        image = ET.SubElement(
            rectangle,
            "Image",
            Self=name + "image",
            ActualPpi="72 72",
            EffectivePpi=f"{72 / scale} {72 / scale}",
            ItemTransform=f"{scale} 0 0 {scale} 0 0",
            ImageTypeName="$ID/PNG" if linked.endswith(".png") else "$ID/JPEG",
        )
        props = ET.SubElement(image, "Properties")
        ET.SubElement(
            props, "GraphicBounds", Left="0", Top="0", Right=str(width), Bottom=str(height)
        )
        ET.SubElement(
            image,
            "Link",
            Self=name + "link",
            LinkResourceURI="file:" + linked,
            LinkResourceFormat="$ID/PNG" if linked.endswith(".png") else "$ID/JPEG",
            LinkClassID="35906",
            LinkClientID="257",
            LinkResourceState="Normal",
            LinkResourceStoredState="Normal",
            LinkImportPolicy="NoAutoImport",
            LinkImportStatus="NoAutoImport",
            StoredState="Normal",
        )

    def write(self, destination: Path, document: ReportDocument) -> None:
        links = destination.parent / "Links"
        links.mkdir(exist_ok=True)
        design = ET.Element(
            "Document",
            DOMVersion="6.0",
            Self="d",
            Name=destination.name,
            ActiveLayer="layer",
            ZeroPoint="0 0",
        )
        ET.SubElement(
            design,
            "Layer",
            Self="layer",
            Name="Mapping",
            Visible="true",
            Locked="false",
            Printable="true",
            IgnoreWrap="false",
            ShowGuides="true",
            LockGuides="false",
        )
        contents: dict[str, bytes] = {}
        stories: list[str] = []
        for number, page in enumerate(document.pages, 1):
            package = ET.Element(f"{{{PKG}}}Spread", DOMVersion="6.0")
            spread = ET.SubElement(
                package,
                "Spread",
                Self=f"spread{number}",
                PageCount="1",
                BindingLocation="0",
                AllowPageShuffle="false",
                ItemTransform="1 0 0 1 0 0",
            )
            page_element = ET.SubElement(
                spread,
                "Page",
                Self=f"page{number}",
                Name=str(number),
                GeometricBounds=f"0 0 {document.height} {document.width}",
                ItemTransform="1 0 0 1 0 0",
                AppliedMaster="n",
                MasterPageTransform="1 0 0 1 0 0",
            )
            ET.SubElement(
                page_element,
                "MarginPreference",
                Top="32",
                Bottom="32",
                Left="32",
                Right="32",
                ColumnCount="1",
                ColumnGutter="12",
            )
            for index, text in enumerate(page.texts):
                name = f"story{number}_{index}"
                stories.append(name)
                story_path = f"Stories/Story_{name}.xml"
                contents[story_path] = self._xml(self._story(name, text))
                ET.SubElement(design, f"{{{PKG}}}Story", src=story_path)
                frame = ET.SubElement(
                    spread,
                    "TextFrame",
                    Self=f"frame{number}_{index}",
                    ParentStory=name,
                    PreviousTextFrame="n",
                    NextTextFrame="n",
                    ContentType="TextType",
                    ItemLayer="layer",
                    AppliedObjectStyle="ObjectStyle/$ID/[Normal Text Frame]",
                    ItemTransform=f"1 0 0 1 {text.x} {text.y}",
                    FillColor="Swatch/None",
                    StrokeColor="Swatch/None",
                )
                self._geometry(frame, text.width, text.height)
                ET.SubElement(
                    frame,
                    "TextFramePreference",
                    TextColumnCount="1",
                    TextColumnGutter="0",
                    FirstBaselineOffset="AscentOffset",
                    VerticalJustification="TopAlign",
                    IgnoreWrap="true",
                )
            for index, image in enumerate(page.images):
                digest = hashlib.sha256(image.path.read_bytes()).hexdigest()
                with Image.open(image.path) as raw:
                    extension = ".png" if raw.format == "PNG" else ".jpg"
                relative = f"Links/{digest}{extension}"
                target = destination.parent / relative
                if not target.exists():
                    shutil.copyfile(image.path, target)
                self._image(spread, f"image{number}_{index}", image, relative)
            spread_path = f"Spreads/Spread_{number}.xml"
            contents[spread_path] = self._xml(package)
            ET.SubElement(design, f"{{{PKG}}}Spread", src=spread_path)
        design.set("StoryList", " ".join(stories))
        for kind in ("Graphic", "Fonts", "Styles", "Preferences"):
            ET.SubElement(design, f"{{{PKG}}}{kind}", src=f"Resources/{kind}.xml")
        graphic = ET.Element(f"{{{PKG}}}Graphic", DOMVersion="6.0")
        ET.SubElement(graphic, "Swatch", Self="Swatch/None", Name="None")
        ET.SubElement(
            graphic,
            "Color",
            Self="Color/Black",
            Name="Black",
            Model="Process",
            Space="CMYK",
            ColorValue="0 0 0 100",
        )
        fonts = ET.Element(f"{{{PKG}}}Fonts", DOMVersion="6.0")
        family = ET.SubElement(fonts, "FontFamily", Self="fontfamily", Name="Noto Sans SC")
        ET.SubElement(
            family,
            "Font",
            Self="fontregular",
            FontFamily="Noto Sans SC",
            Name="Noto Sans SC Regular",
            PostScriptName="NotoSansSC-Regular",
            FontStyleName="Regular",
            FontType="OpenTypeTrueType",
            Status="Installed",
        )
        styles = ET.Element(f"{{{PKG}}}Styles", DOMVersion="6.0")
        chars = ET.SubElement(styles, "RootCharacterStyleGroup", Self="chars")
        ET.SubElement(
            chars,
            "CharacterStyle",
            Self="CharacterStyle/$ID/[No character style]",
            Name="$ID/[No character style]",
        )
        paragraphs = ET.SubElement(styles, "RootParagraphStyleGroup", Self="paragraphs")
        ET.SubElement(
            paragraphs,
            "ParagraphStyle",
            Self="ParagraphStyle/Body",
            Name="Body",
            PointSize="10",
            FontStyle="Regular",
            FillColor="Color/Black",
            Hyphenation="false",
        )
        objects = ET.SubElement(styles, "RootObjectStyleGroup", Self="objects")
        for name in ("[None]", "[Normal Text Frame]"):
            ET.SubElement(
                objects, "ObjectStyle", Self=f"ObjectStyle/$ID/{name}", Name=f"$ID/{name}"
            )
        prefs = ET.Element(f"{{{PKG}}}Preferences", DOMVersion="6.0")
        ET.SubElement(
            prefs,
            "DocumentPreference",
            PageWidth=str(document.width),
            PageHeight=str(document.height),
            PagesPerDocument=str(len(document.pages)),
            FacingPages="false",
            DocumentBleedTopOffset="0",
            DocumentBleedBottomOffset="0",
            DocumentBleedInsideOrLeftOffset="0",
            DocumentBleedOutsideOrRightOffset="0",
        )
        for name, node in (
            ("Graphic", graphic),
            ("Fonts", fonts),
            ("Styles", styles),
            ("Preferences", prefs),
        ):
            contents[f"Resources/{name}.xml"] = self._xml(node)
        contents["designmap.xml"] = self._xml(design)
        contents["META-INF/container.xml"] = (
            b'<?xml version="1.0"?><container version="1.0" '
            b'xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
            b'<rootfile full-path="designmap.xml" media-type="text/xml"/>'
            b"</rootfiles></container>"
        )
        with ZipFile(destination, "w", compression=ZIP_DEFLATED) as archive:
            archive.writestr(
                "mimetype", "application/vnd.adobe.indesign-idml-package", compress_type=ZIP_STORED
            )
            for name, payload in contents.items():
                archive.writestr(name, payload)
        fonts_folder = destination.parent / "Document fonts"
        fonts_folder.mkdir(exist_ok=True)
        shutil.copyfile(font_path(), fonts_folder / font_path().name)
