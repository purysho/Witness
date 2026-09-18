"""Provider-neutral claim/entity extraction for the evidence graph."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+|\n+")
_TOKEN_RE = re.compile(r"[A-Za-z0-9_./:#-]+", re.UNICODE)
_ENTITY_RE = re.compile(
    r"\b(?:[A-Z][A-Za-z0-9_-]*(?:\s+[A-Z][A-Za-z0-9_-]*)+|[A-Z]{2,}[A-Z0-9_-]*|[A-Za-z]+[-_][A-Za-z0-9_-]+)\b"
)
_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "because", "been", "by", "for",
    "from", "has", "have", "how", "in", "is", "it", "of", "on", "or", "that",
    "the", "their", "this", "to", "was", "were", "what", "when", "where", "which",
    "who", "why", "with",
}


@dataclass(frozen=True)
class ExtractedClaim:
    text: str
    entities: tuple[str, ...]


class ClaimExtractionProvider(Protocol):
    @property
    def provider_id(self) -> str: ...

    def extract(self, text: str) -> tuple[ExtractedClaim, ...]: ...


@dataclass(frozen=True)
class DeterministicClaimExtractionProvider:
    """Network-free baseline used by indexing and CI.

    A learned extractor may replace this provider without changing graph storage
    or retrieval contracts.
    """

    @property
    def provider_id(self) -> str:
        return "deterministic-claim-extractor:v1"

    def _entities(self, text: str) -> tuple[str, ...]:
        values: list[str] = []
        for match in _ENTITY_RE.finditer(text):
            name = " ".join(match.group(0).split())
            if name and name.casefold() not in _STOPWORDS:
                values.append(name)
        for token in _TOKEN_RE.findall(text):
            lowered = token.casefold()
            if lowered in _STOPWORDS:
                continue
            if any(char in token for char in ("_", "-", "/", ":", "#")) or (
                any(char.isdigit() for char in token)
                and any(char.isalpha() for char in token)
            ):
                values.append(token)
        return tuple(dict.fromkeys(values))

    def extract(self, text: str) -> tuple[ExtractedClaim, ...]:
        claims: list[ExtractedClaim] = []
        for raw in _SENTENCE_RE.split(text):
            sentence = " ".join(raw.strip().split())
            if len(_TOKEN_RE.findall(sentence)) < 3:
                continue
            claims.append(
                ExtractedClaim(
                    text=sentence,
                    entities=self._entities(sentence),
                )
            )
        return tuple(claims)
