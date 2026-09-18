from __future__ import annotations

import json

from witness_engine.chunking import Chunk
from witness_engine.retrieval import (
    DeterministicTokenReranker,
    LocalEvidenceIndex,
    LocalVectorIndex,
    RetrievalCandidate,
    RoutedRetriever,
    TransparentRetrievalRouter,
    analyze_query,
    rerank_candidates,
)


class SemanticFixtureProvider:
    provider_id = "fixture:semantic-v2"
    dimensions = 3

    def embed(self, texts):
        vectors = []
        for text in texts:
            lowered = text.casefold()
            if any(term in lowered for term in ("auth", "authentication", "token", "login")):
                vectors.append((1.0, 0.0, 0.0))
            elif any(term in lowered for term in ("deploy", "deployment", "release", "rollout")):
                vectors.append((0.0, 1.0, 0.0))
            elif any(term in lowered for term in ("database", "storage", "sqlite")):
                vectors.append((0.0, 0.0, 1.0))
            else:
                vectors.append((0.33, 0.33, 0.33))
        return vectors


def test_query_understanding_extracts_explicit_signals():
    features = analyze_query('Why did "auth-service" change after version 2025?')

    assert features.quoted_phrases == ("auth-service",)
    assert "auth-service" in features.identifiers
    assert "2025" in features.temporal_signals
    assert features.relational is True
    assert features.explanatory is True
    assert features.exact_lookup is True


def test_router_uses_lexical_only_for_compact_exact_lookup():
    plan = TransparentRetrievalRouter().plan('What port is "auth-api"?')

    assert plan.should_run("lexical") is True
    assert plan.should_run("dense") is False
    assert plan.advisory_routes == ()
    assert any("quoted phrase" in reason for reason in plan.decision("lexical").reasons)


def test_router_executes_specialized_routes_when_signals_are_present():
    plan = TransparentRetrievalRouter().plan(
        "Summarize how deployment dependencies changed after 2025 across all documents"
    )

    assert plan.should_run("lexical") is True
    assert plan.should_run("dense") is True
    assert plan.should_run("temporal") is True
    assert plan.should_run("graph") is True
    assert plan.should_run("hierarchical") is True
    assert plan.advisory_routes == ()
    assert plan.decision("temporal").executable is True


def test_deterministic_reranker_records_pre_and_post_ranks():
    candidates = (
        RetrievalCandidate("a", "authentication overview", 0.9, 1, "rrf-hybrid"),
        RetrievalCandidate("b", "authentication token expiry policy", 0.8, 2, "rrf-hybrid"),
    )

    result = rerank_candidates(
        "authentication token expiry",
        candidates,
        DeterministicTokenReranker(),
    )

    assert [candidate.chunk_id for candidate in result.candidates] == ["b", "a"]
    b_trace = next(item for item in result.trace if item.chunk_id == "b")
    assert b_trace.pre_rank == 2
    assert b_trace.post_rank == 1
    assert b_trace.rerank_score > 0


def test_routed_retriever_executes_plan_and_serializes_trace(tmp_path):
    database = tmp_path / "witness.sqlite3"
    provider = SemanticFixtureProvider()

    with LocalEvidenceIndex(database) as lexical:
        lexical.index_chunks(
            [
                (
                    Chunk(
                        "chunk-auth",
                        "block-auth",
                        "Authentication tokens expire after sixty minutes.",
                        0,
                        52,
                    ),
                    "source-auth",
                    "line:1",
                ),
                (
                    Chunk(
                        "chunk-deploy",
                        "block-deploy",
                        "The rollout was delayed by a service dependency.",
                        0,
                        49,
                    ),
                    "source-deploy",
                    "line:2",
                ),
            ]
        )
        with LocalVectorIndex(database) as vectors:
            vectors.sync(provider)
            retriever = RoutedRetriever(lexical, vectors, provider)

            exact = retriever.search('What token is used by "authentication"?', limit=2)
            semantic = retriever.search(
                "Why did the deployment rollout depend on another service?",
                limit=2,
            )

    assert exact.trace.plan.should_run("lexical") is True
    assert exact.trace.plan.should_run("dense") is False
    assert exact.trace.dense_candidates == ()

    assert semantic.trace.plan.should_run("lexical") is True
    assert semantic.trace.plan.should_run("dense") is True
    assert semantic.trace.plan.should_run("graph") is True
    assert semantic.trace.advisory_routes == ()
    # Direct chunk insertion does not create graph projections; the route still
    # executes truthfully and reports an empty graph result rather than faking one.
    assert semantic.trace.graph_candidates == ()
    assert semantic.trace.rerank_trace
    assert semantic.candidates[0].rank == 1

    payload = semantic.trace.to_dict()
    json.dumps(payload)
    assert payload["plan"]["features"]["relational"] is True
    assert payload["reranker_provider_id"].startswith("deterministic-token-reranker")



def test_router_marks_visual_queries_advisory_until_provider_is_available():
    unavailable = TransparentRetrievalRouter().plan(
        "What does the revenue chart show?"
    )
    available = TransparentRetrievalRouter(
        visual_available=True
    ).plan("What does the revenue chart show?")

    assert unavailable.decision("visual").requested is True
    assert unavailable.decision("visual").executable is False
    assert "visual" in unavailable.advisory_routes
    assert available.should_run("visual") is True
    assert available.features.visual_signals == ("chart",)
