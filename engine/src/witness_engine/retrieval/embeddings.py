"""Embedding provider contracts for dense evidence retrieval."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from math import sqrt
from typing import Protocol, Sequence


Vector = tuple[float, ...]


class EmbeddingProvider(Protocol):
    """Provider-neutral embedding interface.

    Provider identity is persisted beside vectors so embeddings from different
    models/configurations are never mixed silently.
    """

    @property
    def provider_id(self) -> str: ...

    @property
    def dimensions(self) -> int: ...

    def embed(self, texts: Sequence[str]) -> list[Vector]: ...


def normalize(vector: Sequence[float]) -> Vector:
    magnitude = sqrt(sum(value * value for value in vector))
    if magnitude == 0:
        return tuple(0.0 for _ in vector)
    return tuple(float(value / magnitude) for value in vector)


@dataclass(frozen=True)
class DeterministicHashEmbeddingProvider:
    """Dependency-free deterministic embedder for tests and offline baselines.

    This is *not* presented as a semantic model. It exists so vector storage,
    ranking, persistence, fusion, and tracing can be tested without network or
    model downloads. Production semantic retrieval can use the optional
    SentenceTransformerEmbeddingProvider below.
    """

    dimensions: int = 64
    namespace: str = "witness-test-hash-v1"

    @property
    def provider_id(self) -> str:
        return f"hash:{self.namespace}:{self.dimensions}"

    def embed(self, texts: Sequence[str]) -> list[Vector]:
        vectors: list[Vector] = []
        for text in texts:
            values = [0.0] * self.dimensions
            tokens = [token.casefold() for token in text.split() if token.strip()]
            for token in tokens:
                digest = sha256(f"{self.namespace}:{token}".encode("utf-8")).digest()
                bucket = int.from_bytes(digest[:4], "little") % self.dimensions
                sign = 1.0 if digest[4] & 1 else -1.0
                values[bucket] += sign
            vectors.append(normalize(values))
        return vectors


class SentenceTransformerEmbeddingProvider:
    """Local semantic embedding provider backed by sentence-transformers.

    The dependency is optional. The model is loaded lazily so the Witness core
    and deterministic test suite do not require a model download.
    """

    def __init__(
        self,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        *,
        device: str | None = None,
        local_files_only: bool = True,
    ) -> None:
        self.model_name = model_name
        self.device = device
        self.local_files_only = local_files_only
        self._model = None
        self._dimensions: int | None = None

    @property
    def provider_id(self) -> str:
        return f"sentence-transformers:{self.model_name}"

    def _load(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:  # pragma: no cover - optional dependency
                raise RuntimeError(
                    "Install witness-engine[embeddings] to use local semantic embeddings"
                ) from exc
            try:
                self._model = SentenceTransformer(
                    self.model_name,
                    device=self.device,
                    local_files_only=self.local_files_only,
                )
            except Exception as exc:
                mode = "local cache" if self.local_files_only else "configured source"
                raise RuntimeError(
                    f"Semantic embedding model '{self.model_name}' is unavailable "
                    f"from the {mode}. Install witness-engine[embeddings] and "
                    "cache the model locally before selecting it."
                ) from exc
            self._dimensions = int(self._model.get_sentence_embedding_dimension())
        return self._model

    @property
    def dimensions(self) -> int:
        self._load()
        assert self._dimensions is not None
        return self._dimensions

    def embed(self, texts: Sequence[str]) -> list[Vector]:
        if not texts:
            return []
        model = self._load()
        matrix = model.encode(
            list(texts),
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return [tuple(float(value) for value in row) for row in matrix]
