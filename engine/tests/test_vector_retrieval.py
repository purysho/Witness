from __future__ import annotations

from pathlib import Path

import pytest

from witness_engine.chunking import Chunk
from witness_engine.retrieval import LocalEvidenceIndex, LocalVectorIndex


class FixedEmbeddingProvider:
    provider_id = "fixed:test-v1"
    dimensions = 3

    def embed(self, texts):
        vectors = []
        for text in texts:
            lowered = text.casefold()
            if "vehicle" in lowered or "automobile" in lowered or "engine" in lowered:
                vectors.append((1.0, 0.0, 0.0))
            elif "banana" in lowered or "fruit" in lowered:
                vectors.append((0.0, 1.0, 0.0))
            else:
                vectors.append((0.0, 0.0, 1.0))
        return vectors


def _seed(database: Path) -> None:
    with LocalEvidenceIndex(database) as lexical:
        lexical.index_chunks(
            [
                (
                    Chunk("chunk-car", "block-car", "automobile engine manual", 0, 24),
                    "source-a",
                    "line:1",
                ),
                (
                    Chunk("chunk-fruit", "block-fruit", "banana fruit guide", 0, 18),
                    "source-b",
                    "line:1",
                ),
            ]
        )


def test_dense_index_persists_and_preserves_provenance(tmp_path):
    database = tmp_path / "witness.sqlite3"
    provider = FixedEmbeddingProvider()
    _seed(database)

    with LocalVectorIndex(database) as vectors:
        assert vectors.sync(provider) == 2
        assert vectors.sync(provider) == 0
        results = vectors.search("vehicle troubleshooting", provider, limit=2)
        assert results[0].chunk_id == "chunk-car"
        assert results[0].source_version_id == "source-a"
        assert results[0].locator == "line:1"
        assert results[0].score == pytest.approx(1.0)

    with LocalVectorIndex(database) as reopened:
        assert reopened.count(provider.provider_id) == 2
        assert reopened.search("vehicle", provider, limit=1)[0].chunk_id == "chunk-car"


def test_provider_identity_prevents_silent_vector_mixing(tmp_path):
    database = tmp_path / "witness.sqlite3"
    _seed(database)

    first = FixedEmbeddingProvider()

    class OtherProvider(FixedEmbeddingProvider):
        provider_id = "fixed:test-v2"

    second = OtherProvider()

    with LocalVectorIndex(database) as vectors:
        assert vectors.sync(first) == 2
        assert vectors.sync(second) == 2
        assert vectors.count(first.provider_id) == 2
        assert vectors.count(second.provider_id) == 2
