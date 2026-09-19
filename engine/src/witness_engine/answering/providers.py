"""Provider-neutral answer generation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from ..evidence.sufficiency import SufficiencyState
from ..retrieval.query import analyze_query
from .context import ContextPack
from .models import GeneratedAnswer, GeneratedSentence

_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+|\n+")
_TOKEN_RE = re.compile(r"[A-Za-z0-9_./:#'-]+", re.UNICODE)
_QUERY_GENERIC = {
    "a", "an", "and", "are", "as", "at", "be", "by", "did", "do", "does",
    "for", "from", "give", "how", "in", "is", "it", "me", "of", "on", "or",
    "please", "show", "tell", "that", "the", "their", "this", "to", "was",
    "were", "what", "when", "where", "which", "who", "why", "with",
}


class GenerationProvider(Protocol):
    @property
    def provider_id(self) -> str: ...

    def generate(self, context: ContextPack) -> GeneratedAnswer: ...


def _first_sentence(text: str) -> str:
    for raw in _SENTENCE_RE.split(text):
        sentence = " ".join(raw.strip().split())
        if sentence:
            return sentence
    return " ".join(text.strip().split())


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


def _query_terms(question: str) -> set[str]:
    return {
        _stem(token)
        for token in _TOKEN_RE.findall(question)
        if token.casefold() not in _QUERY_GENERIC
    }


def _sentence_terms(text: str) -> set[str]:
    return {_stem(token) for token in _TOKEN_RE.findall(text)}


def _best_sentence(question: str, text: str) -> tuple[str, float]:
    query_terms = _query_terms(question)
    candidates: list[tuple[float, int, int, str]] = []
    for position, raw in enumerate(_SENTENCE_RE.split(text)):
        sentence = " ".join(raw.strip().split())
        if not sentence:
            continue
        terms = _sentence_terms(sentence)
        overlap = len(query_terms & terms)
        score = overlap / len(query_terms) if query_terms else 0.0
        candidates.append((score, len(terms), -position, sentence))
    if not candidates:
        return " ".join(text.strip().split()), 0.0
    score, _term_count, _position, sentence = max(candidates)
    return sentence, float(score)


@dataclass(frozen=True)
class DeterministicExtractiveGenerationProvider:
    """Offline reference generator used to prove grounding and citation plumbing.

    It intentionally extracts rather than paraphrases. Witness can later attach
    richer model providers to the same structured contract without weakening
    citation validation or evidence-state handling.
    """

    max_sentences: int = 3

    @property
    def provider_id(self) -> str:
        return "deterministic-extractive-generator:v1"

    def generate(self, context: ContextPack) -> GeneratedAnswer:
        if context.sufficiency_state == SufficiencyState.INSUFFICIENT:
            return GeneratedAnswer(
                state=context.sufficiency_state,
                sentences=(
                    GeneratedSentence(
                        "The available evidence is insufficient to answer this question.",
                        (),
                    ),
                ),
            )

        by_id = context.evidence_by_id()
        if (
            context.sufficiency_state == SufficiencyState.CONFLICTED
            and context.unresolved_conflicts
        ):
            conflict = context.unresolved_conflicts[0]
            left = by_id[conflict.left_evidence_id]
            right = by_id[conflict.right_evidence_id]
            return GeneratedAnswer(
                state=context.sufficiency_state,
                sentences=(
                    GeneratedSentence(
                        (
                            "Conflicting evidence reports: "
                            f"{_first_sentence(left.text)} / {_first_sentence(right.text)}"
                        ),
                        (left.evidence_id, right.evidence_id),
                    ),
                ),
            )

        scored: list[tuple[float, int, str, str]] = []
        for item in context.evidence:
            text, relevance = _best_sentence(context.question, item.text)
            if text:
                scored.append(
                    (relevance, -item.rank, item.evidence_id, text)
                )

        features = analyze_query(context.question)
        scored.sort(key=lambda row: (-row[0], -row[1], row[2]))
        if scored and not features.broad_summary:
            best = scored[0][0]
            if best > 0:
                scored = [
                    row for row in scored
                    if row[0] >= best * 0.75
                ]

        sentences: list[GeneratedSentence] = []
        seen_text: set[str] = set()
        for _relevance, _rank, evidence_id, text in scored:
            normalized = text.casefold()
            if normalized in seen_text:
                continue
            seen_text.add(normalized)
            sentences.append(GeneratedSentence(text, (evidence_id,)))
            if len(sentences) >= max(self.max_sentences, 1):
                break

        if not sentences:
            return GeneratedAnswer(
                state=SufficiencyState.INSUFFICIENT,
                sentences=(
                    GeneratedSentence(
                        "The available evidence is insufficient to answer this question.",
                        (),
                    ),
                ),
            )

        return GeneratedAnswer(
            state=context.sufficiency_state,
            sentences=tuple(sentences),
        )
