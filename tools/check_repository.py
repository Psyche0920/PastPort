"""Check specification files offline; this is not a product runtime test."""
from __future__ import annotations

import ast
import json
import os
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote


@dataclass(frozen=True)
class Finding:
    path: Path
    message: str


class RepositoryChecker:
    """Keep local and CI planning checks identical without third-party packages."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.findings: list[Finding] = []

    def check(self) -> tuple[Finding, ...]:
        self.findings.clear()
        excluded = {'.git', '.venv', 'node_modules', '__pycache__', 'var', '.pytest_cache', '.mypy_cache', '.ruff_cache'}
        for folder, directories, names in os.walk(self.root):
            directories[:] = sorted(name for name in directories if name not in excluded)
            for name in sorted(names):
                path = Path(folder) / name
                if path.suffix not in {'.md', '.json', '.py'}:
                    continue
                try:
                    text = path.read_text(encoding='utf-8')
                    if path.suffix == '.json':
                        json.loads(text)
                    elif path.suffix == '.py':
                        ast.parse(text, filename=str(path))
                    else:
                        self._check_markdown(path, text)
                except (OSError, UnicodeError, ValueError, SyntaxError) as error:
                    self.findings.append(Finding(path, str(error)))
        return tuple(self.findings)

    @staticmethod
    def _slug(value: str) -> str:
        value = value.lower().replace(' ', '-')
        return ''.join(char for char in value if char in '-_' or not unicodedata.category(char).startswith(('P', 'S')))

    @staticmethod
    def _prose_lines(text: str) -> tuple[list[str], bool]:
        lines: list[str] = []
        marker = ''
        for line in text.splitlines():
            fence = re.match(r'^\s*(`{3,}|~{3,})', line)
            if fence:
                current = fence.group(1)
                if not marker:
                    marker = current
                elif current[0] == marker[0] and len(current) >= len(marker):
                    marker = ''
                continue
            if not marker:
                lines.append(line)
        return lines, bool(marker)

    def _anchors(self, path: Path) -> set[str]:
        lines, _ = self._prose_lines(path.read_text(encoding='utf-8'))
        counts: dict[str, int] = {}
        result: set[str] = set()
        for line in lines:
            heading = re.match(r'^#{1,6}\s+(.+)', line)
            if heading:
                slug = self._slug(heading.group(1))
                count = counts.get(slug, 0)
                result.add(slug if count == 0 else f'{slug}-{count}')
                counts[slug] = count + 1
        return result

    def _check_markdown(self, path: Path, text: str) -> None:
        lines, unclosed = self._prose_lines(text)
        if unclosed:
            self.findings.append(Finding(path, 'Unclosed code fence'))
        for href in re.findall(r'\]\((<[^>]+>|[^)]+)\)', '\n'.join(lines)):
            href = href.strip('<>')
            if re.match(r'^[A-Za-z][A-Za-z0-9+.-]*:', href):
                continue
            relative, _, fragment = unquote(href).partition('#')
            target = (path.parent / relative).resolve() if relative else path
            if not target.exists():
                self.findings.append(Finding(path, f'Missing local link: {href}'))
            elif fragment and target.is_file() and target.suffix == '.md' and fragment not in self._anchors(target):
                self.findings.append(Finding(path, f'Missing section: {href}'))
        if path.name == 'SKILL.md':
            frontmatter = re.match(r'\A---\n(.*?)\n---\n', text, re.DOTALL)
            if not frontmatter:
                self.findings.append(Finding(path, 'Missing Skill frontmatter'))
                return
            name = re.search(r'^name:\s*([a-z0-9-]+)\s*$', frontmatter.group(1), re.MULTILINE)
            description = re.search(r'^description:\s*(\S[^\n]*)$', frontmatter.group(1), re.MULTILINE)
            if not name or name.group(1) != path.parent.name or not description:
                self.findings.append(Finding(path, 'Skill name/description missing or folder name mismatch'))


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    findings = RepositoryChecker(root).check()
    for finding in findings:
        print(f'{finding.path.relative_to(root)}: {finding.message}')
    if findings:
        return 1
    print('Repository structure checks passed. Runtime, model and player behavior were not tested.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
