"""Structured generation and validated answer contracts."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from ..evidence.sufficiency import SufficiencyState


@dataclass(frozen=True)
class GeneratedSentence:
    text: str
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class GeneratedAnswer:
    state: SufficiencyState
    sentences: tuple[GeneratedSentence, ...]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class AnswerSentence:
    text: str
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class Citation:
    evidence_id: str
    chunk_id: str
    source_version_id: str
    locator: str | None


@dataclass(frozen=True)
class ValidatedAnswer:
    state: SufficiencyState
    sentences: tuple[AnswerSentence, ...]
    citations: tuple[Citation, ...]

    def to_dict(self) -> dict:
        return asdict(self)
