# Changelog

All notable Witness changes are recorded here.

## [Unreleased] — V1.1

### Added
- Source-version details, immutable version-chain inspection, archive/restore, and
  explicit ACTIVE / HISTORICAL / ARCHIVED Library states.
- First-run and empty-workspace UX for the normal install -> workspace -> import
  -> Ask -> Trace path.
- Integrity-checked workspace backup/restore with a versioned manifest,
  checksums, protected-state fingerprint verification, and path-traversal
  defenses.
- Mixed-format large-corpus stress harness and Windows benchmark workflow.
- Fixed RAG quality regression dataset and reproducible Quality Baseline
  workflow.
- Optional local-only SentenceTransformer text embeddings with explicit
  provider identity and separate vector projections.
- Release metadata consistency and Windows distribution metadata checks.

### Changed
- Installed-package smoke now verifies normal desktop shutdown, sidecar
  termination, and actual NSIS uninstall.
- Evidence reconciliation scopes contradictions to query-relevant claims.
- Deterministic extraction is more focused for direct questions while preserving
  compound multimodal and structural-summary evidence.
- Hierarchical retrieval carries covered-locator provenance through Lab scoring.
- Exact 25% query coverage is treated as insufficient rather than partial.

### Fixed
- Duplicate candidates can no longer inflate nDCG above 1.0.
- Explicit polarity contradictions such as enabled/disabled are detected without
  poisoning unrelated queries.
- The runtime Python package version is synchronized with the released 1.0.0
  package metadata.

## [1.0.0] — 2026-09-19

First public Witness release. See [RELEASE_NOTES_v1.0.0.md](RELEASE_NOTES_v1.0.0.md).
