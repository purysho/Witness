mod commands;
mod engine;
mod security;

fn main() {
    tauri::Builder::default()
        .manage(engine::EngineState::new())
        .invoke_handler(tauri::generate_handler![commands::engine_call])
        .run(tauri::generate_context!())
        .expect("error while running Witness desktop");
}
