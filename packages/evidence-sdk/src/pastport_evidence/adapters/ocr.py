"""Bounded Tesseract TSV recognition with page-space line provenance."""

import csv
import io
import os
import re
import shutil
import subprocess
import unicodedata
from collections import defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

from pastport_evidence.domain.pdf import PDFRegion, PDFTextLine
from pastport_evidence.ports.ocr import OCRError, OCRResult


class TesseractPageOCR:
    def __init__(self, executable: Path | None = None, languages: str | None = None) -> None:
        self._executable = executable
        self._languages = languages

    def recognize(
        self,
        image: bytes,
        page_width: float,
        page_height: float,
        timeout_seconds: int,
    ) -> OCRResult:
        executable = str(self._executable) if self._executable else shutil.which("tesseract")
        if not executable:
            raise OCRError("OCR_REQUIRED: install Tesseract and the PDF's language data")
        try:
            available_result = subprocess.run(
                [executable, "--list-langs"],
                check=True,
                capture_output=True,
                text=True,
                timeout=min(timeout_seconds, 10),
            )
            available = set(available_result.stdout.splitlines()[1:])
            configured = self._languages or os.environ.get("PASTPORT_OCR_LANGUAGES")
            languages = configured or "+".join(
                lang for lang in ("eng", "chi_sim", "chi_tra", "tur", "deu") if lang in available
            )
            if not languages or not re.fullmatch(r"[a-zA-Z_]+(?:\+[a-zA-Z_]+)*", languages):
                raise OCRError("OCR_LANGUAGE_UNAVAILABLE: configure PASTPORT_OCR_LANGUAGES")
            if not set(languages.split("+")) <= available:
                raise OCRError(
                    "OCR_LANGUAGE_UNAVAILABLE: install configured Tesseract language data"
                )
            version = subprocess.run(
                [executable, "--version"],
                check=True,
                capture_output=True,
                text=True,
                timeout=min(timeout_seconds, 10),
            ).stdout.splitlines()[0]
            with Image.open(io.BytesIO(image)) as page:
                width, height = page.size
            with TemporaryDirectory(prefix="pastport-page-ocr-") as folder:
                source = Path(folder) / "page.jpg"
                source.write_bytes(image)
                result = subprocess.run(
                    [executable, str(source), "stdout", "-l", languages, "--oem", "1", "tsv"],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=timeout_seconds,
                    env={**os.environ, "OMP_THREAD_LIMIT": "1"},
                )
        except (OSError, subprocess.SubprocessError) as error:
            raise OCRError(
                "OCR_FAILED: local recognition failed or exceeded its timeout"
            ) from error
        if len(result.stdout) > 16 * 1024**2:
            raise OCRError("OCR_FAILED: page output exceeds its bound")
        groups: dict[tuple[str, str, str], list[tuple[str, float, float, float, float]]] = (
            defaultdict(list)
        )
        confidences: list[float] = []
        try:
            for row in csv.DictReader(io.StringIO(result.stdout), delimiter="\t"):
                text = row.get("text", "").strip()
                if row["level"] != "5" or not text:
                    continue
                confidence = float(row["conf"])
                if confidence < 0:
                    continue
                x, y = float(row["left"]), float(row["top"])
                x1, y1 = x + float(row["width"]), y + float(row["height"])
                if not 0 <= x <= x1 <= width or not 0 <= y <= y1 <= height:
                    raise OCRError("OCR_FAILED: word bounds are outside the rendered page")
                groups[(row["block_num"], row["par_num"], row["line_num"])].append(
                    (text, x, y, x1, y1)
                )
                confidences.append(confidence)
        except (KeyError, TypeError, ValueError) as error:
            raise OCRError("OCR_FAILED: invalid TSV recognition output") from error
        mean_confidence = sum(confidences) / len(confidences) if confidences else None
        if mean_confidence is not None and mean_confidence < 40:
            raise OCRError("OCR_LOW_CONFIDENCE: review the scan before using its text as evidence")
        lines: list[PDFTextLine] = []
        for words in groups.values():
            text = " ".join(word[0] for word in words)
            lines.append(
                PDFTextLine(
                    line_index=len(lines),
                    text=text,
                    normalized_text=unicodedata.normalize("NFKC", text),
                    region=PDFRegion(
                        x0=min(w[1] for w in words) / width * page_width,
                        top=min(w[2] for w in words) / height * page_height,
                        x1=max(w[3] for w in words) / width * page_width,
                        bottom=max(w[4] for w in words) / height * page_height,
                    ),
                )
            )
        return OCRResult(tuple(lines), version, languages, mean_confidence)
