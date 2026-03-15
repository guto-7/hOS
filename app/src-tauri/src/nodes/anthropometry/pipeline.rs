use crate::pipeline::error::PipelineError;
use crate::pipeline::types::{ContractMetadata, EvaluationOutput, OutputContract, RawData};

use super::unify::AnthropometryData;

/// Assemble the output contract for a anthropometry pipeline run.
pub fn build_output(
    raw: &RawData,
    data: &AnthropometryData,
    evaluation: &EvaluationOutput,
) -> Result<OutputContract, PipelineError> {
    let unified_data = serde_json::to_value(data)
        .map_err(|e| PipelineError::Pipeline(format!("Failed to serialize unified data: {e}")))?;

    Ok(OutputContract {
        node_id: "anthropometry".to_string(),
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
    let duration = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default();
    let secs = duration.as_secs();
    format!("{secs}")
}

fn build_processing_notes(data: &AnthropometryData) -> Vec<String> {
    let mut notes = Vec::new();
    notes.push(format!("{} markers parsed", data.markers.len()));
    if let Some(ref device) = data.device {
        notes.push(format!("Device: {device}"));
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
