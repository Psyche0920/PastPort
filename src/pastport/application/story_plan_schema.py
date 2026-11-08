"""Constrain content selections to the pinned evidence catalog before generation."""

import re

from pydantic import JsonValue

from pastport.domain.common import SourceLocator
from pastport.domain.story_plan import (
    BranchStoryPlan, CatalogFictionInput, CatalogFictionSection, StoryPlan,
)

from pastport.application.story_reference_contract import StoryReferenceContract
from pastport.domain.evidence import EvidencePackage


def constrain_plan_schema(schema: JsonValue, evidence: EvidencePackage) -> JsonValue:
    obj = StoryReferenceContract._object
    root = obj(schema)
    definitions = obj(root.get("$defs"))
    task = obj(obj(definitions.get("StoryPlanTask")).get("properties"))
    obj(task.get("asset_id"))["enum"] = [a.asset_id for a in evidence.assets]
    claims: list[JsonValue] = [c.claim_id for c in evidence.claims]
    obj(obj(task.get("claim_ids")).get("items"))["enum"] = claims
    source = obj(obj(definitions.get("SourceChoiceRequirement")).get("properties"))
    obj(source.get("target_claim_id"))["enum"] = claims
    obj(obj(source.get("contrast_claim_ids")).get("items"))["enum"] = claims
    return root


class CatalogFictionContract:
    """Preserve explicitly marked catalogue fiction without promoting it to fact.

    This bounded English heading profile recognises section IDs followed by
    '/ FICTION' and material headings with numbered IDs. Other layouts remain
    available in the complete page text; no semantic classification is guessed.
    """

    PREFIX = "UNTRUSTED_CATALOG_FICTION_V1: "
    HEADING = re.compile(r"^([A-Z][A-Z0-9_-]{0,63})[ \t]*/[ \t]*FICTION[ \t]*$", re.M)
    MATERIAL = re.compile(r"^MATERIAL[ \t]+([A-Z][A-Z_-]*[0-9]+)\b", re.M)

    @classmethod
    def read(cls, fragments: tuple[SourceLocator, ...]) -> CatalogFictionInput:
        # Rejoin page chunks before recognizing a heading crossing the chunk boundary.
        pages: dict[tuple[str, str, str, int | None], list[SourceLocator]] = {}
        for fragment in fragments:
            key = (fragment.source_id, fragment.source_version, fragment.file_sha256,
                   fragment.page_index)
            pages.setdefault(key, []).append(fragment)
        sections: list[CatalogFictionSection] = []
        for parts in pages.values():
            content = "".join(p.paragraph_or_region or "" for p in parts)
            matches = list(cls.HEADING.finditer(content))
            for number, match in enumerate(matches):
                body = content[match.start():matches[number + 1].start() if number + 1 < len(matches)
                               else len(content)].strip()
                locator = parts[0].model_copy(update={"paragraph_or_region": body})
                sections.append(CatalogFictionSection(
                    section_id=match[1], locator=locator,
                    material_ids=tuple(dict.fromkeys(cls.MATERIAL.findall(body))),
                ))
        ids = [s.section_id for s in sections]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate catalogue fiction section IDs need explicit source refinement")
        return CatalogFictionInput(sections=tuple(sections))

    @classmethod
    def from_constraints(cls, constraints: tuple[str, ...]) -> CatalogFictionInput | None:
        values = [line[len(cls.PREFIX):] for line in constraints if line.startswith(cls.PREFIX)]
        if len(values) > 1:
            raise ValueError("Multiple catalogue fiction inputs are ambiguous")
        return CatalogFictionInput.model_validate_json(values[0]) if values else None

    @staticmethod
    def normalize(text: str) -> str:
        return " ".join(text.split())

    @classmethod
    def validate(cls, plan: StoryPlan | BranchStoryPlan, catalog: CatalogFictionInput) -> None:
        sections = {s.section_id: s for s in catalog.sections}
        covered: set[str] = set()
        used_materials: set[tuple[str, str]] = set()
        for material in plan.fictional_materials:
            section = sections.get(material.section_id)
            if section is None:
                raise ValueError("Fiction adaptation refers to an unknown source section")
            allowed = section.material_ids or (section.section_id,)
            if material.material_id not in allowed:
                raise ValueError("Fiction adaptation refers to an unknown source material")
            quote = cls.normalize(material.source_quote)
            if len(quote) < 20 or quote not in cls.normalize(section.locator.paragraph_or_region or ""):
                raise ValueError("Fiction adaptation quote is absent from its original source section")
            covered.add(section.section_id)
            used_materials.add((section.section_id, material.material_id))
        expected = {(s.section_id, m) for s in catalog.sections
                    for m in (s.material_ids or (s.section_id,))}
        if covered != set(sections) or used_materials != expected:
            raise ValueError("Fiction adaptation omitted source events or materials")
