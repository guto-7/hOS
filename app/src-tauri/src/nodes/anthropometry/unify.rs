use serde::{Deserialize, Serialize};

use crate::pipeline::error::PipelineError;
use crate::pipeline::types::{
    DeviationMetric, FlagClassification, RawData, ValidationResult, ValidationStatus,
};

/// Unified body composition data: parsed markers with standardised units and flags.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BodyCompositionData {
    /// All parsed markers from the BIA report.
    pub markers: Vec<BodyCompositionMarker>,
    /// Validation result for the overall dataset.
    pub validation: ValidationResult,
    /// BIA device if identified.
    pub device: Option<String>,
    /// Test date.
    pub collection_date: Option<String>,
    /// Stage 3 evaluation output from Python evaluator (if available).
    pub python_evaluation: Option<serde_json::Value>,
}

/// A single parsed body composition marker.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BodyCompositionMarker {
    /// Canonical marker name (e.g. "Body Mass Index").
    pub name: String,
    /// Original name as it appeared on the PDF.
    pub original_name: Option<String>,
    /// Marker category (e.g. "Obesity Analysis", "Muscularity").
    pub category: Option<String>,
    /// Standardised value (after unit conversion).
    pub value: f64,
    /// Standardised unit.
    pub unit: String,
    /// Original value before conversion.
    pub original_value: Option<f64>,
    /// Original unit before conversion.
    pub original_unit: Option<String>,
    /// Whether a unit conversion was applied.
    pub unit_converted: bool,
    /// Note about demographic adjustment (e.g. "Male, age 34 reference range").
    pub adjustment_note: Option<String>,
    /// Named tier the value falls into (e.g. "overfat", "elevated").
    pub canonical_tier: Option<String>,
    /// Whether this marker was computed from other parsed values (not read from PDF).
    pub is_derived: bool,
    /// Evaluation type: "direct", "derived_input", or "informational".
    pub evaluation_type: Option<String>,
    /// Deviation from reference range.
    pub deviation: DeviationMetric,
}

/// Unify raw body composition data by reading the enriched Stage 2 output from Python.
pub fn unify(raw: &RawData) -> Result<BodyCompositionData, PipelineError> {
    let device = raw
        .content
        .get("record")
        .and_then(|r| r.get("device"))
        .and_then(|d| d.as_str())
        .map(String::from);

    let collection_date = raw.collection_date.clone();

    let markers = parse_markers_from_content(&raw.content);

    // Carry through Stage 3 evaluation output from Python (may be absent for stage2-only runs).
    let python_evaluation = raw.content.get("evaluation").cloned();

    let validation = ValidationResult {
        status: if markers.is_empty() {
            ValidationStatus::Warning("No markers parsed from raw data".to_string())
        } else {
            ValidationStatus::Valid
        },
        field_issues: vec![],
    };

    Ok(BodyCompositionData {
        markers,
        validation,
        device,
        collection_date,
        python_evaluation,
    })
}

fn parse_markers_from_content(content: &serde_json::Value) -> Vec<BodyCompositionMarker> {
    let marker_array = match content.get("markers").and_then(|m| m.as_array()) {
        Some(arr) => arr,
        None => return Vec::new(),
    };

    let mut markers = Vec::with_capacity(marker_array.len());

    for item in marker_array {
        let name = item
            .get("marker_name")
            .and_then(|n| n.as_str())
            .unwrap_or("Unknown")
            .to_string();

        let original_name = item
            .get("pdf_name")
            .and_then(|n| n.as_str())
            .map(String::from);

        let category = item
            .get("category")
            .and_then(|c| c.as_str())
            .map(String::from);

        let std_value = item
            .get("std_value")
            .and_then(|v| v.as_f64())
            .unwrap_or(0.0);

        let std_unit = item
            .get("std_unit")
            .and_then(|u| u.as_str())
            .unwrap_or("")
            .to_string();

        let original_value = item.get("original_value").and_then(|v| v.as_f64());

        let original_unit = item
            .get("original_unit")
            .and_then(|u| u.as_str())
            .map(String::from);

        let unit_converted = item
            .get("unit_converted")
            .and_then(|v| v.as_bool())
            .unwrap_or(false);

        let adjustment_note = item
            .get("adjustment_note")
            .and_then(|n| n.as_str())
            .map(String::from);

        // canonical_tier: strip "TIER:" prefix if it appears in the flag field,
        // or read directly from the canonical_tier field if present.
        let raw_flag_str = item
            .get("flag")
            .and_then(|f| f.as_str())
            .unwrap_or("");

        let canonical_tier = if raw_flag_str.starts_with("TIER:") {
            Some(raw_flag_str[5..].to_string())
        } else {
            item.get("canonical_tier")
                .and_then(|t| t.as_str())
                .map(String::from)
        };

        let is_derived = item
            .get("is_derived")
            .and_then(|v| v.as_bool())
            .unwrap_or(false);

        let evaluation_type = item
            .get("evaluation_type")
            .and_then(|e| e.as_str())
            .map(String::from);

        let ref_low = item.get("canonical_ref_low").and_then(|v| v.as_f64());
        let ref_high = item.get("canonical_ref_high").and_then(|v| v.as_f64());

        let flag = map_python_flag(raw_flag_str);

        let deviation_pct = item.get("deviation_pct").and_then(|v| v.as_f64());
        let deviation_fraction = deviation_pct.map(|pct| pct / 100.0);

        markers.push(BodyCompositionMarker {
            name,
            original_name,
            category,
            value: std_value,
            unit: std_unit.clone(),
            original_value,
            original_unit,
            unit_converted,
            adjustment_note,
            canonical_tier,
            is_derived,
            evaluation_type,
            deviation: DeviationMetric {
                value: std_value,
                reference_low: ref_low,
                reference_high: ref_high,
                unit: std_unit,
                flag,
                deviation_fraction,
            },
        });
    }

    markers
}

fn map_python_flag(flag: &str) -> FlagClassification {
    match flag {
        "OPTIMAL" => FlagClassification::Normal,
        "LOW" => FlagClassification::Low,
        "HIGH" => FlagClassification::High,
        "INFO" => FlagClassification::Info,
        "CRITICAL_LOW" | "CRITICAL_HIGH" => FlagClassification::Critical,
        // TIER:* flags — tier name is stored in canonical_tier, flag is Normal
        f if f.starts_with("TIER:") => FlagClassification::Normal,
        // No range could be resolved
        "UNRESOLVED" => FlagClassification::Info,
        _ => FlagClassification::Normal,
    }
}
