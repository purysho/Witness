from __future__ import annotations

from witness_engine.pipeline import index_document, search_routed_evidence
from witness_engine.retrieval import (
    DeterministicHashEmbeddingProvider,
    LocalEvidenceGraph,
    LocalEvidenceIndex,
    LocalHierarchyIndex,
    LocalTemporalIndex,
    LocalVectorIndex,
)


def test_temporal_retrieval_selects_version_valid_in_requested_year(tmp_path):
    database = tmp_path / "witness.sqlite3"
    document = tmp_path / "architecture.md"

    with LocalEvidenceIndex(database) as lexical:
        document.write_text("# Authentication\n\nThe API port is 4100.", encoding="utf-8")
        old = index_document(document, lexical, valid_from="2024-03-01T00:00:00+00:00")

        document.write_text("# Authentication\n\nThe API port is 5200.", encoding="utf-8")
        new = index_document(document, lexical, valid_from="2025-04-01T00:00:00+00:00")

        temporal = LocalTemporalIndex(lexical)
        historical = temporal.search("authentication port in 2024", limit=10)
        current = temporal.search("latest authentication port", limit=10)

    assert historical.selection.mode == "year"
    assert historical.selection.source_version_ids == (old.source_version_id,)
    assert historical.candidates
    assert all(item.source_version_id == old.source_version_id for item in historical.candidates)
    assert any("4100" in item.text for item in historical.candidates)

    assert current.selection.mode == "latest"
    assert current.selection.source_version_ids == (new.source_version_id,)
    assert current.candidates
    assert all(item.source_version_id == new.source_version_id for item in current.candidates)
    assert any("5200" in item.text for item in current.candidates)


def test_hierarchical_retrieval_expands_markdown_heading_context(tmp_path):
    database = tmp_path / "witness.sqlite3"
    document = tmp_path / "design.md"
    document.write_text(
        "# Authentication\n\nBearer tokens expire after sixty minutes.\n\n"
        "## Recovery\n\nExpired sessions require a fresh login.\n",
        encoding="utf-8",
    )

    with LocalEvidenceIndex(database) as lexical:
        index_document(document, lexical)
        hierarchy = LocalHierarchyIndex(lexical)
        result = hierarchy.search("authentication", limit=5)

    assert result.candidates
    assert any("Authentication" in item.text for item in result.candidates)
    assert any(
        "Bearer tokens expire after sixty minutes" in item.text
        for item in result.candidates
    )
    assert result.trace
    assert any(item.descendant_block_ids for item in result.trace)


def test_claim_graph_expands_claims_back_to_evidence_chunks(tmp_path):
    database = tmp_path / "witness.sqlite3"
    document = tmp_path / "services.md"
    document.write_text(
        "# Services\n\nAuthentication Service depends on Token Service. "
        "Token Service validates signed credentials.\n",
        encoding="utf-8",
    )

    with LocalEvidenceIndex(database) as lexical:
        indexed = index_document(document, lexical)
        graph = LocalEvidenceGraph(lexical)
        result = graph.search(
            "How is Authentication Service connected to Token Service?",
            limit=10,
        )

    assert indexed.claim_edge_count >= 2
    assert result.candidates
    assert any("depends on Token Service" in item.text for item in result.candidates)
    assert result.trace
    assert any("entity-expansion" in item.matched_by for item in result.trace)
    assert all(item.evidence_chunk_ids for item in result.trace)


def test_routed_retrieval_executes_all_specialized_routes_and_traces_them(tmp_path):
    database = tmp_path / "witness.sqlite3"
    document = tmp_path / "deployment.md"
    document.write_text(
        "# Deployment\n\nAuthentication Service depends on Token Service. "
        "The dependency delayed deployment in 2025.\n",
        encoding="utf-8",
    )
    provider = DeterministicHashEmbeddingProvider(dimensions=32)

    with LocalEvidenceIndex(database) as lexical, LocalVectorIndex(database) as vectors:
        index_document(
            document,
            lexical,
            vector_index=vectors,
            embedding_provider=provider,
            valid_from="2025-01-15T00:00:00+00:00",
        )
        result = search_routed_evidence(
            "Summarize how deployment dependencies changed after 2025 across all documents",
            lexical,
            vectors,
            provider,
            limit=5,
        )

    plan = result.trace.plan
    assert plan.should_run("temporal") is True
    assert plan.should_run("graph") is True
    assert plan.should_run("hierarchical") is True
    assert result.trace.advisory_routes == ()
    assert result.trace.temporal_selection is not None
    assert result.trace.temporal_candidates
    assert result.trace.hierarchical_candidates
    assert result.trace.graph_candidates
    assert result.trace.fusion_candidates
