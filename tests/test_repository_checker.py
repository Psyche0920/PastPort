"""Regression checks for real Markdown targets and false anchors in examples."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tools.check_repository import RepositoryChecker


class RepositoryCheckerTests(unittest.TestCase):
    """Run offline without optional test dependencies."""

    def test_explicit_anchors_resolve_across_documents(self) -> None:
        with TemporaryDirectory() as directory:
            self._test_explicit_anchors_resolve_across_documents(Path(directory))

    @staticmethod
    def _test_explicit_anchors_resolve_across_documents(tmp_path: Path) -> None:
        (tmp_path / "source.md").write_text(
            "[Section](target.md#section-id)\n[Legacy](target.md#legacy)\n"
            "[Unicode](target.md#%E7%AB%A0%E8%8A%82)\n",
            encoding="utf-8",
        )
        (tmp_path / "target.md").write_text(
            "<a id='section-id'></a>\n<a name=\"legacy\"></a>\n"
            "<section id=\"章节\">Text</section>\n",
            encoding="utf-8",
        )
        assert RepositoryChecker(tmp_path).check() == ()


    def test_nonrendered_anchors_do_not_hide_broken_links(self) -> None:
        with TemporaryDirectory() as directory:
            self._test_nonrendered_anchors_do_not_hide_broken_links(Path(directory))

    @staticmethod
    def _test_nonrendered_anchors_do_not_hide_broken_links(tmp_path: Path) -> None:
        (tmp_path / "guide.md").write_text(
            "[Fenced](#fenced)\n[Inline](#inline)\n[Comment](#comment)\n"
            "```html\n<a id=\"fenced\"></a>\n```\n"
            "`<a id=\"inline\"></a>`\n<!-- <a id=\"comment\"></a> -->\n",
            encoding="utf-8",
        )
        findings = RepositoryChecker(tmp_path).check()
        assert {finding.message for finding in findings} == {
            "Missing section: #fenced",
            "Missing section: #inline",
            "Missing section: #comment",
        }


    def test_heading_duplicates_and_missing_targets_remain_checked(self) -> None:
        with TemporaryDirectory() as directory:
            self._test_heading_duplicates_and_missing_targets_remain_checked(Path(directory))

    @staticmethod
    def _test_heading_duplicates_and_missing_targets_remain_checked(tmp_path: Path) -> None:
        (tmp_path / "guide.md").write_text(
            "# Topic\n# Topic\n<a id=\"explicit\"></a>\n"
            "[First](#topic)\n[Second](#topic-1)\n[Explicit](#explicit)\n"
            "[Missing heading](#topic-2)\n[Missing file](absent.md)\n",
            encoding="utf-8",
        )
        findings = RepositoryChecker(tmp_path).check()
        assert {finding.message for finding in findings} == {
            "Missing section: #topic-2",
            "Missing local link: absent.md",
        }


    def test_unclosed_fence_remains_a_failure(self) -> None:
        with TemporaryDirectory() as directory:
            self._test_unclosed_fence_remains_a_failure(Path(directory))

    @staticmethod
    def _test_unclosed_fence_remains_a_failure(tmp_path: Path) -> None:
        (tmp_path / "guide.md").write_text("```html\n<a id='not-rendered'>\n")
        assert [finding.message for finding in RepositoryChecker(tmp_path).check()] == [
            "Unclosed code fence"
        ]
