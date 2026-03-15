"""
flagger.py — Flag computation and deviation calculation for body composition.

Computes the flag status for each marker based on its standardised value,
canonical reference range, tier, and alert thresholds from ranger.py.

Flag hierarchy (highest priority first):
  CRITICAL_LOW / CRITICAL_HIGH  — alert threshold crossed
  INFO                          — informational or derived_input evaluation type
  TIER:<name>                   — named tier resolved (e.g. TIER:obese, TIER:elevated)
  LOW / OPTIMAL / HIGH          — standard range comparison (no tier)
  UNRESOLVED                    — no canonical range available

Input:  list of RangedMarker
Output: list of FlaggedMarker (the final enriched output of Stage 2)
"""

from dataclasses import dataclass, field
from .ranger import RangedMarker


@dataclass
class FlaggedMarker:
    """The final enriched marker — ready for display."""
    # Identity
    pdf_name: str
    marker_id: str | None
    marker_name: str | None
    category: str | None
    evaluation_type: str | None
    is_derived: bool
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
    canonical_tier: str | None
    adjustment_note: str | None
    # Flags
    flag: str
    deviation: str | None
    deviation_pct: float | None
    # Metadata
    match_type: str
    confidence: str
    confidence_reasons: list[str]
    raw_text: str
    available_from: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialisation."""
        return {
            "pdf_name": self.pdf_name,
            "marker_id": self.marker_id,
            "marker_name": self.marker_name,
            "category": self.category,
            "evaluation_type": self.evaluation_type,
            "is_derived": self.is_derived,
            "original_value": self.original_value,
            "original_unit": self.original_unit,
            "std_value": self.std_value,
            "std_unit": self.std_unit,
            "unit_converted": self.unit_converted,
            "lab_ref_low": self.lab_ref_low,
            "lab_ref_high": self.lab_ref_high,
            "canonical_ref_low": self.canonical_ref_low,
            "canonical_ref_high": self.canonical_ref_high,
            "canonical_tier": self.canonical_tier,
            "adjustment_note": self.adjustment_note,
            "flag": self.flag,
            "deviation": self.deviation,
            "deviation_pct": self.deviation_pct,
            "match_type": self.match_type,
            "confidence": self.confidence,
            "confidence_reasons": self.confidence_reasons,
            "raw_text": self.raw_text,
            "available_from": self.available_from,
        }


def _compute_flag(
    value: float,
    ref_low: float | None,
    ref_high: float | None,
    canonical_tier: str | None,
    is_critical: bool,
    critical_label: str | None,
    evaluation_type: str | None,
) -> str:
    """
    Compute flag using priority order:
    1. CRITICAL — alert threshold crossed
    2. INFO     — informational or derived_input marker
    3. TIER     — named tier resolved
    4. LOW / OPTIMAL / HIGH — standard range comparison
    5. UNRESOLVED — no range available
    """
    if is_critical and critical_label:
        return critical_label

    if evaluation_type in ("informational", "derived_input"):
        return "INFO"

    if canonical_tier is not None:
        return f"TIER:{canonical_tier}"

    if ref_low is None and ref_high is None:
        return "UNRESOLVED"

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
    """Compute how far out of range a value is."""
    if ref_low is not None and value < ref_low and ref_low != 0:
        pct = round(((ref_low - value) / ref_low) * 100, 1)
        return f"{pct}% below lower limit", -pct

    if ref_high is not None and value > ref_high and ref_high != 0:
        pct = round(((value - ref_high) / ref_high) * 100, 1)
        return f"{pct}% above upper limit", pct

    return None, None


def compute_flags(ranged_markers: list[RangedMarker]) -> list[FlaggedMarker]:
    """Compute flags and deviations for all ranged markers."""
    flagged = []

    for m in ranged_markers:
        flag = _compute_flag(
            value=m.std_value,
            ref_low=m.canonical_ref_low,
            ref_high=m.canonical_ref_high,
            canonical_tier=m.canonical_tier,
            is_critical=m.is_critical,
            critical_label=m.critical_label,
            evaluation_type=m.evaluation_type,
        )

        # Deviation only meaningful for LOW/HIGH/CRITICAL flags
        if flag in ("LOW", "HIGH", "CRITICAL_LOW", "CRITICAL_HIGH"):
            deviation_str, deviation_pct = _compute_deviation(
                m.std_value, m.canonical_ref_low, m.canonical_ref_high
            )
        else:
            deviation_str, deviation_pct = None, None

        flagged.append(FlaggedMarker(
            pdf_name=m.pdf_name,
            marker_id=m.marker_id,
            marker_name=m.marker_name,
            category=m.category,
            evaluation_type=m.evaluation_type,
            is_derived=m.is_derived,
            original_value=m.original_value,
            original_unit=m.original_unit,
            std_value=m.std_value,
            std_unit=m.std_unit,
            unit_converted=m.unit_converted,
            lab_ref_low=m.lab_ref_low,
            lab_ref_high=m.lab_ref_high,
            canonical_ref_low=m.canonical_ref_low,
            canonical_ref_high=m.canonical_ref_high,
            canonical_tier=m.canonical_tier,
            adjustment_note=m.adjustment_note,
            flag=flag,
            deviation=deviation_str,
            deviation_pct=deviation_pct,
            match_type=m.match_type,
            confidence=m.confidence,
            confidence_reasons=m.confidence_reasons,
            raw_text=m.raw_text,
            available_from=m.available_from,
        ))

    return flagged
