# Witness V1.1 Roadmap

V1.1 is a focused daily-driver upgrade to the released V1 evidence system.
It does not replace the V1 architecture or weaken provenance guarantees.

## Compatibility rules

- Existing V1 workspaces must open without destructive migration.
- Existing source-version IDs, evidence IDs, QueryRun/Trace history, Lab runs,
  Attack runs, and provider snapshots must remain resolvable.
- New lifecycle controls may change what participates in **new** retrieval runs,
  but may not rewrite historical runs or delete evidence behind old citations.
- Workspace exports/imports may not persist API keys or environment secrets.
- Optional semantic or multimodal providers must remain provider-explicit in
  Trace/Lab and must fail closed when unavailable.
- Every V1.1 slice lands separately and must pass the full six-job Windows/Linux
  release matrix before the next slice is stacked.

---

## Slice 1 — Library lifecycle

**Goal:** make the Library manageable without turning source management into
destructive deletion.

Deliverables:
- source-version detail RPC with version-chain/provenance metadata;
- archive/restore operations for source versions;
- archived versions excluded from ordinary current retrieval by default;
- historical/explicit retrieval can still resolve archived versions when required;
- prior QueryRun/Trace citations remain resolvable after archive;
- Library UI shows active/archived state and version relationships;
- confirmation UX for archive/restore;
- deterministic lifecycle tests across reopen.

Exit gate:
- archiving a current source removes it from new normal answers without deleting
  chunks/evidence/history;
- restoring it returns it to normal retrieval;
- an old Trace from before archive still opens and resolves the same evidence;
- version chains remain internally consistent.

---

## Slice 2 — Workspace backup and portability

**Goal:** make a Witness workspace safely portable between machines.

Deliverables:
- workspace backup/export command using SQLite backup semantics;
- versioned manifest containing workspace schema/version, checksums, and metadata;
- portable archive format with bounded file count/size and path-traversal defense;
- restore/import into a new empty workspace location;
- no secret/environment values exported;
- desktop Backup / Restore flow;
- export → restore → reopen equivalence tests.

Exit gate:
- a backed-up workspace restores on a clean location with the same source-version
  IDs, evidence IDs, QueryRun/Trace history, Lab/Attack records, and provider
  identifiers;
- checksums detect tampering;
- malformed/path-traversal archives fail closed without modifying the destination.

---

## Slice 3 — Multimodal breadth

**Goal:** extend provenance-safe visual evidence beyond PDF-only extraction.

Deliverables:
- standalone PNG/JPEG/WebP evidence ingestion;
- embedded image extraction from PPTX and DOCX where deterministic source
  locators can be preserved;
- visual source preview for those formats;
- visual retrieval/citation contracts shared with existing PDF-region evidence;
- fixture corpus and objective Lab cases for mixed text + image retrieval.

Exit gate:
- a standalone image or embedded document image can be retrieved and cited with
  an exact source/version/visual locator;
- Trace identifies the visual route/provider that selected it;
- no visual answer bypasses the evidence/citation validator.

---

## Slice 4 — Optional semantic text embeddings

**Goal:** add a real semantic text embedding path without making V1.1 depend on
paid/network providers.

Deliverables:
- provider-explicit semantic text embedding adapter;
- local/offline provider first; remote providers remain optional;
- provider/model identity recorded in configuration snapshots and Trace;
- provider change triggers a new derived projection rather than mixing vectors;
- missing model/provider failure cannot corrupt canonical evidence;
- provider settings UI reports availability and reindex requirements;
- deterministic fallback remains available.

Exit gate:
- the same Lab dataset can compare deterministic-hash and semantic dense
  retrieval as distinct configurations;
- unavailable semantic providers fail clearly and leave the workspace healthy;
- no credentials are stored in workspace state, traces, exports, or backups.

---

## V1.1 release gate

V1.1 is complete only when:

1. all four slices meet their individual exit gates;
2. existing V1 workspaces reopen and pass compatibility tests;
3. the V1 acceptance checklist remains green;
4. the final head passes all six CI jobs:
   - engine tests · Ubuntu;
   - engine tests · Windows;
   - generated RPC contracts;
   - desktop web build;
   - Windows Rust/Tauri host check;
   - frozen sidecar + NSIS installed-app smoke;
5. version metadata is bumped only during final release preparation.

## Out of scope for V1.1

- cloud sync/accounts;
- collaborative multi-user workspaces;
- arbitrary agent/tool execution from retrieved evidence;
- destructive evidence deletion as a normal Library action;
- weakening provenance or citation requirements to broaden model support.
