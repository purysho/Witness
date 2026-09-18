"""Pydantic models for the versioned desktop <-> engine protocol."""

from __future__ import annotations
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field

PROTOCOL_VERSION = 1
MAX_MESSAGE_BYTES = 1_048_576

class RpcRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    v: Literal[1] = PROTOCOL_VERSION
    id: str = Field(min_length=1, max_length=128)
    method: str = Field(min_length=1, max_length=96)
    params: dict[str, Any] = Field(default_factory=dict)

class RpcError(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None

class RpcResultEnvelope(BaseModel):
    v: Literal[1] = PROTOCOL_VERSION
    id: str
    type: Literal["result"] = "result"
    result: dict[str, Any]

class RpcErrorEnvelope(BaseModel):
    v: Literal[1] = PROTOCOL_VERSION
    id: str
    type: Literal["error"] = "error"
    error: RpcError
