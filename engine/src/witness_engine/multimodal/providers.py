"""Provider-neutral cross-modal embedding contracts."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Protocol, Sequence

from ..retrieval.embeddings import Vector, normalize


class VisualEmbeddingProvider(Protocol):
    """A shared vector space for text queries and visual assets."""

    @property
    def provider_id(self) -> str: ...

    @property
    def dimensions(self) -> int: ...

    def embed_images(self, payloads: Sequence[bytes]) -> list[Vector]: ...

    def embed_texts(self, texts: Sequence[str]) -> list[Vector]: ...


@dataclass(frozen=True)
class DeterministicHashVisualEmbeddingProvider:
    """Dependency-free test provider for visual storage/retrieval plumbing.

    It is deliberately not a semantic vision model. Production providers can
    implement CLIP/SigLIP-like shared spaces behind the same contract.
    """

    dimensions: int = 64
    namespace: str = "witness-visual-hash-v1"

    @property
    def provider_id(self) -> str:
        return f"visual-hash:{self.namespace}:{self.dimensions}"

    def _vector(self, payload: bytes, *, kind: str) -> Vector:
        if self.dimensions < 1:
            raise ValueError("visual embedding dimensions must be >= 1")
        values: list[float] = []
        for position in range(self.dimensions):
            digest = sha256(
                self.namespace.encode("utf-8")
                + b"\x1f"
                + kind.encode("ascii")
                + b"\x1f"
                + position.to_bytes(4, "little")
                + payload
            ).digest()
            unsigned = int.from_bytes(digest[:4], "little")
            values.append((unsigned / 0xFFFFFFFF) * 2.0 - 1.0)
        return normalize(values)

    def embed_images(self, payloads: Sequence[bytes]) -> list[Vector]:
        return [self._vector(payload, kind="image") for payload in payloads]

    def embed_texts(self, texts: Sequence[str]) -> list[Vector]:
        return [
            self._vector(text.encode("utf-8"), kind="text")
            for text in texts
        ]
