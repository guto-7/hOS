use std::fs;
use std::process::Command;

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
// Imaging commands (delegate to Python scripts)
// ---------------------------------------------------------------------------

/// Run imaging Stage 1 (Importing) — validate, store, extract metadata.
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
        .map_err(|e| format!("Failed to run imaging pipeline: {e}"))?;

    let _ = fs::remove_file(&image_path);

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(format!("Imaging pipeline failed: {stderr}"));
    }

    Ok(String::from_utf8_lossy(&output.stdout).to_string())
}

/// Run full imaging pipeline (Stage 1 + Stage 2 + model inference).
#[tauri::command]
pub async fn process_image(
    file_name: String,
    file_bytes: Vec<u8>,
    model: String,
) -> Result<String, String> {
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
        .arg("--model")
        .arg(&model)
        .output()
        .map_err(|e| format!("Failed to run imaging pipeline: {e}"))?;

    let _ = fs::remove_file(&image_path);

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(format!("Imaging pipeline failed: {stderr}"));
    }

    let json_output = String::from_utf8_lossy(&output.stdout).to_string();

    if let Ok(parsed) = serde_json::from_str::<serde_json::Value>(&json_output) {
        if let Some(hash) = parsed
            .get("record")
            .and_then(|r| r.get("file_hash"))
            .and_then(|h| h.as_str())
        {
            let results_dir = data.join("results").join("imaging");
            let _ = fs::create_dir_all(&results_dir);
            let result_path = results_dir.join(format!("{hash}.json"));
            let _ = fs::write(&result_path, &json_output);
        }
    }

    Ok(json_output)
}

/// Run Stage 3: Claude API interpretation on a saved imaging result.
#[tauri::command]
pub async fn interpret_image(file_hash: String) -> Result<String, String> {
    let data = util::data_dir()?;
    let result_path = data
        .join("results")
        .join("imaging")
        .join(format!("{file_hash}.json"));

    if !result_path.exists() {
        return Err(format!("No saved result for hash {file_hash}"));
    }

    let script = util::find_script("run_interpret.py")?;
    let python = util::find_venv_python(&script)?;

    let output = Command::new(&python)
        .arg(&script)
        .arg("--result-path")
        .arg(result_path.to_str().unwrap())
        .arg("--json-stdout")
        .output()
        .map_err(|e| format!("Failed to run interpretation: {e}"))?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(format!("Interpretation failed: {stderr}"));
    }

    let json_output = String::from_utf8_lossy(&output.stdout).to_string();

    if let Ok(interp) = serde_json::from_str::<serde_json::Value>(&json_output) {
        if interp
            .get("success")
            .and_then(|s| s.as_bool())
            .unwrap_or(false)
        {
            if let Some(interpretation) = interp.get("interpretation") {
                let saved = data
                    .join("results")
                    .join("imaging")
                    .join(format!("{file_hash}.json"));
                if let Ok(content) = fs::read_to_string(&saved) {
                    if let Ok(mut parsed) =
                        serde_json::from_str::<serde_json::Value>(&content)
                    {
                        if let Some(obj) = parsed.as_object_mut() {
                            obj.insert(
                                "interpretation".to_string(),
                                interpretation.clone(),
                            );
                        }
                        let _ = fs::write(
                            &saved,
                            serde_json::to_string(&parsed).unwrap_or_default(),
                        );
                    }
                }
            }
        }
    }

    Ok(json_output)
}

/// List all saved imaging results (metadata only).
#[tauri::command]
pub async fn list_imaging_results() -> Result<String, String> {
    let data = util::data_dir()?;
    let results_dir = data.join("results").join("imaging");

    if !results_dir.exists() {
        return Ok("[]".to_string());
    }

    let mut records: Vec<serde_json::Value> = Vec::new();

    let entries = fs::read_dir(&results_dir).map_err(|e| e.to_string())?;
    for entry in entries.flatten() {
        let path = entry.path();
        if path.extension().map_or(false, |ext| ext == "json") {
            if let Ok(content) = fs::read_to_string(&path) {
                if let Ok(parsed) = serde_json::from_str::<serde_json::Value>(&content) {
                    let record = parsed
                        .get("record")
                        .cloned()
                        .unwrap_or(serde_json::Value::Null);
                    let summary = parsed
                        .get("summary")
                        .cloned()
                        .unwrap_or(serde_json::Value::Null);
                    let meta = parsed
                        .get("image_metadata")
                        .cloned()
                        .unwrap_or(serde_json::Value::Null);
                    records.push(serde_json::json!({
                        "file_hash": record.get("file_hash"),
                        "original_name": record.get("original_name"),
                        "width": meta.get("width"),
                        "height": meta.get("height"),
                        "format": meta.get("format"),
                        "flagged_count": summary.get("flagged_count"),
                        "total_screened": summary.get("total_pathologies_screened"),
                    }));
                }
            }
        }
    }

    serde_json::to_string(&records).map_err(|e| e.to_string())
}

/// Load a specific saved imaging result by file hash.
#[tauri::command]
pub async fn load_imaging_result(file_hash: String) -> Result<String, String> {
    let data = util::data_dir()?;
    let result_path = data
        .join("results")
        .join("imaging")
        .join(format!("{file_hash}.json"));

    if !result_path.exists() {
        return Err(format!("No saved result for hash {file_hash}"));
    }

    fs::read_to_string(&result_path).map_err(|e| format!("Failed to read result: {e}"))
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
