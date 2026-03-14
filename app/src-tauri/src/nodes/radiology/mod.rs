use std::collections::HashMap;

use serde::{Deserialize, Serialize};

use crate::pipeline::error::PipelineError;
use crate::pipeline::types::{
    CertaintyGrade, CertaintyLevel, ContractMetadata, EvaluationOutput, OutputContract, RawData,
};
use crate::pipeline::Node;

/// Input to the radiology Import layer.
pub struct RadiologyInput {
    pub file_name: String,
    pub file_bytes: Vec<u8>,
    pub modality: String,
}

/// Unified radiology data — stub.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RadiologyData {
    pub modality: String,
    pub collection_date: Option<String>,
}

pub struct RadiologyNode;

impl Node for RadiologyNode {
    type ImportInput = RadiologyInput;
    type UnifiedData = RadiologyData;

    fn node_id(&self) -> &str {
        "radiology"
    }

    fn import(&self, input: RadiologyInput) -> Result<RawData, PipelineError> {
        Ok(RawData {
            source: "radiology-stub".to_string(),
            original_name: Some(input.file_name),
            file_hash: None,
            collection_date: None,
            content: serde_json::json!({"modality": input.modality, "status": "stub"}),
        })
    }

    fn unify(&self, raw: &RawData) -> Result<RadiologyData, PipelineError> {
        let modality = raw
            .content
            .get("modality")
            .and_then(|m| m.as_str())
            .unwrap_or("unknown")
            .to_string();

        Ok(RadiologyData {
            modality,
            collection_date: raw.collection_date.clone(),
        })
    }

    fn evaluate(&self, _data: &RadiologyData) -> Result<EvaluationOutput, PipelineError> {
        let mut engine_versions = HashMap::new();
        engine_versions.insert("radiology_evaluator".to_string(), "0.1.0-stub".to_string());

        Ok(EvaluationOutput {
            critical_flags: vec![],
            categories: HashMap::new(),
            domain_scores: vec![],
            condition_matches: vec![],
            certainty: CertaintyGrade {
                grade: CertaintyLevel::Insufficient,
                confidence: 0.0,
                missing_data: vec!["Radiology node not yet implemented".to_string()],
                incompleteness_impact: "Stub — no analysis performed".to_string(),
            },
            engine_versions,
        })
    }

    fn output(
        &self,
        raw: &RawData,
        data: &RadiologyData,
        evaluation: &EvaluationOutput,
    ) -> Result<OutputContract, PipelineError> {
        let unified_data = serde_json::to_value(data)
            .map_err(|e| PipelineError::Pipeline(e.to_string()))?;

        Ok(OutputContract {
            node_id: "radiology".to_string(),
            schema_version: "0.1.0".to_string(),
            produced_at: String::new(),
            collection_date: raw.collection_date.clone(),
            unified_data,
            evaluation: evaluation.clone(),
            metadata: ContractMetadata {
                source_hash: raw.file_hash.clone(),
                original_name: raw.original_name.clone(),
                engine_versions: evaluation.engine_versions.clone(),
                processing_notes: vec!["Stub implementation".to_string()],
            },
        })
    }
}
