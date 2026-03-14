use std::collections::HashMap;

use serde::{Deserialize, Serialize};

use crate::pipeline::error::PipelineError;
use crate::pipeline::types::{
    CertaintyGrade, CertaintyLevel, ContractMetadata, EvaluationOutput, OutputContract, RawData,
};
use crate::pipeline::Node;

/// Input to the anthropometry Import layer — manual measurements.
pub struct AnthropometryInput {
    pub measurements: serde_json::Value,
}

/// Unified anthropometry data — stub.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AnthropometryData {
    pub measurements: serde_json::Value,
    pub collection_date: Option<String>,
}

pub struct AnthropometryNode;

impl Node for AnthropometryNode {
    type ImportInput = AnthropometryInput;
    type UnifiedData = AnthropometryData;

    fn node_id(&self) -> &str {
        "anthropometry"
    }

    fn import(&self, input: AnthropometryInput) -> Result<RawData, PipelineError> {
        Ok(RawData {
            source: "anthropometry-manual".to_string(),
            original_name: None,
            file_hash: None,
            collection_date: None,
            content: input.measurements,
        })
    }

    fn unify(&self, raw: &RawData) -> Result<AnthropometryData, PipelineError> {
        Ok(AnthropometryData {
            measurements: raw.content.clone(),
            collection_date: raw.collection_date.clone(),
        })
    }

    fn evaluate(&self, _data: &AnthropometryData) -> Result<EvaluationOutput, PipelineError> {
        let mut engine_versions = HashMap::new();
        engine_versions.insert(
            "anthropometry_evaluator".to_string(),
            "0.1.0-stub".to_string(),
        );

        Ok(EvaluationOutput {
            critical_flags: vec![],
            categories: HashMap::new(),
            domain_scores: vec![],
            condition_matches: vec![],
            certainty: CertaintyGrade {
                grade: CertaintyLevel::Insufficient,
                confidence: 0.0,
                missing_data: vec!["Anthropometry node not yet implemented".to_string()],
                incompleteness_impact: "Stub — no analysis performed".to_string(),
            },
            engine_versions,
        })
    }

    fn output(
        &self,
        raw: &RawData,
        data: &AnthropometryData,
        evaluation: &EvaluationOutput,
    ) -> Result<OutputContract, PipelineError> {
        let unified_data = serde_json::to_value(data)
            .map_err(|e| PipelineError::Pipeline(e.to_string()))?;

        Ok(OutputContract {
            node_id: "anthropometry".to_string(),
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
