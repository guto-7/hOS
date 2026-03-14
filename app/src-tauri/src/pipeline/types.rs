use serde::{Deserialize, Serialize};
use std::collections::HashMap;

// ---------------------------------------------------------------------------
// Core primitives
// ---------------------------------------------------------------------------

/// ISO-8601 date string (e.g. "2026-03-14"). Kept as String to avoid
/// forcing a chrono dependency at the type level — parsing happens at
/// the boundary where dates are ingested.
pub type CollectionDate = String;

/// Unique identifier for a node (e.g. "bloodwork", "radiology").
pub type NodeId = String;

// ---------------------------------------------------------------------------
// Import layer outputs
// ---------------------------------------------------------------------------

/// Raw data produced by the Import layer before any parsing or normalisation.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RawData {
    /// Where this data came from (file path, API endpoint, etc.).
    pub source: String,
    /// Original file name if applicable.
    pub original_name: Option<String>,
    /// SHA-256 hash of the source file for deduplication.
    pub file_hash: Option<String>,
    /// When the sample/scan/measurement was collected (not when it was imported).
    pub collection_date: Option<CollectionDate>,
    /// The raw extracted content — structure depends on the node.
    /// Bloodwork: extracted text. Imaging: metadata + pixel path. Etc.
    pub content: serde_json::Value,
}

// ---------------------------------------------------------------------------
// Unify layer types
// ---------------------------------------------------------------------------

/// Outcome of validating a single data point during unification.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum ValidationStatus {
    /// Data point passed all validation checks.
    Valid,
    /// Data point has issues that need user resolution.
    NeedsResolution(String),
    /// Data point is plausible but flagged for review.
    Warning(String),
}

/// Result of validating the entire unified dataset.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ValidationResult {
    pub status: ValidationStatus,
    /// Per-field validation details.
    pub field_issues: Vec<FieldIssue>,
}

/// A specific validation issue on a specific field.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FieldIssue {
    pub field: String,
    pub issue: String,
    pub status: ValidationStatus,
}

/// Initial flag applied during unification — individual data point
/// against its reference range. Not diagnostic, just annotation.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum FlagClassification {
    Normal,
    Low,
    High,
    Critical,
    Info,
}

/// Quantified deviation from reference range.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DeviationMetric {
    /// The data point's value.
    pub value: f64,
    /// Lower bound of reference range.
    pub reference_low: Option<f64>,
    /// Upper bound of reference range.
    pub reference_high: Option<f64>,
    /// Unit after standardisation.
    pub unit: String,
    pub flag: FlagClassification,
    /// How far outside the range, as a fraction of range width.
    /// None if within range or range is undefined.
    pub deviation_fraction: Option<f64>,
}

// ---------------------------------------------------------------------------
// Evaluate layer types
// ---------------------------------------------------------------------------

/// A composite score from a validated clinical scoring system.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DomainScore {
    /// Name of the scoring system (e.g. "MELD", "Framingham").
    pub system: String,
    /// The computed score value.
    pub score: f64,
    /// What the score means in clinical terms.
    pub interpretation: String,
    /// Which data points contributed to this score.
    pub components: Vec<String>,
    /// Version of the scoring system used.
    pub version: String,
}

/// A condition identified by multi-variable pattern matching.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ConditionMatch {
    /// Condition name (e.g. "Iron Deficiency Anaemia").
    pub condition: String,
    /// The clinical criteria used for matching.
    pub criteria: Vec<CriterionResult>,
    /// Overall match strength.
    pub certainty: CertaintyGrade,
}

/// Result of checking a single criterion within a condition.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CriterionResult {
    pub criterion: String,
    pub met: bool,
    /// The actual value that was checked.
    pub observed: Option<String>,
    /// What the criterion expected.
    pub expected: String,
}

/// Graded certainty that accounts for data completeness and significance.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CertaintyGrade {
    /// Qualitative grade.
    pub grade: CertaintyLevel,
    /// 0.0–1.0 confidence based on available data.
    pub confidence: f64,
    /// Data points that were expected but missing.
    pub missing_data: Vec<String>,
    /// How much the missing data affects the grade.
    pub incompleteness_impact: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum CertaintyLevel {
    High,
    Moderate,
    Low,
    Insufficient,
}

/// Full output of the Evaluate layer.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EvaluationOutput {
    /// Critical flags surfaced for immediate attention.
    pub critical_flags: Vec<String>,
    /// Data grouped into domain-specific categories.
    pub categories: HashMap<String, Vec<String>>,
    /// Composite scores from validated scoring systems.
    pub domain_scores: Vec<DomainScore>,
    /// Conditions matched by multi-variable pattern recognition.
    pub condition_matches: Vec<ConditionMatch>,
    /// Overall certainty accounting for data completeness.
    pub certainty: CertaintyGrade,
    /// Model/engine version info for reproducibility.
    pub engine_versions: HashMap<String, String>,
}

// ---------------------------------------------------------------------------
// Output contract
// ---------------------------------------------------------------------------

/// The comprehensive output contract that a node produces.
/// This is the Orchestrator's only data source from each node.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OutputContract {
    /// Which node produced this contract.
    pub node_id: NodeId,
    /// Version of the contract schema.
    pub schema_version: String,
    /// When this contract was produced.
    pub produced_at: String,
    /// Collection date of the underlying data.
    pub collection_date: Option<CollectionDate>,

    /// The unified data — node-specific but serialized for the Orchestrator.
    pub unified_data: serde_json::Value,
    /// Full evaluation output — deterministic, reproducible.
    pub evaluation: EvaluationOutput,

    /// Metadata for audit trail.
    pub metadata: ContractMetadata,
}

/// Metadata attached to every output contract for auditability.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ContractMetadata {
    /// Hash of source data for traceability.
    pub source_hash: Option<String>,
    /// Original file name.
    pub original_name: Option<String>,
    /// Versions of all engines/models used in evaluation.
    pub engine_versions: HashMap<String, String>,
    /// Any warnings or notes about the processing.
    pub processing_notes: Vec<String>,
}
