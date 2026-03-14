"""
ranger.py — Reference range resolution using markers.json + global user profile.

Resolves the canonical reference range for each marker based on
the user's demographics (sex, age, pregnancy status, cycle phase).
Uses the ranges defined in markers.json, not the lab-printed ranges.

Input:  list of NormalisedMarker + user profile + markers.json
Output: list of RangedMarker (with resolved canonical ref range)
"""

from dataclasses import dataclass
from .normaliser import NormalisedMarker
from ..importing.resolver import load_markers


@dataclass
class UserProfile:
    """Global user profile — set during app onboarding."""
    sex: str | None = None          # "male" or "female"
    age: int | None = None          # computed from DOB
    pregnant: bool = False
    cycle_phase: str | None = None  # "follicular", "midcycle", "luteal", "postmenopausal"
    fasting: bool = False


@dataclass
class RangedMarker:
    """A marker with its canonical reference range resolved."""
    # Pass through from normaliser
    pdf_name: str
    marker_id: str | None
    marker_name: str | None
    category: str | None
    match_type: str
    confidence: str
    confidence_reasons: list[str]
    raw_text: str
    lab_flag: str | None
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
    adjustment_note: str | None     # e.g., "Male reference range", "Pregnancy range"


def _age_matches(key: str, age: int) -> bool:
    """Check if an age matches a range key like '<40', '40-49', '55+'."""
    key = key.strip()
    if key.startswith("<=") or key.startswith("≤"):
        return age <= int(key[2:])
    if key.startswith("<"):
        return age < int(key[1:])
    if key.endswith("+"):
        return age >= int(key[:-1])
    if "-" in key:
        parts = key.split("-")
        return int(parts[0]) <= age <= int(parts[1])
    return False


def _resolve_single(marker_def: dict, profile: UserProfile) -> tuple[float | None, float | None, str | None]:
    """
    Resolve the canonical reference range for a single marker.

    Resolution priority:
    1. Pregnancy range (if pregnant and pregnancy_range exists)
    2. Age-stratified ranges
    3. Sex-differentiated ranges
    4. Direct {low, high} range
    """
    ranges = marker_def.get("ranges", {})

    # 1. Pregnancy override
    if profile.pregnant:
        preg = marker_def.get("pregnancy_range")
        if preg:
            return preg.get("low"), preg.get("high"), "Pregnancy reference range"

    # 2. Check if ranges is a simple {low, high}
    if "low" in ranges or "high" in ranges:
        return ranges.get("low"), ranges.get("high"), None

    sex = (profile.sex or "").lower()
    age = profile.age

    # 3. Cycle-phase ranges (for female hormones)
    if profile.cycle_phase and sex == "female":
        phase_key = f"female_{profile.cycle_phase}"
        if phase_key in ranges:
            r = ranges[phase_key]
            return r.get("low"), r.get("high"), f"{profile.cycle_phase.title()} phase range"

    # 4. Sex-differentiated ranges
    if sex in ranges and isinstance(ranges[sex], dict):
        r = ranges[sex]
        if "low" in r or "high" in r:
            label = "Male" if sex == "male" else "Female"
            return r.get("low"), r.get("high"), f"{label} reference range"

    # 5. Age-stratified ranges
    if age is not None:
        for key, r in ranges.items():
            if isinstance(r, dict) and ("low" in r or "high" in r):
                if _age_matches(key, age):
                    return r.get("low"), r.get("high"), f"Age {key} reference range"

    # 6. Fallback: try common keys
    for fallback_key in ["female_follicular", "female", "male"]:
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
    Uses the global user profile for demographic-adjusted ranges.
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
            lab_flag=m.lab_flag,
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
