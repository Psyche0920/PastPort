"""Generate a mock InDesign IDML package for the Turing Retro-Computing Lab."""
from __future__ import annotations

import io
from pathlib import Path
import zipfile


def make_story_xml(story_id: str, content: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<idPkg:Story xmlns:idPkg="http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging" DOMVersion="21.0">
\t<Story Self="{story_id}" UserText="true">
\t\t<ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/$ID/NormalParagraphStyle">
\t\t\t<CharacterStyleRange AppliedCharacterStyle="CharacterStyle/$ID/[No character style]">
\t\t\t\t<Content>{content}</Content>
\t\t\t</CharacterStyleRange>
\t\t</ParagraphStyleRange>
\t</Story>
</idPkg:Story>
"""


def make_spread_xml(spread_id: str, story_ids: list[str]) -> str:
    frames = "\n".join(
        f'\t\t<TextFrame Self="frame_{sid}" ParentStory="{sid}" ItemTransform="1 0 0 1 0 0" />'
        for sid in story_ids
    )
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<idPkg:Spread xmlns:idPkg="http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging" DOMVersion="21.0">
\t<Spread Self="{spread_id}">
{frames}
\t</Spread>
</idPkg:Spread>
"""


def build_turing_idml(output_path: Path) -> Path:
    stories = {
        "st_cat": "Eğitim Yapıları / Computing Heritage",
        "st_dist": "OSMANGAZİ",
        "st_tr_name": "Turing Retro-Hesaplama Laboratuvarı",
        "st_en_name": "TURING RETRO-COMPUTING LAB",
        "st_tr_desc": (
            "1987 yılında Yüksek Teknoloji Endüstriyel tarzında inşa edilen laboratuvar, "
            "Dr. Elena Vance tarafından tasarlandı ve Ada Systems tarafından kuruldu. "
            "Merkez, 1996 yılında tarihi Grandmaster Yapay Zeka Satranç Turnuvasına ev sahipliği yaptı. "
            "Laboratuvardaki en değerli tarihi eser, turnuvada kullanılan deneysel "
            "DeepBlue-Prototype #4 terminal bilgisayarıdır."
        ),
        "st_en_desc": (
            "Built in 1987 in High-Tech Industrial style, this computational laboratory "
            "was designed by Dr. Elena Vance and constructed by Ada Systems. "
            "In 1996, the facility hosted the historic Grandmaster AI Chess Blitz tournament. "
            "The primary historical artifact in the room is the DeepBlue-Prototype #4 computing terminal, "
            "an experimental workstation station famously utilized during the championship."
        ),
        "st_claim_style": "Built in 1987 in High-Tech Industrial style.",
        "st_claim_architect": "Designed by Dr. Elena Vance and constructed by Ada Systems.",
        "st_claim_event": "Hosted the historic Grandmaster AI Chess Blitz in 1996.",
        "st_claim_artifact": "Preserves the DeepBlue-Prototype #4 terminal, an experimental computing artifact.",
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        # IDML mimetype (must be first, uncompressed or standard)
        z.writestr("mimetype", "application/vnd.adobe.indesign-idml-package")

        # Container
        container_xml = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="designmap.xml" media-type="text/xml"/>
  </rootfiles>
</container>"""
        z.writestr("META-INF/container.xml", container_xml)

        # Designmap
        designmap_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Document xmlns:idPkg="http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging" DOMVersion="21.0">
  <idPkg:Spread src="Spreads/Spread_u100.xml"/>
</Document>"""
        z.writestr("designmap.xml", designmap_xml)

        # Spread
        spread_xml = make_spread_xml("u100", list(stories.keys()))
        z.writestr("Spreads/Spread_u100.xml", spread_xml)

        # Stories
        for story_id, content in stories.items():
            story_xml = make_story_xml(story_id, content)
            z.writestr(f"Stories/Story_{story_id}.xml", story_xml)

    print(f"Generated {output_path} with {len(stories)} stories and spread metadata.")
    return output_path


if __name__ == "__main__":
    out = Path("var/sources/turing_lab.idml")
    build_turing_idml(out)
