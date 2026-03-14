"""
parser.py — BIA device identification and marker extraction from PDF text.

Identifies the BIA device manufacturer from header text, then uses
keyword-based regex patterns to extract body composition marker values.

Supports: InBody, Tanita, generic BIA formats.

Input:  raw text from extractor
Output: ParseResult with device info and list of raw marker dicts
"""

import re
from dataclasses import dataclass, field


# Known BIA device signatures
DEVICE_SIGNATURES = {
    "inbody": "InBody",
    "lookinbody": "InBody",
    "tanita": "Tanita",
    "seca": "Seca",
    "omron": "Omron",
    "withings": "Withings",
    "dexa": "DEXA",
    "bod pod": "Bod Pod",
}


@dataclass
class RawMarker:
    """A single marker as extracted from the PDF — no interpretation yet."""
    pdf_name: str
    value: float
    unit: str
    ref_low: float | None
    ref_high: float | None
    raw_text: str  # original line for auditability


@dataclass
class ParseResult:
    device: str | None
    test_date: str | None
    markers: list[RawMarker] = field(default_factory=list)
    total_lines_scanned: int = 0


def identify_device(text: str) -> str | None:
    """
    Identify the BIA device from the report text.
    Matches against known device signatures.
    """
    search_area = (text[:800] + text[-500:]).lower()

    for signature, device_name in DEVICE_SIGNATURES.items():
        if signature in search_area:
            return device_name

    return None


def _extract_test_date(text: str) -> str | None:
    """Extract the test date from the report."""
    patterns = [
        # InBody format: "13.12.2024. 14:01" or "Test Date / Time ... 13.12.2024"
        r"(\d{2}\.\d{2}\.\d{4})",
        # Standard formats
        r"(?:Test\s+)?Date.*?(\d{2}/\d{2}/\d{4})",
        r"(\d{4}-\d{2}-\d{2})",
        r"(\d{2}/\d{2}/\d{4})",
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            return m.group(1)
    return None


# ── Marker extraction patterns ────────────────────────────────────────────
#
# BIA PDFs (especially InBody) are NOT tabular like lab reports.
# Values appear next to labels in various layouts.  We use keyword-based
# extraction: for each marker we know the label text and search for the
# numeric value near it.

# Each entry: (marker_name, regex_pattern, unit)
# Patterns are tried top-to-bottom; first match wins per marker.

_MARKER_PATTERNS: list[tuple[str, list[str], str]] = [
    ("Weight", [
        r"(?:Sum of the above|Sum\b).*?Weight\s*\(kg\)\s*(\d+\.?\d*)",
        r"Weight\s*\(kg\)\s*(\d+\.?\d*)",
        r"Weight\s+(\d+\.?\d*)\s*kg",
    ], "kg"),

    ("Skeletal Muscle Mass", [
        r"SMM\s*\(kg\)\s*(\d+\.?\d*)",
        r"Skeletal\s*Muscle\s*Mass\s*\(kg\)\s*(\d+\.?\d*)",
        r"SMM\s+(\d+\.?\d*)\s*kg",
        r"Skeletal\s*Muscle\s*Mass\s+(\d+\.?\d*)",
    ], "kg"),

    ("Body Fat Mass", [
        r"(?:For storing excess energy|storing excess)\s*Body\s*Fat\s*Mass\s*\(kg\)\s*(\d+\.?\d*)",
        r"Body\s*Fat\s*Mass\s*\(kg\)\s*(\d+\.?\d*)",
        r"Body\s*Fat\s*Mass\s+(\d+\.?\d*)\s*kg",
        r"Body\s*Fat\s*Mass\s+(\d+\.?\d*)",
    ], "kg"),

    ("BMI", [
        r"BMI\s*\(kg/m[²2]\)\s*(\d+\.?\d*)",
        r"BMI\s*(?:Body Mass Index)?\s*\(kg/m[²2]\)\s*(\d+\.?\d*)",
        r"BMI\s+(\d+\.?\d*)\s*kg/m",
        r"BMI\s+(\d+\.?\d*)",
    ], "kg/m²"),

    ("Body Fat Percentage", [
        r"PBF\s*\(%\)\s*(\d+\.?\d*)",
        r"(?:Percent Body Fat|PBF)\s*\(%?\)?\s*(\d+\.?\d*)",
        r"PBF\s+(\d+\.?\d*)\s*%",
        r"Body\s*Fat\s*(?:Percentage|%)\s+(\d+\.?\d*)",
    ], "%"),

    ("Visceral Fat Level", [
        r"Visceral\s*Fat\s*Level\s*[-–]?\s*Level\s+(\d+\.?\d*)",
        r"Visceral\s*Fat\s*Level\s+(\d+\.?\d*)",
        r"Level\s+(\d+)\s",
    ], "level"),

    ("Basal Metabolic Rate", [
        r"Basal\s*Metabolic\s*Rate\s+(\d+\.?\d*)\s*kcal",
        r"Basal\s*Metabolic\s*Rate\s+(\d+\.?\d*)",
        r"BMR\s+(\d+\.?\d*)\s*kcal",
    ], "kcal"),

    ("Fat Free Mass", [
        r"Fat\s*Free\s*Mass\s+(\d+\.?\d*)\s*kg",
        r"Fat\s*Free\s*Mass\s+(\d+\.?\d*)",
        r"FFM\s+(\d+\.?\d*)",
    ], "kg"),

    ("Total Body Water", [
        r"Total\s*Body\s*Water\s*\(L\)\s*(\d+\.?\d*)",
        r"Total\s*Body\s*Water\s+(\d+\.?\d*)\s*L",
        r"Total\s*Body\s*Water\s+(\d+\.?\d*)",
        r"TBW\s+(\d+\.?\d*)",
    ], "L"),

    ("Protein", [
        r"(?:For building muscles|building muscles)\s*Protein\s*\(kg\)\s*(\d+\.?\d*)",
        r"Protein\s*\(kg\)\s*(\d+\.?\d*)",
        r"Protein\s+(\d+\.?\d*)\s*kg",
    ], "kg"),

    ("Minerals", [
        r"(?:For strengthening bones|strengthening bones)\s*Minerals\s*\(kg\)\s*(\d+\.?\d*)",
        r"Minerals\s*\(kg\)\s*(\d+\.?\d*)",
        r"Minerals\s+(\d+\.?\d*)\s*kg",
    ], "kg"),

    ("Target Weight", [
        r"Target\s*Weight\s+(\d+\.?\d*)\s*kg",
        r"Target\s*Weight\s+(\d+\.?\d*)",
        r"Ideal\s*(?:Body\s*)?Weight\s+(\d+\.?\d*)",
    ], "kg"),
]


def parse_markers(text: str) -> ParseResult:
    """
    Parse body composition markers from pdftotext -layout output.

    Uses keyword-based regex matching rather than row-based parsing,
    since BIA reports have varied layouts with charts and graphics.
    """
    device = identify_device(text)
    test_date = _extract_test_date(text)

    markers: list[RawMarker] = []
    lines = text.split("\n")

    for marker_name, patterns, unit in _MARKER_PATTERNS:
        for pattern in patterns:
            m = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if m:
                try:
                    value = float(m.group(1))
                except (ValueError, IndexError):
                    continue

                # Find the source line for auditability
                raw_line = ""
                match_start = m.start()
                pos = 0
                for line in lines:
                    if pos <= match_start < pos + len(line) + 1:
                        raw_line = line.strip()
                        break
                    pos += len(line) + 1

                markers.append(RawMarker(
                    pdf_name=marker_name,
                    value=value,
                    unit=unit,
                    ref_low=None,
                    ref_high=None,
                    raw_text=raw_line,
                ))
                break  # first match wins for this marker

    # Compute derived markers
    weight_marker = next((m for m in markers if m.pdf_name == "Weight"), None)
    tbw_marker = next((m for m in markers if m.pdf_name == "Total Body Water"), None)
    protein_marker = next((m for m in markers if m.pdf_name == "Protein"), None)

    if weight_marker and weight_marker.value > 0:
        # Water Percentage = (TBW in L / Weight in kg) * 100
        # Note: TBW in litres is approx equal to kg for water density ~1
        if tbw_marker:
            water_pct = round((tbw_marker.value / weight_marker.value) * 100, 1)
            markers.append(RawMarker(
                pdf_name="Water Percentage",
                value=water_pct,
                unit="%",
                ref_low=None,
                ref_high=None,
                raw_text=f"Derived: {tbw_marker.value}L / {weight_marker.value}kg * 100",
            ))

        # Protein Percentage = (Protein in kg / Weight in kg) * 100
        if protein_marker:
            protein_pct = round((protein_marker.value / weight_marker.value) * 100, 1)
            markers.append(RawMarker(
                pdf_name="Protein Percentage",
                value=protein_pct,
                unit="%",
                ref_low=None,
                ref_high=None,
                raw_text=f"Derived: {protein_marker.value}kg / {weight_marker.value}kg * 100",
            ))

    # Rename "Minerals" to "Bone Mass" for standardisation
    for m in markers:
        if m.pdf_name == "Minerals":
            m.pdf_name = "Bone Mass"

    # Rename "Target Weight" to "Ideal Weight"
    for m in markers:
        if m.pdf_name == "Target Weight":
            m.pdf_name = "Ideal Weight"

    # Filter out raw intermediates that aren't in our final marker set
    final_names = {
        "Weight", "Skeletal Muscle Mass", "Body Fat Mass", "BMI",
        "Body Fat Percentage", "Visceral Fat Level", "Basal Metabolic Rate",
        "Fat Free Mass", "Water Percentage", "Protein Percentage",
        "Bone Mass", "Ideal Weight",
    }
    markers = [m for m in markers if m.pdf_name in final_names]

    return ParseResult(
        device=device,
        test_date=test_date,
        markers=markers,
        total_lines_scanned=len(lines),
    )
