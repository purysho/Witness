# Witness RAG Lab

RAG Lab evaluates the same retrieval, reconciliation, sufficiency, generation, citation-validation, and Trace pipeline used by Ask.

## Dataset contract

Evaluation datasets are versioned JSON documents with schema version 1.

Each case may define:

- a stable case ID;
- a question;
- zero or more gold evidence selectors;
- an expected sufficiency state;
- optional answer text fragments;
- optional tags.

Gold evidence selectors may use chunk ID, visual-evidence ID, source-version ID, source locator, source path, or a conjunction of those fields. Visual-evidence IDs are the strongest selector for multimodal cases; source-version + page-region locator is useful for portable fixtures. Source paths may be full paths or suffixes such as docs/architecture.md. A case with no gold evidence is useful for abstention tests.

Datasets are stored by a content-addressed fingerprint. Registering edited content creates a new immutable dataset snapshot rather than silently changing historical Lab runs.

## Configuration snapshots

Every run persists:

- retrieval mode: lexical, dense, hybrid, or routed;
- top K;
- candidate pool;
- rerank pool;
- RRF K;
- whether reranking is enabled;
- chunk-size configuration recorded for comparison;
- embedding provider identity;
- reranker identity;
- generation provider identity;
- corpus fingerprint.

The corpus fingerprint is calculated from the ordered immutable text chunk/source/locator projection and, when present, the ordered visual-evidence/source/modality/locator/asset-hash projection. A run therefore records both the benchmark snapshot and the full text/visual evidence snapshot it evaluated. Routed multimodal runs additionally record the visual embedding provider identity; fixed lexical, dense, and hybrid baselines remain text-only.

## Objective metrics

RAG Lab currently calculates deterministic metrics only.

- Recall@K: fraction of gold evidence references matched by the final top-K candidates.
- Precision@K: fraction of returned top-K candidates that match at least one gold evidence reference.
- MRR: reciprocal rank of the first gold-matching candidate.
- nDCG@K: binary relevance discounted cumulative gain against an ideal ordering.
- Citation precision: fraction of answer citations that resolve to gold evidence.
- Citation coverage: fraction of gold evidence references reached by final answer citations.
- Unsupported-claim rate: fraction of returned answer sentences whose cited evidence does not match the case gold evidence. This is an objective gold-reference proxy, not a semantic model judgment.
- Abstention correctness: whether INSufficient vs non-insufficient behavior matches the expected state.
- Contradiction handling: whether CONFLICTED vs non-conflicted behavior matches the expected state.
- State accuracy: exact sufficiency-state match.
- Latency: wall-clock case execution time.
- Cost: provider cost delta when a provider exposes a numeric cost meter. Local deterministic providers are explicitly recorded as cost unavailable rather than assigned invented prices.

Model-judged metrics are stored separately and are empty unless a future explicit judge provider is configured. They are never mixed into the objective metric table.

## Benchmark modes

Lexical, dense, and hybrid are fixed baselines. Routed uses the production transparent router, including temporal, graph, and hierarchical routes when the query warrants them.

All modes still pass through the same reconciliation, sufficiency, context, generation, citation validation, and append-only Trace machinery.

## Persistence and failed-case analysis

Lab persists datasets, configuration snapshots, run summaries, per-case metrics, and the complete Ask result for each case. Every successful case therefore retains its query-run ID and can be opened directly in Trace.

A/B comparison requires the same dataset fingerprint. It reports metric A, metric B, delta B minus A, and a case-level diff. Failed cases retain separate Trace links for each configuration.

## Export

Completed runs can be exported as JSON or CSV. Default desktop exports are written under the workspace exports directory.

JSON preserves the run configuration, aggregate metrics, per-case metrics, and Ask results. CSV is a flat case-level metric export suitable for external analysis.


## Multimodal Lab cases

Phase 7 extends the existing objective metrics rather than defining a separate visual scorecard. A gold reference may identify an immutable visual region by `visual_evidence_id` or by the same conjunctive source-version / source-path / locator selectors used for text.

The fixed lexical, dense, and hybrid modes remain Phase 5 text baselines. Routed mode may execute the visual route when the query contains an explicit visual signal and the workspace has a visual index/provider. Visual candidates then use the same Recall@K, Precision@K, MRR, nDCG, citation precision, and citation coverage calculations because their provenance is represented in the shared retrieval-candidate contract.

This makes a useful regression experiment possible: run the same visual benchmark once with a fixed text-only baseline and once with routed multimodal retrieval, then inspect the metric delta and both traces.
