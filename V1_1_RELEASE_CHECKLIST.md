# Witness V1.1 Release Checklist

This checklist is the final gate for the V1.1 post-release hardening release.
Feature work is complete only when the referenced evidence remains green on the
release candidate commit.

## Product slices

| Slice | Gate | Status |
| --- | --- | --- |
| 0 · Release presentation | README exposes installer, checksum, release notes, verification | Complete |
| 1 · Library lifecycle | Archive/restore/version-chain UX preserves evidence/history | Complete |
| 2 · First-run/install UX | Installed launch -> RPC -> normal exit -> uninstall smoke | Complete |
| 3 · Backup/recovery | Integrity-checked export/restore + fail-closed validation | Complete |
| 4 · Large corpus | 2,000-file baseline, cancellation, repair, reopen cycles | Complete |
| 5 · Quality | Fixed regression corpus; final routed baseline passes 8/8 | Complete |
| 6 · Semantic provider | Optional local-only semantic projection; hash baseline preserved | Complete |
| 7 · Distribution | Metadata guards, release notes/changelog, signing/update policy | Complete |

## Compatibility

The release candidate must preserve:

- source-version and evidence IDs;
- QueryRun/Trace history;
- Lab and Attack history;
- V1 provider settings, including in-place provider-table migration;
- deterministic hash retrieval without optional dependencies;
- backup/restore portability and no persisted secrets.

Relevant coverage includes:

- `engine/tests/test_source_lifecycle.py`;
- `engine/tests/test_backup_restore.py`;
- `engine/tests/test_provider_config.py`;
- `engine/tests/test_workspace_recovery.py`;
- `engine/tests/test_rpc_desktop_e2e.py`.

## Measured baselines

### Large corpus

Stress Benchmark run `35431097813`:

- 2,000 files;
- 8,569 chunks;
- ~50 MB database;
- ~18 files/second hosted-runner import;
- cancellation rollback healthy;
- derived-index repair preserved protected state;
- five healthy reopen/query cycles.

### Retrieval/evidence quality

Quality Baseline run `35439951846` using immutable dataset fingerprint
`2f427210f2f8349e63ce8a5c3241f53727c0ab4a3e5136f7016a146a61aef513`
and corpus fingerprint
`177bfdcc4e5e689fc38b211d265de43e43fd559ef2ccb53ccfbc592134529955`:

- 8/8 routed cases passed;
- Recall@K 1.0;
- MRR 1.0;
- citation precision 1.0;
- state accuracy 1.0;
- abstention correctness 1.0;
- contradiction handling 1.0;
- expected-answer fragment accuracy 1.0;
- unsupported-claim rate 0.0.

## Final release-candidate gate

Before tagging `v1.1.0`:

- [x] Set every release-facing version to `1.1.0`:
  - Tauri app;
  - desktop npm package;
  - Rust desktop crate;
  - Python engine package;
  - Python runtime `__version__`.
- [x] `python tools/check-version-metadata.py` passes.
- [x] `python tools/check-distribution-metadata.py` passes.
- [x] Draft marker is removed from `RELEASE_NOTES_v1.1.0.md`.
- [x] `CHANGELOG.md` moves V1.1 from Unreleased to `1.1.0`.
- [x] README download/checksum/release-note links target `v1.1.0`.
- [x] Engine tests · Ubuntu pass.
- [x] Engine tests · Windows pass.
- [x] Generated RPC contracts pass.
- [x] Desktop TypeScript/build passes.
- [x] Windows Rust/Tauri host check passes.
- [x] Frozen sidecar + installed NSIS smoke passes.
- [x] PR #15 was marked ready and merged at verified head `d9f82353`.

## Publication gate

After the release candidate is merged to `main`:

- [x] `main` CI is green on merge commit `e398fbdc` and publication commit `37940db5`.
- [x] Tag `v1.1.0` points at verified `main` publication commit `37940db5`.
- [x] The one-shot Windows publication workflow passed version/tag and distribution metadata guards.
- [x] `Witness_1.1.0_x64-setup.exe` is published.
- [x] `SHA256SUMS.txt` is published.
- [x] Checked-in `RELEASE_NOTES_v1.1.0.md` is used for the release body.
- [x] Published installer SHA-256 is `d092c31bc2888fa8d4d35e2cb4a26af7a925fe4a4bb96c496e4524f952fc267c`, matching `SHA256SUMS.txt`.
- [x] Release page and README links target the published `v1.1.0` assets.

## Signing and updates

Code signing is **not** a V1.1 blocker because no signing identity is currently
provisioned. The unsigned state must remain disclosed. The signing plan is
documented in `docs/distribution.md` and must be implemented once a trusted
identity is available.

V1.1 performs no automatic update checks. Updating remains an explicit user
action through GitHub Releases. No background network request is introduced by
the release.


## Publication record

- Release: https://github.com/purysho/Witness/releases/tag/v1.1.0
- Published: 2026-09-19
- Installer size: 31,615,762 bytes
- Installer SHA-256: `d092c31bc2888fa8d4d35e2cb4a26af7a925fe4a4bb96c496e4524f952fc267c`
- Release publication workflow: `35446617835`
- Publication commit CI: `35446617801` — success
