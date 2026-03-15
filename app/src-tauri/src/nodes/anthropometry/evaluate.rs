use std::collections::HashMap;

use crate::pipeline::error::PipelineError;
use crate::pipeline::types::{
    CertaintyGrade, CertaintyLevel, DomainScore, EvaluationOutput, FlagClassification,
};

use super::unify::BodyCompositionData;

/// Evaluate unified body composition data.
///
/// Uses the Python Stage 3 evaluation output embedded in `data.python_evaluation`
/// when available. Falls back to a stub grading when the Python evaluation is absent
/// (e.g. stage2-only runs or legacy data).
pub fn evaluate(data: &BodyCompositionData) -> Result<EvaluationOutput, PipelineError> {
    if let Some(ref py_eval) = data.python_evaluation {
        return evaluate_from_python(data, py_eval);
    }
    evaluate_stub(data)
}

// ---------------------------------------------------------------------------
// Python evaluation path
// ---------------------------------------------------------------------------

fn evaluate_from_python(
    data: &BodyCompositionData,
    py_eval: &serde_json::Value,
) -> Result<EvaluationOutput, PipelineError> {
    // Collect critical flags from markers
    let critical_flags: Vec<String> = data
        .markers
        .iter()
        .filter(|m| matches!(m.deviation.flag, FlagClassification::Critical))
        .map(|m| format!("{}: {} {}", m.name, m.value, m.unit))
        .collect();

    // Build domain scores from Python output
    let domain_scores = parse_domain_scores(py_eval);

    // Build categories from markers
    let mut categories: HashMap<String, Vec<String>> = HashMap::new();
    for marker in &data.markers {
        let category = marker
            .category
            .clone()
            .unwrap_or_else(|| "Uncategorised".to_string());
        categories
            .entry(category)
            .or_default()
            .push(marker.name.clone());
    }

    // Map phenotype + signals into condition_matches
    let mut condition_matches = vec![];
    if let Some(ph) = py_eval.get("phenotype").and_then(|p| p.as_object()) {
        let label = ph
            .get("label")
            .and_then(|l| l.as_str())
            .unwrap_or("Unknown")
            .to_string();
        let description = ph
            .get("description")
            .and_then(|d| d.as_str())
            .unwrap_or("")
            .to_string();
        let confidence_str = ph
            .get("confidence")
            .and_then(|c| c.as_str())
            .unwrap_or("low");
        let contributing: Vec<String> = ph
            .get("contributing_signals")
            .and_then(|cs| cs.as_array())
            .map(|arr| {
                arr.iter()
                    .filter_map(|s| s.as_str().map(String::from))
                    .collect()
            })
            .unwrap_or_default();

        let certainty = CertaintyGrade {
            grade: match confidence_str {
                "high" => CertaintyLevel::High,
                "moderate" => CertaintyLevel::Moderate,
                _ => CertaintyLevel::Low,
            },
            confidence: match confidence_str {
                "high" => 0.85,
                "moderate" => 0.65,
                _ => 0.4,
            },
            missing_data: vec![],
            incompleteness_impact: description,
        };

        condition_matches.push(crate::pipeline::types::ConditionMatch {
            condition: label,
            criteria: contributing
                .iter()
                .map(|s| crate::pipeline::types::CriterionResult {
                    criterion: s.clone(),
                    met: true,
                    observed: None,
                    expected: "Contributing marker".to_string(),
                })
                .collect(),
            certainty,
        });
    }

    // Add signals as additional condition entries
    if let Some(signals) = py_eval.get("signals").and_then(|s| s.as_array()) {
        for sig in signals {
            let label = sig
                .get("label")
                .and_then(|l| l.as_str())
                .unwrap_or("Signal")
                .to_string();
            let detail = sig
                .get("detail")
                .and_then(|d| d.as_str())
                .unwrap_or("")
                .to_string();
            let severity = sig
                .get("severity")
                .and_then(|s| s.as_str())
                .unwrap_or("info");
            let markers: Vec<String> = sig
                .get("markers")
                .and_then(|m| m.as_array())
                .map(|arr| {
                    arr.iter()
                        .filter_map(|s| s.as_str().map(String::from))
                        .collect()
                })
                .unwrap_or_default();

            let grade = match severity {
                "concern" => CertaintyLevel::High,
                "warning" => CertaintyLevel::Moderate,
                _ => CertaintyLevel::Low,
            };
            let confidence = match severity {
                "concern" => 0.8,
                "warning" => 0.6,
                _ => 0.4,
            };

            condition_matches.push(crate::pipeline::types::ConditionMatch {
                condition: format!("Signal: {label}"),
                criteria: markers
                    .iter()
                    .map(|m| crate::pipeline::types::CriterionResult {
                        criterion: m.clone(),
                        met: true,
                        observed: None,
                        expected: "Related marker".to_string(),
                    })
                    .collect(),
                certainty: CertaintyGrade {
                    grade,
                    confidence,
                    missing_data: vec![],
                    incompleteness_impact: detail,
                },
            });
        }
    }

    // Build overall certainty
    let certainty_grade_str = py_eval
        .get("certainty_grade")
        .and_then(|g| g.as_str())
        .unwrap_or("moderate");
    let certainty_note = py_eval
        .get("certainty_note")
        .and_then(|n| n.as_str())
        .unwrap_or("")
        .to_string();
    let missing: Vec<String> = py_eval
        .get("missing_for_full_eval")
        .and_then(|m| m.as_array())
        .map(|arr| {
            arr.iter()
                .filter_map(|s| s.as_str().map(String::from))
                .collect()
        })
        .unwrap_or_default();

    let (level, confidence) = match certainty_grade_str {
        "high" => (CertaintyLevel::High, 0.9),
        "moderate" => (CertaintyLevel::Moderate, 0.65),
        "low" => (CertaintyLevel::Low, 0.35),
        _ => (CertaintyLevel::Insufficient, 0.1),
    };

    let certainty = CertaintyGrade {
        grade: level,
        confidence,
        missing_data: missing,
        incompleteness_impact: certainty_note,
    };

    let mut engine_versions = HashMap::new();
    engine_versions.insert(
        "body_composition_evaluator".to_string(),
        "1.0.0".to_string(),
    );

    Ok(EvaluationOutput {
        critical_flags,
        categories,
        domain_scores,
        condition_matches,
        certainty,
        engine_versions,
    })
}

fn parse_domain_scores(py_eval: &serde_json::Value) -> Vec<DomainScore> {
    let arr = match py_eval.get("domain_scores").and_then(|d| d.as_array()) {
        Some(a) => a,
        None => return vec![],
    };

    arr.iter()
        .filter_map(|d| {
            let label = d.get("label")?.as_str()?.to_string();
            let score = d.get("score")?.as_f64()?;
            let grade = d
                .get("grade")
                .and_then(|g| g.as_str())
                .unwrap_or("borderline")
                .to_string();
            let components: Vec<String> = d
                .get("markers_used")
                .and_then(|m| m.as_array())
                .map(|arr| {
                    arr.iter()
                        .filter_map(|s| s.as_str().map(String::from))
                        .collect()
                })
                .unwrap_or_default();
            let notes: Vec<String> = d
                .get("notes")
                .and_then(|n| n.as_array())
                .map(|arr| {
                    arr.iter()
                        .filter_map(|s| s.as_str().map(String::from))
                        .collect()
                })
                .unwrap_or_default();

            let interpretation = if notes.is_empty() {
                grade.clone()
            } else {
                notes.join("; ")
            };

            Some(DomainScore {
                system: label,
                score,
                interpretation,
                components,
                version: "1.0.0".to_string(),
            })
        })
        .collect()
}

// ---------------------------------------------------------------------------
// Stub fallback
// ---------------------------------------------------------------------------

fn evaluate_stub(data: &BodyCompositionData) -> Result<EvaluationOutput, PipelineError> {
    let critical_flags: Vec<String> = data
        .markers
        .iter()
        .filter(|m| matches!(m.deviation.flag, FlagClassification::Critical))
        .map(|m| format!("{}: {} {}", m.name, m.value, m.unit))
        .collect();

    let mut categories: HashMap<String, Vec<String>> = HashMap::new();
    for marker in &data.markers {
        let category = marker
            .category
            .clone()
            .unwrap_or_else(|| "Body Composition".to_string());
        categories
            .entry(category)
            .or_default()
            .push(marker.name.clone());
    }

    let expected = [
        "Weight", "Skeletal Muscle Mass", "Body Fat Mass",
        "Body Mass Index", "Body Fat Percentage",
    ];
    let present: Vec<String> = data.markers.iter().map(|m| m.name.to_lowercase()).collect();
    let missing: Vec<String> = expected
        .iter()
        .filter(|&&n| !present.iter().any(|p| p.contains(&n.to_lowercase())))
        .map(|&n| n.to_string())
        .collect();

    let certainty = CertaintyGrade {
        grade: if data.markers.is_empty() {
            CertaintyLevel::Insufficient
        } else if missing.len() > 3 {
            CertaintyLevel::Low
        } else if missing.is_empty() {
            CertaintyLevel::High
        } else {
            CertaintyLevel::Moderate
        },
        confidence: if data.markers.is_empty() {
            0.0
        } else {
            let total = data.markers.len() + missing.len();
            data.markers.len() as f64 / total as f64
        },
        missing_data: missing,
        incompleteness_impact: "Stage 3 evaluation unavailable — run with height/age/sex for full scoring.".to_string(),
    };

    let mut engine_versions = HashMap::new();
    engine_versions.insert(
        "body_composition_evaluator".to_string(),
        "1.0.0-stub".to_string(),
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
