mod commands;
mod engine;
mod security;

use tauri::Manager;

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .setup(|app| {
            app.manage(engine::EngineState::new(app.handle().clone()));
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            commands::engine_call,
            commands::cancel_job
        ])
        .run(tauri::generate_context!())
        .expect("error while running Witness desktop");
}
