from __future__ import annotations

from dataclasses import dataclass

from witness_engine.chunking import Chunk
from witness_engine.graph import ExtractedClaim
from witness_engine.retrieval import LocalEvidenceGraph, LocalEvidenceIndex


@dataclass(frozen=True)
class FixtureClaimProvider:
    provider_id = "fixture-claims:v1"

    def extract(self, text: str):
        return (
            ExtractedClaim(
                text="Alpha Service depends on Beta Service.",
                entities=("Alpha Service", "Beta Service"),
            ),
        )


def test_graph_index_uses_claim_extraction_provider_boundary(tmp_path):
    database = tmp_path / "witness.sqlite3"

    with LocalEvidenceIndex(database) as lexical:
        lexical.index_chunks(
            [
                (
                    Chunk(
                        "chunk-1",
                        "block-1",
                        "opaque source text",
                        0,
                        18,
                    ),
                    "source-version-1",
                    "line:1",
                )
            ]
        )
        graph = LocalEvidenceGraph(
            lexical,
            extraction_provider=FixtureClaimProvider(),
        )
        graph.index_chunks(
            [
                (
                    Chunk(
                        "chunk-1",
                        "block-1",
                        "opaque source text",
                        0,
                        18,
                    ),
                    "source-version-1",
                    "line:1",
                )
            ]
        )
        result = graph.search(
            "How is Alpha Service connected to Beta Service?",
            limit=5,
        )

    assert result.candidates
    assert result.trace
    assert result.trace[0].claim_text == "Alpha Service depends on Beta Service."
    assert result.trace[0].entity_ids
