# ADR 0002 — SQLite + content-addressed blobs + pluggable local vector index

**Status:** Accepted

## Context
Witness needs local-first persistence, historical source versions, exact provenance, lexical search, graph relationships, and vector retrieval without requiring hosted infrastructure.

## Decision
Use:
- SQLite in WAL mode for canonical metadata, FTS5 lexical search, evidence graph edges, query runs, and evaluation records;
- a SHA-256 content-addressed blob store for immutable imported source versions;
- a pluggable local vector-index adapter, initially backed by HNSW;
- derived index artifacts keyed by source/index configuration fingerprints.

## Consequences
- V1 requires no hosted database, graph database, or vector service.
- Original source versions remain immutable and deduplicated.
- Vector indexes are disposable/rebuildable rather than authoritative.
- Historical query runs can retain exact source/index snapshot identities.
