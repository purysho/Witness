# Phase 2 — Hybrid Retrieval Gate

This branch adds the first dense-retrieval path without weakening Witness' evidence guarantees.

Goals:

- provider-neutral embedding contract;
- persistent local float32 vector store tied to immutable chunk IDs;
- exact cosine retrieval as the deterministic baseline;
- hybrid BM25 + dense retrieval;
- Reciprocal Rank Fusion (RRF);
- inspectable retrieval traces showing per-route ranks and fused scores;
- deterministic tests with a local test embedder;
- optional Sentence Transformers provider for real local semantic embeddings.

The initial vector search is exact rather than approximate. HNSW is an optimization milestone after the retrieval contract and evaluation baseline are stable.
