use crate::pipeline::types::DomainScore;
use super::{MarkerLookup, UserProfile};

const DOMAIN: &str = "Longevity";

/// Levine's PhenoAge (2018) — biological age from 9 blood markers + chronological age.
///
/// Unit conversions from our canonical units:
///   Albumin: g/L → g/dL (÷10)
///   Creatinine: already µmol/L
///   Glucose: already mmol/L
///   hsCRP: mg/L → mg/dL (÷10), then ln()
///   MCV: already fL
///   RDW: already %
///   ALP: already U/L
///   WBC: x10⁹/L → 1000 cells/µL (same numeric value)
///   Lymphocyte%: not directly available — use estimate if missing
pub fn phenoage(m: &MarkerLookup, profile: &UserProfile) -> Option<DomainScore> {
    let age = profile.age? as f64;
    let albumin_gdl = m.val("albumin")? / 10.0;
    let creatinine_umol = m.val("creatinine")?;
    let glucose_mmol = m.val("glucose")?;
    let crp_mgdl = m.val("hscrp")? / 10.0;
    if crp_mgdl <= 0.0 { return None; }
    let ln_crp = crp_mgdl.ln();
    let mcv = m.val("mean corpuscular volume")?;
    let rdw = m.val("red cell distribution width")?;
    let alp = m.val("alkaline phosphatase")?;
    let wbc = m.val("white blood cell")?;

    // Lymphocyte % — not in standard panel, estimate at 30% for hackathon
    let lymph_pct = 30.0;

    // Step 1: linear predictor
    let xb = -19.907
        - 0.0336 * albumin_gdl
        + 0.0095 * creatinine_umol
        + 0.1953 * glucose_mmol
        + 0.0954 * ln_crp
        - 0.0120 * lymph_pct
        + 0.0268 * mcv
        + 0.3306 * rdw
        + 0.00188 * alp
        + 0.0554 * wbc
        + 0.0804 * age;

    // Step 2: Gompertz 10-year mortality score
    let gamma = 0.0076927;
    let mortality_score = 1.0 - (-(xb.exp()) * ((120.0_f64 * gamma).exp() - 1.0) / gamma).exp();

    if mortality_score <= 0.0 || mortality_score >= 1.0 {
        return None;
    }

    // Step 3: convert to PhenoAge
    let pheno_age = 141.50225 + (-0.00553 * (1.0 - mortality_score).ln()).ln() / 0.090165;
    let accel = pheno_age - age;

    let interp = if accel <= -5.0 {
        format!("Biologically {:.1} years younger — excellent", accel.abs())
    } else if accel <= -1.0 {
        format!("Biologically {:.1} years younger than chronological age", accel.abs())
    } else if accel <= 1.0 {
        "Biological age approximately matches chronological age".into()
    } else if accel <= 5.0 {
        format!("Biologically {:.1} years older — moderate acceleration", accel)
    } else {
        format!("Biologically {:.1} years older — significant acceleration", accel)
    };

    Some(DomainScore {
        domain: DOMAIN.into(),
        system: "PhenoAge".into(),
        score: pheno_age,
        interpretation: format!("{interp} (PhenoAge: {pheno_age:.1}, Acceleration: {accel:+.1} years)"),
        components: vec![
            "Albumin".into(), "Creatinine".into(), "Glucose (Fasting)".into(),
            "hsCRP".into(), "MCV".into(), "RDW".into(), "Alkaline Phosphatase (ALP)".into(),
            "White Blood Cell Count (WBC)".into(),
        ],
        version: "Levine 2018".into(),
    })
}

/// Allostatic Load: count of markers outside longevity-optimal ranges.
/// Higher = more physiological wear. Scale 0-9.
pub fn allostatic_load(m: &MarkerLookup, profile: &UserProfile) -> Option<DomainScore> {
    let is_female = profile.sex.as_deref().map(|s| s.to_lowercase())
        .map(|s| s == "female" || s == "f")
        .unwrap_or(false);

    let mut load = 0u32;
    let mut total = 0u32;
    let mut flagged = Vec::new();

    // hsCRP ≥ 3.0 mg/L
    if let Some(v) = m.val("hscrp") {
        total += 1;
        if v >= 3.0 { load += 1; flagged.push("hsCRP ≥ 3.0".into()); }
    }
    // HbA1c ≥ 5.7%
    if let Some(v) = m.val("hba1c") {
        total += 1;
        if v >= 5.7 { load += 1; flagged.push("HbA1c ≥ 5.7%".into()); }
    }
    // Glucose ≥ 5.6 mmol/L
    if let Some(v) = m.val("glucose") {
        total += 1;
        if v >= 5.6 { load += 1; flagged.push("Glucose ≥ 5.6 mmol/L".into()); }
    }
    // Total Cholesterol ≥ 6.22 mmol/L (240 mg/dL)
    if let Some(v) = m.val("total cholesterol") {
        total += 1;
        if v >= 6.22 { load += 1; flagged.push("TC ≥ 6.22 mmol/L".into()); }
    }
    // HDL ≤ 1.04 (M) / ≤ 1.30 (F)
    if let Some(v) = m.val("hdl") {
        total += 1;
        let threshold = if is_female { 1.30 } else { 1.04 };
        if v <= threshold { load += 1; flagged.push(format!("HDL ≤ {threshold:.2}")); }
    }
    // eGFR ≤ 60
    if let Some(v) = m.val("egfr") {
        total += 1;
        if v <= 60.0 { load += 1; flagged.push("eGFR ≤ 60".into()); }
    }
    // Albumin ≤ 35 g/L (3.5 g/dL)
    if let Some(v) = m.val("albumin") {
        total += 1;
        if v <= 35.0 { load += 1; flagged.push("Albumin ≤ 35 g/L".into()); }
    }
    // WBC ≥ 10.0
    if let Some(v) = m.val("white blood cell") {
        total += 1;
        if v >= 10.0 { load += 1; flagged.push("WBC ≥ 10.0".into()); }
    }
    // Homocysteine ≥ 15
    if let Some(v) = m.val("homocysteine") {
        total += 1;
        if v >= 15.0 { load += 1; flagged.push("Homocysteine ≥ 15".into()); }
    }

    if total < 3 { return None; }

    let interp = if load == 0 {
        "Low allostatic load — minimal physiological wear"
    } else if load <= 2 {
        "Mild allostatic load"
    } else if load <= 4 {
        "Moderate allostatic load — multiple stress markers elevated"
    } else {
        "High allostatic load — significant physiological wear"
    };

    Some(DomainScore {
        domain: DOMAIN.into(),
        system: "Allostatic Load".into(),
        score: load as f64,
        interpretation: format!("{interp} ({load}/{total} markers flagged)"),
        components: flagged,
        version: "Seeman 1997 / adapted".into(),
    })
}

/// Longevity-optimal scoring: how many markers are in longevity-optimal vs standard range.
/// Produces a 0-100 score based on marker-by-marker assessment.
pub fn longevity_optimals(m: &MarkerLookup, profile: &UserProfile) -> Option<DomainScore> {
    let is_female = profile.sex.as_deref().map(|s| s.to_lowercase())
        .map(|s| s == "female" || s == "f")
        .unwrap_or(false);

    let mut total_score = 0.0;
    let mut count = 0u32;
    let mut components = Vec::new();

    // Each marker: 1.0 if optimal, 0.5 if normal, 0.0 if abnormal
    // HbA1c: optimal 4.8-5.2, normal <5.7
    if let Some(v) = m.val("hba1c") {
        count += 1;
        if (4.8..=5.2).contains(&v) {
            total_score += 1.0;
            components.push("HbA1c: optimal".into());
        } else if v < 5.7 {
            total_score += 0.5;
            components.push("HbA1c: normal".into());
        } else {
            components.push("HbA1c: elevated".into());
        }
    }
    // hsCRP: optimal <0.5, normal <1.0
    if let Some(v) = m.val("hscrp") {
        count += 1;
        if v < 0.5 {
            total_score += 1.0;
            components.push("hsCRP: optimal".into());
        } else if v < 1.0 {
            total_score += 0.5;
            components.push("hsCRP: normal".into());
        } else {
            components.push("hsCRP: elevated".into());
        }
    }
    // Glucose: optimal 4.0-4.7 mmol/L, normal <5.6
    if let Some(v) = m.val("glucose") {
        count += 1;
        if (4.0..=4.7).contains(&v) {
            total_score += 1.0;
            components.push("Glucose: optimal".into());
        } else if v < 5.6 {
            total_score += 0.5;
            components.push("Glucose: normal".into());
        } else {
            components.push("Glucose: elevated".into());
        }
    }
    // Vitamin D: optimal 75-150 nmol/L, normal 50-250
    if let Some(v) = m.val("vitamin d") {
        count += 1;
        if (75.0..=150.0).contains(&v) {
            total_score += 1.0;
            components.push("Vitamin D: optimal".into());
        } else if (50.0..=250.0).contains(&v) {
            total_score += 0.5;
            components.push("Vitamin D: sufficient".into());
        } else {
            components.push("Vitamin D: suboptimal".into());
        }
    }
    // B12: optimal >370 pmol/L, normal 148-590
    if let Some(v) = m.val("vitamin b12") {
        count += 1;
        if v > 370.0 && v <= 590.0 {
            total_score += 1.0;
            components.push("B12: optimal".into());
        } else if v >= 148.0 {
            total_score += 0.5;
            components.push("B12: normal".into());
        } else {
            components.push("B12: low".into());
        }
    }
    // Homocysteine: optimal <8, normal <15
    if let Some(v) = m.val("homocysteine") {
        count += 1;
        if v < 8.0 {
            total_score += 1.0;
            components.push("Homocysteine: optimal".into());
        } else if v < 15.0 {
            total_score += 0.5;
            components.push("Homocysteine: normal".into());
        } else {
            components.push("Homocysteine: elevated".into());
        }
    }
    // eGFR: optimal >90
    if let Some(v) = m.val("egfr") {
        count += 1;
        if v > 90.0 {
            total_score += 1.0;
            components.push("eGFR: optimal".into());
        } else if v > 60.0 {
            total_score += 0.5;
            components.push("eGFR: mild decline".into());
        } else {
            components.push("eGFR: reduced".into());
        }
    }
    // Albumin: optimal ≥44 g/L, normal ≥35
    if let Some(v) = m.val("albumin") {
        count += 1;
        if v >= 44.0 {
            total_score += 1.0;
            components.push("Albumin: optimal".into());
        } else if v >= 35.0 {
            total_score += 0.5;
            components.push("Albumin: normal".into());
        } else {
            components.push("Albumin: low".into());
        }
    }
    // Ferritin: optimal 50-100, normal 24-336(M)/307(F)
    if let Some(v) = m.val("ferritin") {
        count += 1;
        if (50.0..=100.0).contains(&v) {
            total_score += 1.0;
            components.push("Ferritin: optimal".into());
        } else {
            let high = if is_female { 307.0 } else { 336.0 };
            if v >= 24.0 && v <= high {
                total_score += 0.5;
                components.push("Ferritin: normal".into());
            } else {
                components.push("Ferritin: suboptimal".into());
            }
        }
    }
    // HDL: optimal 1.55+ mmol/L
    if let Some(v) = m.val("hdl") {
        count += 1;
        let min_normal = if is_female { 1.30 } else { 1.04 };
        if v >= 1.55 {
            total_score += 1.0;
            components.push("HDL: optimal".into());
        } else if v >= min_normal {
            total_score += 0.5;
            components.push("HDL: normal".into());
        } else {
            components.push("HDL: low".into());
        }
    }
    // RDW: optimal 11.4-12.5%, normal 9-14.5
    if let Some(v) = m.val("red cell distribution width") {
        count += 1;
        if (11.4..=12.5).contains(&v) {
            total_score += 1.0;
            components.push("RDW: optimal".into());
        } else if (9.0..=14.5).contains(&v) {
            total_score += 0.5;
            components.push("RDW: normal".into());
        } else {
            components.push("RDW: suboptimal".into());
        }
    }

    if count < 3 { return None; }

    let score = (total_score / count as f64) * 100.0;

    let interp = if score >= 80.0 {
        "Excellent longevity biomarker profile"
    } else if score >= 60.0 {
        "Good longevity profile with room for optimisation"
    } else if score >= 40.0 {
        "Average — several markers outside optimal ranges"
    } else {
        "Below average — multiple markers need attention"
    };

    Some(DomainScore {
        domain: DOMAIN.into(),
        system: "Longevity Optimals".into(),
        score,
        interpretation: format!("{interp} ({score:.0}/100)"),
        components,
        version: "Attia/Johnson framework adapted".into(),
    })
}

/// Collect all longevity domain scores.
pub fn all_scores(m: &MarkerLookup, profile: &UserProfile) -> Vec<DomainScore> {
    let scorers: Vec<Option<DomainScore>> = vec![
        phenoage(m, profile),
        allostatic_load(m, profile),
        longevity_optimals(m, profile),
    ];
    scorers.into_iter().flatten().collect()
}
