use serde_json::Value;
use std::env;
use std::io::{BufRead, BufReader, Write};
use std::path::PathBuf;
use std::process::{Child, ChildStdin, ChildStdout, Command, Stdio};
use std::sync::Mutex;

pub struct EngineClient {
    child: Child,
    stdin: ChildStdin,
    stdout: BufReader<ChildStdout>,
}

impl EngineClient {
    pub fn spawn() -> Result<Self, String> {
        let python = env::var("WITNESS_PYTHON").unwrap_or_else(|_| {
            if cfg!(windows) { "python".to_string() } else { "python3".to_string() }
        });
        let engine_src = env::var_os("WITNESS_ENGINE_PYTHONPATH")
            .map(PathBuf::from)
            .unwrap_or_else(|| PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../../engine/src"));
        let mut python_paths = vec![engine_src];
        if let Some(existing) = env::var_os("PYTHONPATH") {
            python_paths.extend(env::split_paths(&existing));
        }
        let python_path = env::join_paths(python_paths)
            .map_err(|error| format!("Could not construct engine PYTHONPATH: {error}"))?;
        let mut child = Command::new(python)
            .args(["-m","witness_engine.rpc.server"])
            .env("PYTHONPATH", python_path)
            .stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::inherit())
            .spawn().map_err(|error| format!("Could not start Witness Python engine: {error}"))?;
        let stdin = child.stdin.take().ok_or_else(|| "Engine stdin was unavailable".to_string())?;
        let stdout = child.stdout.take().ok_or_else(|| "Engine stdout was unavailable".to_string())?;
        Ok(Self { child, stdin, stdout: BufReader::new(stdout) })
    }

    pub fn call(&mut self, request: &Value) -> Result<Value, String> {
        let request_id = request.get("id").and_then(Value::as_str)
            .ok_or_else(|| "RPC request has no id".to_string())?.to_string();
        let encoded = serde_json::to_string(request)
            .map_err(|error| format!("Could not encode engine request: {error}"))?;
        self.stdin.write_all(encoded.as_bytes())
            .and_then(|_| self.stdin.write_all(b"\n"))
            .and_then(|_| self.stdin.flush())
            .map_err(|error| format!("Could not write to Witness engine: {error}"))?;
        loop {
            let mut line=String::new();
            let bytes=self.stdout.read_line(&mut line)
                .map_err(|error| format!("Could not read Witness engine response: {error}"))?;
            if bytes==0 {
                let status=self.child.try_wait().ok().flatten();
                return Err(format!("Witness engine exited before replying: {status:?}"));
            }
            if line.len()>crate::security::MAX_MESSAGE_BYTES {
                return Err("Witness engine response exceeded the 1 MiB boundary limit".to_string());
            }
            let response:Value=serde_json::from_str(&line)
                .map_err(|error| format!("Witness engine returned invalid JSON: {error}"))?;
            if response.get("id").and_then(Value::as_str)==Some(request_id.as_str()) {
                return Ok(response);
            }
        }
    }
}

impl Drop for EngineClient {
    fn drop(&mut self) {
        let _=self.child.kill();
        let _=self.child.wait();
    }
}

pub struct EngineState { client: Mutex<Option<EngineClient>> }

impl EngineState {
    pub fn new() -> Self { Self { client: Mutex::new(None) } }

    pub fn call(&self, request:&Value) -> Result<Value,String> {
        let mut guard=self.client.lock().map_err(|_| "Witness engine state lock was poisoned".to_string())?;
        if guard.is_none() { *guard=Some(EngineClient::spawn()?); }
        match guard.as_mut().expect("engine initialized").call(request) {
            Ok(response)=>Ok(response),
            Err(first_error)=>{
                *guard=Some(EngineClient::spawn()?);
                guard.as_mut().expect("engine restarted").call(request)
                    .map_err(|second_error|format!("Engine request failed after supervised restart: {first_error}; {second_error}"))
            }
        }
    }
}
