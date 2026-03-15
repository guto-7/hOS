mod commands;
mod nodes;
mod orchestrator;
mod pipeline;
mod util;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_fs::init())
        .invoke_handler(tauri::generate_handler![
            commands::run_hepatology,
            commands::list_hepatology,
            commands::get_marker_catalog,
            commands::load_hepatology,
            commands::delete_hepatology,
            commands::run_orchestrator,
            commands::extract_image,
            commands::run_radiology,
            commands::interpret_image,
            commands::list_radiology,
            commands::load_radiology,
            commands::delete_radiology,
            commands::run_anthropometry,
            commands::list_anthropometry,
            commands::load_anthropometry,
            commands::delete_anthropometry,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
