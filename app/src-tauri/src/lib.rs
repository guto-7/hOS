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
            commands::run_bloodwork,
            commands::list_bloodwork,
            commands::load_bloodwork,
            commands::run_orchestrator,
            commands::extract_image,
            commands::process_image,
            commands::interpret_image,
            commands::list_imaging_results,
            commands::load_imaging_result,
            commands::run_body_composition,
            commands::list_body_composition,
            commands::load_body_composition,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
