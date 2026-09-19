"""Persistent local vector evidence index.

The first dense baseline uses exact cosine search. That is intentionally simple
and deterministic: approximate HNSW search can be added after Witness has a
stable retrieval/evaluation contract to measure the trade-off.
"""

from __future__ import annotations

import sqlite3
import struct
from hashlib import sha256
from pathlib import Path
from typing import Callable, Sequence

from .eligibility import active_source_version_ids
from .embeddings import EmbeddingProvider, Vector, normalize
from .models import RetrievalCandidate


class VectorIndexError(RuntimeError):
    pass


def _pack_vector(vector: Sequence[float]) -> bytes:
    return struct.pack(f"<{len(vector)}f", *vector)


def _unpack_vector(blob: bytes, dimensions: int) -> Vector:
    expected = dimensions * 4
    if len(blob) != expected:
        raise VectorIndexError(
            f"Corrupt vector payload: expected {expected} bytes, got {len(blob)}"
        )
    return tuple(float(value) for value in struct.unpack(f"<{dimensions}f", blob))


def _dot(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        raise VectorIndexError(
            f"Vector dimension mismatch: {len(left)} != {len(right)}"
        )
    return float(sum(a * b for a, b in zip(left, right)))


class LocalVectorIndex:
    """SQLite-backed dense vectors keyed by immutable evidence chunk IDs."""

    def __init__(self, database: str | Path):
        self.database = Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.database)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA journal_mode = WAL")
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS chunk_embeddings (
                chunk_id TEXT NOT NULL,
                provider_id TEXT NOT NULL,
                dimensions INTEGER NOT NULL,
                text_sha256 TEXT NOT NULL,
                vector BLOB NOT NULL,
                PRIMARY KEY (chunk_id, provider_id),
                FOREIGN KEY (chunk_id) REFERENCES indexed_chunks(chunk_id)
                    ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_chunk_embeddings_provider
                ON chunk_embeddings(provider_id);
            """
        )

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "LocalVectorIndex":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def count(self, provider_id: str | None = None) -> int:
        if provider_id is None:
            row = self.connection.execute(
                "SELECT COUNT(*) FROM chunk_embeddings"
            ).fetchone()
        else:
            row = self.connection.execute(
                "SELECT COUNT(*) FROM chunk_embeddings WHERE provider_id = ?",
                (provider_id,),
            ).fetchone()
        return int(row[0])

    def sync(
        self,
        provider: EmbeddingProvider,
        *,
        source_version_id: str | None = None,
        batch_size: int = 64,
        cancel_check: Callable[[], None] | None = None,
    ) -> int:
        """Embed missing or stale chunks from the provenance table."""
        if batch_size < 1:
            raise ValueError("batch_size must be >= 1")

        query = "SELECT chunk_id, text FROM indexed_chunks"
        params: tuple[str, ...] = ()
        if source_version_id is not None:
            query += " WHERE source_version_id = ?"
            params = (source_version_id,)
        query += " ORDER BY chunk_id"

        source_rows = self.connection.execute(query, params).fetchall()
        existing = {
            row["chunk_id"]: row["text_sha256"]
            for row in self.connection.execute(
                "SELECT chunk_id, text_sha256 FROM chunk_embeddings WHERE provider_id = ?",
                (provider.provider_id,),
            ).fetchall()
        }

        pending: list[tuple[str, str, str]] = []
        for row in source_rows:
            digest = sha256(row["text"].encode("utf-8")).hexdigest()
            if existing.get(row["chunk_id"]) != digest:
                pending.append((row["chunk_id"], row["text"], digest))

        indexed = 0
        for start in range(0, len(pending), batch_size):
            if cancel_check is not None:
                cancel_check()
            batch = pending[start : start + batch_size]
            vectors = provider.embed([text for _, text, _ in batch])
            if cancel_check is not None:
                cancel_check()
            if len(vectors) != len(batch):
                raise VectorIndexError(
                    "Embedding provider returned a different number of vectors than inputs"
                )

            with self.connection:
                for (chunk_id, _text, digest), raw_vector in zip(batch, vectors):
                    if cancel_check is not None:
                        cancel_check()
                    vector = normalize(raw_vector)
                    if not vector:
                        raise VectorIndexError("Embedding vectors must not be empty")
                    self.connection.execute(
                        """
                        INSERT INTO chunk_embeddings (
                            chunk_id, provider_id, dimensions, text_sha256, vector
                        ) VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(chunk_id, provider_id) DO UPDATE SET
                            dimensions=excluded.dimensions,
                            text_sha256=excluded.text_sha256,
                            vector=excluded.vector
                        """,
                        (
                            chunk_id,
                            provider.provider_id,
                            len(vector),
                            digest,
                            _pack_vector(vector),
                        ),
                    )
                    indexed += 1
        return indexed

    def prune_orphans(self) -> int:
        """Remove vectors whose provenance chunks no longer exist."""
        before = self.count()
        with self.connection:
            self.connection.execute(
                """
                DELETE FROM chunk_embeddings
                WHERE chunk_id NOT IN (SELECT chunk_id FROM indexed_chunks)
                """
            )
        return before - self.count()

    def search(
        self,
        query: str,
        provider: EmbeddingProvider,
        *,
        limit: int = 10,
    ) -> list[RetrievalCandidate]:
        if limit <= 0 or not query.strip():
            return []

        vectors = provider.embed([query])
        if len(vectors) != 1:
            raise VectorIndexError("Embedding provider must return one query vector")
        query_vector = normalize(vectors[0])
        if not query_vector:
            return []

        rows = self.connection.execute(
            """
            SELECT
                e.chunk_id,
                e.dimensions,
                e.vector,
                c.text,
                c.source_version_id,
                c.block_id,
                c.locator
            FROM chunk_embeddings AS e
            JOIN indexed_chunks AS c ON c.chunk_id = e.chunk_id
            WHERE e.provider_id = ?
            ORDER BY e.chunk_id
            """,
            (provider.provider_id,),
        ).fetchall()
        active_ids = active_source_version_ids(self.connection)
        if active_ids is not None:
            active_set = set(active_ids)
            rows = [
                row
                for row in rows
                if row["source_version_id"] in active_set
            ]

        scored: list[tuple[float, sqlite3.Row]] = []
        for row in rows:
            vector = _unpack_vector(row["vector"], int(row["dimensions"]))
            if len(vector) != len(query_vector):
                raise VectorIndexError(
                    "Persisted vector dimensions do not match query provider output"
                )
            scored.append((_dot(query_vector, vector), row))

        scored.sort(key=lambda item: (-item[0], item[1]["chunk_id"]))
        return [
            RetrievalCandidate(
                chunk_id=row["chunk_id"],
                text=row["text"],
                score=float(score),
                rank=rank,
                method=f"dense:{provider.provider_id}",
                source_version_id=row["source_version_id"],
                locator=row["locator"],
                block_id=row["block_id"],
            )
            for rank, (score, row) in enumerate(scored[:limit], start=1)
        ]
