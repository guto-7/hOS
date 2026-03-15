"""
parser.py — BIA device identification and marker extraction from PDF text.

Identifies the BIA device manufacturer from header text, then uses
keyword-based regex patterns to extract anthropometry marker values.

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

    ("Visceral Fat Area", [
        r"Visceral\s*Fat\s*Area\s*\(cm[²2]\)\s*(\d+\.?\d*)",
        r"Visceral\s*Fat\s*Area\s+(\d+\.?\d*)\s*cm",
        r"VFA\s*\(cm[²2]\)\s*(\d+\.?\d*)",
        r"VFA\s+(\d+\.?\d*)",
    ], "cm²"),

    ("Extracellular Water", [
        r"Extracellular\s*Water\s*\(L\)\s*(\d+\.?\d*)",
        r"Extracellular\s*Water\s+(\d+\.?\d*)\s*L",
        r"ECW\s*\(L\)\s*(\d+\.?\d*)",
        r"ECW\s+(\d+\.?\d*)\s*L",
    ], "L"),

    ("Intracellular Water", [
        r"Intracellular\s*Water\s*\(L\)\s*(\d+\.?\d*)",
        r"Intracellular\s*Water\s+(\d+\.?\d*)\s*L",
        r"ICW\s*\(L\)\s*(\d+\.?\d*)",
        r"ICW\s+(\d+\.?\d*)\s*L",
    ], "L"),

    ("ECW/TBW", [
        r"ECW/TBW\s+(\d+\.\d+)",
        r"ECW\s*/\s*TBW\s+(\d+\.\d+)",
        r"E/T\s+(?:Ratio\s+)?(\d+\.\d+)",
        r"ECW\s*Ratio\s+(\d+\.\d+)",
        r"Extracellular\s*Water\s*Ratio\s+(\d+\.\d+)",
        # InBody: ratio value alone on the line below the header
        r"ECW/TBW\s*\n\s*(\d+\.\d{2,3})",
    ], "ratio"),

    ("Phase Angle", [
        r"Phase\s*Angle\s+(\d+\.?\d*)\s*[°\u00b0o]?",
        r"PhA\s+(\d+\.?\d*)",
        r"(?:Body\s*)?Phase\s*Angle\s*[:\-]?\s*(\d+\.?\d*)",
        r"\bPA\b\s+(\d+\.?\d*)\s*[°\u00b0o]?",
        # InBody: "PhA  5.5" possibly with degree in next token
        r"PhA\s{1,20}(\d+\.\d)",
    ], "degrees"),

    # Segmental patterns for single-line formats (non-InBody or
    # InBody models that list each limb on its own line)
    ("Segmental Lean Left Arm", [
        r"(?:Left\s*Arm|L\.?\s*Arm)\s+(\d+\.?\d*)\s*kg",
        r"(?:Left\s*Arm|L\.?\s*Arm)\s+(\d+\.?\d*)(?=\s)",
    ], "kg"),

    ("Segmental Lean Right Arm", [
        r"(?:Right\s*Arm|R\.?\s*Arm)\s+(\d+\.?\d*)\s*kg",
        r"(?:Right\s*Arm|R\.?\s*Arm)\s+(\d+\.?\d*)(?=\s)",
    ], "kg"),

    ("Segmental Lean Left Leg", [
        r"(?:Left\s*Leg|L\.?\s*Leg)\s+(\d+\.?\d*)\s*kg",
        r"(?:Left\s*Leg|L\.?\s*Leg)\s+(\d+\.?\d*)(?=\s)",
    ], "kg"),

    ("Segmental Lean Right Leg", [
        r"(?:Right\s*Leg|R\.?\s*Leg)\s+(\d+\.?\d*)\s*kg",
        r"(?:Right\s*Leg|R\.?\s*Leg)\s+(\d+\.?\d*)(?=\s)",
    ], "kg"),
]


def _parse_inbody_segmental(text: str) -> dict[str, float]:
    """
    Parse InBody segmental lean mass values from the table layout.

    InBody reports print the segmental analysis as a column table:

        Segmental Lean Analysis
                            Right Arm    Left Arm    Right Leg    Left Leg    Trunk
        Body          (kg)  3.20         3.10         9.80         9.70        29.50

    pdftotext -layout preserves column spacing so the column header row
    and the value row are on separate lines. This function locates the
    "Body" value row within the segmental section and maps values back
    to the known column order.

    Returns a dict {pdf_name: value} for each successfully parsed limb.
    """
    # Locate the segmental analysis section (case-insensitive)
    section_m = re.search(
        r"Segmental\s+Lean\s+(?:Analysis|Mass)",
        text, re.IGNORECASE,
    )
    if not section_m:
        return {}

    # Work with the text from the section header onward (limit scope)
    section = text[section_m.start(): section_m.start() + 1500]
    lines = section.split("\n")

    # Find the header line that names the limbs
    header_idx = None
    header_line = ""
    for i, line in enumerate(lines):
        if re.search(r"Right\s+Arm", line, re.IGNORECASE):
            header_idx = i
            header_line = line
            break

    if header_idx is None:
        return {}

    # Find the "Body" value row — the first line after the header that
    # starts with "Body" (possibly followed by "(kg)") and contains
    # at least 4 decimal numbers.
    value_line = ""
    for line in lines[header_idx + 1: header_idx + 6]:
        if re.match(r"\s*Body\b", line, re.IGNORECASE) or (
            not value_line and len(re.findall(r"\d+\.\d+", line)) >= 4
        ):
            value_line = line
            break

    if not value_line:
        return {}

    # Extract all decimal numbers from the value line in left-to-right order
    values = [float(v) for v in re.findall(r"\d+\.\d+", value_line)]
    if len(values) < 4:
        return {}

    # Column order is fixed for InBody: Right Arm, Left Arm, Right Leg, Left Leg
    # (Trunk is 5th if present but we don't use it for symmetry)
    names = [
        "Segmental Lean Right Arm",
        "Segmental Lean Left Arm",
        "Segmental Lean Right Leg",
        "Segmental Lean Left Leg",
    ]

    # Sanity check: plausible limb lean mass range (0.5–12 kg)
    result = {}
    for name, val in zip(names, values[:4]):
        if 0.5 <= val <= 12.0:
            result[name] = val

    return result


def _parse_inbody_ecw_tbw(text: str) -> float | None:
    """
    Parse ECW/TBW ratio from InBody body water section.

    InBody prints the ratio as a small decimal (e.g. 0.380) sometimes
    on its own line or grouped with ECW/ICW values. This function looks
    for a plausible ratio value (0.30–0.50) near ECW/TBW context.
    """
    # Look for value immediately after ECW/TBW label on same or next line
    m = re.search(
        r"ECW\s*/\s*TBW\s*[:\-]?\s*\n?\s*(0\.\d{2,3})",
        text, re.IGNORECASE,
    )
    if m:
        val = float(m.group(1))
        if 0.30 <= val <= 0.55:
            return val

    # Fallback: look for a standalone ratio value near ECW/TBW keywords
    # in a window of text around the keyword
    kw_m = re.search(r"ECW\s*/\s*TBW", text, re.IGNORECASE)
    if kw_m:
        window = text[kw_m.start(): kw_m.start() + 150]
        candidates = re.findall(r"(0\.\d{2,3})", window)
        for c in candidates:
            val = float(c)
            if 0.30 <= val <= 0.55:
                return val

    return None


def parse_markers(text: str) -> ParseResult:
    """
    Parse anthropometry markers from pdftotext -layout output.

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

    # InBody segmental table fallback (handles column-layout format where
    # header row and value row are on separate lines)
    already_parsed_segmental = {m.pdf_name for m in markers if m.pdf_name.startswith("Segmental Lean ")}
    if len(already_parsed_segmental) < 4:
        segmental_values = _parse_inbody_segmental(text)
        for seg_name, seg_val in segmental_values.items():
            if seg_name not in already_parsed_segmental:
                markers.append(RawMarker(
                    pdf_name=seg_name,
                    value=seg_val,
                    unit="kg",
                    ref_low=None,
                    ref_high=None,
                    raw_text=f"InBody segmental table: {seg_val} kg",
                ))

    # InBody ECW/TBW ratio fallback (handles value on separate line after label)
    if not any(m.pdf_name == "ECW/TBW" for m in markers):
        ecw_tbw_val = _parse_inbody_ecw_tbw(text)
        if ecw_tbw_val is not None:
            markers.append(RawMarker(
                pdf_name="ECW/TBW",
                value=ecw_tbw_val,
                unit="ratio",
                ref_low=None,
                ref_high=None,
                raw_text=f"InBody ECW/TBW: {ecw_tbw_val}",
            ))

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

    # Filter out raw intermediates (Protein, Minerals before renaming) that
    # should not be passed downstream as standalone markers.
    _intermediates = {"Protein", "Minerals", "Target Weight"}
    markers = [m for m in markers if m.pdf_name not in _intermediates]

    return ParseResult(
        device=device,
        test_date=test_date,
        markers=markers,
        total_lines_scanned=len(lines),
    )
