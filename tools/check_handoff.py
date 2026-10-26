"""Check module inventories and shared collaboration-document routes offline."""

import sys
from pathlib import Path

SOURCE_SUFFIXES = frozenset({".py", ".mjs", ".ts", ".mts", ".html", ".css"})
DOCUMENT_NAMES = ("README.md", "ACTIVE_PLAN.md", "DECISION_LOG.md", "CHANGELOG.md")
ROUTE_FILES = ("README.md", "AGENTS.md", ".github/copilot-instructions.md")
SUPPORT_DOCUMENTS = frozenset(
    {
        "IMPLEMENTATION_GUIDE.md",
        "PastPort_PRD_CN.md",
        "PastPort_PRD_EN.md",
        "ci-and-copilot.md",
        "technical/STORY_WORKFLOW_ARCHITECTURE.md",
        "showcase/hero.svg",
        "showcase/workflow.svg",
    }
)
REFERENCE_FILES = frozenset(
    {
        "README.md",
        "check_contracts.py",
        "check_plugin.mjs",
        "plugin-api.d.ts",
        "sdk-contracts.schema.json",
        "test_reference_contracts.py",
        "examples/host-lifecycle.json",
        "examples/game/bundle.json",
        *(
            f"examples/game/data/{name}.json"
            for name in (
                "evidence",
                "filter-report",
                "museum",
                "narrative-draft",
                "plugin-receipt",
                "presentation",
                "resources",
                "route",
                "runtime",
                "source-corpus",
                "tour",
            )
        ),
        *(
            f"examples/game/media/{name}"
            for name in (
                "cartoon-one.png",
                "pano-one.png",
                "pano-two.png",
                "source-image.png",
                "synthetic-hatch.svg",
                "synthetic-source.txt",
            )
        ),
        *(
            f"examples/game/plugins/pastport.match-pairs/1.0.0/{name}"
            for name in (
                "logic.mjs",
                "manifest.json",
                "view.mjs",
            )
        ),
    }
)


def check(root: Path) -> tuple[str, ...]:
    errors: list[str] = []
    package = root / "src/pastport"
    main_readme = (root / "README.md").read_text()
    folders = [
        package,
        *(p for p in sorted(package.iterdir()) if p.is_dir() and (p / "__init__.py").exists()),
    ]
    for folder in folders:
        readme = folder / "README.md"
        if not readme.is_file():
            errors.append(f"{folder.relative_to(root)}: missing README.md")
            continue
        text = readme.read_text()
        for source in sorted(folder.iterdir()):
            if (
                source.is_file()
                and source.suffix in SOURCE_SUFFIXES
                and f"]({source.name})" not in text
            ):
                errors.append(
                    f"{readme.relative_to(root)}: missing source purpose link: {source.name}"
                )
        if readme.relative_to(root).as_posix() not in main_readme:
            errors.append(f"README.md: missing module link: {readme.relative_to(root)}")
    documents = {root / "docs" / name for name in DOCUMENT_NAMES}
    for document in sorted(documents):
        if not document.is_file():
            errors.append(f"{document.relative_to(root)}: missing collaboration document")
    for name in ROUTE_FILES:
        route = root / name
        if not route.is_file():
            errors.append(f"{name}: missing collaboration entry point")
            continue
        text = route.read_text()
        for document in sorted(documents):
            relative = document.relative_to(root).as_posix()
            if relative not in text:
                errors.append(f"{name}: missing collaboration route: {relative}")
    for path in sorted((root / "docs").rglob("*")):
        if path.suffix == ".pyc" and "__pycache__" in path.parts:
            continue
        if path.is_file() and path not in documents:
            relative = path.relative_to(root / "docs").as_posix()
            reference = relative.removeprefix("technical/sdk-v1/")
            if relative not in SUPPORT_DOCUMENTS and not (
                relative.startswith("technical/sdk-v1/") and reference in REFERENCE_FILES
            ):
                errors.append(
                    f"{path.relative_to(root)}: use the canonical documents "
                    "or registered reference files"
                )
    for name in ("CHANGELOG.md", "changelogs"):
        if (root / name).exists():
            errors.append(f"{name}: use the single docs/CHANGELOG.md")
    return tuple(errors)


def main() -> int:
    try:
        errors = check(Path(__file__).resolve().parents[1])
    except (OSError, ValueError) as error:
        print("Handoff check failed: " + type(error).__name__)
        return 1
    if errors:
        print("\n".join(errors))
        return 1
    print("Handoff checks passed: module inventories, shared routes and registered references.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
