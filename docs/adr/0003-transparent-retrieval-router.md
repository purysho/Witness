# ADR 0003 — Transparent routing before learned routing

**Status:** Accepted

## Context
Witness is intended to expose why retrieval happened. Making the first routing layer an opaque model call would weaken that goal and make evaluation harder.

## Decision
V1 starts with a deterministic, inspectable rule-based retrieval router.

Examples:
- quoted phrases / identifiers -> lexical emphasis;
- semantic explanatory questions -> lexical + dense hybrid;
- relational/multi-hop language -> graph expansion;
- date/current/history language -> temporal route;
- broad summary/theme requests -> hierarchical route.

Every decision emits structured route reasons into Trace.

A learned or LLM router may be added later as another strategy and benchmarked against the transparent baseline in Lab.

## Consequences
- routing behavior is reproducible and easy to debug;
- the system has a strong baseline for future learned routing experiments;
- early routing may be less flexible than an LLM classifier, but failures are observable rather than mysterious.
