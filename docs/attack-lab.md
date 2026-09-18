# Witness Attack Lab

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
- `gold_recall_not_reduced`.

Invariant results are separate from normal RAG metrics and use PASS / FAIL / NOT_APPLICABLE states.

## Execution model

Attack Lab does not implement a second retrieval or answer engine.

Clean and attacked runs both execute through `EvalRunner`, which itself uses the production Ask pipeline. The Attack layer owns only snapshot isolation, adversarial materialization, comparison, invariant evaluation, and persistence metadata.
