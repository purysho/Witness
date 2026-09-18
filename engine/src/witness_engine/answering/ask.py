"""First complete evidence-first Ask -> Trace engine loop."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from uuid import uuid4

from ..evidence.reconcile import EvidenceReconciler, ReconciliationResult
from ..evidence.sufficiency import SufficiencyDecision, SufficiencyGate
from ..ids import stable_id
from ..retrieval.adaptive import AdaptiveRetrievalResult, RoutedRetriever
from .context import ContextPack, build_context_pack
from .models import ValidatedAnswer
from .providers import DeterministicExtractiveGenerationProvider, GenerationProvider
from .trace import LocalRunStore, TraceEvent
from .validate import validate_generation


@dataclass(frozen=True)
class AskResult:
    run_id: str
    answer: ValidatedAnswer
    context: ContextPack
    retrieval: AdaptiveRetrievalResult
    reconciliation: ReconciliationResult
    sufficiency: SufficiencyDecision
    trace: tuple[TraceEvent, ...]

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "answer": self.answer.to_dict(),
            "context": self.context.to_dict(),
            "retrieval": {
                "candidates": [asdict(item) for item in self.retrieval.candidates],
                "trace": self.retrieval.trace.to_dict(),
            },
            "reconciliation": self.reconciliation.to_dict(),
            "sufficiency": self.sufficiency.to_dict(),
            "trace": [item.to_dict() for item in self.trace],
        }


class AskEngine:
    """Orchestrate retrieval, reconciliation, sufficiency, generation, and validation."""

    def __init__(
        self,
        retriever: RoutedRetriever,
        *,
        generator: GenerationProvider | None = None,
        run_store: LocalRunStore | None = None,
    ) -> None:
        self.retriever = retriever
        self.generator = generator or DeterministicExtractiveGenerationProvider()
        self.run_store = run_store or LocalRunStore(retriever.lexical_index)
        self.reconciler = EvidenceReconciler(retriever.lexical_index)
        self.sufficiency_gate = SufficiencyGate()

    def ask(
        self,
        question: str,
        *,
        limit: int = 10,
        candidate_pool: int = 30,
        rerank_pool: int = 20,
        rrf_k: int = 60,
    ) -> AskResult:
        run_id = stable_id("query-run", question, uuid4().hex)
        self.run_store.start_run(run_id, question)
        self.run_store.append(
            run_id,
            "query.received",
            {"question": question},
        )

        retrieval = self.retriever.search(
            question,
            limit=limit,
            candidate_pool=candidate_pool,
            rerank_pool=rerank_pool,
            rrf_k=rrf_k,
        )
        self.run_store.append(
            run_id,
            "query.normalized",
            asdict(retrieval.trace.plan.features),
        )
        self.run_store.append(
            run_id,
            "route.decided",
            retrieval.trace.plan.to_dict(),
        )
        self.run_store.append(
            run_id,
            "retrieval.lexical.completed",
            {"candidates": [asdict(item) for item in retrieval.trace.lexical_candidates]},
        )
        self.run_store.append(
            run_id,
            "retrieval.dense.completed",
            {"candidates": [asdict(item) for item in retrieval.trace.dense_candidates]},
        )
        self.run_store.append(
            run_id,
            "retrieval.visual.completed",
            {
                "provider_id": retrieval.trace.visual_embedding_provider_id,
                "candidates": [
                    asdict(item) for item in retrieval.trace.visual_candidates
                ],
            },
        )
        self.run_store.append(
            run_id,
            "retrieval.temporal.completed",
            {
                "selection": (
                    asdict(retrieval.trace.temporal_selection)
                    if retrieval.trace.temporal_selection is not None
                    else None
                ),
                "candidates": [
                    asdict(item) for item in retrieval.trace.temporal_candidates
                ],
            },
        )
        self.run_store.append(
            run_id,
            "retrieval.hierarchical.completed",
            {
                "candidates": [
                    asdict(item) for item in retrieval.trace.hierarchical_candidates
                ],
                "expansions": [
                    asdict(item) for item in retrieval.trace.hierarchy_trace
                ],
            },
        )
        self.run_store.append(
            run_id,
            "retrieval.graph.completed",
            {
                "candidates": [
                    asdict(item) for item in retrieval.trace.graph_candidates
                ],
                "paths": [asdict(item) for item in retrieval.trace.graph_trace],
            },
        )
        self.run_store.append(
            run_id,
            "fusion.completed",
            {
                "candidates": [
                    asdict(item) for item in retrieval.trace.fusion_candidates
                ],
                "rrf_k": retrieval.trace.rrf_k,
            },
        )
        self.run_store.append(
            run_id,
            "rerank.completed",
            {
                "provider_id": retrieval.trace.reranker_provider_id,
                "items": [asdict(item) for item in retrieval.trace.rerank_trace],
            },
        )

        reconciliation = self.reconciler.reconcile(retrieval.candidates)
        self.run_store.append(
            run_id,
            "evidence.reconciled",
            reconciliation.to_dict(),
        )

        sufficiency = self.sufficiency_gate.decide(
            question,
            retrieval.candidates,
            reconciliation,
            temporal_selection=retrieval.trace.temporal_selection,
        )
        self.run_store.append(
            run_id,
            "sufficiency.decided",
            sufficiency.to_dict(),
        )

        context = build_context_pack(
            question,
            retrieval.candidates,
            sufficiency,
            reconciliation,
        )
        self.run_store.append(
            run_id,
            "context.built",
            context.to_dict(),
        )

        generated = self.generator.generate(context)
        self.run_store.append(
            run_id,
            "generation.completed",
            {
                "provider_id": self.generator.provider_id,
                "generation": generated.to_dict(),
            },
        )

        answer = validate_generation(context, generated)
        self.run_store.append(
            run_id,
            "answer.validated",
            answer.to_dict(),
        )
        self.run_store.append(
            run_id,
            "run.completed",
            {
                "state": answer.state.value,
                "citation_count": len(answer.citations),
            },
        )
        self.run_store.complete(run_id, answer.state.value, answer.to_dict())

        return AskResult(
            run_id=run_id,
            answer=answer,
            context=context,
            retrieval=retrieval,
            reconciliation=reconciliation,
            sufficiency=sufficiency,
            trace=self.run_store.load_events(run_id),
        )
