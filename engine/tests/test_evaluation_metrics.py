from witness_engine.evaluation.metrics import (
    CandidateMeta,
    _ndcg,
    _unique_ranked_relevance,
)
from witness_engine.evaluation.models import GoldEvidenceRef


def test_ndcg_counts_each_gold_reference_only_once():
    gold = (GoldEvidenceRef(source_path="duplicate.md"),)
    candidates = [
        CandidateMeta(
            chunk_id="a",
            visual_evidence_id="",
            source_version_id="source-a",
            locator="line:3",
            source_path="duplicate.md",
        ),
        CandidateMeta(
            chunk_id="b",
            visual_evidence_id="",
            source_version_id="source-b",
            locator="line:3",
            source_path="duplicate.md",
        ),
    ]

    relevance = _unique_ranked_relevance(gold, candidates)

    assert relevance == [1, 0]
    assert _ndcg(relevance, len(gold), 10) == 1.0
