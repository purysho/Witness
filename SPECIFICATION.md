# Witness — Product Specification

## 1. Product definition

Witness is an **evidence-first RAG workbench** for building, inspecting, testing, and attacking retrieval-augmented generation systems.

Its defining behavior is not that it can answer questions over documents. Many tools already do that. Witness is designed to make an answer **auditable**:

1. What claim is being made?
2. Which exact evidence spans support it?
3. Which evidence contradicts it?
4. Which source version did the evidence come from?
5. How did the retrieval system find and rank that evidence?
6. Was the available evidence sufficient to justify the answer?
7. Would a different retrieval strategy or corpus version have changed the result?

Witness therefore treats provenance, contradictions, temporal validity, retrieval traces, and evaluation as product features rather than debugging afterthoughts.

---

## 2. Product goals

### 2.1 Primary goals

- Produce answers whose important factual sentences are linked to precise evidence spans.
- Make retrieval behavior visible and reproducible.
- Represent support, contradiction, uncertainty, and stale evidence explicitly.
- Detect when the corpus is insufficient and abstain instead of filling gaps with fluent speculation.
- Support multiple retrieval strategies and expose the route chosen for each query.
- Preserve source versions and temporal context.
- Provide a built-in evaluation laboratory for retrieval and answer quality.
- Provide a built-in adversarial test surface for prompt injection, corpus poisoning, distractors, stale information, and conflicting evidence.
- Support text-first V1 ingestion while providing a clean path to multimodal evidence.
- Remain local-first: source files, indexes, traces, and evaluation artifacts live on the user's machine unless an explicitly configured model provider is called.

### 2.2 Secondary goals

- Be useful as a serious RAG debugging tool, not merely a portfolio demo.
- Make architectural decisions inspectable enough that developers can compare retrievers, rerankers, chunking strategies, and models.
- Keep the evidence model provider-independent.
- Allow deterministic replay of prior query runs when the same corpus/index/configuration is available.

### 2.3 Non-goals

V1 is not intended to be:

- a general autonomous agent;
- a browser automation system;
- a collaborative SaaS knowledge base;
- a secrets vault;
- a replacement for source documents;
- a system that executes instructions embedded inside retrieved content;
- a claim that LLM-generated judgments are ground truth.

---

## 3. Core principles

### Evidence before fluency
If evidence is missing, weak, stale, or contradictory, the answer must reflect that state. A shorter qualified answer or abstention is preferable to unsupported completion.

### Provenance is structural
Citations are not decorative links appended after generation. Evidence spans are first-class records connected to chunks, source versions, retrieval candidates, claims, and answer sentences.

### Retrieval is inspectable
Witness records query interpretation, selected retrieval routes, candidates, scores, fusion, reranking, exclusions, and final evidence selection.

### Contradiction is not noise
Conflicting evidence must remain visible. The system may reconcile it using source version, date, scope, or authority metadata, but it must not erase the disagreement.

### Time changes truth conditions
A statement may have been supported in one source version and superseded later. Witness tracks source versions and temporal qualifiers so that old evidence is not silently treated as current evidence.

### Source content is untrusted data
A document may contain malicious or irrelevant instructions. Retrieved text is evidence, not control input.

### Evaluation belongs beside the product
A RAG configuration is not considered improved because one demo answer looks better. Witness records measurable retrieval and evidence outcomes across repeatable cases.

---

## 4. Primary user workflows

### 4.1 Build a corpus
1. Create or open a workspace.
2. Import files or folders.
3. Witness fingerprints each source and records metadata.
4. Parsers extract document structure and location data.
5. Normalization creates canonical blocks/spans.
6. Chunking creates retrievable units while preserving parent structure.
7. Lexical and dense indexes are built.
8. Optional entity/claim extraction enriches the evidence graph.
9. The Library shows source status, version, parser warnings, and index status.

### 4.2 Ask a question
1. Enter a question in **Ask**.
2. Witness classifies query characteristics and selects retrieval routes.
3. Multiple retrievers return candidates.
4. Candidates are fused and reranked.
5. Evidence reconciliation identifies supporting, contradicting, stale, or weak evidence.
6. A sufficiency gate decides whether the evidence can support a direct answer.
7. The answer is generated only inside that evidence boundary.
8. Each material factual sentence links to evidence.
9. The run is saved and can be inspected in **Trace**.

### 4.3 Inspect why an answer happened
1. Open a completed query in **Trace**.
2. See query interpretation and selected routes.
3. Compare lexical, dense, graph, temporal, and other candidate lists.
4. Inspect rank fusion and reranker score changes.
5. See why candidates were included or dropped.
6. Inspect evidence selected for each answer sentence.
7. Replay the query under a different configuration.

### 4.4 Investigate contradictions
1. Open an answer or graph node.
2. View claims and linked evidence.
3. See support/contradiction edges.
4. Compare source version, date, scope, and authority metadata.
5. Mark a contradiction as unresolved, superseded, scoped, or explained.

### 4.5 Benchmark a RAG configuration
1. Create/import an evaluation set.
2. Choose corpus snapshot and configuration A/B.
3. Run cases.
4. Measure retrieval, citation, faithfulness, sufficiency, contradiction, latency, and cost metrics.
5. Compare regressions and save the run.

### 4.6 Attack the corpus/system
1. Select an attack fixture or generate a controlled adversarial variant.
2. Run questions against clean and attacked corpora.
3. Compare route/candidate/answer changes.
4. Inspect whether malicious instructions, stale documents, distractors, or poisoned chunks altered the result.
5. Record pass/fail against explicit expectations.

---

## 5. V1 application surfaces

### 5.1 Library
Purpose: corpus and source management.

Required capabilities:
- create/open workspace;
- add files and folders;
- supported-type detection;
- source fingerprinting using cryptographic hash;
- source/version list;
- extraction/index status;
- parser warnings;
- source metadata editor;
- source preview with stable location identifiers;
- re-index source;
- disable source without deleting it;
- inspect source history;
- corpus snapshot identifier.

V1 file targets:
- PDF;
- Markdown;
- plain text;
- HTML saved locally;
- DOCX;
- PPTX;
- XLSX/CSV;
- common source-code text files.

Later multimodal targets:
- image OCR;
- screenshots;
- chart/table visual interpretation;
- scanned PDFs;
- audio/video transcripts.

### 5.2 Ask
Purpose: evidence-constrained question answering.

Required capabilities:
- question input;
- optional source/date/type filters;
- answer with inline evidence markers;
- evidence panel with exact source spans;
- source/version/date display;
- sufficiency state;
- contradiction notice;
- route summary;
- latency/cost summary when available;
- open run in Trace;
- retry with alternate configuration.

Sufficiency states:
- **SUFFICIENT** — evidence directly supports the material answer.
- **PARTIAL** — some requested parts are supported, others are not.
- **CONFLICTED** — material evidence conflicts and cannot be safely collapsed.
- **INSUFFICIENT** — corpus does not justify a direct answer.

These are evidence states, not model confidence scores.

### 5.3 Trace
Purpose: make the retrieval pipeline inspectable.

Required trace stages:
- normalized query;
- query features/route decision;
- active filters;
- retrievers invoked;
- raw candidate ranks and scores;
- rank fusion result;
- reranker result;
- evidence classification;
- dropped candidate reasons;
- final context pack;
- answer sentence -> evidence mapping;
- model/provider/configuration identifiers;
- corpus snapshot/index version;
- timings for each stage.

A trace must be serializable and replayable.

### 5.4 Graph
Purpose: inspect relationships among sources, claims, entities, and evidence.

Initial node types:
- Source;
- SourceVersion;
- Entity;
- Claim;
- EvidenceSpan;
- QueryRun.

Initial edge types:
- CONTAINS;
- VERSION_OF;
- MENTIONS;
- SUPPORTS;
- CONTRADICTS;
- SUPERSEDES;
- DERIVED_FROM;
- USED_IN;

The graph is an evidence graph, not an attempt to auto-generate a universal ontology.

### 5.5 Lab
Purpose: repeatable RAG evaluation.

Required capabilities:
- evaluation dataset CRUD/import/export;
- expected evidence references where available;
- configuration snapshots;
- A/B runs;
- per-case trace links;
- aggregate metrics;
- regression comparison;
- JSON/CSV export.

Core V1 metrics:
- Recall@K;
- Precision@K where gold evidence exists;
- MRR;
- nDCG;
- citation precision;
- citation coverage;
- evidence support coverage;
- unsupported-claim rate;
- abstention correctness;
- contradiction handling accuracy;
- latency;
- model/token cost where available.

Model-judged metrics may be included, but must be labeled as model judgments rather than objective measurements.

### 5.6 Attack
Purpose: adversarial RAG testing.

Initial attack classes:
- prompt injection embedded in source text;
- instruction hierarchy spoofing;
- keyword stuffing;
- irrelevant high-similarity distractors;
- duplicated evidence flooding;
- stale but semantically strong documents;
- mutually contradictory documents;
- subtly altered near-duplicate claims;
- fake citation/reference bait;
- malformed parser input;
- hidden or unusual Unicode text where safe to test.

Each attack case records:
- clean corpus/query baseline;
- mutation applied;
- expected invariant;
- attacked trace;
- observed answer/evidence change;
- pass/fail and notes.

---

## 6. Retrieval specification

### 6.1 Query understanding
Query analysis should produce structured features, not hidden prose reasoning. Example fields:

- normalized text;
- requested entities;
- temporal expressions;
- comparison intent;
- aggregation intent;
- exact-name/exact-phrase signals;
- likely need for graph expansion;
- likely need for hierarchical context;
- requested source filters;
- requested output scope.

### 6.2 Retrieval routes
V1 must support:

**Lexical retrieval**
- BM25/FTS-based;
- strong for names, identifiers, quotes, and exact terminology.

**Dense retrieval**
- embedding similarity;
- strong for semantic paraphrase.

**Hierarchical retrieval**
- retrieve document/section summaries or parents before/alongside fine chunks;
- reduces isolated-chunk context loss.

**Graph retrieval**
- expand from matched entities/claims/evidence relationships;
- never replace the underlying evidence spans with graph assertions alone.

**Temporal retrieval**
- apply date/version awareness;
- prefer relevant current versions for current-state questions while preserving historical answers when explicitly requested.

**Multimodal retrieval**
- architecture included in V1;
- implementation may mature after text-first retrieval is stable.

### 6.3 Fusion and reranking
- Each retriever returns normalized candidate records.
- Reciprocal Rank Fusion is the default deterministic fusion baseline.
- A reranker may reorder the fused list.
- Pre-rerank and post-rerank ranks must both remain in the trace.
- Rerankers are pluggable and may be local or provider-backed.

### 6.4 Context construction
The final context pack must:
- deduplicate overlapping evidence;
- retain source/version/location metadata;
- keep contradictory evidence when material;
- respect configurable context limits;
- prefer coherent parent/child coverage over arbitrary adjacent chunks;
- never strip provenance identifiers.

---

## 7. Evidence and answer specification

### 7.1 Evidence unit
The smallest citable unit is an `EvidenceSpan` that includes:
- source version ID;
- parent block/chunk ID;
- normalized text;
- original locator;
- character/token offsets where available;
- page/slide/sheet/cell/line coordinates where applicable;
- extraction method;
- hash/fingerprint.

### 7.2 Claim representation
A claim is a normalized proposition used to connect evidence and answers. A claim may be:
- supported;
- contradicted;
- disputed;
- superseded;
- unresolved.

Claim extraction is an aid to evidence reconciliation, not a replacement for source text.

### 7.3 Answer sentence provenance
Every material factual answer sentence should record:
- sentence text;
- zero or more evidence span IDs;
- support classification;
- optional uncertainty note.

A sentence with no adequate evidence must not be presented as established fact from the corpus.

### 7.4 Contradiction reconciliation
Witness may distinguish apparent contradictions using:
- source version;
- date;
- entity identity;
- scope/jurisdiction;
- units/definitions;
- quoted speaker versus author assertion;
- supersession metadata.

When a material contradiction remains unresolved, the answer state becomes `CONFLICTED` or explicitly presents both supported positions.

---

## 8. Data/versioning requirements

Every ingest creates or reuses stable identities based on content and source location.

Required concepts:
- Workspace;
- Source;
- SourceVersion;
- DocumentBlock;
- Chunk;
- EvidenceSpan;
- Entity;
- Claim;
- EvidenceEdge;
- IndexSnapshot;
- QueryRun;
- RetrievalCandidate;
- Answer;
- AnswerSentence;
- Citation;
- EvalDataset;
- EvalCase;
- EvalRun;
- AttackCase;
- AttackRun;
- ConfigurationSnapshot.

Deleting/replacing a file must not silently mutate historical traces. Prior runs retain references to the source/index versions they used.

---

## 9. Reproducibility requirements

A saved query run records enough information to explain/replay it:
- query;
- workspace/corpus snapshot;
- active source filters;
- chunking/index configuration;
- embedding model identifier;
- retriever configuration;
- reranker configuration;
- answer model identifier;
- prompt/template version identifiers;
- selected evidence span IDs;
- timing and token/cost metadata;
- random seeds where meaningful;
- application schema/version.

Exact model output may still vary for non-deterministic external providers. Witness must distinguish pipeline reproducibility from provider nondeterminism.

---

## 10. Provider model

Witness core must not depend directly on one model vendor.

Provider interfaces:
- `EmbeddingProvider`;
- `RerankProvider`;
- `GenerationProvider`;
- `VisionProvider`;
- optional `ClaimExtractionProvider`.

Initial implementation can support one primary cloud provider plus deterministic/mock providers for tests. Local providers can be added without changing the evidence domain model.

No API secret is written into workspace documents or traces. Secrets are read from environment/OS-backed configuration and represented only by provider/key names in persisted configuration.

---

## 11. Performance targets for V1

These are engineering targets rather than guarantees:
- application opens an existing small workspace in <2 seconds excluding model startup;
- incremental re-ingest skips unchanged source versions;
- lexical retrieval response for a small/medium local corpus should generally be sub-second;
- retrieval trace should begin rendering before generation completes;
- UI must remain responsive during indexing and evaluation runs;
- all long-running ingestion/index/evaluation operations are cancellable;
- logs and histories are bounded or paginated.

---

## 12. Reliability requirements

- Atomic writes for workspace metadata/configuration.
- Schema versioning and forward-version refusal rather than destructive downgrade.
- Crash-safe task state for ingestion/evaluation jobs where practical.
- Idempotent ingestion based on fingerprints.
- Corrupt index detection and rebuild path.
- No silent evidence deletion during reindex.
- Explicit parser/index errors surfaced in Library.
- Deterministic unit tests for routing/fusion/provenance logic.
- Integration fixtures for representative file types.

---

## 13. Privacy and safety requirements

- Local files stay local except the minimum content explicitly sent to a configured external model provider.
- Provider calls must be visible in traces/configuration.
- Source text is always treated as untrusted data.
- Retrieved instructions cannot alter application policy or tool behavior.
- File ingestion must not execute macros, scripts, embedded binaries, or source code.
- Archive/import limits prevent decompression bombs and unbounded expansion.
- URL/network ingestion is not implicit; network access must be an explicit feature.
- Workspace paths must be constrained and normalized before file operations.
- Exported traces should support redaction before public sharing.

See `SECURITY.md` for the detailed threat model.

---

## 14. V1 acceptance criteria

Witness V1 is ready only when all of the following are true:

1. A user can create a workspace and ingest a mixed local corpus.
2. Unchanged files are detected; changed files create new source versions.
3. Lexical + dense retrieval work through one normalized candidate contract.
4. Fusion and reranking are recorded in a trace.
5. Ask can produce an evidence-constrained answer or abstain.
6. Material answer sentences map to precise evidence spans.
7. Trace shows why evidence was selected and what was dropped.
8. Contradictory evidence is surfaced instead of silently hidden.
9. Current-versus-historical source versions can be distinguished.
10. Lab can run a repeatable benchmark and compare two configurations.
11. Attack can demonstrate at least prompt-injection, stale-source, distractor, and contradiction tests.
12. Core logic has deterministic tests independent of paid model calls.
13. A first-run demo corpus demonstrates the complete flow from ingestion to evidence trace.
14. The application can be packaged and run on Windows without requiring a developer environment.
