"""Clean-vs-attacked execution over the production Witness evaluation pipeline."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from ..evaluation import EvalConfig, EvalDataset, EvalRunner
from ..evaluation.runner import corpus_fingerprint
from ..ids import stable_id
from ..pipeline import index_document
from ..retrieval import EmbeddingProvider, LocalEvidenceIndex, LocalVectorIndex
from .models import (
    AttackCaseComparison,
    AttackInvariant,
    AttackInvariantResult,
    AttackInvariantStatus,
    AttackManifest,
    AttackRunResult,
    AttackRunSummary,
)
from .snapshot import create_attack_snapshot
from .store import AttackStore


def _answer_text(case) -> str:
    payload = case.ask_result or {}
    answer = payload.get("answer", {}) if isinstance(payload, dict) else {}
    sentences = answer.get("sentences", []) if isinstance(answer, dict) else []
    return " ".join(
        str(item.get("text", ""))
        for item in sentences
        if isinstance(item, dict)
    )


def _independent_source_count(case) -> int | None:
    payload = case.ask_result or {}
    sufficiency = payload.get("sufficiency", {}) if isinstance(payload, dict) else {}
    value = (
        sufficiency.get("independent_source_count")
        if isinstance(sufficiency, dict)
        else None
    )
    return int(value) if isinstance(value, int) else None


def _citations_resolve_to_context(case) -> bool | None:
    payload = case.ask_result or {}
    if not isinstance(payload, dict):
        return None
    context = payload.get("context", {})
    answer = payload.get("answer", {})
    if not isinstance(context, dict) or not isinstance(answer, dict):
        return None
    evidence = context.get("evidence", [])
    citations = answer.get("citations", [])
    if not isinstance(evidence, list) or not isinstance(citations, list):
        return None
    evidence_ids = {
        item.get("evidence_id")
        for item in evidence
        if isinstance(item, dict) and item.get("evidence_id")
    }
    return all(
        isinstance(item, dict)
        and item.get("evidence_id") in evidence_ids
        for item in citations
    )


def _case_map(result):
    return {case.case_id: case for case in result.cases}


def _delta(attacked: float | None, clean: float | None) -> float | None:
    if attacked is None or clean is None:
        return None
    return attacked - clean


class AttackRunner:
    """Apply synthetic evidence only to an isolated snapshot, then compare runs."""

    def __init__(
        self,
        canonical_lexical: LocalEvidenceIndex,
        canonical_vectors: LocalVectorIndex,
        embedding_provider: EmbeddingProvider,
        *,
        workspace_path: str | Path,
        store: AttackStore | None = None,
    ) -> None:
        self.canonical = canonical_lexical
        self.canonical_vectors = canonical_vectors
        self.embedding_provider = embedding_provider
        self.workspace_path = Path(workspace_path).expanduser().resolve()
        self.store = store or AttackStore(canonical_lexical)

    def _materialize_mutations(
        self,
        manifest: AttackManifest,
        artifacts: Path,
        lexical: LocalEvidenceIndex,
        vectors: LocalVectorIndex,
    ) -> None:
        for mutation in manifest.mutations:
            for copy_index in range(mutation.copies):
                stem = stable_id(
                    "attack-artifact",
                    manifest.fingerprint,
                    mutation.mutation_id,
                    str(copy_index),
                )[:16]
                suffix = Path(mutation.filename).suffix or ".md"
                path = artifacts / f"{mutation.mutation_id}-{copy_index + 1}-{stem}{suffix}"
                path.write_text(mutation.content, encoding="utf-8")
                index_document(
                    path,
                    lexical,
                    vector_index=vectors,
                    embedding_provider=self.embedding_provider,
                    valid_from=mutation.valid_from,
                )

    def _evaluate_invariant(
        self,
        invariant: AttackInvariant,
        *,
        canonical_before: str,
        canonical_after: str,
        clean_cases: dict,
        attacked_cases: dict,
    ) -> AttackInvariantResult:
        if invariant.kind == "canonical_corpus_unchanged":
            passed = canonical_before == canonical_after
            return AttackInvariantResult(
                invariant_id=invariant.invariant_id,
                kind=invariant.kind,
                status=(
                    AttackInvariantStatus.PASS
                    if passed
                    else AttackInvariantStatus.FAIL
                ),
                detail=(
                    "Canonical corpus fingerprint is unchanged."
                    if passed
                    else "Canonical corpus fingerprint changed during attack execution."
                ),
            )

        clean = clean_cases.get(invariant.case_id)
        attacked = attacked_cases.get(invariant.case_id)
        if clean is None or attacked is None:
            return AttackInvariantResult(
                invariant_id=invariant.invariant_id,
                kind=invariant.kind,
                status=AttackInvariantStatus.NOT_APPLICABLE,
                case_id=invariant.case_id,
                detail="Case is not present in both clean and attacked results.",
            )

        if invariant.kind == "forbidden_answer_text_absent":
            forbidden = (invariant.forbidden_text or "").casefold()
            passed = forbidden not in _answer_text(attacked).casefold()
            detail = (
                f"Forbidden text {invariant.forbidden_text!r} is absent."
                if passed
                else f"Forbidden text {invariant.forbidden_text!r} appeared in attacked answer."
            )
        elif invariant.kind == "expected_state":
            passed = attacked.answer_state == invariant.expected_state
            detail = (
                f"Attacked state is {attacked.answer_state.value if attacked.answer_state else None}; "
                f"expected {invariant.expected_state.value if invariant.expected_state else None}."
            )
        elif invariant.kind == "gold_recall_not_reduced":
            clean_recall = clean.metrics.recall_at_k
            attacked_recall = attacked.metrics.recall_at_k
            if clean_recall is None or attacked_recall is None:
                return AttackInvariantResult(
                    invariant_id=invariant.invariant_id,
                    kind=invariant.kind,
                    status=AttackInvariantStatus.NOT_APPLICABLE,
                    case_id=invariant.case_id,
                    detail="Recall@K is unavailable for this case.",
                )
            passed = attacked_recall >= clean_recall
            detail = (
                f"Recall@K clean={clean_recall:.4f}, attacked={attacked_recall:.4f}."
            )
        elif invariant.kind == "max_independent_source_delta":
            clean_count = _independent_source_count(clean)
            attacked_count = _independent_source_count(attacked)
            if clean_count is None or attacked_count is None:
                return AttackInvariantResult(
                    invariant_id=invariant.invariant_id,
                    kind=invariant.kind,
                    status=AttackInvariantStatus.NOT_APPLICABLE,
                    case_id=invariant.case_id,
                    detail="Independent source counts are unavailable for this case.",
                )
            actual_delta = attacked_count - clean_count
            passed = actual_delta <= int(invariant.max_delta or 0)
            detail = (
                f"Independent sources clean={clean_count}, attacked={attacked_count}, "
                f"delta={actual_delta}, allowed<={invariant.max_delta}."
            )
        elif invariant.kind == "citations_resolve_to_context":
            resolved = _citations_resolve_to_context(attacked)
            if resolved is None:
                return AttackInvariantResult(
                    invariant_id=invariant.invariant_id,
                    kind=invariant.kind,
                    status=AttackInvariantStatus.NOT_APPLICABLE,
                    case_id=invariant.case_id,
                    detail="Citation/context artifacts are unavailable for this case.",
                )
            passed = resolved
            detail = (
                "Every attacked citation resolves to evidence in its context pack."
                if passed
                else "At least one attacked citation does not resolve to its context pack."
            )
        else:
            return AttackInvariantResult(
                invariant_id=invariant.invariant_id,
                kind=invariant.kind,
                status=AttackInvariantStatus.NOT_APPLICABLE,
                case_id=invariant.case_id,
                detail="Invariant kind is not implemented.",
            )

        return AttackInvariantResult(
            invariant_id=invariant.invariant_id,
            kind=invariant.kind,
            status=(
                AttackInvariantStatus.PASS
                if passed
                else AttackInvariantStatus.FAIL
            ),
            case_id=invariant.case_id,
            detail=detail,
        )

    def run(
        self,
        manifest: AttackManifest,
        dataset: EvalDataset,
        config: EvalConfig,
    ) -> AttackRunResult:
        self.store.register_manifest(manifest)
        canonical_before = corpus_fingerprint(self.canonical)
        attack_run_id = stable_id(
            "attack-run",
            manifest.fingerprint,
            dataset.fingerprint,
            canonical_before,
            uuid4().hex,
        )
        snapshot = create_attack_snapshot(
            self.canonical,
            self.workspace_path,
            manifest_fingerprint=manifest.fingerprint,
            attack_run_id=attack_run_id,
        )

        attacked_lexical = LocalEvidenceIndex(snapshot.database)
        attacked_vectors = LocalVectorIndex(snapshot.database)
        started_at = ""
        try:
            self._materialize_mutations(
                manifest,
                snapshot.artifacts,
                attacked_lexical,
                attacked_vectors,
            )
            attacked_fingerprint = corpus_fingerprint(attacked_lexical)
            started_at = self.store.start_run(
                attack_run_id=attack_run_id,
                manifest_fingerprint=manifest.fingerprint,
                dataset_fingerprint=dataset.fingerprint,
                config_json=config.model_dump_json(),
                canonical_corpus_fingerprint=canonical_before,
                attacked_corpus_fingerprint=attacked_fingerprint,
                snapshot_id=snapshot.snapshot_id,
                snapshot_path=str(snapshot.root),
            )

            clean = EvalRunner(
                self.canonical,
                self.canonical_vectors,
                self.embedding_provider,
            ).run(dataset, config)
            attacked = EvalRunner(
                attacked_lexical,
                attacked_vectors,
                self.embedding_provider,
            ).run(dataset, config)

            canonical_after = corpus_fingerprint(self.canonical)
            clean_cases = _case_map(clean)
            attacked_cases = _case_map(attacked)

            cases = []
            for case in dataset.cases:
                clean_case = clean_cases[case.case_id]
                attacked_case = attacked_cases[case.case_id]
                cases.append(
                    AttackCaseComparison(
                        case_id=case.case_id,
                        question=case.question,
                        clean_state=clean_case.answer_state,
                        attacked_state=attacked_case.answer_state,
                        clean_passed=clean_case.metrics.passed,
                        attacked_passed=attacked_case.metrics.passed,
                        clean_query_run_id=clean_case.query_run_id,
                        attacked_query_run_id=attacked_case.query_run_id,
                        recall_delta=_delta(
                            attacked_case.metrics.recall_at_k,
                            clean_case.metrics.recall_at_k,
                        ),
                        precision_delta=_delta(
                            attacked_case.metrics.precision_at_k,
                            clean_case.metrics.precision_at_k,
                        ),
                        citation_coverage_delta=_delta(
                            attacked_case.metrics.citation_coverage,
                            clean_case.metrics.citation_coverage,
                        ),
                    )
                )

            invariants = tuple(
                self._evaluate_invariant(
                    invariant,
                    canonical_before=canonical_before,
                    canonical_after=canonical_after,
                    clean_cases=clean_cases,
                    attacked_cases=attacked_cases,
                )
                for invariant in manifest.invariants
            )
            if not any(
                item.kind == "canonical_corpus_unchanged"
                for item in manifest.invariants
            ):
                invariants = (
                    AttackInvariantResult(
                        invariant_id="canonical-corpus-unchanged",
                        kind="canonical_corpus_unchanged",
                        status=(
                            AttackInvariantStatus.PASS
                            if canonical_before == canonical_after
                            else AttackInvariantStatus.FAIL
                        ),
                        detail=(
                            "Canonical corpus fingerprint is unchanged."
                            if canonical_before == canonical_after
                            else "Canonical corpus fingerprint changed during attack execution."
                        ),
                    ),
                    *invariants,
                )

            summary = AttackRunSummary(
                attack_run_id=attack_run_id,
                attack_manifest_fingerprint=manifest.fingerprint,
                attack_id=manifest.attack_id,
                attack_name=manifest.name,
                dataset_fingerprint=dataset.fingerprint,
                config=config,
                canonical_corpus_fingerprint=canonical_before,
                attacked_corpus_fingerprint=attacked_fingerprint,
                snapshot_id=snapshot.snapshot_id,
                snapshot_path=str(snapshot.root),
                status="completed",
                started_at=started_at,
                completed_at=None,
            )
            result = AttackRunResult(
                run=summary,
                clean=clean,
                attacked=attacked,
                cases=tuple(cases),
                invariants=invariants,
            )
            self.store.complete_run(result)
            persisted = self.store.load_run(attack_run_id)
            return persisted
        except Exception:
            if started_at:
                self.store.fail_run(attack_run_id)
            raise
        finally:
            attacked_vectors.close()
            attacked_lexical.close()
