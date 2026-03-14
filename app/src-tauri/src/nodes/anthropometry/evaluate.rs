use std::collections::HashMap;

use crate::pipeline::error::PipelineError;
use crate::pipeline::types::{
    CertaintyGrade, CertaintyLevel, EvaluationOutput, FlagClassification,
};

use super::unify::BodyCompositionData;

/// Evaluate unified body composition data: surface critical flags, group by category,
/// grade certainty.
///
/// Stub implementation — returns structure derived from the unified data
/// without real clinical scoring.
pub fn evaluate(data: &BodyCompositionData) -> Result<EvaluationOutput, PipelineError> {
    let critical_flags: Vec<String> = data
        .markers
        .iter()
        .filter(|m| matches!(m.deviation.flag, FlagClassification::Critical))
        .map(|m| format!("{}: {} {}", m.name, m.value, m.unit))
        .collect();

    let mut categories: HashMap<String, Vec<String>> = HashMap::new();
    for marker in &data.markers {
        let category = categorise_marker(&marker.name);
        categories
            .entry(category)
            .or_default()
            .push(marker.name.clone());
    }

    let expected_markers = [
        "Weight",
        "Skeletal Muscle Mass",
        "Body Fat Mass",
        "Body Mass Index",
        "Body Fat Percentage",
        "Visceral Fat Level",
        "Basal Metabolic Rate",
        "Fat Free Mass",
        "Water Percentage",
        "Protein Percentage",
        "Bone Mass",
        "Ideal Weight",
    ];

    let present: Vec<String> = data
        .markers
        .iter()
        .map(|m| m.name.to_lowercase())
        .collect();

    let missing_data: Vec<String> = expected_markers
        .iter()
        .filter(|&&name| !present.iter().any(|p| p.contains(&name.to_lowercase())))
        .map(|&name| name.to_string())
        .collect();

    let certainty = CertaintyGrade {
        grade: if data.markers.is_empty() {
            CertaintyLevel::Insufficient
        } else if missing_data.len() > 4 {
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
    engine_versions.insert(
        "body_composition_evaluator".to_string(),
        "0.1.0-stub".to_string(),
    );

    Ok(EvaluationOutput {
        critical_flags,
        categories,
        domain_scores: vec![],
        condition_matches: vec![],
        certainty,
        engine_versions,
    })
}

fn categorise_marker(name: &str) -> String {
    let lower = name.to_lowercase();
    if lower.contains("bmi") || lower.contains("body mass index") || lower.contains("body fat percentage") {
        "Obesity Analysis".to_string()
    } else if lower.contains("visceral") {
        "Visceral Health".to_string()
    } else if lower.contains("basal") || lower.contains("metabolic") {
        "Metabolism".to_string()
    } else {
        "Body Composition".to_string()
    }
}
