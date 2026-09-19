"""Objective, deterministic RAG Lab metrics."""

from __future__ import annotations

from dataclasses import dataclass
from math import log2
from pathlib import PurePath
from statistics import mean

from ..answering.ask import AskResult
from ..evidence.sufficiency import SufficiencyState
from .models import EvalCase, EvalCaseMetrics, EvalCaseResult, EvalRunMetrics, GoldEvidenceRef


@dataclass(frozen=True)
class CandidateMeta:
    chunk_id: str
    visual_evidence_id: str
    source_version_id: str
    locator: str
    source_path: str


def _norm_path(value: str) -> str:
    return value.replace("\\", "/").strip("/").casefold()


def evidence_matches(ref: GoldEvidenceRef, candidate: CandidateMeta) -> bool:
    if ref.chunk_id and ref.chunk_id != candidate.chunk_id:
        return False
    if (
        ref.visual_evidence_id
        and ref.visual_evidence_id != candidate.visual_evidence_id
    ):
        return False
    if ref.source_version_id and ref.source_version_id != candidate.source_version_id:
        return False
    if ref.locator and ref.locator != candidate.locator:
        return False
    if ref.source_path:
        wanted = _norm_path(ref.source_path)
        actual = _norm_path(candidate.source_path)
        if actual != wanted and not actual.endswith("/" + wanted):
            if "/" not in wanted and PurePath(actual).name.casefold() != wanted:
                return False
            if "/" in wanted:
                return False
    return True


def _match_gold_indices(
    refs: tuple[GoldEvidenceRef, ...],
    candidates: list[CandidateMeta],
) -> set[int]:
    return {
        index
        for index, ref in enumerate(refs)
        if any(evidence_matches(ref, candidate) for candidate in candidates)
    }


def _candidate_relevance(
    refs: tuple[GoldEvidenceRef, ...],
    candidate: CandidateMeta,
) -> int:
    return int(any(evidence_matches(ref, candidate) for ref in refs))


def _unique_ranked_relevance(
    refs: tuple[GoldEvidenceRef, ...],
    candidates: list[CandidateMeta],
) -> list[int]:
    """Binary relevance where each gold reference earns DCG credit once."""

    matched_gold: set[int] = set()
    relevance: list[int] = []
    for candidate in candidates:
        matches = {
            index
            for index, ref in enumerate(refs)
            if evidence_matches(ref, candidate)
        }
        new_matches = matches - matched_gold
        relevance.append(1 if new_matches else 0)
        matched_gold.update(matches)
    return relevance


def _ndcg(relevance: list[int], gold_count: int, k: int) -> float:
    if gold_count <= 0:
        return 1.0
    dcg = sum(
        rel / log2(rank + 1)
        for rank, rel in enumerate(relevance[:k], start=1)
    )
    ideal_relevant = min(gold_count, k)
    idcg = sum(
        1.0 / log2(rank + 1)
        for rank in range(1, ideal_relevant + 1)
    )
    return float(dcg / idcg) if idcg else 0.0


def score_case(
    case: EvalCase,
    ask_result: AskResult,
    *,
    source_paths: dict[str, str],
    latency_ms: float,
    cost_usd: float | None,
    cost_available: bool,
    top_k: int,
) -> EvalCaseMetrics:
    candidate_meta = [
        CandidateMeta(
            chunk_id=item.chunk_id,
            visual_evidence_id=item.visual_evidence_id,
            source_version_id=item.source_version_id,
            locator=item.locator,
            source_path=source_paths.get(item.source_version_id, ""),
        )
        for item in ask_result.retrieval.candidates
    ]
    gold = case.gold_evidence

    if gold:
        matched = _match_gold_indices(gold, candidate_meta)
        relevance = [_candidate_relevance(gold, item) for item in candidate_meta]
        unique_relevance = _unique_ranked_relevance(gold, candidate_meta)
        recall = len(matched) / len(gold)
        precision = sum(relevance[:top_k]) / top_k
        reciprocal_rank = next(
            (1.0 / rank for rank, rel in enumerate(relevance, start=1) if rel),
            0.0,
        )
        ndcg = _ndcg(unique_relevance, len(gold), top_k)
    else:
        matched = set()
        recall = precision = reciprocal_rank = ndcg = None

    context_by_id = {
        item.evidence_id: CandidateMeta(
            chunk_id=item.chunk_id,
            visual_evidence_id=item.visual_evidence_id,
            source_version_id=item.source_version_id,
            locator=item.locator or "",
            source_path=source_paths.get(item.source_version_id, ""),
        )
        for item in ask_result.context.evidence
    }
    cited = [
        context_by_id[citation.evidence_id]
        for citation in ask_result.answer.citations
        if citation.evidence_id in context_by_id
    ]

    if gold:
        cited_relevant = [item for item in cited if _candidate_relevance(gold, item)]
        citation_precision = len(cited_relevant) / len(cited) if cited else 0.0
        citation_coverage = len(_match_gold_indices(gold, cited)) / len(gold)
    else:
        citation_precision = 1.0 if not cited else 0.0
        citation_coverage = 1.0 if not cited else 0.0

    if ask_result.answer.state == SufficiencyState.INSUFFICIENT and not gold:
        unsupported_claim_rate = 0.0
    elif ask_result.answer.sentences:
        unsupported = 0
        for sentence in ask_result.answer.sentences:
            sentence_candidates = [
                context_by_id[evidence_id]
                for evidence_id in sentence.evidence_ids
                if evidence_id in context_by_id
            ]
            if gold and not any(
                _candidate_relevance(gold, item) for item in sentence_candidates
            ):
                unsupported += 1
            elif not gold and sentence_candidates:
                unsupported += 1
        unsupported_claim_rate = unsupported / len(ask_result.answer.sentences)
    else:
        unsupported_claim_rate = 0.0

    actual_state = ask_result.answer.state
    state_correct = (
        actual_state == case.expected_state
        if case.expected_state is not None
        else None
    )
    abstention_correct = (
        (actual_state == SufficiencyState.INSUFFICIENT)
        == (case.expected_state == SufficiencyState.INSUFFICIENT)
        if case.expected_state is not None
        else None
    )
    contradiction_correct = (
        (actual_state == SufficiencyState.CONFLICTED)
        == (case.expected_state == SufficiencyState.CONFLICTED)
        if case.expected_state is not None
        else None
    )

    answer_text = " ".join(
        sentence.text for sentence in ask_result.answer.sentences
    ).casefold()
    answer_contains_correct = (
        all(
            fragment.casefold() in answer_text
            for fragment in case.expected_answer_contains
        )
        if case.expected_answer_contains
        else None
    )

    failures: list[str] = []
    if gold and recall < 1.0:
        failures.append(
            f"retrieval matched {len(matched)}/{len(gold)} gold evidence reference(s)"
        )
    if state_correct is False:
        failures.append(
            f"expected state {case.expected_state.value}; got {actual_state.value}"
        )
    if answer_contains_correct is False:
        failures.append("answer omitted one or more expected text fragments")
    if gold and citation_precision < 1.0:
        failures.append("one or more answer citations do not match gold evidence")
    if unsupported_claim_rate > 0:
        failures.append(
            "one or more answer sentences are unsupported by gold evidence"
        )

    return EvalCaseMetrics(
        recall_at_k=recall,
        precision_at_k=precision,
        reciprocal_rank=reciprocal_rank,
        ndcg_at_k=ndcg,
        citation_precision=citation_precision,
        citation_coverage=citation_coverage,
        unsupported_claim_rate=unsupported_claim_rate,
        abstention_correct=abstention_correct,
        contradiction_handling_correct=contradiction_correct,
        state_correct=state_correct,
        answer_contains_correct=answer_contains_correct,
        latency_ms=float(latency_ms),
        cost_usd=cost_usd,
        cost_available=cost_available,
        matched_gold_count=len(matched),
        gold_count=len(gold),
        retrieved_count=len(candidate_meta),
        passed=not failures,
        failure_reasons=tuple(failures),
    )


def _mean_defined(values: list[float | None]) -> float | None:
    defined = [float(value) for value in values if value is not None]
    return float(mean(defined)) if defined else None


def _bool_rate(values: list[bool | None]) -> float | None:
    defined = [value for value in values if value is not None]
    return (
        sum(1 for value in defined if value) / len(defined)
        if defined
        else None
    )


def aggregate_case_results(results: list[EvalCaseResult]) -> EvalRunMetrics:
    metrics = [result.metrics for result in results]
    objective: dict[str, float] = {}

    named = {
        "recall_at_k": _mean_defined([item.recall_at_k for item in metrics]),
        "precision_at_k": _mean_defined(
            [item.precision_at_k for item in metrics]
        ),
        "mrr": _mean_defined([item.reciprocal_rank for item in metrics]),
        "ndcg_at_k": _mean_defined([item.ndcg_at_k for item in metrics]),
        "citation_precision": _mean_defined(
            [item.citation_precision for item in metrics]
        ),
        "citation_coverage": _mean_defined(
            [item.citation_coverage for item in metrics]
        ),
        "unsupported_claim_rate": _mean_defined(
            [item.unsupported_claim_rate for item in metrics]
        ),
        "abstention_correctness": _bool_rate(
            [item.abstention_correct for item in metrics]
        ),
        "contradiction_handling": _bool_rate(
            [item.contradiction_handling_correct for item in metrics]
        ),
        "state_accuracy": _bool_rate([item.state_correct for item in metrics]),
        "answer_contains_accuracy": _bool_rate(
            [item.answer_contains_correct for item in metrics]
        ),
        "pass_rate": (
            sum(1 for item in metrics if item.passed) / len(metrics)
            if metrics
            else 0.0
        ),
    }
    objective.update(
        {name: float(value) for name, value in named.items() if value is not None}
    )

    latencies = sorted(item.latency_ms for item in metrics)
    total_latency = sum(latencies)
    if latencies:
        p95_index = min(
            len(latencies) - 1,
            max(0, int((len(latencies) - 1) * 0.95 + 0.999999)),
        )
        p95 = latencies[p95_index]
        mean_latency = total_latency / len(latencies)
    else:
        p95 = mean_latency = 0.0

    known_costs = [
        item.cost_usd
        for item in metrics
        if item.cost_available and item.cost_usd is not None
    ]
    all_costs_available = bool(metrics) and len(known_costs) == len(metrics)

    objective["mean_latency_ms"] = float(mean_latency)
    objective["p95_latency_ms"] = float(p95)
    if all_costs_available:
        objective["total_cost_usd"] = float(sum(known_costs))

    return EvalRunMetrics(
        objective=objective,
        model_judged={},
        case_count=len(metrics),
        passed_cases=sum(1 for item in metrics if item.passed),
        failed_cases=sum(1 for item in metrics if not item.passed),
        total_latency_ms=float(total_latency),
        mean_latency_ms=float(mean_latency),
        p95_latency_ms=float(p95),
        total_cost_usd=(
            float(sum(known_costs)) if all_costs_available else None
        ),
        cost_available=all_costs_available,
    )
