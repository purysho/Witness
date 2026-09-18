# Witness Attack Lab

**Phase 6 status: Complete — 2026-09-18**

Attack Lab measures how the production Witness pipeline changes when adversarial evidence is introduced into an isolated clone of a canonical corpus.

## Isolation boundary

Attack experiments never insert adversarial evidence into the canonical corpus.

For every run Witness:

1. fingerprints the canonical corpus;
2. creates a transactionally consistent SQLite snapshot using the SQLite backup API;
3. materializes attack documents under `.witness/attacks/<attack-run-id>/artifacts`;
4. ingests those documents through the normal parser, chunker, lexical index, embeddings, temporal metadata, hierarchy and graph projections;
5. runs the same RAG Lab dataset/configuration against the clean and attacked corpora;
6. fingerprints the canonical corpus again;
7. records an explicit invariant result proving whether canonical evidence changed.

The attack snapshot is retained so attacked QueryRuns and traces remain inspectable. Attack artifacts cannot automatically become canonical evidence.

Attack source identities are synthetic and deterministic (`attack://...`) rather than derived from the random per-run filesystem directory. Repeating the same manifest against the same canonical corpus therefore reproduces the same attacked corpus fingerprint even though each physical snapshot remains isolated. Mutations without an explicit `valid_from` receive a deterministic fallback timestamp rather than inheriting a run-specific file modification time.

## Manifest contract

Attack manifests are schema-versioned, content-addressed JSON. A mutation contains the exact synthetic document content, which makes the manifest fingerprint independent of an external fixture file changing later.

Supported Phase 6 attack kinds:

- prompt injection;
- stale evidence;
- high-similarity distractors;
- duplicate poisoning;
- conflicting sources;
- altered near-duplicates;
- citation bait.

A mutation may create multiple copies for duplicate-poisoning experiments and may assign a `valid_from` timestamp for temporal/staleness attacks.

## Deterministic invariants

The first invariant layer supports:

- `canonical_corpus_unchanged`;
- `forbidden_answer_text_absent`;
- `expected_state`;
- `gold_recall_not_reduced`;
- `max_independent_source_delta`, which prevents repeated copies of one poisoned document from masquerading as many independent sources;
- `citations_resolve_to_context`, which rejects citation-shaped bait that does not resolve to the actual context pack.

Every run also records a structural `pipeline_configuration_unchanged` result comparing retrieval settings plus embedding, reranker, and generator provider identities between clean and attacked executions.

Invariant results are separate from normal RAG metrics and use PASS / FAIL / NOT_APPLICABLE states.

## Execution model

Attack Lab does not implement a second retrieval or answer engine.

Clean and attacked runs both execute through `EvalRunner`, which itself uses the production Ask pipeline. The Attack layer owns only snapshot isolation, adversarial materialization, comparison, invariant evaluation, and persistence metadata.


## Duplicate poisoning hardening

Exact-content duplicate documents are collapsed when Witness calculates independent source count. This is stricter than comparing paths: five byte/content-identical copies under five different filenames do not become five independent corroborating sources.

The reconciler still distinguishes genuinely different source documents that happen to support the same claim.

## Persistence and export

Attack manifests and completed run results persist in the canonical workspace, while attacked evidence remains confined to its snapshot database. Persisted results contain both clean and attacked Ask artifacts, including their full structured Trace, so either side can be reopened after restarting Witness without promoting attack evidence into the canonical corpus.

Attack runs export to JSON or CSV. JSON preserves the complete run, clean/attacked evaluation results, case diffs, invariants, corpus fingerprints, configuration, and snapshot identity. CSV emits case and invariant rows for external analysis.
