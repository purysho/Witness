"""Deterministic query feature extraction for transparent retrieval routing."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass


_QUOTED_RE = re.compile(r'"([^"\n]+)"|\'([^\'\n]+)\'')
_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
_TOKEN_RE = re.compile(r"[A-Za-z0-9_./:#-]+", re.UNICODE)

_TEMPORAL_TERMS = {
    "after",
    "before",
    "changed",
    "change",
    "current",
    "currently",
    "earlier",
    "history",
    "historical",
    "latest",
    "later",
    "now",
    "previous",
    "previously",
    "since",
    "today",
    "version",
    "versions",
    "when",
}
_RELATIONAL_TERMS = {
    "affect",
    "affected",
    "because",
    "between",
    "cause",
    "caused",
    "connected",
    "connection",
    "depend",
    "dependency",
    "depends",
    "downstream",
    "impact",
    "influence",
    "related",
    "relationship",
    "upstream",
    "why",
}
_BROAD_TERMS = {
    "all",
    "across",
    "overview",
    "pattern",
    "patterns",
    "summarize",
    "summary",
    "theme",
    "themes",
    "trend",
    "trends",
}
_EXPLANATORY_TERMS = {
    "explain",
    "how",
    "reason",
    "reasons",
    "why",
}
_EXACT_LOOKUP_TERMS = {
    "file",
    "id",
    "identifier",
    "name",
    "path",
    "port",
    "setting",
    "url",
    "value",
    "version",
}


@dataclass(frozen=True)
class QueryFeatures:
    """Structured, serializable features used by the deterministic router."""

    original_query: str
    normalized_query: str
    tokens: tuple[str, ...]
    quoted_phrases: tuple[str, ...]
    identifiers: tuple[str, ...]
    temporal_signals: tuple[str, ...]
    comparison: bool
    relational: bool
    broad_summary: bool
    explanatory: bool
    exact_lookup: bool

    def to_dict(self) -> dict:
        return asdict(self)


def _looks_like_identifier(token: str) -> bool:
    if len(token) < 2:
        return False
    if any(char.isdigit() for char in token):
        return True
    if any(char in token for char in ("_", ".", "/", ":", "#", "-")):
        return True
    if token.isupper() and len(token) > 2:
        return True
    if any(char.isupper() for char in token[1:]) and any(char.islower() for char in token):
        return True
    return False


def analyze_query(query: str) -> QueryFeatures:
    """Extract routing signals without model calls or hidden reasoning."""

    normalized = " ".join(query.strip().split())
    raw_tokens = tuple(_TOKEN_RE.findall(normalized))
    tokens = tuple(token.casefold() for token in raw_tokens)
    token_set = set(tokens)

    quoted: list[str] = []
    for match in _QUOTED_RE.finditer(normalized):
        value = match.group(1) or match.group(2)
        value = " ".join(value.strip().split())
        if value:
            quoted.append(value)

    identifiers = tuple(
        dict.fromkeys(token for token in raw_tokens if _looks_like_identifier(token))
    )

    temporal = set(token_set.intersection(_TEMPORAL_TERMS))
    temporal.update(_YEAR_RE.findall(normalized))

    comparison = bool(
        token_set.intersection({"compare", "comparison", "versus", "vs", "difference", "differences"})
        or "compared to" in normalized.casefold()
    )
    relational = bool(token_set.intersection(_RELATIONAL_TERMS))
    broad_summary = bool(token_set.intersection(_BROAD_TERMS))
    explanatory = bool(token_set.intersection(_EXPLANATORY_TERMS))
    exact_lookup = bool(
        quoted
        or identifiers
        or token_set.intersection(_EXACT_LOOKUP_TERMS)
        or normalized.endswith("?") and len(tokens) <= 7 and "what" in token_set
    )

    return QueryFeatures(
        original_query=query,
        normalized_query=normalized,
        tokens=tokens,
        quoted_phrases=tuple(quoted),
        identifiers=identifiers,
        temporal_signals=tuple(sorted(temporal)),
        comparison=comparison,
        relational=relational,
        broad_summary=broad_summary,
        explanatory=explanatory,
        exact_lookup=exact_lookup,
    )
