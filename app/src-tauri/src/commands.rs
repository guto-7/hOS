use crate::nodes::bloodwork::import::BloodworkInput;
use crate::nodes::bloodwork::BloodworkNode;
use crate::orchestrator::{OrchestratorInput, OrchestratorNode};
use crate::pipeline::storage::{FsNodeStorage, NodeStorage};
use crate::pipeline::types::OutputContract;
use crate::pipeline::{self, Node};
use crate::util;

// ---------------------------------------------------------------------------
// Bloodwork commands
// ---------------------------------------------------------------------------

/// Run the full bloodwork pipeline on an uploaded PDF.
#[tauri::command]
pub async fn run_bloodwork(
    file_name: String,
    file_bytes: Vec<u8>,
    sex: Option<String>,
    age: Option<u32>,
    pregnant: Option<bool>,
    cycle_phase: Option<String>,
    fasting: Option<bool>,
) -> Result<String, String> {
    let node = BloodworkNode;
    let input = BloodworkInput {
        file_name,
        file_bytes,
        sex,
        age,
        pregnant,
        cycle_phase,
        fasting,
    };

    let contract = pipeline::run_pipeline(&node, input).map_err(|e| e.to_string())?;

    // Store the contract
    let base_dir = util::data_dir()?;
    let storage =
        FsNodeStorage::new(&base_dir, node.node_id()).map_err(|e| e.to_string())?;
    storage.store_contract(&contract).map_err(|e| e.to_string())?;

    serde_json::to_string(&contract).map_err(|e| e.to_string())
}

/// List all stored bloodwork results (metadata only).
#[tauri::command]
pub async fn list_bloodwork() -> Result<String, String> {
    let base_dir = util::data_dir()?;
    let storage = FsNodeStorage::new(&base_dir, "bloodwork").map_err(|e| e.to_string())?;

    let hashes = storage.list_contracts().map_err(|e| e.to_string())?;

    let mut summaries: Vec<serde_json::Value> = Vec::new();
    for hash in &hashes {
        if let Ok(contract) = storage.load_contract(hash) {
            summaries.push(serde_json::json!({
                "source_hash": contract.metadata.source_hash,
                "original_name": contract.metadata.original_name,
                "collection_date": contract.collection_date,
                "node_id": contract.node_id,
                "schema_version": contract.schema_version,
                "critical_flags_count": contract.evaluation.critical_flags.len(),
                "certainty_grade": format!("{:?}", contract.evaluation.certainty.grade),
            }));
        }
    }

    serde_json::to_string(&summaries).map_err(|e| e.to_string())
}

/// Load a specific bloodwork result by source hash.
#[tauri::command]
pub async fn load_bloodwork(source_hash: String) -> Result<String, String> {
    let base_dir = util::data_dir()?;
    let storage = FsNodeStorage::new(&base_dir, "bloodwork").map_err(|e| e.to_string())?;

    let contract = storage
        .load_contract(&source_hash)
        .map_err(|e| e.to_string())?;

    serde_json::to_string(&contract).map_err(|e| e.to_string())
}

// ---------------------------------------------------------------------------
// Orchestrator commands
// ---------------------------------------------------------------------------

/// Run the orchestrator across all available node results.
#[tauri::command]
pub async fn run_orchestrator() -> Result<String, String> {
    let base_dir = util::data_dir()?;

    // Collect the latest contract from each node that has results
    let mut contracts: Vec<OutputContract> = Vec::new();

    let node_ids = ["bloodwork", "radiology", "anthropometry"];
    for node_id in &node_ids {
        let storage = match FsNodeStorage::new(&base_dir, node_id) {
            Ok(s) => s,
            Err(_) => continue,
        };
        let hashes = match storage.list_contracts() {
            Ok(h) => h,
            Err(_) => continue,
        };
        // Load the most recent contract (last in the list)
        if let Some(hash) = hashes.last() {
            if let Ok(contract) = storage.load_contract(hash) {
                contracts.push(contract);
            }
        }
    }

    if contracts.is_empty() {
        return Err("No node results available for orchestration".to_string());
    }

    let orchestrator = OrchestratorNode;
    let input = OrchestratorInput { contracts };

    let contract =
        pipeline::run_pipeline(&orchestrator, input).map_err(|e| e.to_string())?;

    serde_json::to_string(&contract).map_err(|e| e.to_string())
}
