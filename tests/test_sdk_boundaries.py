"""Package installation cannot silently activate providers or reverse SDK dependencies."""

import ast
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def imports(root: Path) -> set[str]:
    modules: set[str] = set()
    for path in root.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom) and node.module:
                modules.add(node.module.split(".")[0])
            elif isinstance(node, ast.Import):
                modules.update(alias.name.split(".")[0] for alias in node.names)
    return modules


def test_sdk_dependencies_are_one_way_and_main_runtime_stays_independent() -> None:
    assert not imports(ROOT / "src/pastport") & {
        "pastport_evidence",
        "pastport_pdf_vr",
        "pastport_matched_environment",
        "pastport_stylization",
    }
    assert not imports(ROOT / "packages/evidence-sdk/src") & {
        "pastport",
        "pastport_matched_environment",
        "pastport_stylization",
    }
    assert not imports(ROOT / "packages/matched-environment-sdk/src") & {
        "pastport",
        "pastport_evidence",
        "pastport_pdf_vr",
        "pastport_stylization",
    }
    assert not imports(ROOT / "packages/stylization-sdk/src") & {
        "pastport",
        "pastport_evidence",
        "pastport_pdf_vr",
    }


def test_authoring_and_provider_installation_require_explicit_extras() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    assert all("pastport-" not in item and "codex" not in item for item in project["dependencies"])
    extras = project["optional-dependencies"]
    assert set(extras["authoring"]) == {
        "pastport-evidence==0.1.0",
        "pastport-matched-environment==0.1.0",
        "pastport-stylization==0.1.0",
    }
    assert set(extras["authoring-codex"]) == {
        "pastport-evidence[codex]==0.1.0",
        "pastport-matched-environment[codex]==0.1.0",
        "pastport-stylization[codex]==0.1.0",
    }
    style = tomllib.loads((ROOT / "packages/stylization-sdk/pyproject.toml").read_text())
    assert style["project"]["dependencies"] == ["pastport-matched-environment==0.1.0"]
