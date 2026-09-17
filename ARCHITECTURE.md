# Witness — Technical Architecture

## 1. Architectural goal

Witness is a local-first desktop RAG workbench whose differentiator is **evidence integrity and observability**. The architecture is therefore organized around immutable source versions, inspectable retrieval stages, explicit evidence records, and replayable query runs.

The system should make it difficult to produce an answer that cannot be traced back to exact evidence.

---

## 2. Top-level system

```text
┌──────────────────────────────────────────────────────────────┐
│                    WITNESS DESKTOP                           │
│  React / TypeScript UI inside Tauri                          │
│                                                              │
│  Library  Ask  Trace  Graph  Lab  Attack                     │
└──────────────────────────┬───────────────────────────────────┘
                           │ typed local IPC
┌──────────────────────────▼───────────────────────────────────┐
│                    TAURI HOST / RUST                         │
│  windowing · filesystem permissions · sidecar lifecycle      │
│  secret/environment resolution · packaging boundary          │
└──────────────────────────┬───────────────────────────────────┘
                           │ NDJSON request/event protocol
┌──────────────────────────▼───────────────────────────────────┐
│                    WITNESS ENGINE                            │
│  Python 3.12                                                 │
│                                                              │
│  ingest → normalize → index → route → retrieve → fuse        │
│  → rerank → reconcile → sufficiency → answer → trace         │
│                                                              │
│  eval · attack · graph · provider adapters                    │
└──────────────────────────┬───────────────────────────────────┘
                           │
          ┌────────────────┼────────────────┐
          │                │                │
     SQLite/FTS5       Vector index     Content store
     metadata/graph     local HNSW      immutable blobs
```

No network server is required for normal desktop operation. The frontend talks to the Python engine through the Tauri host, avoiding an unnecessary localhost HTTP attack surface.

---

## 3. Chosen stack

### Desktop shell
- **Tauri 2**
- Rust host process
- React + TypeScript frontend
- Vite build

Why: small distributable, native desktop lifecycle, strong filesystem/process boundary, and enough UI freedom for a distinctive evidence-inspection experience.

### Engine
- **Python 3.12**
- Pydantic for versioned RPC/config models
- standard-library-first domain core where practical

Why: the RAG/parser/evaluation ecosystem is strongest in Python, while keeping the domain code independent from specific orchestration frameworks.

### Storage
- **SQLite** in WAL mode for metadata, graph edges, runs, evaluation data, and FTS5 lexical search
- **content-addressed blob store** for immutable imported source versions
- **HNSW vector index** behind a `VectorIndex` adapter for dense retrieval
- derived extraction/index artifacts keyed by source hash + configuration hash

Witness does **not** require a separate graph database or hosted vector database for V1.

### Model/provider boundary
Provider interfaces rather than framework-owned chains:
- `EmbeddingProvider`
- `RerankProvider`
- `GenerationProvider`
- `VisionProvider`
- `ClaimExtractionProvider`

A deterministic fake provider is mandatory for tests.

### Parsing
Parser adapters feed one canonical document model. Individual libraries may change without affecting retrieval/evidence contracts.

Initial adapters:
- PDF
- Markdown/text
- HTML
- DOCX
- PPTX
- XLSX/CSV
- source-code text

---

## 4. Repository architecture

```text
Witness/
├─ README.md
├─ SPECIFICATION.md
├─ ARCHITECTURE.md
├─ ROADMAP.md
├─ SECURITY.md
├─ LICENSE
├─ .gitignore
├─ .github/
│  └─ workflows/
│     ├─ ci.yml
│     └─ release.yml
│
├─ apps/
│  └─ desktop/
│     ├─ package.json
│     ├─ vite.config.ts
│     ├─ src/
│     │  ├─ app/
│     │  ├─ components/
│     │  ├─ features/
│     │  │  ├─ library/
│     │  │  ├─ ask/
│     │  │  ├─ trace/
│     │  │  ├─ graph/
│     │  │  ├─ lab/
│     │  │  └─ attack/
│     │  ├─ state/
│     │  └─ contracts/
│     └─ src-tauri/
│        ├─ Cargo.toml
│        └─ src/
│           ├─ main.rs
│           ├─ engine.rs
│           ├─ commands.rs
│           └─ security.rs
│
├─ engine/
│  ├─ pyproject.toml
│  ├─ witness/
│  │  ├─ domain/
│  │  ├─ storage/
│  │  ├─ ingest/
│  │  ├─ chunking/
│  │  ├─ indexing/
│  │  ├─ retrieval/
│  │  ├─ routing/
│  │  ├─ evidence/
│  │  ├─ answering/
│  │  ├─ graph/
│  │  ├─ evaluation/
│  │  ├─ attack/
│  │  ├─ providers/
│  │  ├─ rpc/
│  │  └─ cli/
│  └─ tests/
│     ├─ unit/
│     ├─ integration/
│     ├─ adversarial/
│     └─ fixtures/
│
├─ contracts/
│  ├─ schema-version.txt
│  ├─ json-schema/
│  └─ generated/
│
├─ fixtures/
│  ├─ demo-corpus/
│  ├─ eval/
│  └─ attacks/
│
├─ docs/
│  ├─ adr/
│  ├─ data-model.md
│  ├─ trace-format.md
│  └─ evaluation.md
│
└─ tools/
   ├─ generate-contracts.py
   ├─ build-sidecar.ps1
   ├─ smoke.py
   └─ make-demo-corpus.py
```

### Ownership rule
- `apps/desktop` owns presentation only.
- `src-tauri` owns OS/process/security boundary only.
- `engine/witness` owns domain behavior.
- `contracts` defines the versioned IPC surface.
- No UI component may implement retrieval logic.
- No provider implementation may own domain rules.

---

## 5. Workspace layout

A Witness workspace is portable and self-describing.

```text
MyResearch.witness/
├─ witness.db
├─ workspace.json
├─ blobs/
│  └─ sha256/<digest>
├─ extracts/
│  └─ <artifact-key>.jsonl
├─ indexes/
│  ├─ dense/
│  └─ manifests/
├─ exports/
└─ temp/
```

### Rules
- Imported source versions are immutable blobs addressed by SHA-256.
- Logical `Source` records point to one or more `SourceVersion` records.
- Derived artifacts are reproducible and disposable; original blobs are authoritative.
- Historical query runs reference immutable source/index snapshots.
- Temporary files never become canonical state through rename unless validation succeeds.

---

## 6. Core domain model

### Workspace
A local evidence environment containing sources, indexes, configurations, runs, and evaluations.

### Source
Logical identity such as `Architecture Specification`.

### SourceVersion
Immutable imported content version.

Key fields:
- `id`
- `source_id`
- `blob_sha256`
- `byte_size`
- `media_type`
- `observed_path`
- `effective_from`
- `effective_to`
- `ingested_at`
- `supersedes_version_id`

### DocumentBlock
Structural extraction unit: heading, paragraph, table, code block, slide object, worksheet range, etc.

### Chunk
Retrieval unit derived from one or more blocks under a named chunking configuration.

### EvidenceSpan
Smallest citable span. Always anchored to a `SourceVersion` and original locator.

### Entity
Canonical entity used for graph expansion.

### Claim
Normalized proposition used for support/contradiction analysis.

### EvidenceEdge
Typed relationship such as `SUPPORTS`, `CONTRADICTS`, or `SUPERSEDES`.

### IndexSnapshot
Immutable manifest describing exactly which source versions/configuration produced a retrieval view.

### QueryRun
One complete question execution with configuration and trace.

### RetrievalCandidate
Candidate evidence returned by a retriever at a named stage.

### AnswerSentence
Material answer sentence linked to evidence spans and support classification.

---

## 7. Ingestion pipeline

```text
file
 ↓
security/type gate
 ↓
SHA-256 fingerprint
 ↓
content-addressed blob
 ↓
parser adapter
 ↓
canonical DocumentBlock stream
 ↓
normalizer
 ↓
chunker
 ↓
EvidenceSpan generation
 ↓
lexical index + dense index
 ↓
optional entity/claim extraction
 ↓
IndexSnapshot
```

### Canonical block requirements
Every block preserves:
- source version;
- structural type;
- order;
- parent/child relation;
- original locator;
- normalized text;
- extraction warnings;
- stable derived fingerprint.

No parser is allowed to return anonymous text chunks without source location.

---

## 8. Retrieval architecture

All retrievers implement one contract:

```text
retrieve(QueryContext, RetrievalRequest) -> list[RetrievalCandidate]
```

A candidate contains:
- evidence/chunk identity;
- retriever name/version;
- raw score;
- rank;
- reason metadata;
- source/version/date metadata.

### LexicalRetriever
SQLite FTS5 / BM25 baseline.

### DenseRetriever
Embedding similarity through `VectorIndex`.

### HierarchicalRetriever
Uses parent sections/document summaries to recover coherent context.

### GraphRetriever
Expands from matched entities/claims through bounded typed edges.

### TemporalRetriever
Applies version/date relationships and freshness constraints.

### MultimodalRetriever
Reserved contract in V1; later handles page/image/chart embeddings and visual evidence.

---

## 9. Retrieval router

The first router is **transparent and rule-based**, not an opaque LLM decision.

Example route signals:
- quoted phrase / identifier -> lexical emphasis;
- semantic explanatory query -> dense + lexical;
- relationship/multi-hop wording -> graph expansion;
- `when`, `before`, `after`, named dates, `current`, `originally` -> temporal route;
- broad theme/summary -> hierarchical route.

Every route emits a structured `RouteDecision` with reasons. A learned/LLM router can be added later and compared in Lab.

Hybrid lexical+dense remains the safe default.

---

## 10. Fusion and reranking

1. Retrieve per-route candidates.
2. Preserve each raw list.
3. Deduplicate by evidence identity.
4. Apply deterministic Reciprocal Rank Fusion baseline.
5. Optionally rerank top N using configured provider.
6. Preserve before/after ranks and score metadata.
7. Pass final candidates into evidence reconciliation.

No stage overwrites the prior stage's data in the trace.

---

## 11. Evidence reconciliation

`EvidenceReconciler` groups evidence around candidate claims and classifies relationships:
- support;
- contradiction;
- temporal supersession;
- scope mismatch;
- duplicate/corroborating source;
- unresolved.

This layer never replaces evidence text with a model summary. Its outputs remain links to exact evidence spans.

### Sufficiency gate
The gate uses explicit features such as:
- evidence coverage of requested subquestions;
- number of independent supporting sources;
- retrieval/rerank quality thresholds;
- contradiction severity;
- freshness requirement satisfaction;
- missing required entities/fields.

Output:
- `SUFFICIENT`
- `PARTIAL`
- `CONFLICTED`
- `INSUFFICIENT`

The gate must expose its feature values and rules in Trace.

---

## 12. Answer architecture

The generator receives a **context pack**, not arbitrary retrieved documents.

Context pack contains:
- question;
- answer constraints;
- selected evidence spans;
- source/version/location metadata;
- unresolved contradictions;
- sufficiency state.

The model is instructed to produce structured answer sentences with evidence IDs. The engine validates cited IDs and rejects invented citations.

Post-generation validation checks:
- every citation ID exists;
- cited evidence was in the context pack;
- unsupported factual sentences are flagged;
- answer state is compatible with sufficiency state.

---

## 13. Trace architecture

Every query produces an append-only trace containing events such as:

```text
query.received
query.normalized
route.decided
retrieval.lexical.completed
retrieval.dense.completed
fusion.completed
rerank.completed
evidence.reconciled
sufficiency.decided
context.built
generation.completed
answer.validated
run.completed
```

Each event has:
- `event_id`
- `run_id`
- `sequence`
- `timestamp`
- `stage`
- `schema_version`
- structured payload
- duration where relevant.

Trace is UI data, evaluation data, and debugging data; it is not hidden model chain-of-thought.

---

## 14. Evidence graph architecture

The graph is stored in normal SQLite tables:

```text
nodes(id, type, canonical_key, metadata_json)
edges(id, from_id, to_id, type, confidence, origin, metadata_json)
```

Graph assertions always retain an `origin` pointing to extraction evidence or a user action.

No Neo4j dependency is required for V1. Bounded traversal occurs in the engine.

---

## 15. Evaluation architecture

An evaluation case may include:
- query;
- expected answer facts;
- gold evidence span/source references;
- expected sufficiency state;
- expected contradiction behavior;
- tags.

A configuration snapshot freezes:
- corpus/index snapshot;
- retrievers;
- router;
- chunking;
- fusion settings;
- reranker;
- answer provider/prompt version.

Lab runs configurations through identical cases and stores both metrics and trace IDs.

Objective metrics and model-judged metrics are stored separately.

---

## 16. Attack architecture

Attack runs never mutate the canonical corpus. They operate against an isolated derived snapshot.

```text
clean snapshot
   ↓ clone manifest
attack mutation
   ↓
attacked snapshot
   ↓
same query/config
   ↓
diff traces + answers + evidence
```

This makes adversarial experiments reproducible and reversible.

---

## 17. IPC contract

Tauri and Python communicate through newline-delimited JSON over managed stdin/stdout.

Request example:

```json
{"v":1,"id":"req_123","method":"query.run","params":{"workspace_id":"w1","question":"..."}}
```

Response/event examples:

```json
{"v":1,"id":"req_123","type":"result","result":{"run_id":"r9"}}
{"v":1,"id":"req_123","type":"event","event":{"stage":"retrieval","message":"Dense retrieval complete"}}
```

Rules:
- explicit protocol version;
- request IDs;
- bounded message sizes;
- typed errors;
- cancellable long-running operations;
- no arbitrary command execution through RPC;
- generated TypeScript contracts from the engine schema.

---

## 18. Concurrency model

- One engine sidecar per desktop process.
- SQLite WAL allows responsive reads while indexing writes occur.
- Long operations run as cancellable jobs.
- Provider requests use bounded concurrency.
- Per-workspace write serialization protects canonical metadata.
- Query traces are append-only during execution.
- UI receives progress events instead of polling full state.

---

## 19. Failure model

Expected failures are domain states, not crashes:
- unsupported file;
- parser partial failure;
- corrupt source;
- missing provider key;
- provider timeout;
- embedding/index mismatch;
- stale index;
- insufficient evidence;
- contradiction;
- cancelled job.

The engine returns structured errors. The desktop must not infer errors from log strings.

---

## 20. Testing architecture

### Unit
- hashing/version identity;
- chunk boundaries;
- route decisions;
- RRF fusion;
- temporal selection;
- graph traversal bounds;
- sufficiency rules;
- citation validation;
- metric calculations.

### Integration
- parser -> block -> chunk -> index;
- lexical/dense retrieval;
- persisted workspace reopen;
- query trace replay;
- provider failure handling.

### Adversarial
- prompt injection source;
- stale authoritative-looking source;
- duplicated poisoning;
- contradictory versions;
- Unicode confusables/distractors;
- malformed document fixtures.

### Golden end-to-end
A small deterministic demo corpus with known questions/evidence. CI uses fake embeddings/generation where required so core correctness never depends on network access or paid APIs.

---

## 21. Packaging boundary

Windows V1 package contains:
- Tauri desktop executable;
- bundled Witness Python engine sidecar;
- required parser/runtime libraries;
- no API keys;
- no preloaded private corpus.

A packaged smoke test must cover:
1. create temporary workspace;
2. ingest fixture documents;
3. build indexes;
4. run deterministic query;
5. verify evidence IDs/citation mapping;
6. reopen workspace;
7. clean shutdown.

---

## 22. Architectural invariants

These are non-negotiable:

1. No answer citation may reference evidence that was not retrieved into the run context.
2. Every evidence span must resolve to an immutable source version and locator.
3. Historical runs must not silently change when a source is re-ingested.
4. Source content can never become application instructions.
5. Retrieval stages must preserve prior-stage trace data.
6. Provider-specific objects cannot leak into core domain models.
7. Evaluation and attack runs must be reproducible from saved snapshots/configuration.
8. The UI cannot bypass the engine to mutate workspace evidence state directly.
9. Derived indexes may be rebuilt; original source blobs and canonical metadata are authoritative.
10. When the evidence boundary is insufficient, Witness must be able to say so.
