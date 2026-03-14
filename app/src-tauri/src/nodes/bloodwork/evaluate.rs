use std::collections::HashMap;

use crate::pipeline::error::PipelineError;
use crate::pipeline::types::{
    CertaintyGrade, CertaintyLevel, ConditionMatch, CriterionResult, DomainScore,
    EvaluationOutput, FlagClassification,
};

use super::scoring::composite::domain_composite;
use super::scoring::MarkerLookup;
use super::scoring::{hormonal, longevity, metabolic};
use super::unify::BloodworkData;

/// Evaluate unified bloodwork data: surface critical flags, group by category,
/// compute domain scores, match conditions, grade certainty.
pub fn evaluate(data: &BloodworkData) -> Result<EvaluationOutput, PipelineError> {
    let lookup = MarkerLookup::new(&data.markers);
    let profile = &data.profile;

    // ── 3a. Surface critical flags ──────────────────────────────────────
    let critical_flags: Vec<String> = data
        .markers
        .iter()
        .filter(|m| matches!(m.deviation.flag, FlagClassification::Critical))
        .map(|m| format!("{}: {} {}", m.name, m.value, m.unit))
        .collect();

    // ── 3b. Group markers by category ───────────────────────────────────
    let mut categories: HashMap<String, Vec<String>> = HashMap::new();
    for marker in &data.markers {
        let category = marker
            .category
            .clone()
            .unwrap_or_else(|| categorise_marker(&marker.name));
        categories
            .entry(category)
            .or_default()
            .push(marker.name.clone());
    }

    // ── 3c. Missing data estimation ─────────────────────────────────────
    let missing_data = estimate_missing_data(data);

    // ── 3d. Certainty ───────────────────────────────────────────────────
    let certainty = CertaintyGrade {
        grade: if data.markers.is_empty() {
            CertaintyLevel::Insufficient
        } else if missing_data.len() > 5 {
            CertaintyLevel::Low
        } else if missing_data.is_empty() {
            CertaintyLevel::High
        } else {
            CertaintyLevel::Moderate
        },
        confidence: if data.markers.is_empty() {
            0.0
        } else {
            let total_expected = data.markers.len() + missing_data.len();
            data.markers.len() as f64 / total_expected as f64
        },
        missing_data,
        incompleteness_impact: "Scores only compute when required markers are present".into(),
    };

    // ── 3e. Domain scores ───────────────────────────────────────────────
    let metabolic_scores = metabolic::all_scores(&lookup, profile);
    let longevity_scores = longevity::all_scores(&lookup, profile);
    let hormonal_scores = hormonal::all_scores(&lookup, profile);

    // Compute domain composites (0-100 headline number)
    let metabolic_composite = domain_composite("Metabolic", &metabolic_scores);
    let longevity_composite = domain_composite("Longevity", &longevity_scores);
    let hormonal_composite = domain_composite("Hormonal", &hormonal_scores);

    // Assemble all scores: composites first, then individual scores
    let mut domain_scores: Vec<DomainScore> = Vec::new();
    if let Some(c) = metabolic_composite {
        domain_scores.push(c);
    }
    if let Some(c) = longevity_composite {
        domain_scores.push(c);
    }
    if let Some(c) = hormonal_composite {
        domain_scores.push(c);
    }
    domain_scores.extend(metabolic_scores);
    domain_scores.extend(longevity_scores);
    domain_scores.extend(hormonal_scores);

    // ── 3f. Condition pattern matching ───────────────────────────────────
    let condition_matches = detect_conditions(&lookup, profile, &domain_scores);

    // ── Engine versions ─────────────────────────────────────────────────
    let mut engine_versions = HashMap::new();
    engine_versions.insert("bloodwork_evaluator".into(), "1.0.0".into());
    engine_versions.insert("scoring_metabolic".into(), "1.0.0".into());
    engine_versions.insert("scoring_longevity".into(), "1.0.0".into());
    engine_versions.insert("scoring_hormonal".into(), "1.0.0".into());

    Ok(EvaluationOutput {
        critical_flags,
        categories,
        domain_scores,
        condition_matches,
        certainty,
        engine_versions,
    })
}

/// Detect clinical conditions by multi-variable pattern matching.
fn detect_conditions(
    m: &MarkerLookup,
    profile: &super::unify::UserProfile,
    scores: &[DomainScore],
) -> Vec<ConditionMatch> {
    let mut matches = Vec::new();

    // ── Insulin Resistance ──────────────────────────────────────────────
    if let Some(homa) = find_score(scores, "HOMA-IR") {
        if homa.score > 2.9 {
            matches.push(condition(
                "Insulin Resistance",
                vec![criterion("HOMA-IR > 2.9", true, &format!("{:.2}", homa.score), "> 2.9")],
                CertaintyLevel::High,
            ));
        }
    }

    // ── Metabolic Syndrome (partial) ────────────────────────────────────
    if let Some(mets) = find_score(scores, "MetS Blood Score") {
        if mets.score >= 3.0 {
            matches.push(condition(
                "Metabolic Syndrome (blood markers)",
                vec![criterion("≥3 blood criteria met", true, &format!("{:.0}/3", mets.score), "≥ 3")],
                CertaintyLevel::High,
            ));
        } else if mets.score >= 2.0 {
            matches.push(condition(
                "Metabolic Syndrome Risk",
                vec![criterion("2 of 3 blood criteria met", true, &format!("{:.0}/3", mets.score), "≥ 3 for diagnosis")],
                CertaintyLevel::Moderate,
            ));
        }
    }

    // ── Prediabetes ─────────────────────────────────────────────────────
    if let Some(hba1c) = m.val("hba1c") {
        if (5.7..6.5).contains(&hba1c) {
            matches.push(condition(
                "Prediabetes",
                vec![criterion("HbA1c 5.7–6.4%", true, &format!("{:.1}%", hba1c), "5.7–6.4%")],
                CertaintyLevel::High,
            ));
        } else if hba1c >= 6.5 {
            matches.push(condition(
                "Diabetes Range HbA1c",
                vec![criterion("HbA1c ≥ 6.5%", true, &format!("{:.1}%", hba1c), "≥ 6.5%")],
                CertaintyLevel::High,
            ));
        }
    }

    // ── Accelerated Biological Aging ────────────────────────────────────
    if let Some(pa) = find_score(scores, "PhenoAge") {
        if let Some(age) = profile.age {
            let accel = pa.score - age as f64;
            if accel > 5.0 {
                matches.push(condition(
                    "Accelerated Biological Aging",
                    vec![criterion(
                        "PhenoAge acceleration > 5 years",
                        true,
                        &format!("{:+.1} years", accel),
                        "> +5 years",
                    )],
                    CertaintyLevel::Moderate,
                ));
            }
        }
    }

    // ── Subclinical Hypothyroidism ──────────────────────────────────────
    if let (Some(tsh), Some(ft4_marker)) = (m.val("tsh"), m.get("free t4")) {
        let ft4 = ft4_marker.value;
        let ft4_normal = ft4 >= 10.0 && ft4 <= 23.0;
        if tsh > 4.0 && ft4_normal {
            matches.push(condition(
                "Subclinical Hypothyroidism",
                vec![
                    criterion("TSH elevated", true, &format!("{:.2} mIU/L", tsh), "> 4.0"),
                    criterion("FT4 normal", true, &format!("{:.1} pmol/L", ft4), "10–23"),
                ],
                CertaintyLevel::Moderate,
            ));
        }
    }

    // ── Iron Deficiency ─────────────────────────────────────────────────
    {
        let ferritin_low = m.val("ferritin").map(|v| v < 24.0).unwrap_or(false);
        let iron_low = m.val("iron").map(|v| v < 9.0).unwrap_or(false);
        let tsat_low = m.val("iron saturation").map(|v| v < 20.0).unwrap_or(false);

        let criteria_met = [ferritin_low, iron_low, tsat_low].iter().filter(|&&x| x).count();
        if criteria_met >= 2 {
            let mut criteria = Vec::new();
            if let Some(v) = m.val("ferritin") {
                criteria.push(criterion("Ferritin low", ferritin_low, &format!("{:.0} µg/L", v), "< 24"));
            }
            if let Some(v) = m.val("iron") {
                criteria.push(criterion("Iron low", iron_low, &format!("{:.1} µmol/L", v), "< 9"));
            }
            if let Some(v) = m.val("iron saturation") {
                criteria.push(criterion("TSAT low", tsat_low, &format!("{:.0}%", v), "< 20%"));
            }
            matches.push(condition("Iron Deficiency", criteria, CertaintyLevel::High));
        }
    }

    // ── Hyperandrogenism (females) ──────────────────────────────────────
    let is_female = profile.sex.as_deref().map(|s| s.to_lowercase())
        .map(|s| s == "female" || s == "f")
        .unwrap_or(false);
    if is_female {
        if let Some(fai) = find_score(scores, "Free Androgen Index") {
            if fai.score > 5.0 {
                matches.push(condition(
                    "Hyperandrogenism",
                    vec![criterion("FAI > 5 (female)", true, &format!("{:.1}", fai.score), "> 5.0")],
                    CertaintyLevel::Moderate,
                ));
            }
        }
    }

    // ── Vitamin D Deficiency ────────────────────────────────────────────
    if let Some(vd) = m.val("vitamin d") {
        if vd < 30.0 {
            matches.push(condition(
                "Vitamin D Deficiency",
                vec![criterion("25-OH Vitamin D < 30 nmol/L", true, &format!("{:.0} nmol/L", vd), "< 30")],
                CertaintyLevel::High,
            ));
        } else if vd < 50.0 {
            matches.push(condition(
                "Vitamin D Insufficiency",
                vec![criterion("25-OH Vitamin D 30–50 nmol/L", true, &format!("{:.0} nmol/L", vd), "< 50")],
                CertaintyLevel::High,
            ));
        }
    }

    // ── Liver Fibrosis Risk ─────────────────────────────────────────────
    if let Some(fib4) = find_score(scores, "FIB-4 Index") {
        if fib4.score > 2.67 {
            matches.push(condition(
                "Advanced Liver Fibrosis Risk",
                vec![criterion("FIB-4 > 2.67", true, &format!("{:.2}", fib4.score), "> 2.67")],
                CertaintyLevel::Moderate,
            ));
        }
    }

    matches
}

// ── Helpers ─────────────────────────────────────────────────────────────

fn find_score<'a>(scores: &'a [DomainScore], system: &str) -> Option<&'a DomainScore> {
    scores.iter().find(|s| s.system == system)
}

fn criterion(name: &str, met: bool, observed: &str, expected: &str) -> CriterionResult {
    CriterionResult {
        criterion: name.into(),
        met,
        observed: Some(observed.into()),
        expected: expected.into(),
    }
}

fn condition(name: &str, criteria: Vec<CriterionResult>, grade: CertaintyLevel) -> ConditionMatch {
    let met_count = criteria.iter().filter(|c| c.met).count();
    let total = criteria.len();
    ConditionMatch {
        condition: name.into(),
        criteria,
        certainty: CertaintyGrade {
            grade,
            confidence: met_count as f64 / total.max(1) as f64,
            missing_data: vec![],
            incompleteness_impact: String::new(),
        },
    }
}

/// Categorise marker by name when the category field is absent.
fn categorise_marker(name: &str) -> String {
    let lower = name.to_lowercase();
    if lower.contains("haemoglobin") || lower.contains("hemoglobin") || lower.contains("rbc")
        || lower.contains("wbc") || lower.contains("platelet") || lower.contains("mcv")
        || lower.contains("mch") || lower.contains("hematocrit") || lower.contains("rdw")
    {
        "CBC".into()
    } else if lower.contains("iron") || lower.contains("ferritin") || lower.contains("transferrin") {
        "Iron Studies".into()
    } else if lower.contains("cholesterol") || lower.contains("triglyceride")
        || lower.contains("hdl") || lower.contains("ldl")
    {
        "Lipids".into()
    } else if lower.contains("glucose") || lower.contains("hba1c") || lower.contains("insulin") {
        "Metabolic".into()
    } else if lower.contains("tsh") || lower.contains("t3") || lower.contains("t4") {
        "Thyroid".into()
    } else if lower.contains("alt") || lower.contains("ast") || lower.contains("ggt")
        || lower.contains("bilirubin") || lower.contains("albumin") || lower.contains("alkaline")
    {
        "Liver Function".into()
    } else if lower.contains("creatinine") || lower.contains("urea") || lower.contains("egfr")
        || lower.contains("sodium") || lower.contains("potassium")
    {
        "Electrolytes/Renal".into()
    } else if lower.contains("vitamin") || lower.contains("folate") || lower.contains("b12") {
        "Vitamins".into()
    } else if lower.contains("testosterone") || lower.contains("shbg") || lower.contains("dhea") {
        "Androgens".into()
    } else if lower.contains("fsh") || lower.contains("lh") || lower.contains("oestradiol")
        || lower.contains("progesterone") || lower.contains("prolactin")
    {
        "Pituitary/Gonadal".into()
    } else if lower.contains("crp") || lower.contains("homocysteine") {
        "Inflammation".into()
    } else {
        "Other".into()
    }
}

/// Estimate which common markers are missing from the dataset.
fn estimate_missing_data(data: &BloodworkData) -> Vec<String> {
    let common_markers = [
        "Haemoglobin", "White Blood Cells", "Platelets", "Ferritin",
        "Iron", "Glucose", "HbA1c", "Cholesterol", "TSH",
        "Creatinine", "ALT", "Vitamin D", "Vitamin B12",
    ];

    let present: Vec<String> = data.markers.iter().map(|m| m.name.to_lowercase()).collect();

    common_markers
        .iter()
        .filter(|&&name| !present.iter().any(|p| p.contains(&name.to_lowercase())))
        .map(|&name| name.to_string())
        .collect()
}
