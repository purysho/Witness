from witness_engine.pipeline import index_document, search_hybrid_evidence
from witness_engine.retrieval import LocalEvidenceIndex, LocalVectorIndex


class PipelineFixtureProvider:
    provider_id = "fixture:pipeline-v1"
    dimensions = 2

    def embed(self, texts):
        output = []
        for text in texts:
            lowered = text.casefold()
            if any(word in lowered for word in ("vehicle", "automobile", "engine")):
                output.append((1.0, 0.0))
            else:
                output.append((0.0, 1.0))
        return output


def test_document_to_hybrid_candidates_with_trace(tmp_path):
    document = tmp_path / "manual.md"
    document.write_text(
        "# Maintenance\n\nThe automobile engine requires scheduled servicing.\n",
        encoding="utf-8",
    )
    database = tmp_path / "witness.sqlite3"
    provider = PipelineFixtureProvider()

    with LocalEvidenceIndex(database) as lexical, LocalVectorIndex(database) as vectors:
        indexed = index_document(
            document,
            lexical,
            vector_index=vectors,
            embedding_provider=provider,
        )
        result = search_hybrid_evidence(
            "vehicle servicing",
            lexical,
            vectors,
            provider,
            limit=3,
        )

    assert indexed.embedded_chunk_count == indexed.chunk_count
    assert result.candidates
    assert "automobile engine" in result.candidates[0].text
    assert result.candidates[0].locator.startswith("line:")
    assert result.trace.dense_candidates
    assert result.trace.fused_candidates
