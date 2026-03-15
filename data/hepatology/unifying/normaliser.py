"""
normaliser.py — Unit normalisation against markers.json.

Converts extracted marker values to the canonical unit defined
in markers.json using the unit_conversions[] array. Preserves
the original value and unit alongside the standardised ones.

Input:  list of ScoredMarker + markers.json definitions
Output: list of NormalisedMarker (with std_value, std_unit)
"""

from dataclasses import dataclass
from ..importing.confidence import ScoredMarker
from ..importing.resolver import load_markers


UNIT_ALIASES = {
    "ug/l": "µg/L",
    "umol/l": "µmol/L",
    "ug/dl": "µg/dL",
    "x10^9/l": "x10⁹/L",
    "x10^12/l": "x10¹²/L",
    "ml/min/1.73m2": "mL/min/1.73m²",
}


@dataclass
class NormalisedMarker:
    """A marker after unit normalisation."""
    # Original fields from importing
    pdf_name: str
    marker_id: str | None
    marker_name: str | None
    category: str | None
    match_type: str
    confidence: str
    confidence_reasons: list[str]
    raw_text: str
    lab_flag: str | None
    ref_low: float | None
    ref_high: float | None
    # Normalisation fields
    original_value: float
    original_unit: str
    std_value: float
    std_unit: str
    unit_converted: bool  # True if a conversion was applied


def _normalise_unit_string(unit: str) -> str:
    """Normalise common unit string variants."""
    return UNIT_ALIASES.get(unit.lower(), unit)


def _convert(value: float, from_unit: str, marker_def: dict) -> tuple[float, str, bool]:
    """
    Convert a value to the marker's canonical unit.
    Returns (converted_value, canonical_unit, was_converted).
    """
    canonical_unit = marker_def.get("unit", from_unit)
    from_normalised = _normalise_unit_string(from_unit)

    # Already in canonical unit
    if from_normalised == canonical_unit:
        return value, canonical_unit, False

    # Check unit_conversions for a matching conversion
    for conv in marker_def.get("unit_conversions", []):
        if _normalise_unit_string(conv["from"]) == from_normalised:
            converted = round(value * conv["multiply"], 4)
            return converted, canonical_unit, True

    # No conversion found — return as-is with normalised unit string
    return value, from_normalised, False


def normalise_units(
    scored_markers: list[ScoredMarker],
    markers_def: list[dict] | None = None,
) -> list[NormalisedMarker]:
    """
    Normalise units for all scored markers.
    Unmatched markers (marker_id is None) pass through with no conversion.
    """
    if markers_def is None:
        markers_def = load_markers()

    # Build id → definition lookup
    defs_by_id = {m["id"]: m for m in markers_def}

    normalised = []
    for m in scored_markers:
        if m.marker_id and m.marker_id in defs_by_id:
            std_value, std_unit, converted = _convert(
                m.value, m.unit, defs_by_id[m.marker_id]
            )
        else:
            std_value, std_unit, converted = m.value, m.unit, False

        normalised.append(NormalisedMarker(
            pdf_name=m.pdf_name,
            marker_id=m.marker_id,
            marker_name=m.marker_name,
            category=m.category,
            match_type=m.match_type,
            confidence=m.confidence,
            confidence_reasons=m.confidence_reasons,
            raw_text=m.raw_text,
            lab_flag=m.lab_flag,
            ref_low=m.ref_low,
            ref_high=m.ref_high,
            original_value=m.value,
            original_unit=m.unit,
            std_value=std_value,
            std_unit=std_unit,
            unit_converted=converted,
        ))

    return normalised
