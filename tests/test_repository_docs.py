"""Keep explicit documentation anchors valid without hiding broken references."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def checker() -> ModuleType:
    path = Path(__file__).resolve().parents[1] / "tools/check_repository.py"
    specification = importlib.util.spec_from_file_location("repository_check", path)
    assert specification and specification.loader
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


def test_explicit_anchors_and_heading_links_are_checked(tmp_path: Path) -> None:
    (tmp_path / "target.md").write_text('<a id="s2-9"></a>\n# Ownership\n')
    source = tmp_path / "README.md"
    source.write_text("[contract](target.md#s2-9)\n[heading](target.md#ownership)")
    assert checker().RepositoryChecker(tmp_path).check() == ()
    source.write_text("[missing section](target.md#missing)\n[missing file](gone.md)")
    findings = checker().RepositoryChecker(tmp_path).check()
    assert {finding.message for finding in findings} == {
        "Missing section: target.md#missing",
        "Missing local link: gone.md",
    }


def test_fenced_example_is_not_an_anchor(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text('```html\n<a id="example"></a>\n```\n[bad](#example)\n')
    assert len(checker().RepositoryChecker(tmp_path).check()) == 1


def test_runtime_and_sdk_build_outputs_are_not_source(tmp_path: Path) -> None:
    for name in (".runtime", "packages/sample/build", "packages/sample/dist"):
        folder = tmp_path / name
        folder.mkdir(parents=True)
        (folder / "invalid.json").write_text("not JSON")
    assert checker().RepositoryChecker(tmp_path).check() == ()
    (tmp_path / "packages/sample/invalid.json").write_text("not JSON")
    assert len(checker().RepositoryChecker(tmp_path).check()) == 1
