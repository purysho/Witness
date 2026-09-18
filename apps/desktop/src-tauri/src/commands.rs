use serde_json::Value;
use std::fs;
use std::path::PathBuf;
use tauri::State;
use crate::engine::EngineState;
use crate::security;

#[tauri::command]
pub fn engine_call(request: Value, state: State<'_, EngineState>) -> Result<Value,String> {
    security::validate_request(&request)?;
    state.call(&request)
}


#[tauri::command]
pub fn cancel_job(workspace_path: String, job_id: String) -> Result<(), String> {
    let valid = !job_id.is_empty()
        && job_id.len() <= 128
        && job_id
            .chars()
            .all(|value| value.is_ascii_alphanumeric() || matches!(value, '.' | '_' | '-'));
    if !valid {
        return Err(
            "job_id must be 1-128 characters using letters, numbers, '.', '_' or '-'"
                .to_string(),
        );
    }

    let root = PathBuf::from(workspace_path)
        .canonicalize()
        .map_err(|error| format!("Could not resolve workspace path: {error}"))?;
    if !root.is_dir() {
        return Err("Workspace path is not a directory".to_string());
    }

    let cancel_dir = root.join(".witness").join("cancel");
    fs::create_dir_all(&cancel_dir)
        .map_err(|error| format!("Could not create cancellation directory: {error}"))?;
    let flag = cancel_dir.join(format!("{job_id}.cancel"));
    fs::write(&flag, b"cancel\n")
        .map_err(|error| format!("Could not request cancellation: {error}"))?;
    Ok(())
}
