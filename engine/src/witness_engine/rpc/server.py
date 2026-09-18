"""Newline-delimited JSON RPC process used by the Tauri host."""

from __future__ import annotations
import json
import sys
from typing import Any
from pydantic import ValidationError
from .models import MAX_MESSAGE_BYTES, PROTOCOL_VERSION, RpcError, RpcErrorEnvelope, RpcRequest, RpcResultEnvelope
from .service import RpcService, RpcServiceError

def _write(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
    sys.stdout.flush()

def _error(request_id: str, code: str, message: str, details: dict | None = None) -> None:
    _write(RpcErrorEnvelope(
        v=PROTOCOL_VERSION, id=request_id,
        error=RpcError(code=code, message=message, details=details)
    ).model_dump(mode="json"))

def main() -> int:
    service = RpcService()
    try:
        for raw in sys.stdin.buffer:
            if len(raw) > MAX_MESSAGE_BYTES:
                _error("", "message_too_large", "RPC message exceeds the 1 MiB limit")
                continue
            try:
                decoded = raw.decode("utf-8")
                payload = json.loads(decoded)
                request = RpcRequest.model_validate(payload)
            except UnicodeDecodeError:
                _error("", "invalid_encoding", "RPC messages must be UTF-8")
                continue
            except json.JSONDecodeError as exc:
                _error("", "invalid_json", "RPC message is not valid JSON", {"position": exc.pos})
                continue
            except ValidationError as exc:
                request_id = str(payload.get("id", "")) if isinstance(locals().get("payload"), dict) else ""
                _error(request_id, "invalid_request", "RPC request failed schema validation",
                       {"errors": exc.errors(include_url=False)})
                continue
            try:
                result = service.handle(request.method, request.params)
                _write(RpcResultEnvelope(id=request.id, result=result).model_dump(mode="json"))
            except RpcServiceError as exc:
                _error(request.id, exc.code, str(exc), exc.details)
            except Exception as exc:
                _error(request.id, "internal_error", "Witness engine request failed",
                       {"exception_type": type(exc).__name__})
    finally:
        service.close()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
