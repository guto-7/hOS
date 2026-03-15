"""
evaluator.py — Stage 3 clinical evaluation engine for anthropometry.

Takes the list of FlaggedMarkers (Stage 2 output) and produces:
  - domain_scores: scored 0-100 for Adiposity, Muscularity, Fluid Health, Metabolic Risk
  - phenotype: detected anthropometry phenotype (skinny fat, sarcopenic obesity, etc.)
  - signals: cross-reference observations worth surfacing
  - certainty: data completeness grade

Domain scoring uses marker tiers/flags, not raw values, so the engine is
decoupled from unit specifics.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Output types
# ---------------------------------------------------------------------------

@dataclass
class DomainScore:
    domain: str                      # "adiposity" | "muscularity" | "fluid_health" | "metabolic_health"
    label: str                       # Human-readable name
    score: float                     # 0 (worst) to 100 (best)
    grade: str                       # Status label: "Optimal" | "Moderate" | "Elevated" | "High Risk" | etc.
    markers_used: list[str]          # Marker names that contributed
    notes: list[str]                 # Short clinical notes


@dataclass
class Phenotype:
    id: str                          # "skinny_fat" | "sarcopenic_obesity" | "sarcopenia_risk" | "overfat_normal_bmi" | "none"
    label: str                       # Display label
    description: str                 # 1-sentence explanation
    confidence: str                  # "high" | "moderate" | "low"
    contributing_signals: list[str]  # Marker names that triggered this


@dataclass
class Signal:
    id: str                          # Short machine ID
    label: str                       # Display label
    detail: str                      # Clinical detail
    severity: str                    # "info" | "warning" | "concern"
    markers: list[str]               # Related marker names


@dataclass
class EvaluationResult:
    domain_scores: list[DomainScore]
    phenotype: Phenotype | None
    signals: list[Signal]
    certainty_grade: str             # "high" | "moderate" | "low" | "insufficient"
    certainty_note: str
    missing_for_full_eval: list[str]
    body_score: float                # 0–100 headline composite score
    body_score_label: str            # "Optimal" | "Good" | "Needs Attention" | "At Risk"
    body_age: int | None             # Estimated biological age (None if chronological age unknown)
    chronological_age: int | None    # User's actual age (passed in for reference)


# ---------------------------------------------------------------------------
# Marker lookup helpers
# ---------------------------------------------------------------------------

_CONCERNING_FLAGS = {"LOW", "HIGH", "CRITICAL_LOW", "CRITICAL_HIGH"}
_CONCERNING_TIERS = {
    "obese", "overfat", "overweight", "elevated", "high_risk",
    "underfat", "underweight", "low", "critically_low",
    "mild_imbalance", "significant_imbalance",
}
_GOOD_TIERS = {"healthy", "normal", "optimal", "sufficient", "symmetric"}


def _get_value(markers_by_id: dict, marker_id: str) -> float | None:
    m = markers_by_id.get(marker_id)
    return m.get("std_value") if m else None


def _get_flag(markers_by_id: dict, marker_id: str) -> str | None:
    m = markers_by_id.get(marker_id)
    return m.get("flag") if m else None


def _get_tier(markers_by_id: dict, marker_id: str) -> str | None:
    m = markers_by_id.get(marker_id)
    if m is None:
        return None
    flag = m.get("flag", "")
    if flag.startswith("TIER:"):
        return flag[5:]
    return m.get("canonical_tier")


def _is_concerning(m: dict) -> bool:
    flag = m.get("flag", "")
    if flag in _CONCERNING_FLAGS:
        return True
    tier = _get_tier_from_marker(m)
    return tier in _CONCERNING_TIERS if tier else False


def _is_good(m: dict) -> bool:
    flag = m.get("flag", "")
    if flag == "OPTIMAL":
        return True
    tier = _get_tier_from_marker(m)
    return tier in _GOOD_TIERS if tier else False


def _get_tier_from_marker(m: dict) -> str | None:
    flag = m.get("flag", "")
    if flag.startswith("TIER:"):
        return flag[5:]
    return m.get("canonical_tier")


# ---------------------------------------------------------------------------
# Domain scoring
# ---------------------------------------------------------------------------

_ADIPOSITY_SCORE_VALUES: dict[str, float] = {
    "Optimal":   100.0,
    "Moderate":   82.0,
    "Low":        70.0,
    "Elevated":   55.0,
    "High Risk":  25.0,
}


def _score_adiposity(markers_by_id: dict) -> DomainScore:
    """
    Score adiposity domain using tier-based categorical label.
    Priority: visceral fat > body fat % > BMI.
    """
    vfa_tier = _get_tier(markers_by_id, "VFA")
    vfl_tier = _get_tier(markers_by_id, "VFL")
    pbf_tier = _get_tier(markers_by_id, "PBF")
    fmi_tier = _get_tier(markers_by_id, "FMI")
    bmi_tier = _get_tier(markers_by_id, "BMI")

    used = [
        (markers_by_id.get(mid) or {}).get("marker_name") or mid
        for mid in ("VFA", "VFL", "PBF", "FMI", "BMI", "BFM")
        if markers_by_id.get(mid) is not None
    ]
    notes: list[str] = []

    if vfa_tier == "high_risk" or vfl_tier == "high_risk":
        status = "High Risk"
        notes.append("Visceral fat: high risk")
    elif vfa_tier == "elevated" or vfl_tier == "elevated":
        status = "Elevated"
        notes.append("Visceral fat: elevated")
    elif pbf_tier in ("overfat", "obese") or fmi_tier in ("overfat", "obese"):
        status = "Elevated"
        tier = pbf_tier if pbf_tier in ("overfat", "obese") else fmi_tier
        notes.append(f"Body fat: {tier}")
    elif bmi_tier in ("overweight", "obese"):
        status = "Moderate"
        notes.append(f"BMI: {bmi_tier}")
    elif pbf_tier == "underfat" or fmi_tier == "underfat":
        status = "Low"
        notes.append("Body fat: low")
    else:
        status = "Optimal"

    score = _ADIPOSITY_SCORE_VALUES.get(status, 50.0)
    return DomainScore(
        domain="adiposity", label="Adiposity",
        score=score, grade=status,
        markers_used=used, notes=notes,
    )


_MUSCULARITY_SCORE_VALUES: dict[str, float] = {
    "Normal":                100.0,
    "Asymmetry Detected":     78.0,
    "Above Natural Ceiling":  72.0,
    "Low":                    50.0,
    "Critically Low":         20.0,
}


def _score_muscularity(markers_by_id: dict) -> DomainScore:
    """
    Score muscularity domain: SMM, SMI, FFMI, BMR (proxy for muscle mass).
    Special cases: physiological ceiling on FFMI, limb asymmetry.
    """
    used = []
    notes = []
    penalties = 0
    total_weight = 0

    checks = [
        ("SMI",  35),
        ("FFMI", 30),
        ("SMM",  20),
        ("BMR",  15),
    ]

    for mid, weight in checks:
        m = markers_by_id.get(mid)
        if m is None:
            continue
        total_weight += weight
        name = m.get("marker_name") or mid
        used.append(name)

        if _is_concerning(m):
            tier = _get_tier_from_marker(m)
            flag = m.get("flag", "")
            if tier in ("underfat", "underweight", "critically_low") or flag == "CRITICAL_LOW":
                penalties += weight * 1.0
                notes.append(f"{name}: critically low")
            elif tier == "low" or flag == "LOW":
                penalties += weight * 0.6
                notes.append(f"{name}: low")

    if total_weight == 0:
        return DomainScore(
            domain="muscularity", label="Muscularity",
            score=_MUSCULARITY_SCORE_VALUES["Low"], grade="Low",
            markers_used=[], notes=["Insufficient data"]
        )

    continuous = max(0.0, min(100.0, 100.0 - (penalties / total_weight * 100)))

    # Determine categorical grade — check special cases first
    ffmi_tier = _get_tier(markers_by_id, "FFMI")
    arm_tier  = _get_tier(markers_by_id, "LimbSymmetry_Arms")
    leg_tier  = _get_tier(markers_by_id, "LimbSymmetry_Legs")
    has_asymmetry = arm_tier == "asymmetric" or leg_tier == "asymmetric"

    if ffmi_tier == "physiological_ceiling":
        grade = "Above Natural Ceiling"
    elif continuous < 30:
        grade = "Critically Low"
    elif continuous < 65:
        grade = "Low"
    elif has_asymmetry:
        grade = "Asymmetry Detected"
    else:
        grade = "Normal"

    score = _MUSCULARITY_SCORE_VALUES.get(grade, 50.0)
    return DomainScore(
        domain="muscularity", label="Muscularity",
        score=score, grade=grade,
        markers_used=used, notes=notes,
    )


_FLUID_HEALTH_SCORE_VALUES: dict[str, float] = {
    "Optimal":                 100.0,
    "Normal":                  100.0,
    "Cellular Health Concern":  72.0,
    "Mild Imbalance":           58.0,
    "Significant Imbalance":    28.0,
}


def _fluid_health_status_label(score: float) -> str:
    if score >= 85:
        return "Optimal"
    if score >= 70:
        return "Normal"
    if score >= 50:
        return "Cellular Health Concern"
    if score >= 30:
        return "Mild Imbalance"
    return "Significant Imbalance"


def _score_fluid_health(markers_by_id: dict) -> DomainScore:
    """
    Score fluid and cellular health: ECW_TBW, PhaseAngle, TBW, WaterPct.
    """
    used = []
    notes = []
    penalties = 0
    rewards = 0
    total_weight = 0

    checks = [
        ("ECW_TBW",    35),
        ("PhaseAngle", 35),
        ("WaterPct",   20),
        ("TBW",        10),
    ]

    for mid, weight in checks:
        m = markers_by_id.get(mid)
        if m is None:
            continue
        total_weight += weight
        name = m.get("marker_name") or mid
        used.append(name)

        if _is_concerning(m):
            flag = m.get("flag", "")
            if flag in ("CRITICAL_LOW", "CRITICAL_HIGH"):
                penalties += weight * 1.0
            elif flag in ("LOW", "HIGH"):
                penalties += weight * 0.6
            elif _get_tier_from_marker(m) in ("elevated", "high_risk"):
                penalties += weight * 0.7
            notes.append(f"{name}: {flag or _get_tier_from_marker(m)}")
        elif _is_good(m):
            rewards += weight * 0.1

    if total_weight == 0:
        return DomainScore(
            domain="fluid_health", label="Fluid & Cellular Health",
            score=_FLUID_HEALTH_SCORE_VALUES["Cellular Health Concern"], grade="Cellular Health Concern",
            markers_used=[], notes=["Insufficient data"]
        )

    base = 100.0 - (penalties / total_weight * 100)
    continuous = max(0.0, min(100.0, base + rewards))
    grade = _fluid_health_status_label(continuous)
    score = _FLUID_HEALTH_SCORE_VALUES.get(grade, 50.0)

    return DomainScore(
        domain="fluid_health", label="Fluid & Cellular Health",
        score=score, grade=grade,
        markers_used=used, notes=notes,
    )


_METABOLIC_SCORE_VALUES: dict[str, float] = {
    "Optimal":       100.0,
    "Below Average":  70.0,
    "Moderate":       62.0,
    "Suppressed":     45.0,
    "High Risk":      30.0,
    "Critical":       12.0,
}


def _score_metabolic_health(
    markers_by_id: dict,
    domain_scores: dict[str, DomainScore],
    bmr_actual: float | None,
    bmr_expected: float | None,
) -> DomainScore:
    """
    Score metabolic health: BMR vs expected, modulated by adiposity and muscularity.
    Low BMR relative to expected + adverse anthropometry = high metabolic risk.
    """
    bmr_tier = _get_tier(markers_by_id, "BMR")
    adip = domain_scores.get("adiposity")
    musc = domain_scores.get("muscularity")

    adip_label = adip.grade if adip else "Optimal"
    musc_label = musc.grade if musc else "Normal"

    if bmr_expected and bmr_actual and bmr_expected > 0:
        bmr_ratio = bmr_actual / bmr_expected
    else:
        bmr_ratio = 1.0

    used: list[str] = []
    notes: list[str] = []

    # BMR context note — shown as primary driver text on the domain card
    bmr_m = markers_by_id.get("BMR")
    if bmr_m:
        used.append(bmr_m.get("marker_name") or "Basal Metabolic Rate")
        ref_low = bmr_m.get("canonical_ref_low")
        ref_high = bmr_m.get("canonical_ref_high")
        if bmr_actual is not None and ref_low is not None and ref_high is not None:
            if bmr_actual < ref_low:
                notes.append(
                    f"BMR {int(bmr_actual)} kcal — below age average ({int(ref_low)}–{int(ref_high)})"
                )
            else:
                notes.append(
                    f"BMR {int(bmr_actual)} kcal — within age range ({int(ref_low)}–{int(ref_high)})"
                )
        elif bmr_actual is not None:
            notes.append(f"BMR {int(bmr_actual)} kcal")

    if bmr_tier == "low" or bmr_ratio < 0.85:
        if adip_label in ("Elevated", "High Risk") and musc_label in ("Low", "Critically Low"):
            status = "Critical"
        else:
            status = "Suppressed"
    elif bmr_ratio < 0.95:
        if adip_label in ("Elevated", "High Risk") and musc_label in ("Low", "Critically Low"):
            status = "High Risk"
        else:
            status = "Below Average"
    elif adip_label in ("Elevated", "High Risk") and musc_label in ("Low", "Critically Low"):
        status = "High Risk"
    elif adip_label in ("Elevated", "High Risk") and musc_label == "Normal":
        status = "Moderate"
    elif adip_label in ("Normal", "Moderate") and musc_label in ("Low", "Critically Low"):
        status = "Moderate"
    else:
        status = "Optimal"

    score = _METABOLIC_SCORE_VALUES.get(status, 50.0)
    return DomainScore(
        domain="metabolic_health", label="Metabolic Health",
        score=score, grade=status,
        markers_used=used,
        notes=notes,
    )


def _grade_score(score: float) -> str:
    if score >= 85:
        return "optimal"
    if score >= 70:
        return "good"
    if score >= 50:
        return "borderline"
    if score >= 30:
        return "poor"
    return "critical"


# ---------------------------------------------------------------------------
# Phenotype detection
# ---------------------------------------------------------------------------

def _detect_phenotype(markers_by_id: dict, domain_scores: dict[str, DomainScore]) -> Phenotype | None:
    """
    Detect anthropometry phenotype from domain scores + key marker tiers.
    """
    adip = domain_scores.get("adiposity")
    musc = domain_scores.get("muscularity")

    pbf_tier = _get_tier(markers_by_id, "PBF")
    bmi_tier = _get_tier(markers_by_id, "BMI")
    smi_tier = _get_tier(markers_by_id, "SMI")
    ffmi_tier = _get_tier(markers_by_id, "FFMI")
    pbf_flag = _get_flag(markers_by_id, "PBF")
    smi_flag = _get_flag(markers_by_id, "SMI")

    signals = []

    # Sarcopenic obesity: high fat + low muscle
    if (
        adip and musc
        and adip.score <= 60
        and musc.score <= 55
        and pbf_tier in ("overfat", "obese")
        and smi_tier in ("low", None)
    ):
        if smi_flag in ("LOW", "CRITICAL_LOW") or smi_tier == "low":
            signals = ["Body Fat Percentage", "Skeletal Muscle Index"]
            return Phenotype(
                id="sarcopenic_obesity",
                label="Sarcopenic Obesity",
                description="Excess body fat combined with reduced skeletal muscle mass — a high-risk metabolic phenotype.",
                confidence="high" if (pbf_flag in _CONCERNING_FLAGS and smi_flag in _CONCERNING_FLAGS) else "moderate",
                contributing_signals=signals,
            )

    # Skinny fat (normal BMI, elevated body fat, low muscle)
    if (
        bmi_tier in ("normal", None)
        and pbf_tier in ("overfat", "obese")
        and (smi_tier in ("low", None) or (ffmi_tier and ffmi_tier in ("low",)))
    ):
        signals = ["BMI", "Body Fat Percentage"]
        if smi_tier:
            signals.append("Skeletal Muscle Index")
        return Phenotype(
            id="skinny_fat",
            label="Skinny Fat (MONW)",
            description="Normal BMI masking excess fat and insufficient muscle — metabolically obese, normal weight.",
            confidence="moderate",
            contributing_signals=signals,
        )

    # Sarcopenia risk: low muscle, normal or low fat
    if (
        musc and musc.score <= 55
        and (smi_flag in ("LOW", "CRITICAL_LOW") or smi_tier == "low")
    ):
        signals = ["Skeletal Muscle Index"]
        if ffmi_tier:
            signals.append("Fat-Free Mass Index")
        return Phenotype(
            id="sarcopenia_risk",
            label="Sarcopenia Risk",
            description="Low skeletal muscle mass index indicates risk of sarcopenia — monitor with strength and functional assessments.",
            confidence="moderate",
            contributing_signals=signals,
        )

    # Overfat at normal BMI (less specific than skinny fat)
    if bmi_tier == "normal" and pbf_tier in ("overfat", "obese"):
        return Phenotype(
            id="overfat_normal_bmi",
            label="Overfat at Normal BMI",
            description="BMI is within normal range but body fat percentage is elevated — BMI underestimates adiposity.",
            confidence="moderate",
            contributing_signals=["BMI", "Body Fat Percentage"],
        )

    return None


# ---------------------------------------------------------------------------
# Cross-reference signals
# ---------------------------------------------------------------------------

def _find_signals(markers_by_id: dict) -> list[Signal]:
    signals: list[Signal] = []

    # ECW/TBW elevated — fluid retention or inflammation
    ecw_tbw_tier = _get_tier(markers_by_id, "ECW_TBW")
    if ecw_tbw_tier in ("elevated", "high_risk"):
        signals.append(Signal(
            id="ecw_tbw_elevated",
            label="Elevated ECW/TBW Ratio",
            detail="Extracellular water ratio is high, which may indicate oedema, inflammation, or poor cellular hydration.",
            severity="warning",
            markers=["ECW/TBW Ratio"],
        ))

    # Phase angle critically low
    pa_m = markers_by_id.get("PhaseAngle")
    if pa_m and pa_m.get("is_critical"):
        signals.append(Signal(
            id="phase_angle_critical",
            label="Critical Phase Angle",
            detail="Phase angle below critical threshold indicates severely compromised cellular integrity.",
            severity="concern",
            markers=["Phase Angle"],
        ))
    elif pa_m and _get_flag(markers_by_id, "PhaseAngle") in ("LOW",):
        signals.append(Signal(
            id="phase_angle_low",
            label="Low Phase Angle",
            detail="Phase angle is below the reference range — may reflect reduced cell membrane integrity or undernutrition.",
            severity="warning",
            markers=["Phase Angle"],
        ))

    # Limb asymmetry (tier names: "symmetric" / "asymmetric")
    for sym_id, label in (("LimbSymmetry_Arms", "Arm"), ("LimbSymmetry_Legs", "Leg")):
        m = markers_by_id.get(sym_id)
        if m is None:
            continue
        tier = _get_tier_from_marker(m)
        value = m.get("std_value", 0)
        if tier == "asymmetric":
            severity = "concern" if value > 20 else "warning"
            signals.append(Signal(
                id=f"{sym_id.lower()}_asymmetry",
                label=f"{label} Lean Mass Asymmetry",
                detail=(
                    f"{round(value, 1)}% asymmetry in {label.lower()} lean mass — "
                    f"consider injury history, dominant-side compensation, or neuromuscular dysfunction."
                ),
                severity=severity,
                markers=[f"{label} Lean Mass Symmetry"],
            ))

    # BMI overweight driven by high lean mass, not excess fat
    bmi_tier = _get_tier(markers_by_id, "BMI")
    pbf_tier = _get_tier(markers_by_id, "PBF")
    smi_m = markers_by_id.get("SMI")
    if (
        bmi_tier == "overweight"
        and pbf_tier in ("healthy", "underfat", "normal")
        and smi_m is not None
        and _get_tier_from_marker(smi_m) not in ("low", None)
    ):
        signals.append(Signal(
            id="bmi_driven_by_muscle",
            label="BMI Overweight Driven by Lean Mass",
            detail=(
                "BMI falls in the overweight range, but body fat percentage and muscle index "
                "are both healthy. This pattern indicates above-average muscle mass, not excess fat. "
                "The BMI overweight classification is not clinically significant in this context."
            ),
            severity="info",
            markers=["BMI", "Body Fat Percentage", "Skeletal Muscle Index"],
        ))

    # Visceral fat elevated alongside normal BMI
    vfa_tier = _get_tier(markers_by_id, "VFA") or _get_tier(markers_by_id, "VFL")
    if bmi_tier == "normal" and vfa_tier in ("elevated", "high_risk"):
        signals.append(Signal(
            id="hidden_visceral_fat",
            label="Hidden Visceral Adiposity",
            detail="Visceral fat is elevated despite normal BMI — this pattern is associated with increased metabolic and cardiovascular risk.",
            severity="concern",
            markers=["BMI", "Visceral Fat Area" if "VFA" in markers_by_id else "Visceral Fat Level"],
        ))

    # Low protein percentage
    prot_m = markers_by_id.get("ProteinPct")
    if prot_m and _get_flag(markers_by_id, "ProteinPct") == "LOW":
        signals.append(Signal(
            id="low_protein_pct",
            label="Low Protein Percentage",
            detail="Body protein percentage is below reference — may reflect inadequate protein intake or muscle breakdown.",
            severity="warning",
            markers=["Protein Percentage"],
        ))

    return signals


# ---------------------------------------------------------------------------
# Certainty grading
# ---------------------------------------------------------------------------

_CORE_MARKERS = {"Weight", "SMM", "BFM", "PBF", "BMI", "TBW", "FFM"}
_EXTENDED_MARKERS = {"SMI", "FFMI", "ECW_TBW", "PhaseAngle", "VFA", "VFL", "FMI"}


def _grade_certainty(markers_by_id: dict) -> tuple[str, str, list[str]]:
    present = set(markers_by_id.keys())
    core_present = _CORE_MARKERS & present
    extended_present = _EXTENDED_MARKERS & present
    missing_core = _CORE_MARKERS - present

    missing_for_full = list((_CORE_MARKERS | _EXTENDED_MARKERS) - present)

    if len(core_present) == 0:
        return "insufficient", "No core anthropometry markers found.", missing_for_full

    if len(core_present) < 3:
        return (
            "low",
            f"Only {len(core_present)}/{len(_CORE_MARKERS)} core markers present. "
            "Evaluation is limited.",
            missing_for_full,
        )

    if missing_core:
        note = (
            f"{len(core_present)}/{len(_CORE_MARKERS)} core markers present. "
            f"Missing: {', '.join(sorted(missing_core))}."
        )
        grade = "moderate"
    else:
        grade = "high" if len(extended_present) >= 3 else "moderate"
        note = (
            "All core markers present"
            + (f" + {len(extended_present)} extended markers." if extended_present else ".")
        )

    return grade, note, missing_for_full


# ---------------------------------------------------------------------------
# Body Score
# ---------------------------------------------------------------------------

_DOMAIN_WEIGHTS = {
    "adiposity":        0.30,
    "muscularity":      0.30,
    "fluid_health":     0.20,
    "metabolic_health": 0.20,
}

_PHENOTYPE_PENALTY = {
    "sarcopenic_obesity":            15,
    "sarcopenia_risk":               12,
    "skinny_fat":                    10,
    "treatment_response_distortion":  8,
    "overfat_normal_bmi":             8,
}


def _compute_body_score(domain_scores: list[DomainScore], phenotype: Phenotype | None) -> tuple[float, str]:
    """
    Compute the headline Body Score (0–100) as a weighted average of the
    actual domain scores, then subtract any phenotype penalty.

    Uses d.score (the continuous 0-100 domain value) rather than grade buckets
    so a 94.5 adiposity score contributes 94.5, not 100.
    """
    weighted = sum(
        d.score * _DOMAIN_WEIGHTS.get(d.domain, 0)
        for d in domain_scores
        if d.domain in _DOMAIN_WEIGHTS
    )

    if phenotype:
        weighted -= _PHENOTYPE_PENALTY.get(phenotype.id, 0)

    score = max(0.0, min(100.0, round(weighted, 1)))

    if score >= 85:
        label = "Optimal"
    elif score >= 70:
        label = "Good"
    elif score >= 50:
        label = "Needs Attention"
    else:
        label = "At Risk"

    return score, label


# ---------------------------------------------------------------------------
# Body Age
# ---------------------------------------------------------------------------

# Ideal reference values for body age calculation (male defaults; female overrides below)
_IDEAL_PBF = {"male": 15.0, "female": 23.0}
_IDEAL_SMM_RATIO = 0.45  # SMM / Weight
_IDEAL_VFL = 5


def _compute_body_age(
    markers_by_id: dict,
    chronological_age: int | None,
    sex: str | None,
) -> int | None:
    """
    Estimate biological age from body composition relative to chronological age.

    Formula:
      body_age = chronological_age
                 + (PBF - ideal_PBF) × 0.5           # fat penalty/bonus
                 + (ideal_SMM_ratio - SMM_ratio) × 20 # muscle penalty/bonus
                 + (VFL - ideal_VFL) × 0.3             # visceral fat penalty/bonus

    Returns None if chronological age is unknown.
    """
    if chronological_age is None:
        return None

    sex_key = (sex or "male").lower()
    ideal_pbf = _IDEAL_PBF.get(sex_key, 15.0)

    adjustment = 0.0

    # PBF component
    pbf_val = _get_value(markers_by_id, "PBF")
    if pbf_val is not None:
        adjustment += (pbf_val - ideal_pbf) * 0.5

    # SMM/Weight ratio component
    smm_val = _get_value(markers_by_id, "SMM")
    weight_val = _get_value(markers_by_id, "Weight")
    if smm_val is not None and weight_val is not None and weight_val > 0:
        smm_ratio = smm_val / weight_val
        adjustment += (_IDEAL_SMM_RATIO - smm_ratio) * 20

    # Visceral fat level component
    vfl_val = _get_value(markers_by_id, "VFL")
    if vfl_val is not None:
        adjustment += (vfl_val - _IDEAL_VFL) * 0.3

    body_age = round(chronological_age + adjustment)
    # Clamp to reasonable range
    return max(18, min(chronological_age + 20, body_age))


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def evaluate(flagged_markers: list[dict], chronological_age: int | None = None, sex: str | None = None) -> EvaluationResult:
    """
    Run Stage 3 evaluation on a list of flagged marker dicts (from Stage 2 output).

    Each marker dict should have at minimum:
      marker_id, marker_name, std_value, std_unit, flag, canonical_tier, is_derived
    """
    # Index by marker_id for fast lookup
    markers_by_id: dict[str, dict] = {}
    for m in flagged_markers:
        mid = m.get("marker_id")
        if mid:
            markers_by_id[mid] = m

    # Extract BMR values for metabolic health scoring
    bmr_actual = next(
        (m.get("std_value") for m in flagged_markers if m.get("marker_id") == "BMR"),
        None,
    )
    bmr_expected = next(
        (m.get("std_value") for m in flagged_markers if m.get("marker_id") == "BMR_expected"),
        None,
    )

    # Score all domains
    adip = _score_adiposity(markers_by_id)
    musc = _score_muscularity(markers_by_id)
    fluid = _score_fluid_health(markers_by_id)

    domain_scores_map = {
        "adiposity": adip,
        "muscularity": musc,
        "fluid_health": fluid,
    }
    metab = _score_metabolic_health(markers_by_id, domain_scores_map, bmr_actual, bmr_expected)

    domain_scores = [adip, musc, fluid, metab]

    # Detect phenotype
    domain_scores_map["metabolic_health"] = metab
    phenotype = _detect_phenotype(markers_by_id, domain_scores_map)

    # Find signals
    signals = _find_signals(markers_by_id)

    # Grade certainty
    grade, note, missing = _grade_certainty(markers_by_id)

    # Headline Body Score
    body_score, body_score_label = _compute_body_score(domain_scores, phenotype)

    # Body Age
    body_age = _compute_body_age(markers_by_id, chronological_age, sex)

    return EvaluationResult(
        domain_scores=domain_scores,
        phenotype=phenotype,
        signals=signals,
        certainty_grade=grade,
        certainty_note=note,
        missing_for_full_eval=missing,
        body_score=body_score,
        body_score_label=body_score_label,
        body_age=body_age,
        chronological_age=chronological_age,
    )
