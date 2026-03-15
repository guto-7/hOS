"""
flagger.py — Flag computation and deviation calculation.

Computes the flag status (LOW, OPTIMAL, HIGH) for each marker
based on its standardised value and canonical reference range.

Also computes deviation: how far out of range as a percentage.

Input:  list of RangedMarker
Output: list of FlaggedMarker (the final enriched output of Stage 2)
"""

from dataclasses import dataclass
from .ranger import RangedMarker


@dataclass
class FlaggedMarker:
    """The final enriched marker — ready for display and Stage 3 ML input."""
    # Identity
    pdf_name: str
    marker_id: str | None
    marker_name: str | None
    category: str | None
    # Values
    original_value: float
    original_unit: str
    std_value: float
    std_unit: str
    unit_converted: bool
    # Reference ranges
    lab_ref_low: float | None
    lab_ref_high: float | None
    canonical_ref_low: float | None
    canonical_ref_high: float | None
    adjustment_note: str | None
    # Flags
    flag: str                       # LOW, OPTIMAL, HIGH
    deviation: str | None           # e.g., "23% below lower limit"
    deviation_pct: float | None     # numeric deviation for ML input
    lab_flag: str | None            # what the lab printed (H/L)
    # Metadata
    match_type: str
    confidence: str
    confidence_reasons: list[str]
    raw_text: str

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialisation."""
        return {
            "pdf_name": self.pdf_name,
            "marker_id": self.marker_id,
            "marker_name": self.marker_name,
            "category": self.category,
            "original_value": self.original_value,
            "original_unit": self.original_unit,
            "std_value": self.std_value,
            "std_unit": self.std_unit,
            "unit_converted": self.unit_converted,
            "lab_ref_low": self.lab_ref_low,
            "lab_ref_high": self.lab_ref_high,
            "canonical_ref_low": self.canonical_ref_low,
            "canonical_ref_high": self.canonical_ref_high,
            "adjustment_note": self.adjustment_note,
            "flag": self.flag,
            "deviation": self.deviation,
            "deviation_pct": self.deviation_pct,
            "lab_flag": self.lab_flag,
            "match_type": self.match_type,
            "confidence": self.confidence,
            "confidence_reasons": self.confidence_reasons,
            "raw_text": self.raw_text,
        }


def _compute_flag(
    value: float,
    ref_low: float | None,
    ref_high: float | None,
) -> str:
    """
    Compute flag for a single marker value.

    OPTIMAL — within reference range
    LOW    — below reference range
    HIGH   — above reference range
    """
    if ref_low is not None and value < ref_low:
        return "LOW"
    if ref_high is not None and value > ref_high:
        return "HIGH"

    return "OPTIMAL"


def _compute_deviation(
    value: float,
    ref_low: float | None,
    ref_high: float | None,
) -> tuple[str | None, float | None]:
    """
    Compute how far out of range a value is.
    Returns (human-readable string, numeric percentage).
    """
    if ref_low is not None and value < ref_low and ref_low != 0:
        pct = round(((ref_low - value) / ref_low) * 100, 1)
        return f"{pct}% below lower limit", -pct

    if ref_high is not None and value > ref_high and ref_high != 0:
        pct = round(((value - ref_high) / ref_high) * 100, 1)
        return f"{pct}% above upper limit", pct

    return None, None


def compute_flags(
    ranged_markers: list[RangedMarker],
) -> list[FlaggedMarker]:
    """
    Compute flags and deviations for all ranged markers.
    """
    flagged = []
    for m in ranged_markers:
        flag = _compute_flag(
            m.std_value, m.canonical_ref_low, m.canonical_ref_high
        )
        deviation_str, deviation_pct = _compute_deviation(
            m.std_value, m.canonical_ref_low, m.canonical_ref_high
        )

        flagged.append(FlaggedMarker(
            pdf_name=m.pdf_name,
            marker_id=m.marker_id,
            marker_name=m.marker_name,
            category=m.category,
            original_value=m.original_value,
            original_unit=m.original_unit,
            std_value=m.std_value,
            std_unit=m.std_unit,
            unit_converted=m.unit_converted,
            lab_ref_low=m.lab_ref_low,
            lab_ref_high=m.lab_ref_high,
            canonical_ref_low=m.canonical_ref_low,
            canonical_ref_high=m.canonical_ref_high,
            adjustment_note=m.adjustment_note,
            flag=flag,
            deviation=deviation_str,
            deviation_pct=deviation_pct,
            lab_flag=m.lab_flag,
            match_type=m.match_type,
            confidence=m.confidence,
            confidence_reasons=m.confidence_reasons,
            raw_text=m.raw_text,
        ))

    return flagged
