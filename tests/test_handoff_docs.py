"""Keep module inventories and canonical team-document routes consistent."""

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
    package = root / "src/pastport"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "README.md").write_text("[Purpose](__init__.py)")
    routes = "\n".join(
        f"docs/{name}"
        for name in ("README.md", "ACTIVE_PLAN.md", "DECISION_LOG.md", "CHANGELOG.md")
    )
    (root / "README.md").write_text("[package](src/pastport/README.md)\n" + routes)
    (root / "AGENTS.md").write_text(routes)
    (root / ".github").mkdir()
    (root / ".github/copilot-instructions.md").write_text(routes)
    (root / "docs").mkdir()
    for name in ("README.md", "ACTIVE_PLAN.md", "DECISION_LOG.md", "CHANGELOG.md"):
        (root / "docs" / name).write_text("Current authority")


def test_missing_file_purpose_and_duplicate_documentation_are_reported(tmp_path: Path) -> None:
    documentation_fixture(tmp_path)
    package = tmp_path / "src/pastport"
    (package / "README.md").write_text("Namespace without a file inventory")
    docs = tmp_path / "docs"
    (docs / "obsolete-guide.md").write_text("Unnecessary parallel guide")
    (tmp_path / "CHANGELOG.md").write_text("Obsolete change history")
    errors = checker().check(tmp_path)
    assert any("__init__.py" in error for error in errors)
    assert any("use the four canonical documents" in error for error in errors)
    assert any("use the single docs/CHANGELOG.md" in error for error in errors)


def test_canonical_documents_are_allowed_and_required(tmp_path: Path) -> None:
    documentation_fixture(tmp_path)
    assert checker().check(tmp_path) == ()
    (tmp_path / "docs/ACTIVE_PLAN.md").unlink()
    assert checker().check(tmp_path) == ("docs/ACTIVE_PLAN.md: missing collaboration document",)


def test_agents_and_copilot_must_route_to_shared_documents(tmp_path: Path) -> None:
    documentation_fixture(tmp_path)
    (tmp_path / "AGENTS.md").write_text("docs/README.md")
    (tmp_path / ".github/copilot-instructions.md").unlink()
    errors = checker().check(tmp_path)
    assert "AGENTS.md: missing collaboration route: docs/ACTIVE_PLAN.md" in errors
    assert "AGENTS.md: missing collaboration route: docs/DECISION_LOG.md" in errors
    assert "AGENTS.md: missing collaboration route: docs/CHANGELOG.md" in errors
    assert ".github/copilot-instructions.md: missing collaboration entry point" in errors


def test_current_repo_handoff_checks_pass() -> None:
    assert checker().check(Path(__file__).resolve().parents[1]) == ()
