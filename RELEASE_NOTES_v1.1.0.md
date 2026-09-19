# Witness v1.1.0

Witness v1.1 is a post-release hardening release. It keeps the V1 local-first,
evidence-first architecture while improving everyday source management,
recovery, scale, retrieval quality, provider choice, and Windows distribution.

## Daily-driver improvements

- Library source lifecycle: inspect immutable version chains, archive a source
  version without deleting evidence/history, and restore it later.
- Clear ACTIVE / HISTORICAL / ARCHIVED states and confirmation UX.
- Improved first-launch, workspace, empty-state, import, and Ask guidance.
- Installed Windows smoke now covers launch, bundled-engine RPC, normal exit,
  sidecar shutdown, and real uninstall.

## Backup and recovery

- Portable workspace backups containing a versioned manifest and coherent SQLite
  backup.
- SHA-256 and protected-state fingerprint validation.
- Restore into a new empty workspace only.
- Bounded archive sizes and strict two-entry ZIP layout prevent traversal or
  surprise payloads.
- Secrets remain outside workspace backups.

## Large-corpus robustness

The default Windows stress baseline completed with:

- 2,000 mixed-format source files;
- 8,569 chunks;
- ~50 MB workspace database;
- ~18 files/second import throughput on the hosted runner;
- healthy cancellation rollback;
- deterministic derived-index repair;
- five healthy reopen/query cycles.

The measured ~33.6-second derived-index repair time is retained as a future
optimization baseline rather than hidden behind an unmeasured rewrite.

## Search and evidence quality

V1.1 adds an immutable quality regression dataset spanning exact facts,
duplicates, temporal evidence, contradictions, abstention, graph retrieval, and
hierarchical summaries.

The final routed baseline passed 8/8 cases with:

- Recall@K 1.0;
- MRR 1.0;
- citation precision 1.0;
- state accuracy 1.0;
- abstention correctness 1.0;
- contradiction handling 1.0;
- expected-answer fragment accuracy 1.0;
- unsupported-claim rate 0.0.

## Optional semantic embeddings

The deterministic hash provider remains the guaranteed offline baseline.

V1.1 additionally supports the optional local-only
`sentence-transformers/all-MiniLM-L6-v2` text embedding provider when its
dependency and model are already installed/cached. Witness will not silently
download the model.

Provider changes use distinct vector projections. Unavailable semantic providers
fail closed without corrupting canonical evidence, and workspaces remain
inspectable/back-up-able if an optional model later disappears.

## Distribution

- Release-facing version metadata is checked for consistency.
- Tagged releases fail if the Git tag does not match embedded metadata.
- NSIS product/publisher/install-mode/icon metadata is validated in CI.
- Draft release notes can be published directly by the tagged release workflow.
- Automatic update checks remain disabled in V1.1; releases remain explicit
  user downloads with SHA-256 verification.
- Code signing remains pending a signing identity. See
  [docs/distribution.md](docs/distribution.md).

## Compatibility

V1.1 preserves existing source-version/evidence IDs, QueryRun/Trace history,
Lab/Attack history, and existing V1 provider settings. Legacy provider settings
tables migrate in place.
