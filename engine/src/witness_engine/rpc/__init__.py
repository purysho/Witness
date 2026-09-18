"""Versioned local RPC boundary for the Witness desktop host."""

from .models import PROTOCOL_VERSION, RpcErrorEnvelope, RpcRequest, RpcResultEnvelope
from .service import RpcService

__all__ = ["PROTOCOL_VERSION", "RpcErrorEnvelope", "RpcRequest", "RpcResultEnvelope", "RpcService"]
