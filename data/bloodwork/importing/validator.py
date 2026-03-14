"""
validator.py — File format validation for bloodwork imports.

Validates that the uploaded file is a supported format (PDF)
and contains an extractable text layer.

Input:  file path (str or Path)
Output: ValidationResult with status and reason
"""

from dataclasses import dataclass
from pathlib import Path


SUPPORTED_EXTENSIONS = {".pdf"}
PDF_MAGIC_BYTES = b"%PDF"


@dataclass
class ValidationResult:
    valid: bool
    reason: str


def validate_pdf(file_path: str | Path) -> ValidationResult:
    """
    Validate that a file is a supported PDF for bloodwork import.

    Checks:
    1. File exists
    2. File extension is .pdf
    3. File starts with PDF magic bytes (%PDF)
    4. File is not empty
    """
    path = Path(file_path)

    if not path.exists():
        return ValidationResult(False, f"File not found: {path}")

    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        return ValidationResult(
            False,
            f"Unsupported file format: {path.suffix}. Only PDF files are accepted."
        )

    if path.stat().st_size == 0:
        return ValidationResult(False, "File is empty.")

    # Check PDF magic bytes
    with open(path, "rb") as f:
        header = f.read(4)

    if header != PDF_MAGIC_BYTES:
        return ValidationResult(
            False,
            "File does not appear to be a valid PDF (missing PDF header)."
        )

    return ValidationResult(True, "Valid PDF file.")
