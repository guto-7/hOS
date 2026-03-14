use crate::pipeline::types::DomainScore;
use super::{MarkerLookup, UserProfile};

const DOMAIN: &str = "Metabolic";

/// HOMA-IR: (Insulin [mU/L] × Glucose [mmol/L] × 18.016) / 405
/// Canonical units: Glucose mmol/L, Insulin mU/L (= µU/mL)
pub fn homa_ir(m: &MarkerLookup) -> Option<DomainScore> {
    let insulin = m.val("insulin")?;
    let glucose = m.val("glucose")?;
    let glucose_mgdl = glucose * 18.016;
    let score = insulin * glucose_mgdl / 405.0;

    let interp = if score < 1.0 {
        "Optimal insulin sensitivity"
    } else if score < 2.0 {
        "Normal"
    } else if score < 3.0 {
        "Early insulin resistance"
    } else {
        "Significant insulin resistance"
    };

    Some(DomainScore {
        domain: DOMAIN.into(),
        system: "HOMA-IR".into(),
        score,
        interpretation: interp.into(),
        components: vec!["Insulin (Fasting)".into(), "Glucose (Fasting)".into()],
        version: "Matthews 1985".into(),
    })
}

/// TyG Index: ln(TG [mg/dL] × Glucose [mg/dL] / 2)
/// Canonical units: TG mmol/L (÷0.0113 → mg/dL), Glucose mmol/L (÷0.0556 → mg/dL)
pub fn tyg_index(m: &MarkerLookup) -> Option<DomainScore> {
    let tg_mmol = m.val("triglycerides")?;
    let glucose_mmol = m.val("glucose")?;
    let tg_mgdl = tg_mmol / 0.0113;
    let glucose_mgdl = glucose_mmol / 0.0556;
    let score = (tg_mgdl * glucose_mgdl / 2.0).ln();

    let interp = if score < 8.5 {
        "Low insulin resistance risk"
    } else if score < 9.0 {
        "Moderate insulin resistance"
    } else {
        "High insulin resistance risk"
    };

    Some(DomainScore {
        domain: DOMAIN.into(),
        system: "TyG Index".into(),
        score,
        interpretation: interp.into(),
        components: vec!["Triglycerides".into(), "Glucose (Fasting)".into()],
        version: "Simental-Mendia 2008".into(),
    })
}

/// AIP: log10(TG / HDL) — both in mmol/L (ratio is unitless)
pub fn aip(m: &MarkerLookup) -> Option<DomainScore> {
    let tg = m.val("triglycerides")?;
    let hdl = m.val("hdl")?;
    if hdl <= 0.0 { return None; }
    let score = (tg / hdl).log10();

    let interp = if score < 0.11 {
        "Low cardiovascular risk"
    } else if score < 0.21 {
        "Intermediate cardiovascular risk"
    } else {
        "High cardiovascular risk"
    };

    Some(DomainScore {
        domain: DOMAIN.into(),
        system: "Atherogenic Index of Plasma".into(),
        score,
        interpretation: interp.into(),
        components: vec!["Triglycerides".into(), "HDL Cholesterol".into()],
        version: "Dobiasova & Frohlich 2001".into(),
    })
}

/// TG/HDL Ratio — both in mmol/L
pub fn tg_hdl_ratio(m: &MarkerLookup, profile: &UserProfile) -> Option<DomainScore> {
    let tg = m.val("triglycerides")?;
    let hdl = m.val("hdl")?;
    if hdl <= 0.0 { return None; }
    // Convert to mg/dL for standard thresholds
    let tg_mgdl = tg / 0.0113;
    let hdl_mgdl = hdl / 0.0259;
    let score = tg_mgdl / hdl_mgdl;

    let is_female = profile.sex.as_deref().map(|s| s.to_lowercase())
        .map(|s| s == "female" || s == "f")
        .unwrap_or(false);

    let threshold = if is_female { 2.5 } else { 3.5 };
    let interp = if score < 2.0 {
        "Ideal — insulin sensitive"
    } else if score < threshold {
        "Normal range"
    } else {
        "Elevated — insulin resistance likely"
    };

    Some(DomainScore {
        domain: DOMAIN.into(),
        system: "TG/HDL Ratio".into(),
        score,
        interpretation: interp.into(),
        components: vec!["Triglycerides".into(), "HDL Cholesterol".into()],
        version: "Gasevic 2024".into(),
    })
}

/// MetS Blood Score: count of metabolic syndrome criteria met from blood markers.
/// 3 of 5 criteria assessable: TG ≥ 1.70 mmol/L, HDL < threshold, Glucose ≥ 5.6 mmol/L.
pub fn mets_blood_score(m: &MarkerLookup, profile: &UserProfile) -> Option<DomainScore> {
    let tg = m.val("triglycerides");
    let hdl = m.val("hdl");
    let glucose = m.val("glucose");

    // Need at least 2 of 3 to be useful
    let available = [tg.is_some(), hdl.is_some(), glucose.is_some()];
    if available.iter().filter(|&&x| x).count() < 2 {
        return None;
    }

    let is_female = profile.sex.as_deref().map(|s| s.to_lowercase())
        .map(|s| s == "female" || s == "f")
        .unwrap_or(false);

    let mut met = 0u32;
    let mut total = 0u32;
    let mut components = Vec::new();

    if let Some(tg_val) = tg {
        total += 1;
        if tg_val >= 1.70 {
            met += 1;
            components.push("Triglycerides ≥ 1.70 mmol/L".into());
        }
    }
    if let Some(hdl_val) = hdl {
        total += 1;
        let threshold = if is_female { 1.30 } else { 1.04 };
        if hdl_val < threshold {
            met += 1;
            components.push(format!("HDL < {:.2} mmol/L", threshold));
        }
    }
    if let Some(gluc_val) = glucose {
        total += 1;
        if gluc_val >= 5.6 {
            met += 1;
            components.push("Fasting Glucose ≥ 5.6 mmol/L".into());
        }
    }

    let interp = if met == 3 {
        "Metabolic syndrome confirmed from blood markers alone (3/3 criteria met)"
    } else if met == 2 {
        "2 of 3 blood criteria met — at risk"
    } else if met == 1 {
        "1 of 3 blood criteria met — borderline"
    } else {
        "No blood-based MetS criteria met"
    };

    Some(DomainScore {
        domain: DOMAIN.into(),
        system: "MetS Blood Score".into(),
        score: met as f64,
        interpretation: format!("{interp} ({met}/{total} assessable criteria)"),
        components,
        version: "Harmonized 2009".into(),
    })
}

/// De Ritis Ratio: AST / ALT
pub fn de_ritis(m: &MarkerLookup) -> Option<DomainScore> {
    let ast = m.val("ast")?;
    let alt = m.val("alt")?;
    if alt <= 0.0 { return None; }
    let score = ast / alt;

    let interp = if score < 1.0 {
        "Normal — ALT predominant (typical healthy liver)"
    } else if score < 2.0 {
        "Mildly elevated — possible chronic hepatitis or early fibrosis"
    } else {
        "Significantly elevated — suggests alcoholic liver disease or advanced fibrosis"
    };

    Some(DomainScore {
        domain: DOMAIN.into(),
        system: "De Ritis Ratio".into(),
        score,
        interpretation: interp.into(),
        components: vec!["AST".into(), "ALT".into()],
        version: "Botros & Sikaris 2013".into(),
    })
}

/// FIB-4: (Age × AST) / (Platelets × √ALT)
/// Platelets in x10⁹/L, AST and ALT in U/L.
pub fn fib4(m: &MarkerLookup, profile: &UserProfile) -> Option<DomainScore> {
    let age = profile.age? as f64;
    let ast = m.val("ast")?;
    let alt = m.val("alt")?;
    let plt = m.val("platelets")?;
    if plt <= 0.0 || alt <= 0.0 { return None; }
    let score = (age * ast) / (plt * alt.sqrt());

    let interp = if score < 1.3 {
        "Low risk of advanced fibrosis"
    } else if score < 2.67 {
        "Indeterminate — further assessment recommended"
    } else {
        "High probability of advanced fibrosis"
    };

    Some(DomainScore {
        domain: DOMAIN.into(),
        system: "FIB-4 Index".into(),
        score,
        interpretation: interp.into(),
        components: vec!["AST".into(), "ALT".into(), "Platelets (PLT)".into()],
        version: "Sterling 2006".into(),
    })
}

/// hsCRP cardiovascular risk tier (AHA/CDC).
pub fn hscrp_tier(m: &MarkerLookup) -> Option<DomainScore> {
    let crp = m.val("hscrp")?;

    let interp = if crp >= 10.0 {
        "Likely acute infection — not valid for CV risk"
    } else if crp >= 3.0 {
        "High cardiovascular risk"
    } else if crp >= 1.0 {
        "Moderate cardiovascular risk"
    } else {
        "Low cardiovascular risk"
    };

    Some(DomainScore {
        domain: DOMAIN.into(),
        system: "hsCRP Risk".into(),
        score: crp,
        interpretation: interp.into(),
        components: vec!["hsCRP".into()],
        version: "AHA/CDC 2003".into(),
    })
}

/// HbA1c glycaemic category (ADA).
pub fn hba1c_tier(m: &MarkerLookup) -> Option<DomainScore> {
    let hba1c = m.val("hba1c")?;

    let interp = if hba1c >= 6.5 {
        "Diabetes range"
    } else if hba1c >= 5.7 {
        "Prediabetes range"
    } else {
        "Normal glucose metabolism"
    };

    Some(DomainScore {
        domain: DOMAIN.into(),
        system: "HbA1c Category".into(),
        score: hba1c,
        interpretation: interp.into(),
        components: vec!["HbA1c".into()],
        version: "ADA 2024".into(),
    })
}

/// Uric Acid metabolic risk tier.
/// Canonical unit: mmol/L. Thresholds from literature are in mg/dL.
/// Conversion: mmol/L × 16.81 = mg/dL
pub fn uric_acid_tier(m: &MarkerLookup, profile: &UserProfile) -> Option<DomainScore> {
    let ua_mmol = m.val("uric acid")?;
    let ua_mgdl = ua_mmol * 16.81;

    let is_female = profile.sex.as_deref().map(|s| s.to_lowercase())
        .map(|s| s == "female" || s == "f")
        .unwrap_or(false);

    let high_threshold = if is_female { 6.0 } else { 7.0 };

    let interp = if ua_mgdl < 5.0 {
        "Optimal metabolic range"
    } else if ua_mgdl < 5.6 {
        "Borderline — emerging CV risk"
    } else if ua_mgdl < high_threshold {
        "Elevated metabolic risk"
    } else {
        "Clinical hyperuricemia"
    };

    Some(DomainScore {
        domain: DOMAIN.into(),
        system: "Uric Acid Risk".into(),
        score: ua_mgdl,
        interpretation: interp.into(),
        components: vec!["Uric Acid".into()],
        version: "URRAH / Feig 2008".into(),
    })
}

/// Collect all metabolic domain scores.
pub fn all_scores(m: &MarkerLookup, profile: &UserProfile) -> Vec<DomainScore> {
    let scorers: Vec<Option<DomainScore>> = vec![
        homa_ir(m),
        tyg_index(m),
        aip(m),
        tg_hdl_ratio(m, profile),
        mets_blood_score(m, profile),
        de_ritis(m),
        fib4(m, profile),
        hscrp_tier(m),
        hba1c_tier(m),
        uric_acid_tier(m, profile),
    ];
    scorers.into_iter().flatten().collect()
}
