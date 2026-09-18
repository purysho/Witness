# Witness — Implementation Roadmap

The build order is deliberately evidence-first. We will not start with a polished chat UI and retrofit provenance later.

**Implementation status (2026-09-18): Phases 3, 4, 5, and 6 complete; Phase 7 in progress.** Witness now has hybrid/specialized retrieval, evidence reconciliation/time/graph behavior, functional Ask/Trace/Graph/Lab/Attack surfaces, reproducible RAG evaluation, isolated adversarial testing, and the first provenance-safe multimodal evidence foundation. Release hardening remains.

## Phase 0 — Specification and contracts

**Goal:** freeze the system boundaries before implementation.

Deliverables:
- product specification;
- technical architecture;
- security model;
- domain vocabulary;
- versioned RPC envelope;
- initial repository skeleton;
- architectural decision records for desktop/engine/storage choices.

Exit gate:
- every V1 feature maps to an owning subsystem;
- evidence/source/version/query-run identities are unambiguous;
- no unresolved architectural decision blocks Phase 1.

---

## Phase 1 — Evidence foundation

**Goal:** build the domain and persistence layer without any LLM dependency.

Deliverables:
- Python package and test harness;
- SQLite schema + migrations;
- workspace create/open/validate;
- content-addressed SHA-256 blob store;
- `Source`, `SourceVersion`, `DocumentBlock`, `Chunk`, `EvidenceSpan`, `IndexSnapshot`, `QueryRun` domain models;
- atomic workspace metadata writes;
- schema forward-version refusal;
- deterministic IDs/fingerprints;
- fixture corpus.

Tests:
- Unicode/space-heavy paths;
- duplicate imports;
- changed file creates new version;
- historical source version remains accessible;
- interrupted write/corrupt metadata recovery;
- forward-schema refusal.

Exit gate:
- a source can be imported twice unchanged without duplication;
- a modified source becomes a new immutable version;
- evidence spans resolve to exact source locations after reopen.

---

## Phase 2 — Structured ingestion + lexical retrieval

**Goal:** prove retrieval and provenance before embeddings.

Deliverables:
- parser adapter interface;
- text/Markdown/PDF first;
- DOCX/PPTX/XLSX/CSV adapters next;
- canonical block model;
- structure-aware chunker;
- SQLite FTS5/BM25 index;
- lexical retriever;
- source preview/locator contracts;
- ingestion job progress/cancellation.

Exit gate:
- mixed fixture corpus can be ingested;
- lexical query returns ranked evidence with exact source/version/locator;
- every retrieval result can be opened back at its evidence location.

---

## Phase 3 — Hybrid retrieval + first Ask/Trace

**Status: Complete — 2026-09-18**

**Goal:** create the first complete RAG loop while keeping every stage visible.

Deliverables:
- embedding provider interface;
- deterministic fake embedding provider for tests;
- production dense embedding provider;
- local vector index adapter;
- dense retriever;
- Reciprocal Rank Fusion;
- transparent retrieval router;
- reranker interface;
- context pack builder;
- generation provider interface;
- structured answer format;
- citation-ID validation;
- append-only query trace;
- first functional `Ask` and `Trace` UI.

Exit gate:
- one question can run lexical + dense retrieval, fuse candidates, generate an answer, and map every material answer sentence to evidence;
- the same run can be inspected stage-by-stage in Trace;
- fake-provider E2E test is deterministic and network-free.

---

## Phase 4 — Evidence reconciliation + time + graph

**Status: Complete — 2026-09-18**

**Goal:** make Witness meaningfully different from ordinary RAG demos.

Deliverables:
- entity model and extraction adapter;
- claim model;
- support/contradiction evidence edges;
- bounded graph retriever;
- temporal metadata and `SUPERSEDES` relationships;
- temporal retriever;
- evidence reconciler;
- explicit sufficiency gate;
- `SUFFICIENT`, `PARTIAL`, `CONFLICTED`, `INSUFFICIENT` states;
- Graph UI;
- current-vs-historical query behavior.

Exit gate:
- a deliberately contradictory versioned corpus produces a visible conflict rather than a silently blended answer;
- a historical question can retrieve an older valid version while a current-state question prefers the active version;
- graph paths always resolve back to source evidence.

---

## Phase 5 — RAG Lab

**Status: Complete — 2026-09-18**

**Goal:** turn Witness into a measurable retrieval engineering workbench.

Deliverables:
- evaluation dataset format;
- gold evidence references;
- configuration snapshots;
- A/B execution;
- Recall@K, Precision@K, MRR, nDCG;
- citation precision/coverage;
- unsupported-claim rate;
- abstention correctness;
- contradiction handling metrics;
- latency/cost capture;
- regression comparison UI;
- JSON/CSV export.

Exit gate:
- the same benchmark can compare lexical-only, dense-only, hybrid, and routed configurations;
- each failed case links directly to its retrieval trace;
- objective and model-judged metrics are visibly separated.

---

## Phase 6 — Attack Lab

**Status: Complete — 2026-09-18**

**Goal:** test the system against adversarial RAG failure modes rather than claiming safety from normal examples.

Deliverables:
- isolated attacked snapshot mechanism;
- prompt-injection fixture;
- stale-document fixture;
- high-similarity distractor fixture;
- duplicate poisoning fixture;
- conflicting-source fixture;
- near-duplicate altered-claim fixture;
- attack diff view: clean vs attacked retrieval/answer/trace;
- expected-invariant assertions.

Exit gate:
- retrieved source instructions cannot alter application/system behavior;
- attacks cannot mutate canonical corpus state;
- attack runs are reproducible and exportable.

---

## Phase 7 — Multimodal evidence

**Goal:** extend the same evidence model to information that text flattening loses.

Deliverables:
- page/image evidence objects;
- PDF page-region locators;
- image/figure extraction;
- visual embedding provider contract;
- table-aware and chart-aware retrieval experiments;
- evidence viewer that highlights visual regions;
- multimodal evaluation fixtures.

Scope rule:
Multimodal work may not bypass provenance. A visual answer must cite a source page/region just as text answers cite spans.

Exit gate:
- a query can retrieve and cite a chart/image region alongside textual evidence;
- Trace shows which modality caused the evidence to be selected.

---

## Phase 8 — Desktop completion + hardening

**Goal:** turn the engine into a reliable daily-driver application.

Deliverables:
- full Library/Ask/Trace/Graph/Lab/Attack navigation;
- Tauri sidecar supervision;
- bounded/cancellable jobs;
- first-run experience;
- provider configuration without persisted secrets;
- recovery from stale/corrupt derived indexes;
- packaged Windows smoke test;
- destructive workspace testing;
- release CI;
- release checklist and artifact checksum.

Exit gate:
- clean-machine packaged Windows test passes;
- core tests do not require external providers;
- failed provider/network calls cannot corrupt workspace state;
- all V1 acceptance criteria in `SPECIFICATION.md` pass.

---

# V1 scope line

Witness V1 must ship the **evidence-first text/document system** completely: structured ingestion, hybrid retrieval, transparent routing, provenance, contradiction/time handling, Graph, Lab, Attack, reliable desktop packaging, and a small multimodal evidence slice if it reaches the same provenance standard.

Multimodal breadth is explicitly allowed to move to V1.1 rather than weakening V1's evidence integrity.

# Release philosophy

A phase is not complete because code exists. It is complete only after:
1. tests exist for its failure modes;
2. the UI exposes the feature where applicable;
3. persistence/reopen behavior is verified;
4. documentation matches actual behavior;
5. CI is green on the supported release platform.
