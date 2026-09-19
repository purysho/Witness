mod commands;
mod engine;
mod security;

use tauri::{Manager, RunEvent};

fn main() {
    let app = tauri::Builder::default()
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
        .build(tauri::generate_context!())
        .expect("error while building Witness desktop");

    app.run(|app_handle, event| {
        if matches!(event, RunEvent::Exit) {
            app_handle.state::<engine::EngineState>().shutdown();
        }
    });
}
