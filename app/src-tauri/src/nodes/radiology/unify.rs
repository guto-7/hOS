use serde::{Deserialize, Serialize};

use crate::pipeline::error::PipelineError;
use crate::pipeline::types::{RawData, ValidationResult, ValidationStatus};

// ---------------------------------------------------------------------------
// Typed structs matching the Python radiology pipeline output
// ---------------------------------------------------------------------------

/// Unified radiology data produced by the Unify layer.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RadiologyData {
    pub findings: Vec<RadiologyFinding>,
    pub image_metadata: ImageMetadata,
    pub summary: RadiologySummary,
    pub model: String,
    pub model_key: String,
    pub heatmap: Option<String>,
    pub heatmap_pathology: Option<String>,
    pub body_part_detection: Option<BodyPartDetection>,
    pub stored_path: Option<String>,
    pub interpretation: Option<String>,
    pub validation: ValidationResult,
    pub quality: QualityInfo,
    pub standardisation: Option<serde_json::Value>,
}

/// A single model finding (pathology detection).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RadiologyFinding {
    pub pathology: String,
    pub probability: f64,
    pub level: String,
    pub body_part: Option<String>,
    pub bbox: Option<BoundingBox>,
    pub size: Option<FindingSize>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BoundingBox {
    pub x1: f64,
    pub y1: f64,
    pub x2: f64,
    pub y2: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FindingSize {
    pub width_px: f64,
    pub height_px: f64,
    pub area_px: f64,
    pub area_pct: f64,
    pub width_mm: Option<f64>,
    pub height_mm: Option<f64>,
    pub pixel_spacing_mm: Option<f64>,
}

/// Image technical metadata.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ImageMetadata {
    pub width: u32,
    pub height: u32,
    pub channels: u32,
    pub bit_depth: u32,
    pub format: String,
    pub file_size_kb: f64,
    pub is_grayscale: bool,
    pub has_exif: Option<bool>,
    pub orientation: Option<u32>,
    pub warnings: Vec<String>,
}

/// Body part auto-detection result.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BodyPartDetection {
    pub body_part: String,
    pub confidence: f64,
    pub description: String,
    pub recommended_model: Option<String>,
}

/// Summary statistics from the analysis.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RadiologySummary {
    pub total_pathologies_screened: u32,
    pub flagged_count: u32,
    pub high_probability: Vec<String>,
    pub moderate_probability: Vec<String>,
}

/// Quality warnings from import validation.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct QualityInfo {
    pub warnings: Vec<String>,
    pub warning_count: u32,
}

// ---------------------------------------------------------------------------
// Unify function
// ---------------------------------------------------------------------------

pub fn unify(raw: &RawData) -> Result<RadiologyData, PipelineError> {
    let c = &raw.content;

    let findings = parse_findings(c);
    let image_metadata = parse_image_metadata(c)?;
    let summary = parse_summary(c);
    let quality = parse_quality(c);

    let model = c
        .get("model")
        .and_then(|v| v.as_str())
        .unwrap_or("unknown")
        .to_string();

    let model_key = c
        .get("model_key")
        .and_then(|v| v.as_str())
        .unwrap_or("unknown")
        .to_string();

    let heatmap = c.get("heatmap").and_then(|v| v.as_str()).map(String::from);
    let heatmap_pathology = c
        .get("heatmap_pathology")
        .and_then(|v| v.as_str())
        .map(String::from);

    let body_part_detection = c
        .get("body_part_detection")
        .and_then(|v| serde_json::from_value::<BodyPartDetection>(v.clone()).ok());

    let stored_path = c
        .get("record")
        .and_then(|r| r.get("stored_path"))
        .and_then(|v| v.as_str())
        .map(String::from);

    let interpretation = c
        .get("interpretation")
        .and_then(|v| v.as_str())
        .map(String::from);

    let standardisation = c.get("standardisation").cloned();

    let validation = if findings.is_empty() {
        ValidationResult {
            status: ValidationStatus::Warning("No findings from model inference".to_string()),
            field_issues: vec![],
        }
    } else {
        ValidationResult {
            status: ValidationStatus::Valid,
            field_issues: vec![],
        }
    };

    Ok(RadiologyData {
        findings,
        image_metadata,
        summary,
        model,
        model_key,
        heatmap,
        heatmap_pathology,
        body_part_detection,
        stored_path,
        interpretation,
        validation,
        quality,
        standardisation,
    })
}

// ---------------------------------------------------------------------------
// Parsing helpers
// ---------------------------------------------------------------------------

fn parse_findings(content: &serde_json::Value) -> Vec<RadiologyFinding> {
    let arr = match content.get("findings").and_then(|f| f.as_array()) {
        Some(a) => a,
        None => return vec![],
    };

    arr.iter()
        .filter_map(|f| {
            let pathology = f.get("pathology")?.as_str()?.to_string();
            let probability = f.get("probability")?.as_f64()?;
            let level = f
                .get("level")
                .and_then(|l| l.as_str())
                .unwrap_or("MINIMAL")
                .to_string();
            let body_part = f
                .get("body_part")
                .and_then(|b| b.as_str())
                .map(String::from);

            let bbox = f
                .get("bbox")
                .and_then(|b| serde_json::from_value::<BoundingBox>(b.clone()).ok());

            let size = f
                .get("size")
                .and_then(|s| serde_json::from_value::<FindingSize>(s.clone()).ok());

            Some(RadiologyFinding {
                pathology,
                probability,
                level,
                body_part,
                bbox,
                size,
            })
        })
        .collect()
}

fn parse_image_metadata(content: &serde_json::Value) -> Result<ImageMetadata, PipelineError> {
    let meta = content.get("image_metadata").ok_or_else(|| {
        PipelineError::Unify("Missing image_metadata in pipeline output".to_string())
    })?;

    Ok(ImageMetadata {
        width: meta
            .get("width")
            .and_then(|v| v.as_u64())
            .unwrap_or(0) as u32,
        height: meta
            .get("height")
            .and_then(|v| v.as_u64())
            .unwrap_or(0) as u32,
        channels: meta
            .get("channels")
            .and_then(|v| v.as_u64())
            .unwrap_or(0) as u32,
        bit_depth: meta
            .get("bit_depth")
            .and_then(|v| v.as_u64())
            .unwrap_or(0) as u32,
        format: meta
            .get("format")
            .and_then(|v| v.as_str())
            .unwrap_or("unknown")
            .to_string(),
        file_size_kb: meta
            .get("file_size_kb")
            .and_then(|v| v.as_f64())
            .unwrap_or(0.0),
        is_grayscale: meta
            .get("is_grayscale")
            .and_then(|v| v.as_bool())
            .unwrap_or(false),
        has_exif: meta.get("has_exif").and_then(|v| v.as_bool()),
        orientation: meta
            .get("orientation")
            .and_then(|v| v.as_u64())
            .map(|v| v as u32),
        warnings: meta
            .get("warnings")
            .and_then(|v| v.as_array())
            .map(|arr| {
                arr.iter()
                    .filter_map(|s| s.as_str().map(String::from))
                    .collect()
            })
            .unwrap_or_default(),
    })
}

fn parse_summary(content: &serde_json::Value) -> RadiologySummary {
    let s = match content.get("summary") {
        Some(v) => v,
        None => {
            return RadiologySummary {
                total_pathologies_screened: 0,
                flagged_count: 0,
                high_probability: vec![],
                moderate_probability: vec![],
            }
        }
    };

    RadiologySummary {
        total_pathologies_screened: s
            .get("total_pathologies_screened")
            .and_then(|v| v.as_u64())
            .unwrap_or(0) as u32,
        flagged_count: s
            .get("flagged_count")
            .and_then(|v| v.as_u64())
            .unwrap_or(0) as u32,
        high_probability: s
            .get("high_probability")
            .and_then(|v| v.as_array())
            .map(|arr| {
                arr.iter()
                    .filter_map(|s| s.as_str().map(String::from))
                    .collect()
            })
            .unwrap_or_default(),
        moderate_probability: s
            .get("moderate_probability")
            .and_then(|v| v.as_array())
            .map(|arr| {
                arr.iter()
                    .filter_map(|s| s.as_str().map(String::from))
                    .collect()
            })
            .unwrap_or_default(),
    }
}

fn parse_quality(content: &serde_json::Value) -> QualityInfo {
    let q = match content.get("quality") {
        Some(v) => v,
        None => {
            return QualityInfo {
                warnings: vec![],
                warning_count: 0,
            }
        }
    };

    let warnings: Vec<String> = q
        .get("warnings")
        .and_then(|v| v.as_array())
        .map(|arr| {
            arr.iter()
                .filter_map(|s| s.as_str().map(String::from))
                .collect()
        })
        .unwrap_or_default();

    let warning_count = q
        .get("warning_count")
        .and_then(|v| v.as_u64())
        .unwrap_or(warnings.len() as u64) as u32;

    QualityInfo {
        warnings,
        warning_count,
    }
}
