use std::collections::HashMap;

use crate::pipeline::error::PipelineError;
use crate::pipeline::types::{CertaintyGrade, CertaintyLevel, EvaluationOutput, FlagClassification};

use super::unify::BloodworkData;

/// Evaluate unified bloodwork data: surface critical flags, group by category,
/// compute domain scores, match conditions, grade certainty.
///
/// Stub implementation — returns structure derived from the unified data
/// without real clinical scoring or condition matching.
pub fn evaluate(data: &BloodworkData) -> Result<EvaluationOutput, PipelineError> {
    // Surface critical flags
    let critical_flags: Vec<String> = data
        .markers
        .iter()
        .filter(|m| matches!(m.deviation.flag, FlagClassification::Critical))
        .map(|m| format!("{}: {} {}", m.name, m.value, m.unit))
        .collect();

    // Group markers into basic categories (stub — real implementation
    // would use a clinical categorisation system)
    let mut categories: HashMap<String, Vec<String>> = HashMap::new();
    for marker in &data.markers {
        let category = categorise_marker(&marker.name);
        categories
            .entry(category)
            .or_default()
            .push(marker.name.clone());
    }

    // Count how much data we have vs. what a comprehensive panel would include
    let missing_data = estimate_missing_data(data);

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
        incompleteness_impact: "Stub evaluation — no real clinical scoring applied".to_string(),
    };

    let mut engine_versions = HashMap::new();
    engine_versions.insert("bloodwork_evaluator".to_string(), "0.1.0-stub".to_string());

    Ok(EvaluationOutput {
        critical_flags,
        categories,
        domain_scores: vec![],
        condition_matches: vec![],
        certainty,
        engine_versions,
    })
}

/// Basic marker categorisation. Stub — real implementation would use
/// a proper clinical taxonomy.
fn categorise_marker(name: &str) -> String {
    let lower = name.to_lowercase();
    if lower.contains("haemoglobin") || lower.contains("hemoglobin") || lower.contains("rbc")
        || lower.contains("wbc") || lower.contains("platelet") || lower.contains("mcv")
        || lower.contains("mch") || lower.contains("hematocrit")
    {
        "Haematology".to_string()
    } else if lower.contains("iron") || lower.contains("ferritin") || lower.contains("transferrin")
        || lower.contains("tibc")
    {
        "Iron Studies".to_string()
    } else if lower.contains("cholesterol") || lower.contains("triglyceride")
        || lower.contains("hdl") || lower.contains("ldl")
    {
        "Lipid Panel".to_string()
    } else if lower.contains("glucose") || lower.contains("hba1c") || lower.contains("insulin") {
        "Glucose Metabolism".to_string()
    } else if lower.contains("tsh") || lower.contains("t3") || lower.contains("t4")
        || lower.contains("thyroid")
    {
        "Thyroid Function".to_string()
    } else if lower.contains("alt") || lower.contains("ast") || lower.contains("ggt")
        || lower.contains("bilirubin") || lower.contains("albumin")
    {
        "Liver Function".to_string()
    } else if lower.contains("creatinine") || lower.contains("urea") || lower.contains("egfr") {
        "Renal Function".to_string()
    } else if lower.contains("vitamin") || lower.contains("folate") || lower.contains("b12") {
        "Vitamins".to_string()
    } else {
        "Other".to_string()
    }
}

/// Estimate which common markers are missing from the dataset.
/// Stub — real implementation would be configurable per panel type.
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
