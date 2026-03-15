use std::collections::HashMap;

use crate::pipeline::error::PipelineError;
use crate::pipeline::types::{
    CertaintyGrade, CertaintyLevel, ConditionMatch, CriterionResult, DomainScore,
    EvaluationOutput,
};

use super::unify::RadiologyData;

/// Evaluate radiology findings: severity assessment, certainty grading,
/// condition detection, and radiology burden scoring.
pub fn evaluate(data: &RadiologyData) -> Result<EvaluationOutput, PipelineError> {
    let critical_flags = surface_critical_flags(data);
    let categories = group_by_body_part(data);
    let domain_scores = compute_domain_scores(data);
    let condition_matches = detect_conditions(data);
    let certainty = compute_certainty(data);

    let mut engine_versions = HashMap::new();
    engine_versions.insert("radiology_model".to_string(), data.model_key.clone());
    engine_versions.insert("radiology_evaluator".to_string(), "1.0.0".to_string());

    Ok(EvaluationOutput {
        critical_flags,
        categories,
        domain_scores,
        condition_matches,
        certainty,
        engine_versions,
    })
}

// ---------------------------------------------------------------------------
// Critical flags
// ---------------------------------------------------------------------------

fn surface_critical_flags(data: &RadiologyData) -> Vec<String> {
    data.findings
        .iter()
        .filter(|f| f.level == "HIGH")
        .map(|f| {
            format!(
                "HIGH: {} ({:.0}% probability)",
                f.pathology,
                f.probability * 100.0
            )
        })
        .collect()
}

// ---------------------------------------------------------------------------
// Categories — group findings by body part
// ---------------------------------------------------------------------------

fn group_by_body_part(data: &RadiologyData) -> HashMap<String, Vec<String>> {
    let mut categories: HashMap<String, Vec<String>> = HashMap::new();
    for f in &data.findings {
        let region = f.body_part.clone().unwrap_or_else(|| "General".to_string());
        categories
            .entry(region)
            .or_default()
            .push(format!("{} ({})", f.pathology, f.level));
    }
    categories
}

// ---------------------------------------------------------------------------
// Domain scores — Radiology Burden Index
// ---------------------------------------------------------------------------

fn compute_domain_scores(data: &RadiologyData) -> Vec<DomainScore> {
    if data.findings.is_empty() {
        return vec![DomainScore {
            domain: "Radiology".to_string(),
            system: "Radiology Burden Index".to_string(),
            score: 100.0,
            interpretation: "No pathologies detected".to_string(),
            components: vec![],
            version: "1.0.0".to_string(),
        }];
    }

    // Weighted burden: HIGH=3, MODERATE=2, LOW=1, MINIMAL=0
    let mut burden: f64 = 0.0;
    let mut components: Vec<String> = Vec::new();

    for f in &data.findings {
        let weight = match f.level.as_str() {
            "HIGH" => 3.0,
            "MODERATE" => 2.0,
            "LOW" => 1.0,
            _ => 0.0,
        };
        if weight > 0.0 {
            burden += weight;
            components.push(f.pathology.clone());
        }
    }

    // Normalise to 0-100 health scale (100 = best, 0 = worst)
    // Max realistic burden: 5 HIGH findings = 15
    let max_burden = 15.0;
    let score = ((1.0 - (burden / max_burden).min(1.0)) * 100.0).round();

    let interpretation = if score >= 90.0 {
        "Minimal radiology burden".to_string()
    } else if score >= 70.0 {
        "Low radiology burden".to_string()
    } else if score >= 50.0 {
        "Moderate radiology burden".to_string()
    } else {
        "Significant radiology burden".to_string()
    };

    vec![DomainScore {
        domain: "Radiology".to_string(),
        system: "Radiology Burden Index".to_string(),
        score,
        interpretation,
        components,
        version: "1.0.0".to_string(),
    }]
}

// ---------------------------------------------------------------------------
// Condition matching
// ---------------------------------------------------------------------------

fn detect_conditions(data: &RadiologyData) -> Vec<ConditionMatch> {
    let mut conditions = Vec::new();

    // Pneumonia detected at HIGH
    let pneumonia_findings: Vec<&_> = data
        .findings
        .iter()
        .filter(|f| {
            f.level == "HIGH"
                && (f.pathology.to_lowercase().contains("pneumonia")
                    || f.pathology.to_lowercase().contains("consolidation"))
        })
        .collect();

    if !pneumonia_findings.is_empty() {
        conditions.push(ConditionMatch {
            condition: "Pneumonia".to_string(),
            criteria: pneumonia_findings
                .iter()
                .map(|f| CriterionResult {
                    criterion: format!("{} probability", f.pathology),
                    met: true,
                    observed: Some(format!("{:.1}%", f.probability * 100.0)),
                    expected: "≥70%".to_string(),
                })
                .collect(),
            certainty: CertaintyGrade {
                grade: CertaintyLevel::High,
                confidence: pneumonia_findings[0].probability,
                missing_data: vec![],
                incompleteness_impact: "None".to_string(),
            },
        });
    }

    // Cardiomegaly at HIGH
    let cardio_findings: Vec<&_> = data
        .findings
        .iter()
        .filter(|f| f.level == "HIGH" && f.pathology.to_lowercase().contains("cardiomegaly"))
        .collect();

    if !cardio_findings.is_empty() {
        conditions.push(ConditionMatch {
            condition: "Cardiomegaly".to_string(),
            criteria: cardio_findings
                .iter()
                .map(|f| CriterionResult {
                    criterion: format!("{} probability", f.pathology),
                    met: true,
                    observed: Some(format!("{:.1}%", f.probability * 100.0)),
                    expected: "≥70%".to_string(),
                })
                .collect(),
            certainty: CertaintyGrade {
                grade: CertaintyLevel::High,
                confidence: cardio_findings[0].probability,
                missing_data: vec![],
                incompleteness_impact: "None".to_string(),
            },
        });
    }

    // Multiple fractures
    let fracture_findings: Vec<&_> = data
        .findings
        .iter()
        .filter(|f| {
            (f.level == "HIGH" || f.level == "MODERATE")
                && (f.pathology.to_lowercase().contains("fracture")
                    || f.pathology.to_lowercase().contains("bone anomaly"))
        })
        .collect();

    if fracture_findings.len() >= 2 {
        conditions.push(ConditionMatch {
            condition: "Multiple Fractures".to_string(),
            criteria: fracture_findings
                .iter()
                .map(|f| CriterionResult {
                    criterion: format!("{} detected", f.pathology),
                    met: true,
                    observed: Some(format!("{:.1}% in {}", f.probability * 100.0, f.body_part.as_deref().unwrap_or("unspecified"))),
                    expected: "≥2 fracture findings".to_string(),
                })
                .collect(),
            certainty: CertaintyGrade {
                grade: CertaintyLevel::Moderate,
                confidence: fracture_findings.iter().map(|f| f.probability).sum::<f64>()
                    / fracture_findings.len() as f64,
                missing_data: vec![],
                incompleteness_impact: "None".to_string(),
            },
        });
    }

    // Pleural effusion
    let effusion_findings: Vec<&_> = data
        .findings
        .iter()
        .filter(|f| {
            f.level == "HIGH"
                && (f.pathology.to_lowercase().contains("effusion")
                    || f.pathology.to_lowercase().contains("pleural"))
        })
        .collect();

    if !effusion_findings.is_empty() {
        conditions.push(ConditionMatch {
            condition: "Pleural Effusion".to_string(),
            criteria: effusion_findings
                .iter()
                .map(|f| CriterionResult {
                    criterion: format!("{} probability", f.pathology),
                    met: true,
                    observed: Some(format!("{:.1}%", f.probability * 100.0)),
                    expected: "≥70%".to_string(),
                })
                .collect(),
            certainty: CertaintyGrade {
                grade: CertaintyLevel::High,
                confidence: effusion_findings[0].probability,
                missing_data: vec![],
                incompleteness_impact: "None".to_string(),
            },
        });
    }

    conditions
}

// ---------------------------------------------------------------------------
// Certainty grading
// ---------------------------------------------------------------------------

fn compute_certainty(data: &RadiologyData) -> CertaintyGrade {
    if data.findings.is_empty() {
        return CertaintyGrade {
            grade: CertaintyLevel::Insufficient,
            confidence: 0.0,
            missing_data: vec!["No model findings produced".to_string()],
            incompleteness_impact: "Unable to assess — no findings to evaluate".to_string(),
        };
    }

    let quality_warnings = &data.quality.warnings;
    let has_quality_issues = !quality_warnings.is_empty();

    let avg_confidence = data.findings.iter().map(|f| f.probability).sum::<f64>()
        / data.findings.len() as f64;

    if has_quality_issues && avg_confidence < 0.3 {
        CertaintyGrade {
            grade: CertaintyLevel::Low,
            confidence: avg_confidence,
            missing_data: quality_warnings.clone(),
            incompleteness_impact: "Image quality issues may affect model accuracy".to_string(),
        }
    } else if has_quality_issues {
        CertaintyGrade {
            grade: CertaintyLevel::Moderate,
            confidence: avg_confidence,
            missing_data: quality_warnings.clone(),
            incompleteness_impact: "Minor quality warnings present".to_string(),
        }
    } else {
        CertaintyGrade {
            grade: CertaintyLevel::High,
            confidence: avg_confidence,
            missing_data: vec![],
            incompleteness_impact: "None".to_string(),
        }
    }
}
