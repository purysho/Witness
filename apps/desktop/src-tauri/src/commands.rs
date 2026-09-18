use serde_json::Value;
use tauri::State;
use crate::engine::EngineState;
use crate::security;

#[tauri::command]
pub fn engine_call(request: Value, state: State<'_, EngineState>) -> Result<Value,String> {
    security::validate_request(&request)?;
    state.call(&request)
}
