"""Structured context packs separate retrieved evidence from generation instructions."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from ..evidence.reconcile import ReconciliationResult
from ..evidence.sufficiency import SufficiencyDecision, SufficiencyState
from ..ids import stable_id
from ..retrieval.models import RetrievalCandidate


@dataclass(frozen=True)
class ContextEvidence:
    evidence_id: str
    chunk_id: str
    text: str
    source_version_id: str
    locator: str | None
    method: str
    rank: int
    evidence_kind: str = "text"
    visual_evidence_id: str = ""
    modality: str = ""


@dataclass(frozen=True)
class ContextConflict:
    left_evidence_id: str
    right_evidence_id: str
    reason: str


@dataclass(frozen=True)
class ContextPack:
    question: str
    sufficiency_state: SufficiencyState
    sufficiency_reasons: tuple[str, ...]
    evidence: tuple[ContextEvidence, ...]
    unresolved_conflicts: tuple[ContextConflict, ...]

    def evidence_by_id(self) -> dict[str, ContextEvidence]:
        return {item.evidence_id: item for item in self.evidence}

    def to_dict(self) -> dict:
        return asdict(self)


def build_context_pack(
    question: str,
    candidates: tuple[RetrievalCandidate, ...],
    sufficiency: SufficiencyDecision,
    reconciliation: ReconciliationResult,
) -> ContextPack:
    evidence = tuple(
        ContextEvidence(
            evidence_id=stable_id(
                "evidence",
                candidate.evidence_kind,
                candidate.source_version_id or "",
                candidate.chunk_id,
                candidate.locator or "",
            ),
            chunk_id=candidate.chunk_id,
            text=candidate.text,
            source_version_id=candidate.source_version_id or "",
            locator=candidate.locator,
            method=candidate.method,
            rank=candidate.rank,
            evidence_kind=candidate.evidence_kind,
            visual_evidence_id=candidate.visual_evidence_id,
            modality=candidate.modality,
        )
        for candidate in candidates
    )
    by_chunk = {item.chunk_id: item.evidence_id for item in evidence}

    conflicts: list[ContextConflict] = []
    for relation in reconciliation.unresolved_conflicts:
        left = by_chunk.get(relation.left_chunk_id)
        right = by_chunk.get(relation.right_chunk_id)
        if left and right and left != right:
            conflicts.append(
                ContextConflict(
                    left_evidence_id=left,
                    right_evidence_id=right,
                    reason=relation.reason,
                )
            )

    return ContextPack(
        question=question,
        sufficiency_state=sufficiency.state,
        sufficiency_reasons=sufficiency.reasons,
        evidence=evidence,
        unresolved_conflicts=tuple(conflicts),
    )
