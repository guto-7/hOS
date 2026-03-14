"""
parser.py — Lab identification and marker extraction from PDF text.

Identifies the pathology lab from header/footer text, then uses
regex patterns to extract marker rows (name, value, unit, reference range, flag).

Input:  raw text from extractor
Output: ParseResult with lab info and list of raw marker dicts
"""

import re
from dataclasses import dataclass, field


# Known lab providers and their identifying strings
LAB_SIGNATURES = {
    "laverty": "Laverty Pathology",
    "qml": "QML Pathology",
    "sullivan nicolaides": "Sullivan Nicolaides Pathology",
    "australian clinical labs": "Australian Clinical Labs",
    "quest diagnostics": "Quest Diagnostics",
    "labcorp": "LabCorp",
    "sonic healthcare": "Sonic Healthcare",
    "pathology queensland": "Pathology Queensland",
}


@dataclass
class RawMarker:
    """A single marker as extracted from the PDF — no interpretation yet."""
    pdf_name: str
    value: float
    unit: str
    ref_low: float | None
    ref_high: float | None
    lab_flag: str | None
    raw_text: str  # original line for auditability


@dataclass
class ParseResult:
    lab_provider: str | None
    test_date: str | None
    markers: list[RawMarker] = field(default_factory=list)
    total_lines_scanned: int = 0


def identify_lab(text: str) -> str | None:
    """
    Identify the pathology lab from the report text.
    Matches against known lab signatures in headers/footers.
    """
    # Check first 500 and last 500 chars (header/footer area)
    search_area = (text[:500] + text[-500:]).lower()

    for signature, lab_name in LAB_SIGNATURES.items():
        if signature in search_area:
            return lab_name

    return None


def _extract_test_date(text: str) -> str | None:
    """Extract the collection/test date from the report."""
    patterns = [
        r"COLLECTED.*?(\d{2}/\d{2}/\d{4})",
        r"Collection\s+Date.*?(\d{2}/\d{2}/\d{4})",
        r"Date\s+Collected.*?(\d{2}/\d{2}/\d{4})",
        r"(\d{2}/\d{2}/\d{4})",  # fallback: first date found
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            return m.group(1)
    return None


def parse_markers(text: str) -> ParseResult:
    """
    Parse marker rows from pdftotext -layout output.

    Each data row typically looks like:
        MarkerName          value      unit       ref_low - ref_high    flag
    with generous whitespace between columns.
    """
    lab = identify_lab(text)
    test_date = _extract_test_date(text)

    # Regex for a tabular marker row
    row_re = re.compile(
        r"^\s{2,}"                                    # leading whitespace
        r"(?P<name>[A-Za-z][A-Za-z0-9 /\-().,']+?)"  # marker name
        r"\s{3,}"                                     # gap
        r"(?P<value>[<>]?\s*-?\d+\.?\d*)"             # numeric value
        r"\s+"                                        # gap
        r"(?P<unit>[A-Za-z0-9µ%^/².×x]+(?:/[A-Za-z0-9µ².]+)*)"  # unit
        r"\s+"                                        # gap
        r"(?P<ref>"                                   # reference range
        r"(?:\d+\.?\d*\s*[-–]\s*\d+\.?\d*)"           #   low - high
        r"|(?:[<≤>≥]\s*\d+\.?\d*)"                    #   < high or > low
        r")"
        r"(?:\s*\([^)]*\))?"                          # optional parenthetical
        r"(?:\s+(?P<flag>[HL]))?"                     # optional flag
        r"\s*$"
    )

    range_pattern = re.compile(r"(\d+\.?\d*)\s*[-–]\s*(\d+\.?\d*)")
    upper_only = re.compile(r"[<≤]\s*(\d+\.?\d*)")
    lower_only = re.compile(r"[>≥]\s*(\d+\.?\d*)")

    markers = []
    lines = text.split("\n")

    for line in lines:
        m = row_re.match(line)
        if not m:
            continue

        name = m.group("name").strip()
        val_str = m.group("value").strip()
        val_clean = re.sub(r"[<>≤≥]\s*", "", val_str)
        value = float(val_clean)
        unit = m.group("unit")
        ref_str = m.group("ref")
        flag = m.group("flag")

        ref_low = None
        ref_high = None
        rm = range_pattern.search(ref_str)
        um = upper_only.search(ref_str)
        lm = lower_only.search(ref_str)
        if rm:
            ref_low = float(rm.group(1))
            ref_high = float(rm.group(2))
        elif um:
            ref_high = float(um.group(1))
        elif lm:
            ref_low = float(lm.group(1))

        markers.append(RawMarker(
            pdf_name=name,
            value=value,
            unit=unit,
            ref_low=ref_low,
            ref_high=ref_high,
            lab_flag=flag,
            raw_text=line.strip(),
        ))

    return ParseResult(
        lab_provider=lab,
        test_date=test_date,
        markers=markers,
        total_lines_scanned=len(lines),
    )
