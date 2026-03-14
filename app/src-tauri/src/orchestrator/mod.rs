use std::collections::HashMap;

use serde::{Deserialize, Serialize};

use crate::pipeline::error::PipelineError;
use crate::pipeline::types::{
    CertaintyGrade, CertaintyLevel, ContractMetadata, EvaluationOutput, OutputContract, RawData,
};
use crate::pipeline::Node;

/// The Orchestrator's import input: output contracts from other nodes.
pub struct OrchestratorInput {
    pub contracts: Vec<OutputContract>,
}

/// Unified cross-diagnostic data assembled from all node contracts.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CrossDiagnosticData {
    /// Per-node unified data, keyed by node_id.
    pub node_data: HashMap<String, serde_json::Value>,
    /// Per-node evaluation outputs, keyed by node_id.
    pub node_evaluations: HashMap<String, EvaluationOutput>,
    /// Collection dates from each node for longitudinal context.
    pub collection_dates: HashMap<String, Option<String>>,
    /// Which nodes contributed to this dataset.
    pub contributing_nodes: Vec<String>,
}

pub struct OrchestratorNode;

impl Node for OrchestratorNode {
    type ImportInput = OrchestratorInput;
    type UnifiedData = CrossDiagnosticData;

    fn node_id(&self) -> &str {
        "orchestrator"
    }

    /// Import layer: ingest output contracts from all nodes.
    /// Validates contracts are well-formed and extracts their contents.
    fn import(&self, input: OrchestratorInput) -> Result<RawData, PipelineError> {
        if input.contracts.is_empty() {
            return Err(PipelineError::Import(
                "No node contracts provided to orchestrator".to_string(),
            ));
        }

        let content = serde_json::to_value(&input.contracts)
            .map_err(|e| PipelineError::Import(format!("Failed to serialize contracts: {e}")))?;

        Ok(RawData {
            source: "orchestrator".to_string(),
            original_name: None,
            file_hash: None,
            collection_date: None,
            content,
        })
    }

    /// Unify layer: merge all node contracts into a single cross-diagnostic dataset.
    fn unify(&self, raw: &RawData) -> Result<CrossDiagnosticData, PipelineError> {
        let contracts: Vec<OutputContract> = serde_json::from_value(raw.content.clone())
            .map_err(|e| PipelineError::Unify(format!("Failed to deserialize contracts: {e}")))?;

        let mut node_data = HashMap::new();
        let mut node_evaluations = HashMap::new();
        let mut collection_dates = HashMap::new();
        let mut contributing_nodes = Vec::new();

        for contract in &contracts {
            let id = contract.node_id.clone();
            node_data.insert(id.clone(), contract.unified_data.clone());
            node_evaluations.insert(id.clone(), contract.evaluation.clone());
            collection_dates.insert(id.clone(), contract.collection_date.clone());
            contributing_nodes.push(id);
        }

        Ok(CrossDiagnosticData {
            node_data,
            node_evaluations,
            collection_dates,
            contributing_nodes,
        })
    }

    /// Evaluate layer: cross-diagnostic analysis.
    /// Stub — this is where cross-node pattern matching, correlations,
    /// and multi-system condition mapping will live.
    fn evaluate(&self, data: &CrossDiagnosticData) -> Result<EvaluationOutput, PipelineError> {
        // Aggregate critical flags from all nodes
        let critical_flags: Vec<String> = data
            .node_evaluations
            .iter()
            .flat_map(|(node_id, eval)| {
                eval.critical_flags
                    .iter()
                    .map(move |flag| format!("[{node_id}] {flag}"))
            })
            .collect();

        // Aggregate categories across nodes
        let mut categories: HashMap<String, Vec<String>> = HashMap::new();
        for (node_id, eval) in &data.node_evaluations {
            for (cat, items) in &eval.categories {
                let key = format!("{node_id}/{cat}");
                categories.insert(key, items.clone());
            }
        }

        let mut engine_versions = HashMap::new();
        engine_versions.insert("orchestrator".to_string(), "0.1.0-stub".to_string());
        for (node_id, eval) in &data.node_evaluations {
            for (engine, version) in &eval.engine_versions {
                engine_versions.insert(format!("{node_id}/{engine}"), version.clone());
            }
        }

        Ok(EvaluationOutput {
            critical_flags,
            categories,
            domain_scores: vec![],
            condition_matches: vec![],
            certainty: CertaintyGrade {
                grade: if data.contributing_nodes.is_empty() {
                    CertaintyLevel::Insufficient
                } else if data.contributing_nodes.len() == 1 {
                    CertaintyLevel::Low
                } else {
                    CertaintyLevel::Moderate
                },
                confidence: 0.0,
                missing_data: vec![
                    "Cross-diagnostic analysis not yet implemented".to_string(),
                ],
                incompleteness_impact: "Stub — aggregation only, no cross-node inference"
                    .to_string(),
            },
            engine_versions,
        })
    }

    fn output(
        &self,
        _raw: &RawData,
        data: &CrossDiagnosticData,
        evaluation: &EvaluationOutput,
    ) -> Result<OutputContract, PipelineError> {
        let unified_data = serde_json::to_value(data)
            .map_err(|e| PipelineError::Pipeline(format!("Failed to serialize: {e}")))?;

        Ok(OutputContract {
            node_id: "orchestrator".to_string(),
            schema_version: "0.1.0".to_string(),
            produced_at: String::new(),
            collection_date: None,
            unified_data,
            evaluation: evaluation.clone(),
            metadata: ContractMetadata {
                source_hash: None,
                original_name: None,
                engine_versions: evaluation.engine_versions.clone(),
                processing_notes: vec![
                    format!("{} nodes contributed", data.contributing_nodes.len()),
                    format!("Nodes: {}", data.contributing_nodes.join(", ")),
                ],
            },
        })
    }
}
