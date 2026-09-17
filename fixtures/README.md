# Witness fixtures

Synthetic fixtures used for deterministic ingestion, retrieval, evaluation, and adversarial testing.

Planned groups:
- `demo-corpus/` — small human-readable corpus for first-run demos and golden E2E tests;
- `eval/` — benchmark cases with gold evidence/sufficiency expectations;
- `attacks/` — prompt injection, stale-source, contradiction, distractor, duplication, and malformed-input fixtures.

Fixtures must contain synthetic/public-safe data only. No private corpora or credentials belong in this repository.
