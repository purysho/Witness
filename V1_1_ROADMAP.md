# Witness V1.1 — Post-release hardening roadmap

Witness v1.0.0 is released. V1.1 is a focused daily-driver hardening release,
not a new architectural phase and not an excuse to weaken the V1 provenance
boundary.

## Post-release audit — 2026-09-19

Verified from the published repository/release state:

- `v1.0.0` is a public GitHub release.
- `Witness_1.0.0_x64-setup.exe` and `SHA256SUMS.txt` are attached.
- GitHub's release asset metadata reports the installer digest as
  `7f563b8620026dfe64b4bc4021a6bca090e805f8ddf654c552af38ed01040832`.
- the release publication workflow succeeded after the earlier release-path
  failure was corrected;
- `main` CI is green;
- the README needed a clear download/install/checksum path and still described
  the shipped build as a release candidate;
- several old phase/release branches remain. They are cleanup candidates, but
  branch deletion is intentionally not treated as product work;
- first-run demo and fail-closed derived-index repair already exist;
- the original audit found no normal-user workspace backup/restore flow; this
  gap is now closed on the V1.1 branch;
- the original audit found no dedicated large-corpus stress/benchmark suite;
  this gap is now closed on the V1.1 branch;
- RAG Lab provides the right mechanism for quality work, so retrieval tuning
  should be benchmark-driven rather than speculative;
- deterministic offline providers remain the V1 baseline;
- code signing and an update-delivery mechanism are not yet configured.

The release asset metadata verifies the bytes GitHub received. An independent
clean-machine download + rehash remains a useful release-operations check, but
is separate from application correctness.

## Compatibility rules

- Existing V1 workspaces must open without destructive migration.
- Existing source-version IDs, evidence IDs, QueryRun/Trace history, Lab runs,
  Attack runs, and provider snapshots must remain resolvable.
- Lifecycle controls may change what participates in **new** retrieval runs,
  but may not rewrite historical runs or delete evidence behind old citations.
- Workspace backups may not persist API keys or environment secrets.
- Optional semantic providers must remain provider-explicit in Trace/Lab and
  fail closed when unavailable.
- Deterministic offline behavior remains available.
- Every product slice must pass the full six-job Windows/Linux CI matrix before
  the next product slice is stacked.

---

## Slice 0 — Release presentation and cleanup

**Goal:** make the existing v1.0.0 release straightforward to discover, install,
and verify.

Deliverables:
- prominent README download link;
- checksum verification instructions;
- release notes linked from the README;
- shipped/released wording instead of release-candidate wording;
- identify obsolete phase/release branches for deletion when a delete-ref
  operation is available.

Exit gate:
- a user arriving at the repository can find the Windows installer, checksum,
  release notes, and verification command without reading internal docs.

**Status:** documentation cleanup implemented on the V1.1 branch.

---

## Slice 1 — Library lifecycle

**Goal:** make source management usable without destructive deletion.

Deliverables:
- source-version detail RPC with version-chain/provenance metadata;
- archive/restore operations for source versions;
- archived versions excluded from ordinary current retrieval by default;
- explicit historical retrieval can still resolve archived evidence;
- prior QueryRun/Trace citations remain resolvable after archive;
- Library UI shows active/historical/archived state and version relationships;
- confirmation UX for archive/restore;
- deterministic lifecycle tests across reopen.

Exit gate:
- archiving a current source removes its logical source from new normal answers
  without deleting chunks/evidence/history;
- Witness does not silently promote an older superseded version;
- restoring the current version returns it to normal retrieval;
- an old Trace still resolves the same evidence;
- version chains remain internally consistent.

**Status:** backend and desktop lifecycle UX implemented on the V1.1 branch.

---

## Slice 2 — Real-user installation and first-run UX

**Goal:** test Witness as a new user rather than as a developer who knows its
architecture.

Work through the exact flow:

```text
install
  -> first launch
  -> choose/create workspace
  -> optional demo
  -> import evidence
  -> Ask
  -> Trace
  -> close/reopen
  -> uninstall
```

Deliverables:
- unambiguous create/open-workspace wording and empty states;
- useful first-launch guidance without requiring architecture knowledge;
- clear import success/failure/cancellation feedback;
- layout checks at the supported minimum window size;
- clean reopen behavior for the last workspace;
- installed-app and uninstaller rough-edge checklist;
- automated coverage where behavior can be tested deterministically.

Exit gate:
- a clean-machine user can complete the evidence loop without repository docs or
  developer tooling.

**Status:** implemented and verified on the V1.1 branch. The installed Windows
smoke now covers install -> launch -> bundled-engine RPC -> normal desktop exit
-> sidecar termination -> uninstall, and the first-run/empty-workspace UI has
explicit create/open/demo/import guidance.

---

## Slice 3 — Workspace backup, restore, and recovery UX

**Goal:** make a Witness workspace safely portable and recoverable by a normal
user.

Deliverables:
- backup/export command using SQLite backup semantics;
- versioned manifest containing schema/version, checksums, and metadata;
- portable archive with bounded file count/size and path-traversal defense;
- restore into a new empty workspace location;
- no secret/environment values exported;
- desktop Backup / Restore flow;
- recovery guidance that distinguishes repairable derived indexes from protected
  canonical evidence damage;
- export -> restore -> reopen equivalence tests.

Exit gate:
- a backup restores with the same source-version IDs, evidence IDs,
  QueryRun/Trace history, Lab/Attack records, and provider identifiers;
- checksums detect tampering;
- malformed/path-traversal archives fail closed without modifying destination.

**Status:** implemented and verified on the V1.1 branch. Backups contain only a
versioned manifest plus a coherent SQLite backup, verify checksums and the
protected-state fingerprint, reject unexpected/path-traversal entries and
non-empty restore destinations, and are exposed through the desktop Backup /
Restore flow.

---

## Slice 4 — Large-corpus robustness

**Goal:** prove the daily-driver application stays safe and usable under realistic
corpus load.

Deliverables:
- generated stress corpus covering thousands of files and large PDF/Office mixes;
- import throughput and reopen-time measurement;
- memory/high-water instrumentation suitable for CI or reproducible local runs;
- cancellation under sustained ingestion;
- index rebuild/repair under large corpus state;
- repeated reopen/query cycles;
- bounded failure reporting instead of frozen UI;
- regression thresholds documented separately from machine-dependent raw speed.

Exit gate:
- stress runs complete without provenance loss or corrupt partial state;
- cancellation remains responsive and rollback invariants hold;
- reopen/repair behavior remains deterministic;
- baseline performance measurements are captured for future regression checks.

**Status:** complete and verified on the V1.1 branch. The default Windows
baseline completed successfully with 2,000 source files across all nine stress
formats, including 40 enlarged Office/PDF documents. It produced 2,000 source
versions and 8,569 chunks in a ~50 MB workspace, imported at ~18 files/second,
remained healthy, rolled back a sustained-ingestion cancellation cleanly,
repaired a deliberately broken derived FTS projection without changing the
protected-state fingerprint, and passed five reopen/query cycles. Baseline
artifact: Stress Benchmark run 35431097813. Repair took ~33.6 seconds on the
hosted Windows runner and is retained as a performance baseline rather than a
correctness failure.

---

## Slice 5 — Lab-driven search and evidence quality

**Goal:** improve retrieval only when objective evaluation shows the change is
better.

Benchmark areas:
- routing;
- chunk sizing;
- candidate-pool / Top-K;
- reranking;
- duplicate handling;
- temporal reconciliation;
- contradiction behavior;
- visual retrieval where current V1 visual evidence applies.

Deliverables:
- representative regression datasets;
- named baseline configuration for v1.0.0 behavior;
- controlled A/B runs for each proposed change;
- no quality tuning merged without measured evidence;
- retained failure cases linked to Trace.

Exit gate:
- accepted tuning has reproducible objective gains or a documented tradeoff;
- unsupported-claim, citation, contradiction, and abstention metrics do not
  regress silently.

**Status:** complete and benchmarked on the V1.1 branch. The immutable
`witness-v1-1-quality-regression-v1` dataset (fingerprint
`2f427210f2f8349e63ce8a5c3241f53727c0ab4a3e5136f7016a146a61aef513`)
covers exact facts, duplicate evidence, current/historical temporal retrieval,
contradiction handling, abstention, graph retrieval, and hierarchical summary
retrieval. Against the unchanged corpus fingerprint
`177bfdcc4e5e689fc38b211d265de43e43fd559ef2ccb53ccfbc592134529955`,
the final routed baseline passed 8/8 cases with Recall@K 1.0, MRR 1.0,
citation precision 1.0, state accuracy 1.0, abstention correctness 1.0,
contradiction handling 1.0, answer-fragment accuracy 1.0, and unsupported-claim
rate 0. Accepted changes were driven by repeated runs of the same dataset:
duplicate-safe nDCG scoring, query-scoped contradiction reconciliation,
a stricter abstention boundary, focused deterministic extraction, structural
broad-summary generation, and explicit hierarchical covered-locator provenance.
The final benchmark is Quality Baseline run `35439951846`.

---

## Slice 6 — Optional semantic providers

**Goal:** add genuine semantic retrieval/generation capability without replacing
the deterministic offline baseline.

Deliverables:
- provider-explicit semantic text embedding adapter;
- local/offline provider first where practical;
- provider/model identity recorded in configuration snapshots and Trace;
- provider change creates a distinct derived projection rather than mixing vectors;
- unavailable provider cannot corrupt canonical evidence;
- UI reports availability and reindex requirements;
- credentials remain outside workspace state, traces, backups, and exports.

Exit gate:
- Lab can compare deterministic-hash and semantic retrieval as distinct configs;
- unavailable providers fail clearly and leave the workspace healthy;
- deterministic mode remains fully usable.

---

## Slice 7 — Distribution polish

**Goal:** make the released Windows application easier to trust and maintain.

Deliverables:
- code-signing plan and CI integration when a signing identity is available;
- SmartScreen/reputation guidance;
- verified icon/product/version metadata;
- maintained changelog/release notes;
- explicit update-check design;
- automatic updates only if they preserve local-first/security expectations and
  fail safely.

Exit gate:
- release artifacts carry correct metadata and verification information;
- update behavior is explicit and does not silently weaken workspace safety.

---

## Deferred breadth

Broader multimodal ingestion (standalone image files and embedded DOCX/PPTX image
extraction) is useful, but it is not ahead of installation UX, backup, corpus
robustness, measured retrieval quality, or distribution hardening. Treat it as a
V1.2 candidate unless a concrete V1.1 user problem makes it necessary.

## V1.1 release gate

V1.1 is complete only when:

1. the post-release user journey is verified;
2. backup/restore and large-corpus hardening meet their exit gates;
3. accepted retrieval changes have Lab evidence;
4. existing V1 workspaces pass compatibility tests;
5. the V1 acceptance checklist remains green;
6. the final head passes all six CI jobs:
   - engine tests · Ubuntu;
   - engine tests · Windows;
   - generated RPC contracts;
   - desktop web build;
   - Windows Rust/Tauri host check;
   - frozen sidecar + NSIS installed-app smoke;
7. version metadata is bumped only during final release preparation.

## Out of scope for V1.1

- cloud sync/accounts;
- collaborative multi-user workspaces;
- arbitrary agent/tool execution from retrieved evidence;
- destructive evidence deletion as a normal Library action;
- weakening provenance or citation requirements for model convenience.
