"""Offline checks for repository guidance; this is not a product runtime test."""
# This script checks repository guidance offline; it does not start or test the product runtime.
from __future__ import annotations

# ast parses Python syntax; json parses JSON files.
import ast
import json
import os
# Regular expressions, Unicode categories, and URL decoding support Markdown checks.
import re
import sys
import unicodedata
# dataclass defines the result structure; Path handles filesystem paths.
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote


# An immutable finding records the file and reason for an issue.
@dataclass(frozen=True)
class Finding:
    path: Path
    message: str


# The repository checker uses one implementation for local and CI checks.
class RepositoryChecker:
    """Keep local and CI planning checks identical without third-party packages."""

        # Resolve the repository root and prepare the findings list.
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.findings: list[Finding] = []

        # Scan the repository and return any findings.
    def check(self) -> tuple[Finding, ...]:
        # Clear prior results so each run is independent.
        self.findings.clear()
        # Skip dependencies, version control, runtime data, and cache directories.
        excluded = {'.git', '.venv', 'node_modules', '__pycache__', 'var', '.pytest_cache', '.mypy_cache', '.ruff_cache'}
        # Walk the repository recursively.
        for folder, directories, names in os.walk(self.root):
            # Filter directories in place and sort them for stable output.
            directories[:] = sorted(name for name in directories if name not in excluded)
            # Sort filenames to keep output stable.
            for name in sorted(names):
                # Build the file path from the current folder and filename.
                path = Path(folder) / name
                # Check Markdown, JSON, and Python files only.
                if path.suffix not in {'.md', '.json', '.py'}:
                    continue
                # Record read or parse failures and continue with the remaining files.
                try:
                    # Read every target as UTF-8.
                    text = path.read_text(encoding='utf-8')
                    # Parse JSON syntax only.
                    if path.suffix == '.json':
                        json.loads(text)
                    # Parse Python syntax without executing the file.
                    elif path.suffix == '.py':
                        ast.parse(text, filename=str(path))
                    # Delegate Markdown files to the dedicated checker.
                    else:
                        self._check_markdown(path, text)
                # Collect common I/O, encoding, parsing, and syntax errors.
                except (OSError, UnicodeError, ValueError, SyntaxError) as error:
                    self.findings.append(Finding(path, str(error)))
        # Return an immutable collection of findings.
        return tuple(self.findings)

    # This utility does not need access to a checker instance.
    # Convert a Markdown heading into an anchor for link comparison.
    @staticmethod
    def _slug(value: str) -> str:
        # Lowercase the value and replace spaces with hyphens.
        value = value.lower().replace(' ', '-')
        # Remove punctuation and symbols while preserving hyphens and underscores.
        return ''.join(char for char in value if char in '-_' or not unicodedata.category(char).startswith(('P', 'S')))

    # Extract prose lines outside fenced code blocks.
    @staticmethod
    def _prose_lines(text: str) -> tuple[list[str], bool]:
        # lines stores prose; marker tracks whether a code block is open.
        lines: list[str] = []
        marker = ''
        # Scan the text line by line for Markdown fences.
        for line in text.splitlines():
            # A code fence uses at least three backticks or tildes.
            fence = re.match(r'^\s*(`{3,}|~{3,})', line)
            if fence:
                # Record the current fence marker and its length.
                current = fence.group(1)
                # If no block is open, this line opens one.
                if not marker:
                    marker = current
                # A matching fence of sufficient length closes the block.
                elif current[0] == marker[0] and len(current) >= len(marker):
                    marker = ''
                # Do not include fence markers in prose.
                continue
            # Keep lines outside code blocks only.
            if not marker:
                lines.append(line)
        # Return prose lines and whether a fence remains open.
        return lines, bool(marker)

    # Build heading anchors for local Markdown link validation.
    def _anchors(self, path: Path) -> set[str]:
        # Ignore heading-like text inside code blocks.
        lines, _ = self._prose_lines(path.read_text(encoding='utf-8'))
        # Count duplicate headings and add numeric suffixes.
        counts: dict[str, int] = {}
        result: set[str] = set()
        # Check each line for a Markdown heading.
        for line in lines:
            # Support heading levels one through six.
            heading = re.match(r'^#{1,6}\s+(.+)', line)
            if heading:
                # Generate the base anchor from the heading text.
                slug = self._slug(heading.group(1))
                # Get the number of earlier occurrences of this heading.
                count = counts.get(slug, 0)
                # Leave the first anchor unchanged and suffix later duplicates in order.
                result.add(slug if count == 0 else f'{slug}-{count}')
                counts[slug] = count + 1
        return result

    # Check Markdown fences, local links, and Skill metadata.
    def _check_markdown(self, path: Path, text: str) -> None:
        # Exclude code examples so sample links are not treated as real links.
        lines, unclosed = self._prose_lines(text)
        # An unclosed code fence indicates malformed documentation.
        if unclosed:
            self.findings.append(Finding(path, 'Unclosed code fence'))
        # Find Markdown link targets in prose.
        for href in re.findall(r'\]\((<[^>]+>|[^)]+)\)', '\n'.join(lines)):
            # Remove optional angle brackets around a link target.
            href = href.strip('<>')
            # Skip external URI schemes such as https: and mailto:.
            if re.match(r'^[A-Za-z][A-Za-z0-9+.-]*:', href):
                continue
            # Decode the URL and separate the relative path from its anchor.
            relative, _, fragment = unquote(href).partition('#')
            # Resolve relative to this document; an anchor-only link targets this file.
            target = (path.parent / relative).resolve() if relative else path
            # Confirm that the local target exists.
            if not target.exists():
                self.findings.append(Finding(path, f'Missing local link: {href}'))
            # Validate the anchor when the target is a Markdown file.
            elif fragment and target.is_file() and target.suffix == '.md' and fragment not in self._anchors(target):
                self.findings.append(Finding(path, f'Missing section: {href}'))
        # SKILL.md files must also contain the required frontmatter.
        if path.name == 'SKILL.md':
            # Frontmatter must be at the start of the file and enclosed by --- lines.
            frontmatter = re.match(r'\A---\n(.*?)\n---\n', text, re.DOTALL)
            # Fields cannot be checked when frontmatter is missing.
            if not frontmatter:
                self.findings.append(Finding(path, 'Missing Skill frontmatter'))
                return
            # Extract the Skill name; allow lowercase letters, digits, and hyphens.
            name = re.search(r'^name:\s*([a-z0-9-]+)\s*$', frontmatter.group(1), re.MULTILINE)
            # The description must exist and be non-empty.
            description = re.search(r'^description:\s*(\S[^\n]*)$', frontmatter.group(1), re.MULTILINE)
            # Require the Skill name to match its parent folder and include a description.
            if not name or name.group(1) != path.parent.name or not description:
                self.findings.append(Finding(path, 'Skill name/description missing or folder name mismatch'))


# Command-line entry point: run checks and return the process exit status.
def main() -> int:
    # The script is in tools/, so its grandparent is the repository root.
    root = Path(__file__).resolve().parents[1]
    # Create the checker and run it.
    findings = RepositoryChecker(root).check()
    # Print each finding with its repository-relative path.
    for finding in findings:
        print(f'{finding.path.relative_to(root)}: {finding.message}')
    # Return failure when findings exist so CI can detect them.
    if findings:
        return 1
    # State clearly that runtime, model, and player behavior are outside this check.
    print('Repository structure checks passed. Runtime, model and player behavior were not tested.')
    return 0


# Run the command-line checks only when this file is executed directly.
if __name__ == '__main__':
    # Return the check result as the process exit code.
    sys.exit(main())
