"""Deterministic evidence reconciliation over retrieved candidate claims.

The reconciler does not ask a model to "decide the truth". It records concrete
relationships that can be inspected: duplicates, corroboration, contradictions,
and temporal supersession. Ambiguous contradictions remain unresolved.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import asdict, dataclass
from enum import Enum
from itertools import combinations

from ..ids import stable_id
from ..retrieval.index import LocalEvidenceIndex
from ..retrieval.models import RetrievalCandidate

_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+|\n+")
_TOKEN_RE = re.compile(r"[A-Za-z0-9_./:#'-]+", re.UNICODE)
_NUMBER_RE = re.compile(r"\b\d+(?:\.\d+)?\b")
_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "by", "for", "from",
    "has", "have", "how", "in", "is", "it", "of", "on", "or", "that", "the",
    "their", "this", "to", "was", "were", "what", "when", "where", "which",
    "who", "why", "with",
}
_NEGATIONS = {
    "cannot", "can't", "disabled", "doesn't", "false", "never", "no", "not",
    "without",
}
_POLARITY_TERMS = {
    "active", "allowed", "available", "disabled", "enabled", "false",
    "forbidden", "inactive", "off", "on", "required", "true", "unavailable",
}
_OPPOSITE_PAIRS = (
    ({"enabled"}, {"disabled"}),
    ({"active"}, {"inactive"}),
    ({"available"}, {"unavailable"}),
    ({"allowed"}, {"forbidden"}),
    ({"true", "on"}, {"false", "off"}),
)


class EvidenceRelation(str, Enum):
    DUPLICATE = "DUPLICATE"
    CORROBORATES = "CORROBORATES"
    CONTRADICTS = "CONTRADICTS"
    SUPERSEDES = "SUPERSEDES"


@dataclass(frozen=True)
class ClaimObservation:
    observation_id: str
    chunk_id: str
    source_version_id: str
    logical_source_id: str
    locator: str | None
    text: str
    normalized_text: str


@dataclass(frozen=True)
class EvidenceRelationRecord:
    relation_id: str
    relation: EvidenceRelation
    left_observation_id: str
    right_observation_id: str
    left_chunk_id: str
    right_chunk_id: str
    reason: str


@dataclass(frozen=True)
class ReconciliationResult:
    observations: tuple[ClaimObservation, ...]
    relations: tuple[EvidenceRelationRecord, ...]
    unresolved_conflicts: tuple[EvidenceRelationRecord, ...]
    supersessions: tuple[EvidenceRelationRecord, ...]
    duplicates: tuple[EvidenceRelationRecord, ...]
    corroborations: tuple[EvidenceRelationRecord, ...]
    independent_source_count: int

    def to_dict(self) -> dict:
        return asdict(self)


def _normalize(text: str) -> str:
    return " ".join(text.casefold().split())


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


def _clean_token(token: str) -> str:
    return token.strip(".,;:!?()[]{}")


def _tokens(text: str) -> set[str]:
    return {
        _stem(_clean_token(token))
        for token in _TOKEN_RE.findall(text)
        if _clean_token(token)
    }


def _topic_tokens(text: str) -> set[str]:
    values = set()
    for token in _TOKEN_RE.findall(text):
        cleaned = _clean_token(token)
        if not cleaned or _NUMBER_RE.fullmatch(cleaned):
            continue
        stem = _stem(cleaned)
        if (
            stem in _STOPWORDS
            or stem in _NEGATIONS
            or stem in _POLARITY_TERMS
        ):
            continue
        values.add(stem)
    return values


def _similarity(left: str, right: str) -> float:
    a = _topic_tokens(left)
    b = _topic_tokens(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _contradiction_reason(left: str, right: str) -> str | None:
    similarity = _similarity(left, right)
    if similarity < 0.5:
        return None

    left_numbers = set(_NUMBER_RE.findall(left))
    right_numbers = set(_NUMBER_RE.findall(right))
    if left_numbers and right_numbers and left_numbers != right_numbers and similarity >= 0.6:
        return "same topic contains incompatible numeric values"

    left_tokens = _tokens(left)
    right_tokens = _tokens(right)
    left_negated = bool(left_tokens & _NEGATIONS)
    right_negated = bool(right_tokens & _NEGATIONS)
    if left_negated != right_negated and similarity >= 0.6:
        return "same topic differs by explicit negation"

    for positive, negative in _OPPOSITE_PAIRS:
        if (
            (left_tokens & positive and right_tokens & negative)
            or (left_tokens & negative and right_tokens & positive)
        ):
            return "same topic uses opposing state terms"

    return None


class EvidenceReconciler:
    """Classify relationships among claims present in retrieved evidence."""

    def __init__(self, evidence_index: LocalEvidenceIndex) -> None:
        self.index = evidence_index
        self.connection = evidence_index.connection
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS evidence_relations (
                relation_id TEXT PRIMARY KEY,
                relation TEXT NOT NULL,
                left_observation_id TEXT NOT NULL,
                right_observation_id TEXT NOT NULL,
                left_chunk_id TEXT NOT NULL,
                right_chunk_id TEXT NOT NULL,
                reason TEXT NOT NULL
            )
            """
        )

    def _version_metadata(self, source_version_id: str) -> tuple[str, str | None]:
        try:
            row = self.connection.execute(
                """
                SELECT logical_source_id, valid_from
                FROM source_version_metadata
                WHERE source_version_id = ?
                """,
                (source_version_id,),
            ).fetchone()
        except sqlite3.OperationalError:
            row = None
        if row is None:
            return source_version_id, None
        return str(row["logical_source_id"]), str(row["valid_from"])

    def _observations(
        self, candidates: tuple[RetrievalCandidate, ...]
    ) -> tuple[ClaimObservation, ...]:
        values: list[ClaimObservation] = []
        seen: set[tuple[str, str]] = set()

        for candidate in candidates:
            logical_source_id, _valid_from = self._version_metadata(
                candidate.source_version_id or ""
            )
            for raw in _SENTENCE_RE.split(candidate.text):
                sentence = " ".join(raw.strip().split())
                if len(_TOKEN_RE.findall(sentence)) < 3:
                    continue
                normalized = _normalize(sentence)
                dedupe_key = (candidate.source_version_id or "", normalized)
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                values.append(
                    ClaimObservation(
                        observation_id=stable_id(
                            "claim-observation",
                            candidate.source_version_id or "",
                            normalized,
                        ),
                        chunk_id=candidate.chunk_id,
                        source_version_id=candidate.source_version_id or "",
                        logical_source_id=logical_source_id,
                        locator=candidate.locator,
                        text=sentence,
                        normalized_text=normalized,
                    )
                )
        return tuple(values)

    def _supersession_order(
        self,
        left: ClaimObservation,
        right: ClaimObservation,
    ) -> tuple[ClaimObservation, ClaimObservation] | None:
        if left.logical_source_id != right.logical_source_id:
            return None
        _left_source, left_valid = self._version_metadata(left.source_version_id)
        _right_source, right_valid = self._version_metadata(right.source_version_id)
        if not left_valid or not right_valid or left_valid == right_valid:
            return None
        if left_valid > right_valid:
            return left, right
        return right, left

    @staticmethod
    def _record(
        relation: EvidenceRelation,
        left: ClaimObservation,
        right: ClaimObservation,
        reason: str,
    ) -> EvidenceRelationRecord:
        return EvidenceRelationRecord(
            relation_id=stable_id(
                "evidence-relation",
                relation.value,
                left.observation_id,
                right.observation_id,
            ),
            relation=relation,
            left_observation_id=left.observation_id,
            right_observation_id=right.observation_id,
            left_chunk_id=left.chunk_id,
            right_chunk_id=right.chunk_id,
            reason=reason,
        )

    def reconcile(
        self,
        candidates: tuple[RetrievalCandidate, ...],
    ) -> ReconciliationResult:
        observations = self._observations(candidates)
        relations: list[EvidenceRelationRecord] = []

        for left, right in combinations(observations, 2):
            if left.normalized_text == right.normalized_text:
                if left.logical_source_id == right.logical_source_id:
                    relations.append(
                        self._record(
                            EvidenceRelation.DUPLICATE,
                            left,
                            right,
                            "same normalized claim from the same logical source",
                        )
                    )
                else:
                    relations.append(
                        self._record(
                            EvidenceRelation.CORROBORATES,
                            left,
                            right,
                            "same normalized claim appears in independent logical sources",
                        )
                    )
                continue

            contradiction = _contradiction_reason(left.text, right.text)
            if contradiction is None:
                continue

            supersession = self._supersession_order(left, right)
            if supersession is not None:
                newer, older = supersession
                relations.append(
                    self._record(
                        EvidenceRelation.SUPERSEDES,
                        newer,
                        older,
                        f"{contradiction}; newer version supersedes older version",
                    )
                )
            else:
                relations.append(
                    self._record(
                        EvidenceRelation.CONTRADICTS,
                        left,
                        right,
                        contradiction,
                    )
                )

        with self.connection:
            for item in relations:
                self.connection.execute(
                    """
                    INSERT OR REPLACE INTO evidence_relations (
                        relation_id, relation, left_observation_id,
                        right_observation_id, left_chunk_id, right_chunk_id, reason
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item.relation_id,
                        item.relation.value,
                        item.left_observation_id,
                        item.right_observation_id,
                        item.left_chunk_id,
                        item.right_chunk_id,
                        item.reason,
                    ),
                )

        unresolved = tuple(
            item for item in relations if item.relation == EvidenceRelation.CONTRADICTS
        )
        supersessions = tuple(
            item for item in relations if item.relation == EvidenceRelation.SUPERSEDES
        )
        duplicates = tuple(
            item for item in relations if item.relation == EvidenceRelation.DUPLICATE
        )
        corroborations = tuple(
            item for item in relations if item.relation == EvidenceRelation.CORROBORATES
        )

        return ReconciliationResult(
            observations=observations,
            relations=tuple(relations),
            unresolved_conflicts=unresolved,
            supersessions=supersessions,
            duplicates=duplicates,
            corroborations=corroborations,
            independent_source_count=len(
                {item.logical_source_id for item in observations if item.logical_source_id}
            ),
        )
