use std::fs;
use std::process::Command;

use crate::nodes::anthropometry::import::AnthropometryInput;
use crate::nodes::anthropometry::AnthropometryNode;
use crate::nodes::hepatology::import::HepatologyInput;
use crate::nodes::hepatology::HepatologyNode;
use crate::nodes::radiology::import::RadiologyInput;
use crate::nodes::radiology::RadiologyNode;
use crate::orchestrator::{OrchestratorInput, OrchestratorNode};
use crate::pipeline::storage::{FsNodeStorage, NodeStorage};
use crate::pipeline::types::OutputContract;
use crate::pipeline::{self, Node};
use crate::util;

// ---------------------------------------------------------------------------
// Hepatology commands
// ---------------------------------------------------------------------------

/// Run the full hepatology pipeline on an uploaded PDF.
#[tauri::command]
pub async fn run_hepatology(
    file_name: String,
    file_bytes: Vec<u8>,
    sex: Option<String>,
    age: Option<u32>,
    pregnant: Option<bool>,
    cycle_phase: Option<String>,
    fasting: Option<bool>,
) -> Result<String, String> {
    let node = HepatologyNode;
    let input = HepatologyInput {
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

/// List all stored hepatology results (metadata only).
#[tauri::command]
pub async fn list_hepatology() -> Result<String, String> {
    let base_dir = util::data_dir()?;
    let storage = FsNodeStorage::new(&base_dir, "hepatology").map_err(|e| e.to_string())?;

    let hashes = storage.list_contracts().map_err(|e| e.to_string())?;

    let mut summaries: Vec<serde_json::Value> = Vec::new();
    for hash in &hashes {
        if let Ok(contract) = storage.load_contract(hash) {
            summaries.push(serde_json::json!({
                "source_hash": contract.metadata.source_hash,
                "original_name": contract.metadata.original_name,
                "collection_date": contract.collection_date,
                "produced_at": contract.produced_at,
                "node_id": contract.node_id,
                "schema_version": contract.schema_version,
                "critical_flags_count": contract.evaluation.critical_flags.len(),
                "certainty_grade": format!("{:?}", contract.evaluation.certainty.grade),
            }));
        }
    }

    serde_json::to_string(&summaries).map_err(|e| e.to_string())
}

/// Return the marker catalog (markers.json) for rendering empty marker shells.
#[tauri::command]
pub async fn get_marker_catalog() -> Result<String, String> {
    let path = util::find_script("markers.json")?;
    fs::read_to_string(&path).map_err(|e| format!("Failed to read markers.json: {e}"))
}

/// Load a specific hepatology result by source hash.
#[tauri::command]
pub async fn load_hepatology(source_hash: String) -> Result<String, String> {
    let base_dir = util::data_dir()?;
    let storage = FsNodeStorage::new(&base_dir, "hepatology").map_err(|e| e.to_string())?;

    let contract = storage
        .load_contract(&source_hash)
        .map_err(|e| e.to_string())?;

    serde_json::to_string(&contract).map_err(|e| e.to_string())
}

/// Delete a stored hepatology result by source hash.
#[tauri::command]
pub async fn delete_hepatology(source_hash: String) -> Result<(), String> {
    let base_dir = util::data_dir()?;
    let storage = FsNodeStorage::new(&base_dir, "hepatology").map_err(|e| e.to_string())?;
    storage
        .delete_contract(&source_hash)
        .map_err(|e| e.to_string())
}

// ---------------------------------------------------------------------------
// Radiology commands
// ---------------------------------------------------------------------------

/// Pre-pipeline: Stage 1 only — validate, store, extract metadata, detect body part.
/// This is NOT part of the Node trait pipeline. It gives the user a chance to
/// review metadata and select a model before committing to the full pipeline.
#[tauri::command]
pub async fn extract_image(file_name: String, file_bytes: Vec<u8>) -> Result<String, String> {
    let data = util::data_dir()?;

    let tmp_dir = data.join("tmp");
    fs::create_dir_all(&tmp_dir).map_err(|e| format!("Failed to create tmp dir: {e}"))?;
    let image_path = tmp_dir.join(&file_name);
    fs::write(&image_path, &file_bytes).map_err(|e| format!("Failed to save image: {e}"))?;

    let script = util::find_script("run_imaging.py")?;
    let python = util::find_venv_python(&script)?;

    let output = Command::new(&python)
        .arg(&script)
        .arg(image_path.to_str().unwrap())
        .arg("--output-dir")
        .arg(data.to_str().unwrap())
        .arg("--json-stdout")
        .arg("--stage1-only")
        .arg("--detect-body-part")
        .output()
        .map_err(|e| format!("Failed to run radiology pipeline: {e}"))?;

    let _ = fs::remove_file(&image_path);

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(format!("Radiology pipeline failed: {stderr}"));
    }

    Ok(String::from_utf8_lossy(&output.stdout).to_string())
}

/// Run the full radiology pipeline (import → unify → evaluate → output).
#[tauri::command]
pub async fn run_radiology(
    file_name: String,
    file_bytes: Vec<u8>,
    model: String,
) -> Result<String, String> {
    let node = RadiologyNode;
    let input = RadiologyInput {
        file_name,
        file_bytes,
        model,
    };

    let contract = pipeline::run_pipeline(&node, input).map_err(|e| e.to_string())?;

    let base_dir = util::data_dir()?;
    let storage =
        FsNodeStorage::new(&base_dir, node.node_id()).map_err(|e| e.to_string())?;
    storage.store_contract(&contract).map_err(|e| e.to_string())?;

    serde_json::to_string(&contract).map_err(|e| e.to_string())
}

/// Post-pipeline: Claude API interpretation. Loads the stored contract,
/// calls Python for interpretation, patches the contract, and re-stores.
#[tauri::command]
pub async fn interpret_image(source_hash: String) -> Result<String, String> {
    let base_dir = util::data_dir()?;
    let storage =
        FsNodeStorage::new(&base_dir, "radiology").map_err(|e| e.to_string())?;
    let mut contract = storage
        .load_contract(&source_hash)
        .map_err(|e| e.to_string())?;

    // Build a result-like JSON for run_interpret.py (it expects the raw Python output shape)
    let ud = &contract.unified_data;
    let temp_result = serde_json::json!({
        "record": { "stored_path": ud.get("stored_path").and_then(|v| v.as_str()).unwrap_or("") },
        "heatmap": ud.get("heatmap").cloned().unwrap_or(serde_json::Value::Null),
        "findings": ud.get("findings").cloned().unwrap_or(serde_json::json!([])),
        "summary": ud.get("summary").cloned().unwrap_or(serde_json::json!({})),
        "model_key": ud.get("model_key").cloned().unwrap_or(serde_json::json!("unknown")),
        "image_metadata": ud.get("image_metadata").cloned().unwrap_or(serde_json::json!({})),
    });

    let tmp_dir = base_dir.join("tmp");
    fs::create_dir_all(&tmp_dir).map_err(|e| format!("Failed to create tmp dir: {e}"))?;
    let tmp_path = tmp_dir.join(format!("{source_hash}_interpret.json"));
    fs::write(
        &tmp_path,
        serde_json::to_string(&temp_result).map_err(|e| e.to_string())?,
    )
    .map_err(|e| format!("Failed to write temp result: {e}"))?;

    let script = util::find_script("run_interpret.py")?;
    let python = util::find_venv_python(&script)?;

    let output = Command::new(&python)
        .arg(&script)
        .arg("--result-path")
        .arg(tmp_path.to_str().unwrap())
        .arg("--json-stdout")
        .output()
        .map_err(|e| format!("Failed to run interpretation: {e}"))?;

    let _ = fs::remove_file(&tmp_path);

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(format!("Interpretation failed: {stderr}"));
    }

    let json_output = String::from_utf8_lossy(&output.stdout).to_string();

    // Patch contract with interpretation and re-store
    if let Ok(interp) = serde_json::from_str::<serde_json::Value>(&json_output) {
        if interp
            .get("success")
            .and_then(|s| s.as_bool())
            .unwrap_or(false)
        {
            if let Some(interpretation) = interp.get("interpretation") {
                if let Some(obj) = contract.unified_data.as_object_mut() {
                    obj.insert("interpretation".to_string(), interpretation.clone());
                }
                let _ = storage.store_contract(&contract);
            }
        }
    }

    Ok(json_output)
}

/// List all stored radiology results (metadata only).
#[tauri::command]
pub async fn list_radiology() -> Result<String, String> {
    let base_dir = util::data_dir()?;
    let storage = FsNodeStorage::new(&base_dir, "radiology").map_err(|e| e.to_string())?;

    let hashes = storage.list_contracts().map_err(|e| e.to_string())?;

    let mut summaries: Vec<serde_json::Value> = Vec::new();
    for hash in &hashes {
        if let Ok(contract) = storage.load_contract(hash) {
            summaries.push(serde_json::json!({
                "source_hash": contract.metadata.source_hash,
                "original_name": contract.metadata.original_name,
                "collection_date": contract.collection_date,
                "node_id": contract.node_id,
                "critical_flags_count": contract.evaluation.critical_flags.len(),
                "certainty_grade": format!("{:?}", contract.evaluation.certainty.grade),
            }));
        }
    }

    serde_json::to_string(&summaries).map_err(|e| e.to_string())
}

/// Load a specific radiology result by source hash.
#[tauri::command]
pub async fn load_radiology(source_hash: String) -> Result<String, String> {
    let base_dir = util::data_dir()?;
    let storage = FsNodeStorage::new(&base_dir, "radiology").map_err(|e| e.to_string())?;

    let contract = storage
        .load_contract(&source_hash)
        .map_err(|e| e.to_string())?;

    serde_json::to_string(&contract).map_err(|e| e.to_string())
}

/// Delete a stored radiology result by source hash.
#[tauri::command]
pub async fn delete_radiology(source_hash: String) -> Result<(), String> {
    let base_dir = util::data_dir()?;
    let storage = FsNodeStorage::new(&base_dir, "radiology").map_err(|e| e.to_string())?;
    storage
        .delete_contract(&source_hash)
        .map_err(|e| e.to_string())
}

// ---------------------------------------------------------------------------
// Anthropometry commands
// ---------------------------------------------------------------------------

/// Run the full anthropometry pipeline on an uploaded BIA PDF.
#[tauri::command]
pub async fn run_anthropometry(
    file_name: String,
    file_bytes: Vec<u8>,
    sex: Option<String>,
    age: Option<u32>,
    height_cm: Option<f64>,
) -> Result<String, String> {
    let node = AnthropometryNode;
    let input = AnthropometryInput {
        file_name,
        file_bytes,
        sex,
        age,
        height_cm,
    };

    let contract = pipeline::run_pipeline(&node, input).map_err(|e| e.to_string())?;

    // Store the contract
    let base_dir = util::data_dir()?;
    let storage =
        FsNodeStorage::new(&base_dir, node.node_id()).map_err(|e| e.to_string())?;
    storage.store_contract(&contract).map_err(|e| e.to_string())?;

    serde_json::to_string(&contract).map_err(|e| e.to_string())
}

/// List all stored anthropometry results (metadata only).
#[tauri::command]
pub async fn list_anthropometry() -> Result<String, String> {
    let base_dir = util::data_dir()?;
    let storage =
        FsNodeStorage::new(&base_dir, "anthropometry").map_err(|e| e.to_string())?;

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

/// Load a specific anthropometry result by source hash.
#[tauri::command]
pub async fn load_anthropometry(source_hash: String) -> Result<String, String> {
    let base_dir = util::data_dir()?;
    let storage =
        FsNodeStorage::new(&base_dir, "anthropometry").map_err(|e| e.to_string())?;

    let contract = storage
        .load_contract(&source_hash)
        .map_err(|e| e.to_string())?;

    serde_json::to_string(&contract).map_err(|e| e.to_string())
}

/// Delete a stored anthropometry result by source hash.
#[tauri::command]
pub async fn delete_anthropometry(source_hash: String) -> Result<(), String> {
    let base_dir = util::data_dir()?;
    let storage =
        FsNodeStorage::new(&base_dir, "anthropometry").map_err(|e| e.to_string())?;
    storage
        .delete_contract(&source_hash)
        .map_err(|e| e.to_string())
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

    let node_ids = ["hepatology", "radiology", "anthropometry"];
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
