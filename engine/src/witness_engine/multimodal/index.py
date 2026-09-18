"""Persistent exact vector baseline for visual evidence."""

from __future__ import annotations

import sqlite3
import struct
from typing import Sequence

from ..retrieval.embeddings import Vector, normalize
from ..retrieval.index import LocalEvidenceIndex
from .models import VisualModality, VisualRetrievalCandidate
from .providers import VisualEmbeddingProvider
from .store import VisualEvidenceStore


class VisualVectorIndexError(RuntimeError):
    pass


def _pack(vector: Sequence[float]) -> bytes:
    return struct.pack(f"<{len(vector)}f", *vector)


def _unpack(payload: bytes, dimensions: int) -> Vector:
    expected = dimensions * 4
    if len(payload) != expected:
        raise VisualVectorIndexError(
            f"Corrupt visual vector: expected {expected} bytes, got {len(payload)}"
        )
    return tuple(
        float(value)
        for value in struct.unpack(f"<{dimensions}f", payload)
    )


def _dot(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        raise VisualVectorIndexError(
            f"Visual vector dimension mismatch: {len(left)} != {len(right)}"
        )
    return float(sum(a * b for a, b in zip(left, right)))


class LocalVisualVectorIndex:
    def __init__(self, evidence_index: LocalEvidenceIndex) -> None:
        self.connection = evidence_index.connection
        self.store = VisualEvidenceStore(evidence_index)
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS visual_embeddings (
                visual_evidence_id TEXT NOT NULL,
                provider_id TEXT NOT NULL,
                dimensions INTEGER NOT NULL,
                asset_sha256 TEXT NOT NULL,
                vector BLOB NOT NULL,
                PRIMARY KEY (visual_evidence_id, provider_id),
                FOREIGN KEY (visual_evidence_id)
                    REFERENCES visual_evidence(visual_evidence_id)
                    ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_visual_embeddings_provider
                ON visual_embeddings(provider_id);
            """
        )

    def sync(
        self,
        provider: VisualEmbeddingProvider,
        *,
        batch_size: int = 32,
    ) -> int:
        if batch_size < 1:
            raise ValueError("batch_size must be >= 1")
        rows = self.connection.execute(
            """
            SELECT visual_evidence_id, asset_sha256
            FROM visual_evidence
            ORDER BY visual_evidence_id
            """
        ).fetchall()
        existing = {
            row["visual_evidence_id"]: row["asset_sha256"]
            for row in self.connection.execute(
                """
                SELECT visual_evidence_id, asset_sha256
                FROM visual_embeddings
                WHERE provider_id = ?
                """,
                (provider.provider_id,),
            ).fetchall()
        }
        pending = [
            row
            for row in rows
            if existing.get(row["visual_evidence_id"]) != row["asset_sha256"]
        ]

        indexed = 0
        for start in range(0, len(pending), batch_size):
            batch = pending[start : start + batch_size]
            payloads = [
                self.store.asset_bytes(row["asset_sha256"])
                for row in batch
            ]
            vectors = provider.embed_images(payloads)
            if len(vectors) != len(batch):
                raise VisualVectorIndexError(
                    "Visual provider returned a different number of vectors than images"
                )
            with self.connection:
                for row, raw in zip(batch, vectors):
                    vector = normalize(raw)
                    if not vector:
                        raise VisualVectorIndexError(
                            "Visual embedding vectors must not be empty"
                        )
                    self.connection.execute(
                        """
                        INSERT INTO visual_embeddings (
                            visual_evidence_id, provider_id, dimensions,
                            asset_sha256, vector
                        ) VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(visual_evidence_id, provider_id) DO UPDATE SET
                            dimensions=excluded.dimensions,
                            asset_sha256=excluded.asset_sha256,
                            vector=excluded.vector
                        """,
                        (
                            row["visual_evidence_id"],
                            provider.provider_id,
                            len(vector),
                            row["asset_sha256"],
                            _pack(vector),
                        ),
                    )
                    indexed += 1
        return indexed

    def count(self, provider_id: str | None = None) -> int:
        if provider_id is None:
            row = self.connection.execute(
                "SELECT COUNT(*) FROM visual_embeddings"
            ).fetchone()
        else:
            row = self.connection.execute(
                """
                SELECT COUNT(*) FROM visual_embeddings
                WHERE provider_id = ?
                """,
                (provider_id,),
            ).fetchone()
        return int(row[0])

    def search(
        self,
        query: str,
        provider: VisualEmbeddingProvider,
        *,
        limit: int = 10,
    ) -> list[VisualRetrievalCandidate]:
        if limit <= 0 or not query.strip():
            return []
        vectors = provider.embed_texts([query])
        if len(vectors) != 1:
            raise VisualVectorIndexError(
                "Visual provider must return one query vector"
            )
        query_vector = normalize(vectors[0])
        rows = self.connection.execute(
            """
            SELECT
                x.visual_evidence_id,
                x.dimensions,
                x.vector,
                e.source_version_id,
                e.locator,
                e.modality,
                e.label_text
            FROM visual_embeddings AS x
            JOIN visual_evidence AS e
              ON e.visual_evidence_id = x.visual_evidence_id
            WHERE x.provider_id = ?
            ORDER BY x.visual_evidence_id
            """,
            (provider.provider_id,),
        ).fetchall()

        scored: list[tuple[float, sqlite3.Row]] = []
        for row in rows:
            vector = _unpack(row["vector"], int(row["dimensions"]))
            scored.append((_dot(query_vector, vector), row))
        scored.sort(
            key=lambda item: (-item[0], item[1]["visual_evidence_id"])
        )
        return [
            VisualRetrievalCandidate(
                visual_evidence_id=row["visual_evidence_id"],
                source_version_id=row["source_version_id"],
                locator=row["locator"],
                modality=VisualModality(row["modality"]),
                label_text=row["label_text"],
                score=float(score),
                rank=rank,
                method=f"visual:{provider.provider_id}",
            )
            for rank, (score, row) in enumerate(scored[:limit], start=1)
        ]
