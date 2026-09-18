# Witness fixtures

Synthetic fixtures used for deterministic ingestion, retrieval, evaluation, and adversarial testing.

Fixture groups:
- `demo-corpus/` — small human-readable corpus for first-run demos and golden E2E tests;
- `eval/` — benchmark cases with gold evidence/sufficiency expectations;
- `attacks/` — schema-v1 adversarial manifests for prompt injection, stale evidence, high-similarity distractors, duplicate poisoning, conflicting sources, altered near-duplicates, and citation bait.

Fixtures must contain synthetic/public-safe data only. No private corpora or credentials belong in this repository.


The eval directory includes text and multimodal schema-v1 benchmark examples. Gold evidence may identify chunks, visual-evidence IDs, immutable source versions, locators, source path suffixes, or a conjunction of those selectors.


Attack fixtures embed their synthetic document payload directly in the manifest so the manifest fingerprint fully identifies the experiment. They are intended to be registered against a compatible Lab dataset and executed only through Attack Lab isolation.
