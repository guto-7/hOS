"""
confidence.py — Per-marker confidence scoring for anthropometry.

Assigns a confidence level (HIGH / MEDIUM / LOW) to each resolved
marker based on how reliably it was extracted and matched.

Input:  list of ResolvedMarker
Output: list of ScoredMarker (ResolvedMarker + confidence level + reasons)
"""

from dataclasses import dataclass
from .resolver import ResolvedMarker


@dataclass
class ScoredMarker:
    """A marker with confidence scoring applied."""
    pdf_name: str
    value: float
    unit: str
    ref_low: float | None
    ref_high: float | None
    raw_text: str
    marker_id: str | None
    marker_name: str | None
    category: str | None
    match_type: str
    unit_match: bool
    # Confidence fields
    confidence: str              # "HIGH", "MEDIUM", "LOW"
    confidence_reasons: list[str]

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialisation."""
        return {
            "pdf_name": self.pdf_name,
            "value": self.value,
            "unit": self.unit,
            "ref_low": self.ref_low,
            "ref_high": self.ref_high,
            "raw_text": self.raw_text,
            "marker_id": self.marker_id,
            "marker_name": self.marker_name,
            "category": self.category,
            "match_type": self.match_type,
            "unit_match": self.unit_match,
            "confidence": self.confidence,
            "confidence_reasons": self.confidence_reasons,
        }


def _score_single(marker: ResolvedMarker) -> tuple[str, list[str]]:
    """
    Score confidence for a single marker.

    HIGH:   exact alias match + expected unit
    MEDIUM: fuzzy match, or exact match with unexpected unit
    LOW:    no match
    """
    reasons = []

    if marker.match_type == "none":
        reasons.append("No match found in anthropometry_markers.json")
        return "LOW", reasons

    if marker.match_type == "fuzzy":
        reasons.append(f"Fuzzy match: '{marker.pdf_name}' -> '{marker.marker_name}'")

    if not marker.unit_match:
        reasons.append(f"Unit mismatch: extracted '{marker.unit}', expected for '{marker.marker_id}'")

    if marker.match_type == "exact" and marker.unit_match and not reasons:
        return "HIGH", ["Exact alias match with expected unit"]

    if marker.match_type == "exact" and not marker.unit_match:
        return "MEDIUM", reasons

    if marker.match_type == "fuzzy":
        return "MEDIUM", reasons

    if reasons:
        return "MEDIUM", reasons

    return "HIGH", ["Exact alias match with expected unit"]


def score_confidence(resolved_markers: list[ResolvedMarker]) -> list[ScoredMarker]:
    """Score confidence for all resolved markers."""
    scored = []

    for marker in resolved_markers:
        confidence, reasons = _score_single(marker)

        scored.append(ScoredMarker(
            pdf_name=marker.pdf_name,
            value=marker.value,
            unit=marker.unit,
            ref_low=marker.ref_low,
            ref_high=marker.ref_high,
            raw_text=marker.raw_text,
            marker_id=marker.marker_id,
            marker_name=marker.marker_name,
            category=marker.category,
            match_type=marker.match_type,
            unit_match=marker.unit_match,
            confidence=confidence,
            confidence_reasons=reasons,
        ))

    return scored
