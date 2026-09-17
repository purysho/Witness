"""Transparent, deterministic retrieval routing."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from .query import QueryFeatures, analyze_query


@dataclass(frozen=True)
class RouteDecision:
    route: str
    requested: bool
    executable: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class RetrievalPlan:
    query: str
    features: QueryFeatures
    routes: tuple[RouteDecision, ...]

    def decision(self, route: str) -> RouteDecision:
        for item in self.routes:
            if item.route == route:
                return item
        raise KeyError(route)

    def should_run(self, route: str) -> bool:
        decision = self.decision(route)
        return decision.requested and decision.executable

    @property
    def advisory_routes(self) -> tuple[str, ...]:
        return tuple(
            item.route
            for item in self.routes
            if item.requested and not item.executable
        )

    def to_dict(self) -> dict:
        return asdict(self)


class TransparentRetrievalRouter:
    """Rule-based baseline whose decisions are reproducible and inspectable.

    V1 routes are explicit and mechanical. Lexical, dense, temporal, graph, and
    hierarchical retrieval are all executable; the router records why each route
    was requested instead of hiding the decision in a model call.
    """

    def plan(self, query: str) -> RetrievalPlan:
        features = analyze_query(query)
        if not features.normalized_query:
            return RetrievalPlan(
                query=query,
                features=features,
                routes=tuple(
                    RouteDecision(route, False, True, ("empty query",))
                    for route in (
                        "lexical",
                        "dense",
                        "temporal",
                        "graph",
                        "hierarchical",
                    )
                ),
            )

        lexical_reasons: list[str] = []
        dense_reasons: list[str] = []

        if features.quoted_phrases:
            lexical_reasons.append("quoted phrase favors exact lexical matching")
        if features.identifiers:
            lexical_reasons.append("identifier-like token favors lexical matching")
        if features.exact_lookup:
            lexical_reasons.append("exact lookup signal detected")
        if len(features.tokens) <= 5:
            lexical_reasons.append("short query keeps lexical retrieval active")

        semantic_need = bool(
            features.explanatory
            or features.relational
            or features.broad_summary
            or features.comparison
            or features.temporal_signals
            or not features.exact_lookup
        )
        if features.explanatory:
            dense_reasons.append("explanatory query benefits from semantic matching")
        if features.relational:
            dense_reasons.append("relational language benefits from semantic matching")
        if features.broad_summary:
            dense_reasons.append("broad synthesis query benefits from semantic matching")
        if features.comparison:
            dense_reasons.append("comparison query benefits from semantic matching")
        if features.temporal_signals:
            dense_reasons.append("temporal question keeps semantic coverage alongside version-aware retrieval")
        if not features.exact_lookup:
            dense_reasons.append("no exact-lookup signal; semantic retrieval retained")

        lexical_requested = True
        dense_requested = semantic_need or not lexical_reasons

        temporal_reasons = (
            ("temporal/version signal detected",)
            if features.temporal_signals
            else ("no temporal signal detected",)
        )
        graph_reasons = (
            ("relational or multi-hop signal detected",)
            if features.relational
            else ("no relational signal detected",)
        )
        hierarchical_reasons = (
            ("broad summary/theme signal detected",)
            if features.broad_summary
            else ("no broad summary signal detected",)
        )

        return RetrievalPlan(
            query=query,
            features=features,
            routes=(
                RouteDecision(
                    "lexical",
                    lexical_requested,
                    True,
                    tuple(lexical_reasons or ["lexical baseline retained"]),
                ),
                RouteDecision(
                    "dense",
                    dense_requested,
                    True,
                    tuple(dense_reasons or ["exact compact lookup does not require dense retrieval"]),
                ),
                RouteDecision(
                    "temporal",
                    bool(features.temporal_signals),
                    True,
                    temporal_reasons,
                ),
                RouteDecision(
                    "graph",
                    features.relational,
                    True,
                    graph_reasons,
                ),
                RouteDecision(
                    "hierarchical",
                    features.broad_summary,
                    True,
                    hierarchical_reasons,
                ),
            ),
        )
