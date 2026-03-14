"""
resolver.py — Alias resolution and unit checking against markers.json.

Maps extracted marker names to canonical marker IDs using the
aliases[] arrays in markers.json. Also checks whether the extracted
unit matches the expected unit.

Input:  list of RawMarker + markers.json definitions
Output: list of ResolvedMarker (with canonical ID, match type, unit status)
"""

import json
from dataclasses import dataclass
from pathlib import Path

from .parser import RawMarker


MARKERS_JSON = Path(__file__).parent.parent.parent / "markers.json"


@dataclass
class ResolvedMarker:
    """A marker after alias resolution — knows its canonical identity."""
    pdf_name: str
    value: float
    unit: str
    ref_low: float | None
    ref_high: float | None
    lab_flag: str | None
    raw_text: str
    # Resolution fields
    marker_id: str | None        # canonical ID from markers.json (e.g., "Hb")
    marker_name: str | None      # canonical name (e.g., "Haemoglobin (Hb)")
    category: str | None         # e.g., "CBC", "Lipid Profile"
    match_type: str              # "exact", "fuzzy", or "none"
    unit_match: bool             # True if extracted unit matches expected unit


def load_markers(path: str | Path = MARKERS_JSON) -> list[dict]:
    """Load marker definitions from markers.json."""
    with open(path) as f:
        return json.load(f)


def build_alias_index(markers_def: list[dict]) -> dict[str, dict]:
    """
    Build a lowercase alias → marker definition lookup.
    Indexes: id, name, and all aliases.
    """
    index = {}
    for m in markers_def:
        index[m["id"].lower()] = m
        index[m["name"].lower()] = m
        for alias in m.get("aliases", []):
            index[alias.lower()] = m
    return index


def _normalize_unit(unit: str) -> str:
    """Normalize common unit string variants for comparison."""
    replacements = {
        "ug/l": "µg/L",
        "umol/l": "µmol/L",
        "ug/dl": "µg/dL",
        "x10^9/l": "x10⁹/L",
        "x10^12/l": "x10¹²/L",
        "ml/min/1.73m2": "mL/min/1.73m²",
    }
    return replacements.get(unit.lower(), unit)


def _check_unit(extracted_unit: str, marker_def: dict) -> bool:
    """Check if the extracted unit matches the marker's expected unit."""
    expected = marker_def.get("unit", "")
    normalised = _normalize_unit(extracted_unit)
    if normalised == expected:
        return True
    # Also check if it's a known convertible unit
    for conv in marker_def.get("unit_conversions", []):
        if _normalize_unit(conv["from"]) == normalised:
            return True
    return False


def resolve_aliases(
    raw_markers: list[RawMarker],
    markers_def: list[dict] | None = None,
) -> list[ResolvedMarker]:
    """
    Resolve each raw marker against markers.json aliases.

    Match priority:
    1. Exact match on lowercase alias/id/name
    2. Fuzzy match (substring containment)
    3. No match
    """
    if markers_def is None:
        markers_def = load_markers()

    alias_index = build_alias_index(markers_def)
    resolved = []

    for raw in raw_markers:
        lookup_key = raw.pdf_name.lower().strip()

        # 1. Exact match
        marker_def = alias_index.get(lookup_key)
        match_type = "exact" if marker_def else None

        # 2. Fuzzy match (substring containment)
        if not marker_def:
            for alias_key, mdef in alias_index.items():
                if alias_key in lookup_key or lookup_key in alias_key:
                    marker_def = mdef
                    match_type = "fuzzy"
                    break

        # 3. No match
        if not marker_def:
            match_type = "none"

        resolved.append(ResolvedMarker(
            pdf_name=raw.pdf_name,
            value=raw.value,
            unit=raw.unit,
            ref_low=raw.ref_low,
            ref_high=raw.ref_high,
            lab_flag=raw.lab_flag,
            raw_text=raw.raw_text,
            marker_id=marker_def["id"] if marker_def else None,
            marker_name=marker_def["name"] if marker_def else None,
            category=marker_def.get("category") if marker_def else None,
            match_type=match_type,
            unit_match=_check_unit(raw.unit, marker_def) if marker_def else False,
        ))

    return resolved
