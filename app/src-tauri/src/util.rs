use std::fs;
use std::path::PathBuf;

/// Return the local data directory: ~/Documents/hOS/
pub fn data_dir() -> Result<PathBuf, String> {
    let home = dirs::home_dir().ok_or("Cannot determine home directory")?;
    let dir = home.join("Documents").join("hOS");
    fs::create_dir_all(&dir).map_err(|e| format!("Failed to create data dir: {e}"))?;
    Ok(dir)
}

/// Find the best python3 binary: .venv first, then conda, then system.
pub fn find_venv_python(script: &PathBuf) -> Result<PathBuf, String> {
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

/// Locate a script in the data/ directory by name.
pub fn find_script(name: &str) -> Result<PathBuf, String> {
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
