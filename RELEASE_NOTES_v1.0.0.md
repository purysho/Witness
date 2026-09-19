# Witness v1.0.0

Witness v1.0.0 is the first complete V1 release of the evidence-first RAG workbench.

## What ships

- Local-first Library, Ask, Trace, Graph, Lab, and Attack desktop surfaces.
- Structured ingestion for PDF, Markdown, plain text, local HTML, DOCX, PPTX, XLSX, CSV, and common source-code files.
- Lexical, dense, graph, temporal, hierarchical, and provenance-safe visual retrieval.
- Evidence reconciliation, contradiction surfacing, source-version supersession, sufficiency states, and abstention.
- Sentence-level citations tied to exact evidence identities and source locators.
- Append-only QueryRun/Trace history covering routing, retrieval, fusion, reranking, reconciliation, generation, and citation validation.
- RAG Lab with reproducible datasets/configuration snapshots, objective metrics, A/B comparison, regression history, Trace-linked failures, and JSON/CSV export.
- Attack Lab with isolated attacked corpus snapshots, clean-vs-attacked comparison, prompt-injection/stale-source/distractor/poisoning/conflict/citation-bait fixtures, and explicit security invariants.
- Multimodal PDF evidence with page-region provenance, visual routing, visual-gold Lab evaluation, citations, and evidence inspection.
- Cancellable imports, Lab runs, and Attack runs with crash-visible task state and rollback of partially created source versions.
- Fail-closed workspace health and repair for disposable lexical/dense/graph/visual projections while preserving protected evidence and history.
- Secret-free provider configuration with explicit provider identities and reindex signalling.
- Deterministic first-run demo data that demonstrates versioned ingestion → Ask → citations → Trace, plus Lab and Attack assets.

## Windows release

The Windows release is packaged as a current-user NSIS installer and bundles the frozen Witness engine, so a Python or developer environment is not required.

The release CI verifies:

1. engine tests on Ubuntu;
2. engine tests on Windows;
3. generated RPC contracts;
4. desktop TypeScript/build;
5. Windows Rust/Tauri host compilation;
6. frozen-engine persistence and an installed desktop → Rust → bundled-engine RPC round trip.

The tagged release workflow also generates `SHA256SUMS.txt` for the Windows installer.

## Provider boundary

The packaged V1 baseline guarantees the dependency-free deterministic providers. Optional semantic embedding/vision providers remain explicit extras and are not represented as available unless their dependencies/models are actually present.

Witness workspace configuration does not persist API secrets.

## Evidence and safety boundary

Imported files, metadata, extracted text, links, images, model output, provider errors, evaluation fixtures, and Attack Lab content are untrusted input. Retrieved text is evidence, never executable instruction.

Attack Lab mutations operate on isolated derived snapshots and do not mutate the canonical corpus automatically.

## Validation

The V1 acceptance mapping is documented in [`V1_RELEASE_CHECKLIST.md`](V1_RELEASE_CHECKLIST.md). All 14 acceptance criteria in [`SPECIFICATION.md`](SPECIFICATION.md) have automated test or release-gate coverage.

## Version

- Desktop package: `1.0.0`
- Tauri application: `1.0.0`
- Rust desktop crate: `1.0.0`
- Python engine package: `1.0.0`
