use std::fs;
use std::process::Command;

use crate::pipeline::error::PipelineError;
use crate::pipeline::types::RawData;
use crate::util;

/// Input to the radiology Import layer: an image file plus the selected model.
pub struct RadiologyInput {
    pub file_name: String,
    pub file_bytes: Vec<u8>,
    pub model: String,
}

/// Import a radiology image: save to temp, call run_imaging.py for the full pipeline.
pub fn import(input: RadiologyInput) -> Result<RawData, PipelineError> {
    let data = util::data_dir().map_err(PipelineError::Import)?;

    // Save image to temp location
    let tmp_dir = data.join("tmp");
    fs::create_dir_all(&tmp_dir)
        .map_err(|e| PipelineError::Import(format!("Failed to create tmp dir: {e}")))?;
    let image_path = tmp_dir.join(&input.file_name);
    fs::write(&image_path, &input.file_bytes)
        .map_err(|e| PipelineError::Import(format!("Failed to save image: {e}")))?;

    // Call Python radiology pipeline (Stage 1 + 2 + model inference)
    let script = util::find_script("run_imaging.py").map_err(PipelineError::Import)?;
    let python = util::find_venv_python(&script).map_err(PipelineError::Import)?;

    let output = Command::new(&python)
        .arg(&script)
        .arg(image_path.to_str().unwrap_or_default())
        .arg("--output-dir")
        .arg(data.to_str().unwrap_or_default())
        .arg("--json-stdout")
        .arg("--model")
        .arg(&input.model)
        .output()
        .map_err(|e| {
            PipelineError::ExternalProcess(format!("Failed to run radiology pipeline: {e}"))
        })?;

    // Clean up temp file
    let _ = fs::remove_file(&image_path);

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(PipelineError::ExternalProcess(format!(
            "Radiology pipeline failed: {stderr}"
        )));
    }

    let json_str = String::from_utf8_lossy(&output.stdout).to_string();
    let content: serde_json::Value = serde_json::from_str(&json_str)
        .map_err(|e| PipelineError::Import(format!("Invalid JSON from radiology pipeline: {e}")))?;

    // Extract file hash from Python output
    let file_hash = content
        .get("record")
        .and_then(|r| r.get("file_hash"))
        .and_then(|h| h.as_str())
        .map(String::from);

    Ok(RawData {
        source: image_path.to_string_lossy().to_string(),
        original_name: Some(input.file_name),
        file_hash,
        collection_date: None,
        content,
    })
}
