# Witness — Security Model

Witness ingests untrusted documents and may send selected evidence to external model providers. Security is therefore part of the architecture, not an optional hardening pass.

## 1. Trust boundaries

### Trusted
- Witness application code;
- validated workspace metadata;
- explicit user actions;
- configuration schemas;
- generated internal IDs.

### Untrusted
- every imported document;
- document metadata;
- filenames and paths;
- extracted text;
- embedded links;
- images/charts;
- model outputs;
- provider errors;
- evaluation/attack fixtures;
- imported workspace/export files.

Retrieved text is **evidence**, never executable instruction.

---

## 2. Primary threats

### Prompt injection inside sources
A document may contain instructions such as “ignore previous instructions,” fake system messages, or requests to reveal secrets.

Controls:
- source content is wrapped and labeled as untrusted evidence;
- prompts clearly separate instructions from evidence;
- the generator has no arbitrary tool execution authority;
- source text cannot alter provider configuration, files, or application policy;
- Attack Lab includes explicit injection fixtures.

### Corpus poisoning
An attacker may add misleading, duplicated, keyword-stuffed, stale, or near-duplicate content designed to dominate retrieval.

Controls:
- source fingerprints and version history;
- duplicate detection;
- route/fusion trace visibility;
- source/date metadata;
- contradiction surfacing;
- Attack Lab clean-vs-attacked comparisons;
- optional source trust metadata without treating trust as proof of truth.

### Secret leakage
A document or trace may contain credentials, and provider calls may expose local content externally.

Controls:
- no API secret stored in workspace DB, traces, screenshots, or exports;
- provider secrets loaded from environment/OS-backed mechanisms;
- outbound provider use is explicit and visible;
- provider request metadata is recorded without secret values;
- export path supports redaction before sharing;
- logs avoid raw authorization headers.

### Path traversal / unsafe file access
Malicious filenames or imported manifests may attempt to escape the workspace.

Controls:
- normalize/canonicalize paths;
- workspace-managed writes remain under approved roots;
- content store filenames are generated from hashes, not source names;
- imported relative paths cannot contain traversal that resolves outside an allowed root;
- symlink behavior is explicit and tested.

### Parser exploitation
Malformed documents may trigger parser bugs, excessive resource use, macros, or embedded payloads.

Controls:
- do not execute macros/scripts/embedded binaries;
- file type validation based on content where practical, not extension alone;
- parser operations run behind bounded job interfaces;
- file/page/row/object limits;
- timeouts/cancellation where feasible;
- malformed parser fixtures in CI;
- optional future parser subprocess isolation for high-risk formats.

### Decompression / resource bombs
Archives or container formats may expand to extreme size.

Controls:
- hard byte/count limits;
- bounded extraction ratios;
- reject nested/unbounded archive expansion;
- derived artifacts subject to size quotas.

### Malicious model output
A provider can return malformed structured output, invented evidence IDs, or unsafe text.

Controls:
- schema-validate all structured model output;
- citations must resolve to evidence IDs present in the context pack;
- unknown evidence IDs are rejected;
- model output cannot mutate canonical state except through explicit validated engine operations;
- no shell/tool execution from generated content.

### Provenance tampering
A user or corrupted process may alter derived artifacts and create false trace/evidence relationships.

Controls:
- source blobs addressed by SHA-256;
- derived artifact manifests include source/config fingerprints;
- stale/mismatched indexes are rejected/rebuilt;
- historical runs retain immutable source/index references;
- evidence locator integrity checks on workspace open/replay.

### Workspace downgrade corruption
A newer application/schema may produce state an older build does not understand.

Controls:
- explicit schema versions;
- refuse destructive overwrite of future schemas;
- migrations are one-way and tested;
- backup/recovery policy before schema mutation.

---

## 3. External-provider privacy boundary

Witness is local-first, not necessarily local-model-only.

Before an external provider call, the engine knows:
- provider name;
- operation type;
- evidence being sent;
- model identifier;
- request size.

The UI should make the provider boundary visible in configuration and Trace.

A provider adapter receives only the minimum data required for its operation. Whole documents should not be sent when selected evidence spans suffice.

---

## 4. Attack Lab isolation

Attack experiments must never mutate canonical corpus data.

Rules:
- attacks create derived snapshots/manifests;
- mutated fixtures live in a separate attack artifact namespace;
- canonical blobs are read-only from attack code;
- attack output cannot become trusted evidence automatically;
- promotion into the real corpus requires an explicit import action.

---

## 5. Desktop/IPC security

The engine sidecar is child-process scoped.

Controls:
- no public localhost server by default;
- structured versioned IPC only;
- bounded message sizes;
- allowlisted method names;
- no generic `exec`/shell RPC;
- long operations have explicit job IDs and cancellation;
- malformed messages return typed errors and do not terminate the engine.

The Tauri host owns:
- approved file picker paths;
- sidecar startup/shutdown;
- secret/environment resolution;
- OS integration.

The frontend cannot read arbitrary filesystem paths directly.

---

## 6. Logging and trace hygiene

Traces are intentionally detailed, so they can themselves be sensitive.

Requirements:
- never log provider API keys/tokens;
- do not log full environment dictionaries;
- label traces that contain document excerpts;
- configurable retention/export;
- redact filesystem roots or source text on public export when requested;
- bounded application logs;
- trace persistence separate from crash diagnostics where practical.

---

## 7. Security acceptance tests

Before V1 release, automated/adversarial coverage must include:
- source prompt injection does not alter application control flow;
- invented model citation IDs are rejected;
- path traversal import/export attempts fail closed;
- malicious relative paths cannot escape workspace;
- duplicate poisoning remains visible in trace and deduplication;
- stale source cannot silently override explicitly current evidence;
- contradictory evidence yields conflict behavior;
- future schema cannot be overwritten;
- corrupted derived vector index can be discarded/rebuilt without losing sources;
- API key never appears in persisted config, trace, or exported evaluation fixture;
- malformed RPC cannot invoke arbitrary commands;
- attack snapshot cannot mutate canonical source blobs.

---

## 8. Reporting

Until a dedicated private security reporting channel exists, security issues should be described minimally in a GitHub issue without posting credentials, private corpora, or exploit payloads containing sensitive material.

For public test fixtures, use synthetic data only.
