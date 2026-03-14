use crate::pipeline::error::PipelineError;
use crate::pipeline::types::{ContractMetadata, EvaluationOutput, OutputContract, RawData};

use super::unify::BloodworkData;

/// Assemble the output contract for a bloodwork pipeline run.
pub fn build_output(
    raw: &RawData,
    data: &BloodworkData,
    evaluation: &EvaluationOutput,
) -> Result<OutputContract, PipelineError> {
    let unified_data = serde_json::to_value(data)
        .map_err(|e| PipelineError::Pipeline(format!("Failed to serialize unified data: {e}")))?;

    Ok(OutputContract {
        node_id: "bloodwork".to_string(),
        schema_version: "0.1.0".to_string(),
        produced_at: now_iso8601(),
        collection_date: raw.collection_date.clone(),
        unified_data,
        evaluation: evaluation.clone(),
        metadata: ContractMetadata {
            source_hash: raw.file_hash.clone(),
            original_name: raw.original_name.clone(),
            engine_versions: evaluation.engine_versions.clone(),
            processing_notes: build_processing_notes(data),
        },
    })
}

fn now_iso8601() -> String {
    // Simple UTC timestamp without pulling in chrono
    let duration = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default();
    let secs = duration.as_secs();
    // Rough ISO-8601: good enough for metadata, not for clinical dates
    format!("{secs}")
}

fn build_processing_notes(data: &BloodworkData) -> Vec<String> {
    let mut notes = Vec::new();
    notes.push(format!("{} markers parsed", data.markers.len()));
    if let Some(ref provider) = data.lab_provider {
        notes.push(format!("Lab provider: {provider}"));
    }
    match &data.validation.status {
        crate::pipeline::types::ValidationStatus::Valid => {}
        crate::pipeline::types::ValidationStatus::Warning(msg) => {
            notes.push(format!("Warning: {msg}"));
        }
        crate::pipeline::types::ValidationStatus::NeedsResolution(msg) => {
            notes.push(format!("Needs resolution: {msg}"));
        }
    }
    notes
}
