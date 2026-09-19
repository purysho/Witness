use serde_json::Value;
use std::env;
use std::fs;
use std::io::{BufRead, BufReader, Write};
use std::path::PathBuf;
use std::process::{
    Child as PythonChild, ChildStdin, ChildStdout, Command as PythonCommand,
    Stdio,
};
use std::sync::mpsc::{self, Receiver, RecvTimeoutError};
use std::sync::Mutex;
use std::time::Duration;
use tauri::AppHandle;
use tauri_plugin_shell::{
    process::{CommandChild, CommandEvent},
    ShellExt,
};

const ENGINE_RESPONSE_TIMEOUT: Duration = Duration::from_secs(120);

enum SidecarEvent {
    Stdout(Vec<u8>),
    Error(String),
    Terminated(Option<i32>),
}

enum EngineTransport {
    Python {
        child: PythonChild,
        stdin: ChildStdin,
        stdout: BufReader<ChildStdout>,
    },
    Sidecar {
        child: Option<CommandChild>,
        events: Receiver<SidecarEvent>,
    },
}

pub struct EngineClient {
    transport: EngineTransport,
}

impl EngineClient {
    fn spawn_python() -> Result<Self, String> {
        let python = env::var("WITNESS_PYTHON").unwrap_or_else(|_| {
            if cfg!(windows) {
                "python".to_string()
            } else {
                "python3".to_string()
            }
        });
        let engine_src = env::var_os("WITNESS_ENGINE_PYTHONPATH")
            .map(PathBuf::from)
            .unwrap_or_else(|| {
                PathBuf::from(env!("CARGO_MANIFEST_DIR"))
                    .join("../../../engine/src")
            });
        let mut python_paths = vec![engine_src];
        if let Some(existing) = env::var_os("PYTHONPATH") {
            python_paths.extend(env::split_paths(&existing));
        }
        let python_path = env::join_paths(python_paths)
            .map_err(|error| {
                format!("Could not construct engine PYTHONPATH: {error}")
            })?;

        let mut child = PythonCommand::new(python)
            .args(["-m", "witness_engine.rpc.server"])
            .env("PYTHONPATH", python_path)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::inherit())
            .spawn()
            .map_err(|error| {
                format!("Could not start Witness Python engine: {error}")
            })?;
        let stdin = child
            .stdin
            .take()
            .ok_or_else(|| "Engine stdin was unavailable".to_string())?;
        let stdout = child
            .stdout
            .take()
            .ok_or_else(|| "Engine stdout was unavailable".to_string())?;

        Ok(Self {
            transport: EngineTransport::Python {
                child,
                stdin,
                stdout: BufReader::new(stdout),
            },
        })
    }

    fn spawn_sidecar(app: &AppHandle) -> Result<Self, String> {
        let command = app
            .shell()
            .sidecar("witness-engine")
            .map_err(|error| {
                format!("Could not resolve bundled Witness engine: {error}")
            })?;
        let (mut receiver, child) = command.spawn().map_err(|error| {
            format!("Could not start bundled Witness engine: {error}")
        })?;

        let (sender, events) = mpsc::channel();
        tauri::async_runtime::spawn(async move {
            while let Some(event) = receiver.recv().await {
                match event {
                    CommandEvent::Stdout(line) => {
                        if sender.send(SidecarEvent::Stdout(line)).is_err() {
                            break;
                        }
                    }
                    CommandEvent::Stderr(line) => {
                        eprintln!(
                            "Witness engine: {}",
                            String::from_utf8_lossy(&line)
                        );
                    }
                    CommandEvent::Error(error) => {
                        let _ = sender.send(SidecarEvent::Error(error));
                    }
                    CommandEvent::Terminated(payload) => {
                        let _ = sender.send(SidecarEvent::Terminated(
                            payload.code,
                        ));
                        break;
                    }
                    _ => {}
                }
            }
        });

        Ok(Self {
            transport: EngineTransport::Sidecar {
                child: Some(child),
                events,
            },
        })
    }

    pub fn spawn(app: &AppHandle) -> Result<Self, String> {
        let mode = env::var("WITNESS_ENGINE_MODE")
            .unwrap_or_else(|_| {
                if cfg!(debug_assertions) {
                    "python".to_string()
                } else {
                    "sidecar".to_string()
                }
            })
            .trim()
            .to_ascii_lowercase();

        match mode.as_str() {
            "python" => Self::spawn_python(),
            "sidecar" => Self::spawn_sidecar(app),
            value => Err(format!(
                "Unsupported WITNESS_ENGINE_MODE={value:?}; use python or sidecar"
            )),
        }
    }

    fn encoded_request(request: &Value) -> Result<(String, String), String> {
        let request_id = request
            .get("id")
            .and_then(Value::as_str)
            .ok_or_else(|| "RPC request has no id".to_string())?
            .to_string();
        let encoded = serde_json::to_string(request)
            .map_err(|error| {
                format!("Could not encode engine request: {error}")
            })?;
        Ok((request_id, encoded))
    }

    fn parse_response(
        request_id: &str,
        line: &[u8],
    ) -> Result<Option<Value>, String> {
        if line.len() > crate::security::MAX_MESSAGE_BYTES {
            return Err(
                "Witness engine response exceeded the 1 MiB boundary limit"
                    .to_string(),
            );
        }
        let response: Value = serde_json::from_slice(line)
            .map_err(|error| {
                format!("Witness engine returned invalid JSON: {error}")
            })?;
        if response.get("id").and_then(Value::as_str)
            == Some(request_id)
        {
            Ok(Some(response))
        } else {
            Ok(None)
        }
    }

    pub fn call(&mut self, request: &Value) -> Result<Value, String> {
        let (request_id, encoded) = Self::encoded_request(request)?;

        match &mut self.transport {
            EngineTransport::Python {
                child,
                stdin,
                stdout,
            } => {
                stdin
                    .write_all(encoded.as_bytes())
                    .and_then(|_| stdin.write_all(b"\n"))
                    .and_then(|_| stdin.flush())
                    .map_err(|error| {
                        format!(
                            "Could not write to Witness engine: {error}"
                        )
                    })?;

                loop {
                    let mut line = String::new();
                    let bytes = stdout.read_line(&mut line).map_err(
                        |error| {
                            format!(
                                "Could not read Witness engine response: {error}"
                            )
                        },
                    )?;
                    if bytes == 0 {
                        let status = child.try_wait().ok().flatten();
                        return Err(format!(
                            "Witness engine exited before replying: {status:?}"
                        ));
                    }
                    if let Some(response) = Self::parse_response(
                        &request_id,
                        line.as_bytes(),
                    )? {
                        return Ok(response);
                    }
                }
            }
            EngineTransport::Sidecar { child, events } => {
                let process = child.as_mut().ok_or_else(|| {
                    "Bundled Witness engine is not running".to_string()
                })?;
                process
                    .write(format!("{encoded}\n").as_bytes())
                    .map_err(|error| {
                        format!(
                            "Could not write to bundled Witness engine: {error}"
                        )
                    })?;

                loop {
                    match events.recv_timeout(ENGINE_RESPONSE_TIMEOUT) {
                        Ok(SidecarEvent::Stdout(line)) => {
                            if let Some(response) = Self::parse_response(
                                &request_id,
                                &line,
                            )? {
                                return Ok(response);
                            }
                        }
                        Ok(SidecarEvent::Error(error)) => {
                            return Err(format!(
                                "Bundled Witness engine error: {error}"
                            ));
                        }
                        Ok(SidecarEvent::Terminated(code)) => {
                            return Err(format!(
                                "Bundled Witness engine exited before replying: {code:?}"
                            ));
                        }
                        Err(RecvTimeoutError::Timeout) => {
                            return Err(
                                "Timed out waiting for Witness engine response"
                                    .to_string(),
                            );
                        }
                        Err(RecvTimeoutError::Disconnected) => {
                            return Err(
                                "Bundled Witness engine response channel closed"
                                    .to_string(),
                            );
                        }
                    }
                }
            }
        }
    }
}

impl EngineClient {
    fn shutdown(&mut self) {
        match &mut self.transport {
            EngineTransport::Python { child, .. } => {
                let _ = child.kill();
                let _ = child.wait();
            }
            EngineTransport::Sidecar { child, events } => {
                if let Some(process) = child.take() {
                    let _ = process.kill();

                    // CommandChild::kill only sends the termination signal.
                    // Keep the desktop alive briefly so Windows releases the
                    // bundled sidecar executable before app cleanup/uninstall.
                    let deadline = std::time::Instant::now()
                        + Duration::from_secs(5);
                    loop {
                        let now = std::time::Instant::now();
                        if now >= deadline {
                            break;
                        }
                        match events.recv_timeout(deadline - now) {
                            Ok(SidecarEvent::Terminated(_))
                            | Ok(SidecarEvent::Error(_)) => break,
                            Ok(SidecarEvent::Stdout(_)) => continue,
                            Err(_) => break,
                        }
                    }
                }
            }
        }
    }
}

impl Drop for EngineClient {
    fn drop(&mut self) {
        self.shutdown();
    }
}

pub struct EngineState {
    app: AppHandle,
    client: Mutex<Option<EngineClient>>,
}

impl EngineState {
    fn record_smoke_ready(response: &Value) {
        let Some(path) = env::var_os("WITNESS_SMOKE_READY_FILE") else {
            return;
        };
        let response_type = response
            .get("type")
            .and_then(Value::as_str)
            .unwrap_or("unknown");
        let payload = format!("engine-rpc-ready:{response_type}\n");
        if let Err(error) = fs::write(path, payload) {
            eprintln!("Could not write Witness smoke readiness marker: {error}");
        }
    }

    pub fn new(app: AppHandle) -> Self {
        Self {
            app,
            client: Mutex::new(None),
        }
    }

    pub fn call(&self, request: &Value) -> Result<Value, String> {
        let mut guard = self
            .client
            .lock()
            .map_err(|_| {
                "Witness engine state lock was poisoned".to_string()
            })?;

        if guard.is_none() {
            *guard = Some(EngineClient::spawn(&self.app)?);
        }

        match guard
            .as_mut()
            .expect("engine initialized")
            .call(request)
        {
            Ok(response) => {
                Self::record_smoke_ready(&response);
                Ok(response)
            }
            Err(first_error) => {
                *guard = Some(EngineClient::spawn(&self.app)?);
                let response = guard
                    .as_mut()
                    .expect("engine restarted")
                    .call(request)
                    .map_err(|second_error| {
                        format!(
                            "Engine request failed after supervised restart: \
                             {first_error}; {second_error}"
                        )
                    })?;
                Self::record_smoke_ready(&response);
                Ok(response)
            }
        }
    }

    pub fn shutdown(&self) {
        if let Ok(mut guard) = self.client.lock() {
            *guard = None;
        }
    }
}
