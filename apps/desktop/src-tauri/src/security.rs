use serde_json::Value;

pub const MAX_MESSAGE_BYTES: usize = 1_048_576;

pub fn validate_request(request: &Value) -> Result<(), String> {
    let object = request.as_object().ok_or_else(|| "RPC request must be a JSON object".to_string())?;
    let version = object.get("v").and_then(Value::as_u64).ok_or_else(|| "RPC request is missing protocol version".to_string())?;
    if version != 1 {
        return Err(format!("Unsupported RPC protocol version: {version}"));
    }
    let method = object.get("method").and_then(Value::as_str).ok_or_else(|| "RPC request is missing method".to_string())?;
    const ALLOWED: &[&str] = &["ping","workspace.open","workspace.health","workspace.repair","providers.get","providers.set","source.import","source.list","query.run","query.trace","graph.snapshot","lab.dataset.load","lab.dataset.list","lab.run","lab.runs","lab.run.get","lab.case","lab.compare","lab.export","attack.manifest.load","attack.manifest.list","attack.run","attack.runs","attack.run.get","attack.export","visual.evidence.get"];
    if !ALLOWED.contains(&method) {
        return Err(format!("RPC method is not allowlisted: {method}"));
    }
    let encoded = serde_json::to_vec(request).map_err(|error| error.to_string())?;
    if encoded.len() > MAX_MESSAGE_BYTES {
        return Err("RPC request exceeds the 1 MiB boundary limit".to_string());
    }
    Ok(())
}
