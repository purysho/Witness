# Witness engine

The Python engine owns all evidence-domain behavior and is testable without the desktop app or network access.

Current capabilities:

- immutable source-version and chunk identities;
- structured local ingestion for text, Markdown, PDF, DOCX, and source code;
- SQLite FTS5/BM25 lexical retrieval with provenance;
- persistent dense vectors keyed by immutable chunk IDs and embedding-provider identity;
- exact cosine search as the deterministic vector baseline;
- BM25 + dense hybrid retrieval through Reciprocal Rank Fusion (RRF);
- deterministic query understanding and transparent route selection;
- executable temporal retrieval over version-validity intervals and supersession chains;
- executable hierarchical retrieval that expands matched evidence through document structure;
- executable claim/evidence graph retrieval with deterministic claim extraction and entity expansion;
- provider-neutral reranking with deterministic and optional local cross-encoder implementations;
- deterministic evidence reconciliation for duplicates, corroboration, contradictions, and temporal supersession;
- explicit `SUFFICIENT`, `PARTIAL`, `CONFLICTED`, and `INSUFFICIENT` evidence states;
- structured context packs, citation-ID validation, and a provider-neutral generation contract;
- first complete Ask loop with sentence-level evidence IDs and persisted append-only Trace events;
- serializable retrieval traces showing route reasons, specialized-route artifacts, RRF contributions, and pre/post-rerank positions;
- persisted RAG Lab datasets and runs with content-addressed dataset/corpus/configuration snapshots;
- lexical-only, dense-only, hybrid, and routed benchmark execution over the production Ask pipeline;
- objective retrieval, citation, abstention, contradiction, latency, and cost-availability metrics plus A/B comparison and JSON/CSV export;
- isolated Attack Lab snapshots, content-addressed attack manifests, clean-vs-attacked execution, poisoning-aware source independence, deterministic invariants, persisted attack traces, and JSON/CSV export.

## Specialized retrieval

Every import now builds several local projections from the same immutable evidence:

```text
SourceVersion
   ├── chunks -> FTS5 / BM25
   ├── chunks -> dense vectors
   ├── valid_from / valid_to / supersession -> temporal index
   ├── block parent/child structure -> hierarchy index
   └── deterministic claims -> claim/evidence graph
```

Temporal metadata is version-aware. `index_document(..., valid_from=...)` may supply an explicit validity start; otherwise Witness records the file modification time as the baseline. Later versions of the same source path form a supersession chain without deleting earlier evidence.

The graph uses a provider-neutral `ClaimExtractionProvider`. The default deterministic implementation treats sentence-level propositions as claims and records explicit `claim -> supporting chunk` edges plus entity anchors. A learned extractor can replace the provider without changing graph storage or retrieval contracts.

Hierarchical retrieval preserves parser structure. Markdown headings, for example, can retrieve their child paragraphs as coherent context rather than forcing every answer to rely on isolated chunks.

## Local semantic embeddings

Core tests use dependency-free deterministic fixture providers. For real local semantic retrieval and optional cross-encoder reranking, install the optional embedding stack:

```bash
python -m pip install -e ".[embeddings]"
```

Then use `SentenceTransformerEmbeddingProvider`, which defaults to `sentence-transformers/all-MiniLM-L6-v2`. The model is loaded lazily; Witness never requires model downloads merely to run its core test suite.

```python
from witness_engine.pipeline import index_document, search_routed_evidence
from witness_engine.retrieval import (
    CrossEncoderReranker,
    LocalEvidenceIndex,
    LocalVectorIndex,
    SentenceTransformerEmbeddingProvider,
)

provider = SentenceTransformerEmbeddingProvider()
reranker = CrossEncoderReranker()

with LocalEvidenceIndex("witness.sqlite3") as lexical, \
     LocalVectorIndex("witness.sqlite3") as vectors:
    index_document(
        "report.pdf",
        lexical,
        vector_index=vectors,
        embedding_provider=provider,
        valid_from="2026-09-01T00:00:00+00:00",
    )
    result = search_routed_evidence(
        "Summarize how deployment dependencies changed after 2025 across all documents",
        lexical,
        vectors,
        provider,
        reranker=reranker,
    )

    print(result.candidates)
    print(result.trace.to_dict())
```

For a compact exact lookup such as `What port is "auth-api"?`, the transparent router can execute lexical retrieval alone. Explanatory, relational, comparison, broad-summary, or temporal questions activate the relevant specialized routes. Trace records the exact route plan, temporal source selection, hierarchy expansion, claim/entity graph expansion, fusion contributions, and reranking movement.

The exact vector scan is intentional at this stage. HNSW/ANN will be introduced as an optimization only after the Lab has a stable evaluation baseline that can quantify recall and latency changes.


## Evidence reconciliation and Ask

`ask_evidence(...)` is the first complete engine-side RAG loop. It performs routed retrieval, reconciles the selected evidence, decides an explicit sufficiency state, builds a structured context pack, generates a structured answer, validates every cited evidence ID, and persists the run as append-only trace events.

The default generator is intentionally extractive and deterministic. It exists as a network-free reference implementation for CI and Lab, not as a claim of answer-writing quality. Richer generation providers must use the same context and validation contracts.

A run records these stages:

```text
query.received
query.normalized
route.decided
retrieval.lexical.completed
retrieval.dense.completed
retrieval.temporal.completed
retrieval.hierarchical.completed
retrieval.graph.completed
fusion.completed
rerank.completed
evidence.reconciled
sufficiency.decided
context.built
generation.completed
answer.validated
run.completed
```

Trace payloads are versioned structured artifacts with stable event IDs: route decisions, per-route candidate lists, temporal selections, hierarchy expansions, graph paths, fusion/rerank movement, evidence relations, sufficiency features, context evidence IDs, and citation mappings. They do not contain hidden chain-of-thought.


## RAG Lab

The evaluation package treats benchmarks as immutable evidence-engineering artifacts. Dataset content is fingerprinted, each run records the corpus fingerprint and exact retrieval/provider configuration, and every case retains its QueryRun trace.

Objective metrics currently include Recall@K, Precision@K, MRR, nDCG@K, citation precision, citation coverage, an objective gold-reference unsupported-claim proxy, abstention correctness, contradiction handling, exact sufficiency-state accuracy, and latency. Cost is recorded when a provider exposes a numeric cost meter; local deterministic providers are explicitly marked as unmetered.

Model-judged metrics have a separate field and are not mixed with objective metrics. See docs/evaluation.md.


## Attack Lab

Attack Lab is an orchestration layer around the production evaluation and Ask pipeline, not a second RAG implementation. It clones the canonical SQLite database with the SQLite backup API, materializes synthetic untrusted documents in a separate attack namespace, indexes them normally, and compares the same dataset/configuration against clean and attacked corpora.

Attack evidence uses deterministic synthetic identity keys so repeated executions of the same manifest against the same canonical corpus reproduce the same attacked corpus fingerprint despite per-run physical snapshot paths. Exact-content duplicate sources are collapsed for independent-source counting to make duplicate-poisoning amplification visible rather than treating copies as corroboration.

See `docs/attack-lab.md`.
