"""Provider-neutral answer generation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from ..evidence.sufficiency import SufficiencyState
from .context import ContextPack
from .models import GeneratedAnswer, GeneratedSentence

_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+|\n+")


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

        sentences: list[GeneratedSentence] = []
        seen_text: set[str] = set()
        for item in context.evidence:
            text = _first_sentence(item.text)
            normalized = text.casefold()
            if not text or normalized in seen_text:
                continue
            seen_text.add(normalized)
            sentences.append(GeneratedSentence(text, (item.evidence_id,)))
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
