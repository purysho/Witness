# Witness V1 Release Checklist

This checklist maps the 14 acceptance criteria in `SPECIFICATION.md` to concrete
automated tests and release gates. A criterion is not considered complete merely
because the feature exists; the referenced test/gate must pass on the release
candidate commit.

## Acceptance criteria

| # | V1 criterion | Automated evidence | Status |
|---|---|---|---|
| 1 | Create a workspace and ingest a mixed local corpus. | `engine/tests/test_rpc_desktop_e2e.py`; `engine/tests/test_v1_ingestion_targets.py` covers PDF/Markdown/text/HTML/DOCX/PPTX/XLSX/CSV registry targets and representative parser retrieval. | Covered |
| 2 | Detect unchanged files; changed files create new source versions. | `engine/tests/test_local_evidence_index.py::test_identical_reindex_is_idempotent` and `::test_modified_file_creates_new_source_version`; demo idempotence in `test_first_run_demo.py`. | Covered |
| 3 | Lexical + dense retrieval share one normalized candidate contract. | `engine/tests/test_hybrid_pipeline.py::test_document_to_hybrid_candidates_with_trace`; `test_hybrid_retrieval.py`; `test_vector_retrieval.py`. | Covered |
| 4 | Fusion and reranking are recorded in Trace. | `engine/tests/test_ask_trace.py::test_ask_loop_returns_cited_answer_and_persists_append_only_trace`; `test_routing_reranking.py`. | Covered |
| 5 | Ask produces an evidence-constrained answer or abstains. | `test_ask_trace.py`; `test_reconciliation_sufficiency.py::test_unrelated_evidence_is_insufficient`; RAG Lab abstention case in `test_rag_lab.py`. | Covered |
| 6 | Material answer sentences map to precise evidence spans. | `test_ask_trace.py::test_ask_loop_returns_cited_answer_and_persists_append_only_trace` verifies generated sentence evidence IDs resolve to ContextPack evidence; ingestion/retrieval tests verify stable source locators. | Covered |
| 7 | Trace shows why evidence was selected and what was dropped. | `test_ask_trace.py` checks the full route/retrieval/fusion/rerank/reconciliation/sufficiency/generation/validation stage sequence; retrieval-specific trace tests live in `test_specialized_retrieval.py` and `test_routing_reranking.py`. | Covered |
| 8 | Contradictory evidence is surfaced instead of silently hidden. | `test_reconciliation_sufficiency.py::test_independent_numeric_claims_produce_visible_conflict`; `test_ask_trace.py::test_conflicted_ask_does_not_silently_blend_incompatible_values`. | Covered |
| 9 | Current versus historical source versions can be distinguished. | `test_specialized_retrieval.py::test_temporal_retrieval_selects_version_valid_in_requested_year`; `test_reconciliation_sufficiency.py::test_versioned_numeric_claim_is_resolved_as_supersession`; first-run demo temporal chain. | Covered |
| 10 | Lab runs repeatable benchmarks and compares two configurations. | `test_rag_lab.py::test_lab_runner_persists_metrics_and_case_trace_links` and `::test_lab_compares_all_retrieval_modes_and_exports_json_csv`; multimodal Lab coverage in `test_multimodal_lab.py`. | Covered |
| 11 | Attack demonstrates prompt injection, stale source, distractor, and contradiction tests. | `test_attack_lab.py::test_all_public_attack_fixtures_are_schema_valid` requires fixtures covering every `AttackKind`; isolation, prompt-control-flow, duplicate-poisoning, citation, reopen, export, and reproducibility tests live in the same file. | Covered |
| 12 | Core logic has deterministic tests independent of paid model calls. | The engine CI suite uses deterministic embedding/reranking/generation baselines; Ubuntu + Windows `pytest` jobs run without paid provider credentials. | Covered |
| 13 | First-run demo demonstrates ingestion through evidence Trace. | `engine/tests/test_first_run_demo.py` verifies temporal ingestion, Ask/citations, production Trace stages, Lab registration/run, Attack manifest registration, idempotence, and reopen. | Covered |
| 14 | Windows package runs without a developer environment. | `packaged-sidecar-smoke` builds the PyInstaller sidecar and NSIS package; `tools/smoke-sidecar.py` verifies frozen-engine persistence; `tools/smoke-installed.ps1` requires a successful installed desktop → Rust → bundled-engine RPC round trip. | Covered |

## Phase 8 hardening gates

The following are additional release gates beyond the numbered acceptance list:

- **Cross-platform engine tests:** Ubuntu + Windows Python 3.12 jobs are green.
- **Generated contracts:** `python tools/generate-contracts.py --check` is green.
- **Desktop frontend:** TypeScript typecheck/build is green.
- **Tauri host:** Windows `cargo check` is green.
- **Workspace recovery:** `test_workspace_recovery.py` corrupts disposable indexes and proves repair preserves protected evidence/history; canonical visual corruption fails closed.
- **Cancellation:** `test_cancellable_jobs.py` verifies import rollback, cancelled Lab state, and interrupted-task recovery.
- **Provider configuration:** `test_provider_config.py` verifies settings survive reopen, changed vector identity requires reindex, and secrets have no persistence column/path.
- **Multimodal evidence:** `test_multimodal_evidence.py` and `test_multimodal_lab.py` cover provenance-safe visual evidence, visual retrieval/citations, viewer RPC, and Lab scoring.
- **Attack isolation:** canonical corpus fingerprints are checked before/after success and failure paths.
- **Release artifact:** NSIS installer is smoke-tested after installation; release workflow emits SHA-256 checksums and supports tagged GitHub releases.

## Release-candidate rule

Phase 8 / Witness V1 may be marked complete only when the final branch head—not
an earlier feature commit—passes all six CI jobs:

1. engine tests · Ubuntu;
2. engine tests · Windows;
3. generated RPC contracts;
4. desktop web build;
5. Windows Rust/Tauri host check;
6. packaged sidecar + NSIS installed-app smoke.

After that green head, update `ROADMAP.md` and `README.md`, make PR #10 ready for
review, run CI once more on the status-only commit, and merge without bypassing
required checks.
