use std::fs;
use std::path::PathBuf;
use std::process::Command;

/// Return the local data directory: ~/Documents/hOS/
fn data_dir() -> Result<PathBuf, String> {
    let home = dirs::home_dir().ok_or("Cannot determine home directory")?;
    let dir = home.join("Documents").join("hOS");
    fs::create_dir_all(&dir).map_err(|e| format!("Failed to create data dir: {e}"))?;
    Ok(dir)
}

/// Save uploaded PDF to temp, then run the modular bloodwork pipeline
/// (run_bloodwork.py) which handles SHA-256 storage, text extraction,
/// parsing, alias resolution, and confidence scoring.
#[tauri::command]
async fn process_pdf(file_name: String, file_bytes: Vec<u8>) -> Result<String, String> {
    let data = data_dir()?;

    // Save PDF to temp — run_bloodwork.py handles SHA-256 storage
    let tmp_dir = data.join("tmp");
    fs::create_dir_all(&tmp_dir).map_err(|e| format!("Failed to create tmp dir: {e}"))?;
    let pdf_path = tmp_dir.join(&file_name);
    fs::write(&pdf_path, &file_bytes).map_err(|e| format!("Failed to save PDF: {e}"))?;

    let script = find_script("run_bloodwork.py")?;
    let python = find_venv_python(&script)?;

    let output = Command::new(&python)
        .arg(&script)
        .arg(pdf_path.to_str().unwrap())
        .arg("--output-dir")
        .arg(data.to_str().unwrap())
        .arg("--json-stdout")
        .output()
        .map_err(|e| format!("Failed to run pipeline: {e}"))?;

    // Clean up temp file
    let _ = fs::remove_file(&pdf_path);

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(format!("Pipeline failed: {stderr}"));
    }

    let json_output = String::from_utf8_lossy(&output.stdout).to_string();

    // Save result to results/bloodwork/{hash}.json for history
    if let Ok(parsed) = serde_json::from_str::<serde_json::Value>(&json_output) {
        if let Some(hash) = parsed.get("record").and_then(|r| r.get("file_hash")).and_then(|h| h.as_str()) {
            let results_dir = data.join("results").join("bloodwork");
            let _ = fs::create_dir_all(&results_dir);
            let result_path = results_dir.join(format!("{hash}.json"));
            let _ = fs::write(&result_path, &json_output);
        }
    }

    Ok(json_output)
}

/// Run Stage 1 (Importing) only — returns extracted markers for user confirmation.
#[tauri::command]
async fn extract_pdf(file_name: String, file_bytes: Vec<u8>) -> Result<String, String> {
    let data = data_dir()?;

    let tmp_dir = data.join("tmp");
    fs::create_dir_all(&tmp_dir).map_err(|e| format!("Failed to create tmp dir: {e}"))?;
    let pdf_path = tmp_dir.join(&file_name);
    fs::write(&pdf_path, &file_bytes).map_err(|e| format!("Failed to save PDF: {e}"))?;

    let script = find_script("run_bloodwork.py")?;
    let python = find_venv_python(&script)?;

    let output = Command::new(&python)
        .arg(&script)
        .arg(pdf_path.to_str().unwrap())
        .arg("--output-dir")
        .arg(data.to_str().unwrap())
        .arg("--json-stdout")
        .arg("--stage1-only")
        .output()
        .map_err(|e| format!("Failed to run pipeline: {e}"))?;

    let _ = fs::remove_file(&pdf_path);

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(format!("Pipeline failed: {stderr}"));
    }

    let json_output = String::from_utf8_lossy(&output.stdout).to_string();
    Ok(json_output)
}

/// Run imaging Stage 1 (Importing) only — validate, store, extract metadata for confirmation.
#[tauri::command]
async fn extract_image(file_name: String, file_bytes: Vec<u8>) -> Result<String, String> {
    let data = data_dir()?;

    let tmp_dir = data.join("tmp");
    fs::create_dir_all(&tmp_dir).map_err(|e| format!("Failed to create tmp dir: {e}"))?;
    let image_path = tmp_dir.join(&file_name);
    fs::write(&image_path, &file_bytes).map_err(|e| format!("Failed to save image: {e}"))?;

    let script = find_script("run_imaging.py")?;
    let python = find_venv_python(&script)?;

    let output = Command::new(&python)
        .arg(&script)
        .arg(image_path.to_str().unwrap())
        .arg("--output-dir")
        .arg(data.to_str().unwrap())
        .arg("--json-stdout")
        .arg("--stage1-only")
        .output()
        .map_err(|e| format!("Failed to run imaging pipeline: {e}"))?;

    let _ = fs::remove_file(&image_path);

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(format!("Imaging pipeline failed: {stderr}"));
    }

    let json_output = String::from_utf8_lossy(&output.stdout).to_string();
    Ok(json_output)
}

/// Run full imaging pipeline (Stage 1 + Stage 2 + model inference).
/// `model` selects which model adapter to use: "chest-xray" or "fracture".
#[tauri::command]
async fn process_image(file_name: String, file_bytes: Vec<u8>, model: String) -> Result<String, String> {
    let data = data_dir()?;

    let tmp_dir = data.join("tmp");
    fs::create_dir_all(&tmp_dir).map_err(|e| format!("Failed to create tmp dir: {e}"))?;
    let image_path = tmp_dir.join(&file_name);
    fs::write(&image_path, &file_bytes).map_err(|e| format!("Failed to save image: {e}"))?;

    let script = find_script("run_imaging.py")?;
    let python = find_venv_python(&script)?;

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

    // Save result to results/imaging/{hash}.json for history
    if let Ok(parsed) = serde_json::from_str::<serde_json::Value>(&json_output) {
        if let Some(hash) = parsed.get("record").and_then(|r| r.get("file_hash")).and_then(|h| h.as_str()) {
            let results_dir = data.join("results").join("imaging");
            let _ = fs::create_dir_all(&results_dir);
            let result_path = results_dir.join(format!("{hash}.json"));
            let _ = fs::write(&result_path, &json_output);
        }
    }

    Ok(json_output)
}

/// List all saved imaging results (metadata only).
#[tauri::command]
async fn list_imaging_results() -> Result<String, String> {
    let data = data_dir()?;
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
                    let record = parsed.get("record").cloned().unwrap_or(serde_json::Value::Null);
                    let summary = parsed.get("summary").cloned().unwrap_or(serde_json::Value::Null);
                    let meta = parsed.get("image_metadata").cloned().unwrap_or(serde_json::Value::Null);
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
async fn load_imaging_result(file_hash: String) -> Result<String, String> {
    let data = data_dir()?;
    let result_path = data.join("results").join("imaging").join(format!("{file_hash}.json"));

    if !result_path.exists() {
        return Err(format!("No saved result for hash {file_hash}"));
    }

    fs::read_to_string(&result_path).map_err(|e| format!("Failed to read result: {e}"))
}

/// List all saved bloodwork results (metadata only).
/// Returns JSON array of {file_hash, original_name, lab_provider, test_date, flagged, matched}.
#[tauri::command]
async fn list_bloodwork_results() -> Result<String, String> {
    let data = data_dir()?;
    let results_dir = data.join("results").join("bloodwork");

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
                    // Extract just the metadata we need for the list
                    let record = parsed.get("record").cloned().unwrap_or(serde_json::Value::Null);
                    let summary = parsed.get("summary").cloned().unwrap_or(serde_json::Value::Null);
                    records.push(serde_json::json!({
                        "file_hash": record.get("file_hash"),
                        "original_name": record.get("original_name"),
                        "lab_provider": record.get("lab_provider"),
                        "test_date": record.get("test_date"),
                        "matched": summary.get("matched"),
                        "flagged": summary.get("flagged"),
                    }));
                }
            }
        }
    }

    serde_json::to_string(&records).map_err(|e| e.to_string())
}

/// Load a specific saved bloodwork result by file hash.
#[tauri::command]
async fn load_bloodwork_result(file_hash: String) -> Result<String, String> {
    let data = data_dir()?;
    let result_path = data.join("results").join("bloodwork").join(format!("{file_hash}.json"));

    if !result_path.exists() {
        return Err(format!("No saved result for hash {file_hash}"));
    }

    fs::read_to_string(&result_path).map_err(|e| format!("Failed to read result: {e}"))
}

/// Find the best python3 binary: .venv first, then conda, then system.
fn find_venv_python(script: &PathBuf) -> Result<PathBuf, String> {
    // 1. Check for .venv in the script's directory
    if let Some(parent) = script.parent() {
        let venv_python = parent.join(".venv").join("bin").join("python3");
        if venv_python.exists() {
            return Ok(venv_python);
        }
    }
    // 2. Check common conda locations
    let conda_paths = [
        "/opt/anaconda3/bin/python3",
        "/opt/homebrew/anaconda3/bin/python3",
    ];
    for p in &conda_paths {
        let path = PathBuf::from(p);
        if path.exists() {
            return Ok(path);
        }
    }
    if let Ok(home) = std::env::var("HOME") {
        let user_conda = PathBuf::from(&home).join("anaconda3/bin/python3");
        if user_conda.exists() {
            return Ok(user_conda);
        }
        let user_miniconda = PathBuf::from(&home).join("miniconda3/bin/python3");
        if user_miniconda.exists() {
            return Ok(user_miniconda);
        }
    }
    // 3. Fallback to system python3
    Ok(PathBuf::from("python3"))
}

fn find_script(name: &str) -> Result<PathBuf, String> {
    let candidates = [
        std::env::current_exe()
            .ok()
            .and_then(|p| p.parent().map(|p| p.join("../../../data").join(name).to_path_buf())),
        // From app/src-tauri/ (tauri dev working directory)
        Some(PathBuf::from(format!("../../data/{name}"))),
        // From app/
        Some(PathBuf::from(format!("../data/{name}"))),
        // From repo root
        Some(PathBuf::from(format!("data/{name}"))),
        dirs::home_dir().map(|h| h.join("Data/hOS/data").join(name)),
    ];

    for candidate in candidates.iter().flatten() {
        if candidate.exists() {
            return Ok(candidate.canonicalize().map_err(|e| e.to_string())?);
        }
    }

    Err(format!("Cannot find {name}"))
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_fs::init())
        .invoke_handler(tauri::generate_handler![extract_pdf, process_pdf, list_bloodwork_results, load_bloodwork_result, extract_image, process_image, list_imaging_results, load_imaging_result])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
