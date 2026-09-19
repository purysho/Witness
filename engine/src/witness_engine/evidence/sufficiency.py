"""Explicit, inspectable evidence sufficiency decisions."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from enum import Enum

from ..retrieval.models import RetrievalCandidate
from ..retrieval.query import analyze_query
from ..retrieval.temporal import TemporalSelection
from .reconcile import ReconciliationResult

_TOKEN_RE = re.compile(r"[A-Za-z0-9_./:#'-]+", re.UNICODE)
_GENERIC_QUERY_TERMS = {
    "a", "all", "an", "and", "are", "as", "at", "be", "by", "did", "do", "does",
    "document", "documents", "explain", "for", "from", "give", "how", "in", "is",
    "it", "me", "of", "on", "or", "please", "show", "summarize", "summary", "tell",
    "that", "the", "their", "this", "to", "was", "were", "what", "when", "where",
    "which", "who", "why", "with",
}
_TEMPORAL_TERMS = {
    "after", "before", "changed", "change", "current", "currently", "earlier",
    "history", "historical", "latest", "later", "now", "previous", "previously",
    "since", "today", "version", "versions",
}


class SufficiencyState(str, Enum):
    SUFFICIENT = "SUFFICIENT"
    PARTIAL = "PARTIAL"
    CONFLICTED = "CONFLICTED"
    INSUFFICIENT = "INSUFFICIENT"


@dataclass(frozen=True)
class SufficiencyDecision:
    state: SufficiencyState
    query_coverage: float
    evidence_count: int
    independent_source_count: int
    unresolved_conflict_count: int
    temporal_requirement_satisfied: bool
    reasons: tuple[str, ...]

    def to_dict(self) -> dict:
        return asdict(self)


def _stem(token: str) -> str:
    value = token.casefold().strip("'")
    if len(value) > 5 and value.endswith("ies"):
        return value[:-3] + "y"
    if len(value) > 5 and value.endswith("ing"):
        return value[:-3]
    if len(value) > 4 and value.endswith("ed"):
        return value[:-2]
    if len(value) > 4 and value.endswith("es"):
        return value[:-2]
    if len(value) > 3 and value.endswith("s"):
        return value[:-1]
    return value


def _meaningful_query_terms(query: str) -> set[str]:
    terms: set[str] = set()
    for token in _TOKEN_RE.findall(query):
        lowered = token.casefold()
        if lowered in _GENERIC_QUERY_TERMS or lowered in _TEMPORAL_TERMS:
            continue
        if re.fullmatch(r"(?:19|20)\d{2}", lowered):
            continue
        terms.add(_stem(lowered))
    return terms


def _evidence_terms(candidates: tuple[RetrievalCandidate, ...]) -> set[str]:
    values: set[str] = set()
    for candidate in candidates:
        for token in _TOKEN_RE.findall(candidate.text):
            values.add(_stem(token))
    return values


class SufficiencyGate:
    """Map inspectable retrieval/evidence features to a named sufficiency state."""

    def decide(
        self,
        query: str,
        candidates: tuple[RetrievalCandidate, ...],
        reconciliation: ReconciliationResult,
        *,
        temporal_selection: TemporalSelection | None = None,
    ) -> SufficiencyDecision:
        features = analyze_query(query)
        query_terms = _meaningful_query_terms(query)
        evidence_terms = _evidence_terms(candidates)
        coverage = (
            len(query_terms & evidence_terms) / len(query_terms)
            if query_terms
            else (1.0 if candidates else 0.0)
        )

        temporal_required = bool(features.temporal_signals)
        temporal_ok = (
            not temporal_required
            or (
                temporal_selection is not None
                and bool(temporal_selection.source_version_ids)
            )
        )

        reasons: list[str] = []
        if not candidates:
            state = SufficiencyState.INSUFFICIENT
            reasons.append("retrieval produced no evidence candidates")
        elif not temporal_ok:
            state = SufficiencyState.INSUFFICIENT
            reasons.append("query requires temporal evidence but no valid source version was selected")
        elif reconciliation.unresolved_conflicts:
            state = SufficiencyState.CONFLICTED
            reasons.append(
                f"{len(reconciliation.unresolved_conflicts)} unresolved material contradiction(s) remain"
            )
        elif coverage <= 0.25:
            state = SufficiencyState.INSUFFICIENT
            reasons.append(
                f"retrieved evidence covers only {coverage:.0%} of meaningful query terms"
            )
        elif coverage < 0.55:
            state = SufficiencyState.PARTIAL
            reasons.append(
                f"retrieved evidence covers {coverage:.0%} of meaningful query terms"
            )
        else:
            state = SufficiencyState.SUFFICIENT
            reasons.append(
                f"retrieved evidence covers {coverage:.0%} of meaningful query terms"
            )

        if (
            state == SufficiencyState.SUFFICIENT
            and features.comparison
            and reconciliation.independent_source_count < 2
        ):
            state = SufficiencyState.PARTIAL
            reasons.append("comparison query has evidence from fewer than two independent sources")

        if (
            state == SufficiencyState.SUFFICIENT
            and "across" in features.tokens
            and reconciliation.independent_source_count < 2
        ):
            state = SufficiencyState.PARTIAL
            reasons.append("cross-document query currently has evidence from only one logical source")

        if reconciliation.corroborations:
            reasons.append(
                f"{len(reconciliation.corroborations)} corroborating relation(s) were found"
            )
        if reconciliation.supersessions:
            reasons.append(
                f"{len(reconciliation.supersessions)} contradiction(s) were resolved by temporal supersession"
            )

        return SufficiencyDecision(
            state=state,
            query_coverage=float(coverage),
            evidence_count=len(candidates),
            independent_source_count=reconciliation.independent_source_count,
            unresolved_conflict_count=len(reconciliation.unresolved_conflicts),
            temporal_requirement_satisfied=temporal_ok,
            reasons=tuple(reasons),
        )
