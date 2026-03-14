"""
extractor.py — PDF text extraction using pdftotext.

Extracts the full text layer from a digital PDF using the
pdftotext command-line tool with layout preservation.

Input:  PDF file path
Output: ExtractionResult with raw text and metadata
"""

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ExtractionResult:
    text: str
    page_count: int
    success: bool
    error: str | None = None


def _find_pdftotext() -> str:
    """Locate the pdftotext binary."""
    path = shutil.which("pdftotext")
    if path:
        return path
    # macOS Homebrew fallback
    homebrew = "/opt/homebrew/bin/pdftotext"
    if Path(homebrew).exists():
        return homebrew
    raise FileNotFoundError(
        "pdftotext not found. Install it with: brew install poppler"
    )


def extract_text(file_path: str | Path) -> ExtractionResult:
    """
    Extract text from a PDF using pdftotext.

    Tries layout mode first (preserves tabular structure),
    falls back to plain mode if layout fails.
    """
    path = str(file_path)
    pdftotext = _find_pdftotext()

    # Try with -layout first (preserves column alignment)
    result = subprocess.run(
        [pdftotext, "-layout", path, "-"],
        capture_output=True, text=True,
    )

    if result.returncode != 0:
        # Fallback to plain extraction
        result = subprocess.run(
            [pdftotext, path, "-"],
            capture_output=True, text=True,
        )

    if result.returncode != 0:
        return ExtractionResult(
            text="",
            page_count=0,
            success=False,
            error=f"pdftotext failed: {result.stderr.strip()}",
        )

    text = result.stdout

    # Count pages (form feed characters separate pages in pdftotext output)
    page_count = text.count("\f") + 1 if text else 0

    return ExtractionResult(
        text=text,
        page_count=page_count,
        success=True,
    )
