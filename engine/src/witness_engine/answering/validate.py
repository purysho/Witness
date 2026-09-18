"""Citation and grounding validation for generated answers."""

from __future__ import annotations

import re

from ..evidence.sufficiency import SufficiencyState
from .context import ContextPack
from .models import AnswerSentence, Citation, GeneratedAnswer, ValidatedAnswer

_TOKEN_RE = re.compile(r"[A-Za-z0-9_./:#'-]+", re.UNICODE)
_GENERIC = {
    "a", "an", "and", "are", "as", "at", "available", "evidence", "for", "from",
    "in", "is", "it", "of", "on", "or", "reports", "the", "this", "to", "was",
    "were", "with",
}


class AnswerValidationError(ValueError):
    pass


def _content_tokens(text: str) -> set[str]:
    return {
        token.casefold()
        for token in _TOKEN_RE.findall(text)
        if token.casefold() not in _GENERIC
    }


def validate_generation(
    context: ContextPack,
    generated: GeneratedAnswer,
) -> ValidatedAnswer:
    """Reject invented citations and obviously unsupported factual sentences."""

    if generated.state != context.sufficiency_state:
        raise AnswerValidationError(
            "generated answer state does not match the evidence sufficiency state"
        )

    evidence = context.evidence_by_id()
    answer_sentences: list[AnswerSentence] = []
    used_ids: list[str] = []

    for sentence in generated.sentences:
        text = " ".join(sentence.text.strip().split())
        if not text:
            continue

        unknown = [item for item in sentence.evidence_ids if item not in evidence]
        if unknown:
            raise AnswerValidationError(
                f"generated answer referenced unknown evidence IDs: {unknown}"
            )

        if (
            generated.state != SufficiencyState.INSUFFICIENT
            and not sentence.evidence_ids
        ):
            raise AnswerValidationError(
                "material answer sentences must cite at least one context evidence ID"
            )

        if sentence.evidence_ids:
            cited_text = " ".join(evidence[item].text for item in sentence.evidence_ids)
            sentence_tokens = _content_tokens(text)
            cited_tokens = _content_tokens(cited_text)
            if sentence_tokens and not sentence_tokens.intersection(cited_tokens):
                raise AnswerValidationError(
                    "answer sentence has no lexical support in its cited evidence"
                )

        unique_ids = tuple(dict.fromkeys(sentence.evidence_ids))
        answer_sentences.append(AnswerSentence(text=text, evidence_ids=unique_ids))
        for evidence_id in unique_ids:
            if evidence_id not in used_ids:
                used_ids.append(evidence_id)

    if not answer_sentences:
        raise AnswerValidationError("generation produced no answer sentences")

    citations = tuple(
        Citation(
            evidence_id=evidence_id,
            chunk_id=evidence[evidence_id].chunk_id,
            source_version_id=evidence[evidence_id].source_version_id,
            locator=evidence[evidence_id].locator,
        )
        for evidence_id in used_ids
    )

    return ValidatedAnswer(
        state=generated.state,
        sentences=tuple(answer_sentences),
        citations=citations,
    )
