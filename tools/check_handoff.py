"""Check the deliberately small current documentation contract."""

import os
import sys
from pathlib import Path

SDK_NAMES = (
    "evidence-sdk", "matched-environment-sdk", "stylization-sdk", "story-sdk", "gameplay-sdk",
)
PRD = "docs/TECHNICAL_PRD.md"
PRD_EN = "docs/TECHNICAL_PRD_EN.md"
TRANSLATIONS = ("README_EN.md", PRD_EN)
ROUTE_FILES = ("README.md", "handoff.md", "AGENTS.md", ".github/copilot-instructions.md")
REQUIRED_TOPICS = (
    "architecture-and-ownership", "technology-stack", "workflow", "contracts-and-versions",
    "sdk-modules", "story-and-agents", "verification-and-delivery",
)
EXCLUDED = frozenset({
    ".git", ".venv", ".runtime", "var", "node_modules", "__pycache__", "build", "dist",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", ".codex", ".agents",
})


def check(root: Path) -> tuple[str, ...]:
    root = root.resolve()
    errors: list[str] = []
    allowed = {"README.md", "handoff.md", "AGENTS.md", ".github/copilot-instructions.md", PRD}
    allowed.update(TRANSLATIONS)
    allowed.update(f"packages/{name}/README.md" for name in SDK_NAMES)
    for relative in sorted(allowed):
        path = root / relative
        if not path.is_file():
            errors.append(f"{relative}: missing current documentation entry")
    for relative in (PRD, PRD_EN):
        specification = root / relative
        if specification.is_file():
            text = specification.read_text()
            for topic in REQUIRED_TOPICS:
                if f'id="{topic}"' not in text:
                    errors.append(f"{relative}: missing technical topic: {topic}")
    english_readme = root / "README_EN.md"
    if english_readme.is_file() and PRD_EN not in english_readme.read_text():
        errors.append(f"README_EN.md: missing translated PRD route: {PRD_EN}")
    for relative in ROUTE_FILES:
        path = root / relative
        if path.is_file() and PRD not in path.read_text():
            errors.append(f"{relative}: missing canonical route: {PRD}")
    readme = root / "README.md"
    root_text = readme.read_text() if readme.is_file() else ""
    for name in SDK_NAMES:
        relative = f"packages/{name}/README.md"
        if f"]({relative})" not in root_text:
            errors.append(f"README.md: missing SDK link: {relative}")
        path = root / relative
        if path.is_file():
            text = path.read_text()
            for topic in ("Inputs", "Outputs", "Workflow", "Technology"):
                if f"| {topic} |" not in text:
                    errors.append(f"{relative}: missing SDK contract topic: {topic}")
            if "../../" + PRD not in text:
                errors.append(f"{relative}: missing canonical PRD route")
    docs = root / "docs"
    if docs.is_dir():
        for path in sorted(docs.rglob("*")):
            if (
                path.is_file() and path.relative_to(root).as_posix() not in {PRD, PRD_EN}
                and not any(part in EXCLUDED for part in path.relative_to(root).parts)
            ):
                errors.append(
                    f"{path.relative_to(root)}: archive historical docs/resources; keep only {PRD} and its English translation"
                )
    for folder, directories, names in os.walk(root):
        directories[:] = sorted(
            name for name in directories
            if name not in EXCLUDED and not name.endswith(".egg-info")
        )
        for name in sorted(names):
            path = Path(folder) / name
            relative = path.relative_to(root).as_posix()
            if path.suffix != ".md" or relative in allowed or relative == "CHANGELOG.md":
                continue
            # Machine Skills and their supporting resources are not user guides.
            if relative.startswith("skills/"):
                continue
            # Preserve required source and licensing notices in distributed packages.
            if relative.startswith("packages/") and name in {"UPSTREAM.md", "PROVENANCE.md"}:
                continue
            errors.append(f"{relative}: duplicate guide; use root/SDK README or {PRD}")
    return tuple(errors)


def main() -> int:
    errors = check(Path(__file__).resolve().parents[1])
    if errors:
        print("\n".join(errors))
        return 1
    print("Documentation contract passed: bilingual root README/technical PRD, team handoff and five SDK guides.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
