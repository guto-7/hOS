"""
ranger.py — Reference range resolution using body_composition_markers.json + user profile.

Resolves the canonical reference range for each marker based on
the user's demographics (sex, age).

Input:  list of NormalisedMarker + user profile + marker definitions
Output: list of RangedMarker (with resolved canonical ref range)
"""

from dataclasses import dataclass
from .normaliser import NormalisedMarker
from ..importing.resolver import load_markers


@dataclass
class UserProfile:
    """User profile for demographic-adjusted ranges."""
    sex: str | None = None          # "male" or "female"
    age: int | None = None
    height_cm: float | None = None  # used for ideal weight calc


@dataclass
class RangedMarker:
    """A marker with its canonical reference range resolved."""
    pdf_name: str
    marker_id: str | None
    marker_name: str | None
    category: str | None
    match_type: str
    confidence: str
    confidence_reasons: list[str]
    raw_text: str
    original_value: float
    original_unit: str
    std_value: float
    std_unit: str
    unit_converted: bool
    # Lab-printed reference (from PDF)
    lab_ref_low: float | None
    lab_ref_high: float | None
    # Canonical reference (from markers.json + user profile)
    canonical_ref_low: float | None
    canonical_ref_high: float | None
    adjustment_note: str | None


def _resolve_single(marker_def: dict, profile: UserProfile) -> tuple[float | None, float | None, str | None]:
    """
    Resolve the canonical reference range for a single marker.

    Resolution priority:
    1. Sex-differentiated ranges (male/female)
    2. Direct {low, high} range
    3. Empty ranges (e.g., Ideal Weight — no universal reference)
    """
    ranges = marker_def.get("ranges", {})

    if not ranges:
        return None, None, None

    # 1. Simple {low, high}
    if "low" in ranges or "high" in ranges:
        return ranges.get("low"), ranges.get("high"), None

    sex = (profile.sex or "").lower()

    # 2. Sex-differentiated ranges
    if sex in ranges and isinstance(ranges[sex], dict):
        r = ranges[sex]
        if "low" in r or "high" in r:
            label = "Male" if sex == "male" else "Female"
            return r.get("low"), r.get("high"), f"{label} reference range"

    # 3. Fallback to any available sex range
    for fallback_key in ["male", "female"]:
        if fallback_key in ranges and isinstance(ranges[fallback_key], dict):
            r = ranges[fallback_key]
            if "low" in r or "high" in r:
                return r.get("low"), r.get("high"), f"Fallback ({fallback_key}) range"

    return None, None, None


def resolve_ranges(
    normalised_markers: list[NormalisedMarker],
    profile: UserProfile | None = None,
    markers_def: list[dict] | None = None,
) -> list[RangedMarker]:
    """
    Resolve canonical reference ranges for all markers.
    Uses the user profile for demographic-adjusted ranges.
    """
    if profile is None:
        profile = UserProfile()

    if markers_def is None:
        markers_def = load_markers()

    defs_by_id = {m["id"]: m for m in markers_def}

    ranged = []
    for m in normalised_markers:
        canon_low, canon_high, note = None, None, None

        if m.marker_id and m.marker_id in defs_by_id:
            canon_low, canon_high, note = _resolve_single(
                defs_by_id[m.marker_id], profile
            )

        ranged.append(RangedMarker(
            pdf_name=m.pdf_name,
            marker_id=m.marker_id,
            marker_name=m.marker_name,
            category=m.category,
            match_type=m.match_type,
            confidence=m.confidence,
            confidence_reasons=m.confidence_reasons,
            raw_text=m.raw_text,
            original_value=m.original_value,
            original_unit=m.original_unit,
            std_value=m.std_value,
            std_unit=m.std_unit,
            unit_converted=m.unit_converted,
            lab_ref_low=m.ref_low,
            lab_ref_high=m.ref_high,
            canonical_ref_low=canon_low,
            canonical_ref_high=canon_high,
            adjustment_note=note,
        ))

    return ranged
