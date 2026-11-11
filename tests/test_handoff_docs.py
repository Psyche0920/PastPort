"""Current bilingual entries and SDK guides exclude archived intermediate documentation."""

import importlib.util
from pathlib import Path
from types import ModuleType


def checker() -> ModuleType:
    path = Path(__file__).resolve().parents[1] / "tools/check_handoff.py"
    specification = importlib.util.spec_from_file_location("handoff_check", path)
    assert specification and specification.loader
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def documentation_fixture(root: Path) -> None:
    module = checker()
    for relative in module.ROUTE_FILES:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(module.PRD)
    prd = root / module.PRD
    prd.parent.mkdir(parents=True, exist_ok=True)
    prd.write_text("\n".join(f'<a id="{topic}"></a>' for topic in module.REQUIRED_TOPICS))
    root_readme = root / "README.md"
    root_readme.write_text(module.PRD_EN)
    for name in module.SDK_NAMES:
        path = root / "packages" / name / "README.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("../../" + module.PRD + "\n" + "\n".join(
            f"| {topic} | Description |"
            for topic in ("Inputs", "Outputs", "Workflow", "Technology")
        ))
        with root_readme.open("a") as stream:
            stream.write(f"\n[SDK](packages/{name}/README.md)")

    (root / "README_ZH.md").write_text(root_readme.read_text().replace(module.PRD_EN, module.PRD))
    (root / module.PRD_EN).write_text(prd.read_text())


def test_duplicate_guides_are_rejected(tmp_path: Path) -> None:
    documentation_fixture(tmp_path)
    (tmp_path / "docs/obsolete-guide.md").write_text("Old parallel guide")
    (tmp_path / "handoff.md").write_text("Archived team handoff")
    (tmp_path / "CHANGELOG.md").write_text("Archived development log")
    (tmp_path / "docs/PastPort_PRD_EN.md").write_text("Duplicate PRD")
    (tmp_path / "docs/showcase").mkdir()
    (tmp_path / "docs/showcase/old.svg").write_text("<svg/>")
    errors = checker().check(tmp_path)
    assert any("showcase/old.svg: archive historical docs/resources" in e for e in errors)
    assert any("obsolete-guide.md: duplicate guide" in error for error in errors)
    assert any("handoff.md: duplicate guide" in error for error in errors)
    assert any("CHANGELOG.md: duplicate guide" in error for error in errors)
    assert any("PastPort_PRD_EN.md: duplicate guide" in error for error in errors)


def test_current_entries_and_sdk_contracts_are_required(tmp_path: Path) -> None:
    documentation_fixture(tmp_path)
    assert checker().check(tmp_path) == ()
    # Product-facing entry points need not repeat internal SDK navigation.
    (tmp_path / "README.md").write_text(checker().PRD_EN)
    assert checker().check(tmp_path) == ()
    path = tmp_path / "packages/story-sdk/README.md"
    path.write_text("Story text without an interface contract")
    errors = checker().check(tmp_path)
    assert any("story-sdk/README.md: missing SDK contract topic: Inputs" in e for e in errors)
    (tmp_path / checker().PRD).unlink()
    assert any("missing current documentation entry" in e for e in checker().check(tmp_path))


def test_coding_agents_route_to_the_single_prd(tmp_path: Path) -> None:
    documentation_fixture(tmp_path)
    (tmp_path / "AGENTS.md").write_text("Follow old plans")
    assert any("AGENTS.md: missing canonical route" in e for e in checker().check(tmp_path))


def test_current_repo_handoff_checks_pass() -> None:
    assert checker().check(Path(__file__).resolve().parents[1]) == ()


def test_machine_resources_and_provenance_are_not_parallel_guides(tmp_path: Path) -> None:
    documentation_fixture(tmp_path)
    for relative in ("skills/narrative/SKILL.md", "packages/evidence-sdk/UPSTREAM.md"):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("Required machine or provenance resource")
    assert checker().check(tmp_path) == ()
    path = tmp_path / "src/pastport/README.md"
    path.parent.mkdir(parents=True)
    path.write_text("Unwanted extra user entry")
    assert any("src/pastport/README.md: duplicate guide" in e for e in checker().check(tmp_path))


def test_requested_translations_are_required_not_parallel_guides(tmp_path: Path) -> None:
    documentation_fixture(tmp_path)
    translated = tmp_path / checker().PRD_EN
    translated.unlink()
    assert any("TECHNICAL_PRD_EN.md: missing current documentation entry" in error
               for error in checker().check(tmp_path))
    documentation_fixture(tmp_path)
    (tmp_path / "README.md").write_text("English without a specification link")
    assert any("README.md: missing translated PRD route" in error
               for error in checker().check(tmp_path))
