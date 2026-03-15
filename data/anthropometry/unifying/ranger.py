"""
ranger.py — Reference range resolution using anthropometry_markers.json + user profile.

Resolves the canonical reference range and tier for each marker based on
the user's demographics (sex, age) and the marker's evaluation type.

Also computes derived metrics (SMI, FFMI, FMI) from parsed values before
range resolution runs.

Input:  list of NormalisedMarker + user profile + marker definitions
Output: list of RangedMarker (with resolved canonical ref range and tier)
"""

import re as _re
from dataclasses import dataclass, field
from datetime import date
from .normaliser import NormalisedMarker
from ..importing.resolver import load_markers


# ---------------------------------------------------------------------------
# User Profile
# ---------------------------------------------------------------------------

@dataclass
class UserProfile:
    """User profile for demographic-adjusted ranges."""
    sex: str | None = None           # "male" or "female"
    dob: date | None = None          # age computed at query time from dob
    height_cm: float | None = None   # required for SMI, FFMI, FMI computation

    @property
    def age(self) -> int | None:
        """Compute age from DOB at query time. Never stored directly."""
        if self.dob is None:
            return None
        today = date.today()
        return today.year - self.dob.year - (
            (today.month, today.day) < (self.dob.month, self.dob.day)
        )

    @property
    def height_m(self) -> float | None:
        """Height in metres for index calculations."""
        if self.height_cm is None:
            return None
        return self.height_cm / 100.0


# ---------------------------------------------------------------------------
# Ranged Marker
# ---------------------------------------------------------------------------

@dataclass
class RangedMarker:
    """A marker with its canonical reference range and tier resolved."""
    pdf_name: str
    marker_id: str | None
    marker_name: str | None
    category: str | None
    evaluation_type: str | None      # "direct" | "derived_input" | "informational"
    match_type: str
    confidence: str
    confidence_reasons: list[str]
    raw_text: str
    original_value: float
    original_unit: str
    std_value: float
    std_unit: str
    unit_converted: bool
    is_derived: bool = False         # True for SMI, FFMI, FMI — not parsed from PDF
    # Lab-printed reference (from PDF — None for derived metrics)
    lab_ref_low: float | None = None
    lab_ref_high: float | None = None
    # Canonical reference (from markers.json + user profile)
    canonical_ref_low: float | None = None
    canonical_ref_high: float | None = None
    canonical_tier: str | None = None        # e.g. "healthy", "overfat", "elevated"
    adjustment_note: str | None = None
    # Alert flags
    is_critical: bool = False
    critical_label: str | None = None       # "CRITICAL_LOW" | "CRITICAL_HIGH"
    # Manufacturer availability
    available_from: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Age bracket resolution
# ---------------------------------------------------------------------------

def _resolve_age_bracket(d: dict, age: int | None) -> dict | None:
    """
    Given a dict that may contain age-bracket keys like "18-39", "40-59", "60+",
    return the matching bracket dict for the given age.
    Returns None if no bracket matches or if d has no bracket keys.
    """
    if age is None:
        return None

    for key, value in d.items():
        if not isinstance(value, dict):
            continue
        if key.endswith("+"):
            try:
                lower = int(key[:-1])
                if age >= lower:
                    return value
            except ValueError:
                continue
        elif "-" in key:
            parts = key.split("-")
            if len(parts) == 2:
                try:
                    lower, upper = int(parts[0]), int(parts[1])
                    if lower <= age <= upper:
                        return value
                except ValueError:
                    continue

    return None


# ---------------------------------------------------------------------------
# Tier resolution
# ---------------------------------------------------------------------------

def _is_age_bracket_dict(d: dict) -> bool:
    """
    Return True if the dict's keys look like age brackets ("18-39", "60+").
    Used to distinguish age-bracket dicts from named tier dicts.
    """
    for key in d:
        if isinstance(key, str) and (
            _re.match(r'^\d+-\d+$', key) or _re.match(r'^\d+\+$', key)
        ):
            return True
    return False


def _has_tier_structure(d: dict) -> bool:
    """
    Return True if the dict contains named tier keys rather than just low/high
    and is NOT an age-bracket dict.
    e.g. {"healthy": {"low": 8, "high": 19.9}, "overfat": {...}}
    """
    if _is_age_bracket_dict(d):
        return False
    non_range_keys = {k for k in d if k not in ("low", "high")}
    return bool(non_range_keys) and all(
        isinstance(d[k], dict) for k in non_range_keys
    )


_NORMAL_TIER_NAMES = {"normal", "healthy", "optimal", "sufficient", "symmetric"}


def _resolve_tier(
    tier_dict: dict,
    value: float,
) -> tuple[str | None, float | None, float | None]:
    """
    Given a dict of named tiers, return (tier_name, ref_low, ref_high)
    for the tier the value falls in.

    ref_low/ref_high are always the **normal/healthy tier's** bounds
    (i.e. the ideal reference range) rather than the matched tier's bounds.
    This way the UI shows the target range, not where the value landed.
    """
    matched_tier = None
    for tier_name, bounds in tier_dict.items():
        if not isinstance(bounds, dict):
            continue
        low = bounds.get("low")
        high = bounds.get("high")
        above_low = (low is None) or (value >= low)
        below_high = (high is None) or (value <= high)
        if above_low and below_high:
            matched_tier = tier_name
            break

    # Find the normal/healthy tier's bounds for the reference range display
    ref_low, ref_high = None, None
    for tier_name, bounds in tier_dict.items():
        if not isinstance(bounds, dict):
            continue
        if tier_name in _NORMAL_TIER_NAMES:
            ref_low = bounds.get("low")
            ref_high = bounds.get("high")
            break

    # If no normal tier found, fall back to matched tier's bounds
    if ref_low is None and ref_high is None and matched_tier is not None:
        matched_bounds = tier_dict.get(matched_tier, {})
        ref_low = matched_bounds.get("low")
        ref_high = matched_bounds.get("high")

    return matched_tier, ref_low, ref_high


# ---------------------------------------------------------------------------
# Alert threshold check
# ---------------------------------------------------------------------------

def _check_alert_thresholds(
    marker_def: dict,
    value: float,
    sex: str | None = None,
) -> tuple[bool, str | None]:
    """
    Check if value crosses any critical alert threshold.
    Handles both standard thresholds and sex-specific thresholds
    (e.g. phase angle critical_low_male / critical_low_female).
    Returns (is_critical, critical_label).
    """
    alert = marker_def.get("alert_thresholds", {})
    if not alert:
        return False, None

    sex = (sex or "").lower()

    # Sex-specific critical lows (phase angle)
    if sex in ("male", "female"):
        sex_key = f"critical_low_{sex}"
        if sex_key in alert and value < alert[sex_key]:
            return True, "CRITICAL_LOW"

    # Standard thresholds
    if "critical_low" in alert and value < alert["critical_low"]:
        return True, "CRITICAL_LOW"
    if "critical_high" in alert and value > alert["critical_high"]:
        return True, "CRITICAL_HIGH"

    return False, None


# ---------------------------------------------------------------------------
# Core resolution
# ---------------------------------------------------------------------------

def _resolve_single(
    marker_def: dict,
    value: float,
    profile: UserProfile,
) -> tuple[float | None, float | None, str | None, str | None, bool, str | None]:
    """
    Resolve the canonical reference range and tier for a single marker.

    Returns:
        canonical_low, canonical_high, tier_name, adjustment_note,
        is_critical, critical_label

    Resolution order:
    1. Sex + age stratified  (e.g. PBF, PhaseAngle)
    2. Sex stratified flat   (e.g. WaterPct)
    3. Tiered without sex    (e.g. VFA, VFL, ECW_TBW, SMI, FFMI, FMI)
    4. Simple flat {low, high}
    5. Empty — return all None
    """
    ranges = marker_def.get("ranges", {})
    sex = (profile.sex or "").lower()
    age = profile.age

    if not ranges:
        return None, None, None, None, False, None

    is_crit, crit_label = _check_alert_thresholds(marker_def, value, sex)

    # --- 1. Sex-stratified (with or without age brackets) ---
    if sex in ranges and isinstance(ranges[sex], dict):
        sex_ranges = ranges[sex]

        # Try age bracket first
        bracket = _resolve_age_bracket(sex_ranges, age)
        if bracket is not None:
            age_label = f"age {age}" if age else "unknown age"
            label = "Male" if sex == "male" else "Female"
            note = f"{label}, {age_label} reference range"

            if _has_tier_structure(bracket):
                tier, low, high = _resolve_tier(bracket, value)
                return low, high, tier, note, is_crit, crit_label

            return bracket.get("low"), bracket.get("high"), None, note, is_crit, crit_label

        # age was None but sex_ranges is an age-bracket dict — can't resolve
        if _is_age_bracket_dict(sex_ranges):
            return None, None, None, "Age required to resolve range", is_crit, crit_label

        # No age brackets — sex level is the range directly
        if _has_tier_structure(sex_ranges):
            label = "Male" if sex == "male" else "Female"
            tier, low, high = _resolve_tier(sex_ranges, value)
            return low, high, tier, f"{label} reference range", is_crit, crit_label

        if "low" in sex_ranges or "high" in sex_ranges:
            label = "Male" if sex == "male" else "Female"
            return (
                sex_ranges.get("low"),
                sex_ranges.get("high"),
                None,
                f"{label} reference range",
                is_crit,
                crit_label,
            )

    # --- 2. Fallback to any available sex key ---
    for fallback_key in ("male", "female"):
        if fallback_key in ranges and isinstance(ranges[fallback_key], dict):
            r = ranges[fallback_key]
            note = f"Fallback ({fallback_key}) range — sex not confirmed"

            # Try age bracket within fallback
            bracket = _resolve_age_bracket(r, age)
            if bracket is not None:
                if _has_tier_structure(bracket):
                    tier, low, high = _resolve_tier(bracket, value)
                    return low, high, tier, note, is_crit, crit_label
                return bracket.get("low"), bracket.get("high"), None, note, is_crit, crit_label

            if _is_age_bracket_dict(r):
                return None, None, None, "Age required to resolve range", is_crit, crit_label

            if _has_tier_structure(r):
                tier, low, high = _resolve_tier(r, value)
                return low, high, tier, note, is_crit, crit_label

            low_val = r.get("low")
            high_val = r.get("high")
            if isinstance(low_val, (int, float)) or isinstance(high_val, (int, float)):
                return low_val, high_val, None, note, is_crit, crit_label

    # --- 3. Tiered ranges without sex or age (VFA, VFL, ECW_TBW, etc.) ---
    if _has_tier_structure(ranges):
        tier, low, high = _resolve_tier(ranges, value)
        return low, high, tier, None, is_crit, crit_label

    # --- 4. Simple flat {low, high} ---
    if "low" in ranges or "high" in ranges:
        return ranges.get("low"), ranges.get("high"), None, None, is_crit, crit_label

    return None, None, None, None, is_crit, crit_label


# ---------------------------------------------------------------------------
# Derived metric computation
# ---------------------------------------------------------------------------

DERIVED_METRICS = {
    "SMI": {
        "requires": ["SMM"],
        "formula": lambda vals, profile: (
            round(vals["SMM"] / (profile.height_m ** 2), 2)
            if profile.height_m else None
        ),
    },
    "FFMI": {
        "requires": ["FFM"],
        "formula": lambda vals, profile: (
            round(vals["FFM"] / (profile.height_m ** 2), 2)
            if profile.height_m else None
        ),
    },
    "FMI": {
        "requires": ["BFM"],
        "formula": lambda vals, profile: (
            round(vals["BFM"] / (profile.height_m ** 2), 2)
            if profile.height_m else None
        ),
    },
    "PBF_from_BFM": {
        "requires": ["BFM", "Weight"],
        "formula": lambda vals, profile: (
            round((vals["BFM"] / vals["Weight"]) * 100, 2)
            if vals.get("Weight") else None
        ),
    },
    "ECW_TBW": {
        "requires": ["ECW", "TBW"],
        "formula": lambda vals, profile: (
            round(vals["ECW"] / vals["TBW"], 3)
            if vals.get("TBW") and vals["TBW"] != 0 else None
        ),
    },
    "LimbSymmetry_Arms": {
        "requires": ["SegmentalLean_LA", "SegmentalLean_RA"],
        "formula": lambda vals, profile: (
            round(
                abs(vals["SegmentalLean_LA"] - vals["SegmentalLean_RA"])
                / max(vals["SegmentalLean_LA"], vals["SegmentalLean_RA"]) * 100,
                2,
            )
            if max(vals["SegmentalLean_LA"], vals["SegmentalLean_RA"]) != 0 else None
        ),
    },
    "LimbSymmetry_Legs": {
        "requires": ["SegmentalLean_LL", "SegmentalLean_RL"],
        "formula": lambda vals, profile: (
            round(
                abs(vals["SegmentalLean_LL"] - vals["SegmentalLean_RL"])
                / max(vals["SegmentalLean_LL"], vals["SegmentalLean_RL"]) * 100,
                2,
            )
            if max(vals["SegmentalLean_LL"], vals["SegmentalLean_RL"]) != 0 else None
        ),
    },
    "BMR_expected": {
        "requires": ["FFM"],
        "formula": lambda vals, profile: round(370 + (21.6 * vals["FFM"]), 0),
    },
}

# Map derived computation IDs to the canonical marker ID in markers.json
DERIVED_TO_MARKER_ID = {
    "SMI": "SMI",
    "FFMI": "FFMI",
    "FMI": "FMI",
    "PBF_from_BFM": "PBF",
    "ECW_TBW": "ECW_TBW",
    "LimbSymmetry_Arms": "LimbSymmetry_Arms",
    "LimbSymmetry_Legs": "LimbSymmetry_Legs",
    "BMR_expected": "BMR_expected",
}


def _compute_derived_markers(
    normalised_markers: list[NormalisedMarker],
    profile: UserProfile,
    defs_by_id: dict,
) -> list[NormalisedMarker]:
    """
    Compute derived metrics from parsed values.
    Returns synthetic NormalisedMarker instances for each derived metric.

    Skips PBF_from_BFM if PBF was already parsed directly from the PDF.
    """
    parsed_values: dict[str, float] = {
        m.marker_id: m.std_value
        for m in normalised_markers
        if m.marker_id and m.std_value is not None
    }

    derived = []
    for derived_id, spec in DERIVED_METRICS.items():
        if not all(req in parsed_values for req in spec["requires"]):
            continue

        # Skip derived metrics if already parsed directly from PDF
        if derived_id == "PBF_from_BFM" and "PBF" in parsed_values:
            continue
        if derived_id == "ECW_TBW" and "ECW_TBW" in parsed_values:
            continue
        if derived_id == "BMR_expected" and "BMR_expected" in parsed_values:
            continue

        value = spec["formula"](parsed_values, profile)
        if value is None:
            continue

        marker_id = DERIVED_TO_MARKER_ID[derived_id]
        marker_def = defs_by_id.get(marker_id, {})

        derived.append(NormalisedMarker(
            pdf_name=derived_id,
            marker_id=marker_id,
            marker_name=marker_def.get("name", derived_id),
            category=marker_def.get("category"),
            match_type="derived",
            confidence="HIGH",
            confidence_reasons=[f"Computed from {', '.join(spec['requires'])}"],
            raw_text="",
            original_value=value,
            original_unit=marker_def.get("unit", ""),
            std_value=value,
            std_unit=marker_def.get("unit", ""),
            unit_converted=False,
            ref_low=None,
            ref_high=None,
        ))

    return derived


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def resolve_ranges(
    normalised_markers: list[NormalisedMarker],
    profile: UserProfile | None = None,
    markers_def: list[dict] | None = None,
    manufacturer: str | None = None,
) -> list[RangedMarker]:
    """
    Resolve canonical reference ranges for all markers.

    Steps:
    1. Compute derived metrics (SMI, FFMI, FMI, PBF) and append to list
    2. Skip range resolution for derived_input and informational metrics
    3. Check available_from against manufacturer for device-specific metrics
    4. Resolve ranges and tiers using demographic-adjusted logic
    5. Check alert thresholds
    """
    if profile is None:
        profile = UserProfile()

    if markers_def is None:
        markers_def = load_markers()

    defs_by_id = {m["id"]: m for m in markers_def}

    # Step 1 — compute and append derived metrics
    derived = _compute_derived_markers(normalised_markers, profile, defs_by_id)
    all_markers = list(normalised_markers) + derived

    ranged = []
    for m in all_markers:
        is_derived = m.match_type == "derived"
        canon_low = None
        canon_high = None
        canon_tier = None
        note = None
        is_crit = False
        crit_label = None
        evaluation_type = None
        available_from = []

        if m.marker_id and m.marker_id in defs_by_id:
            marker_def = defs_by_id[m.marker_id]
            evaluation_type = marker_def.get("evaluation")
            available_from = marker_def.get("available_from", [])

            # Step 2 — skip range resolution for non-direct metrics UNLESS they have ranges defined
            if evaluation_type in ("derived_input", "informational") and not marker_def.get("ranges"):
                ranged.append(RangedMarker(
                    pdf_name=m.pdf_name,
                    marker_id=m.marker_id,
                    marker_name=m.marker_name,
                    category=m.category,
                    evaluation_type=evaluation_type,
                    match_type=m.match_type,
                    confidence=m.confidence,
                    confidence_reasons=m.confidence_reasons,
                    raw_text=m.raw_text,
                    original_value=m.original_value,
                    original_unit=m.original_unit,
                    std_value=m.std_value,
                    std_unit=m.std_unit,
                    unit_converted=m.unit_converted,
                    is_derived=is_derived,
                    lab_ref_low=getattr(m, "ref_low", None),
                    lab_ref_high=getattr(m, "ref_high", None),
                    available_from=available_from,
                ))
                continue

            # Step 3 — check manufacturer availability
            if available_from and manufacturer:
                if manufacturer not in available_from:
                    ranged.append(RangedMarker(
                        pdf_name=m.pdf_name,
                        marker_id=m.marker_id,
                        marker_name=m.marker_name,
                        category=m.category,
                        evaluation_type=evaluation_type,
                        match_type="manufacturer_mismatch",
                        confidence="LOW",
                        confidence_reasons=[
                            f"{m.marker_id} not produced by {manufacturer}. "
                            f"Expected from: {available_from}"
                        ],
                        raw_text=m.raw_text,
                        original_value=m.original_value,
                        original_unit=m.original_unit,
                        std_value=m.std_value,
                        std_unit=m.std_unit,
                        unit_converted=m.unit_converted,
                        is_derived=is_derived,
                        lab_ref_low=getattr(m, "ref_low", None),
                        lab_ref_high=getattr(m, "ref_high", None),
                        available_from=available_from,
                    ))
                    continue

            # Step 4 — resolve range and tier
            (
                canon_low,
                canon_high,
                canon_tier,
                note,
                is_crit,
                crit_label,
            ) = _resolve_single(marker_def, m.std_value, profile)

        ranged.append(RangedMarker(
            pdf_name=m.pdf_name,
            marker_id=m.marker_id,
            marker_name=m.marker_name,
            category=m.category,
            evaluation_type=evaluation_type,
            match_type=m.match_type,
            confidence=m.confidence,
            confidence_reasons=m.confidence_reasons,
            raw_text=m.raw_text,
            original_value=m.original_value,
            original_unit=m.original_unit,
            std_value=m.std_value,
            std_unit=m.std_unit,
            unit_converted=m.unit_converted,
            is_derived=is_derived,
            lab_ref_low=getattr(m, "ref_low", None),
            lab_ref_high=getattr(m, "ref_high", None),
            canonical_ref_low=canon_low,
            canonical_ref_high=canon_high,
            canonical_tier=canon_tier,
            adjustment_note=note,
            is_critical=is_crit,
            critical_label=crit_label,
            available_from=available_from,
        ))

    return ranged