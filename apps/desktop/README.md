# Witness desktop

The desktop shell is a functional Tauri 2 + React/TypeScript client for the evidence engine through Phase 7.

Implemented surfaces:

- **Library** — open a local workspace, import evidence files, and inspect immutable source versions.
- **Ask** — run the complete evidence-first query pipeline and inspect sentence-level citations.
- **Trace** — inspect route decisions, retrieval artifacts, reconciliation, sufficiency, generation, validation, and persisted run events.
- **Graph** — inspect SourceVersion, Entity, Claim, and Evidence nodes plus MENTIONS, SUPPORTS, CONTAINS, CONTRADICTS, and SUPERSEDES edges.
- **Lab** — register evaluation datasets, run reproducible A/B retrieval configurations, compare objective metrics, open failed cases directly in Trace, inspect persisted run history, and export JSON/CSV.
- **Attack** — register immutable attack manifests, run clean-vs-attacked corpus experiments in isolated snapshots, inspect invariants and metric deltas, open either Trace, reopen historical runs, and export JSON/CSV.
- **Visual evidence viewer** — open cited image/chart/table evidence from Ask or Trace, inspect its bounded preview, immutable source-version metadata, and exact normalized page-region locator.

The frontend contains presentation logic only. Every evidence mutation or query goes through the Rust host to the Python engine over the versioned NDJSON protocol.

## Development

Requirements: Node.js 20+, Rust stable, and Python 3.12.

From this directory:

    python -m pip install -e ../../engine
    npm install
    npm run tauri dev

By default the Rust host starts python on Windows and python3 elsewhere. Override with WITNESS_PYTHON when necessary. WITNESS_ENGINE_PYTHONPATH can override the development engine source path.

Phase 8 will replace the development Python launch path with a bundled sidecar and packaged smoke tests.


## Multimodal provider boundary

PDF visual evidence is extracted and persisted even when no semantic vision provider is configured. In that state visual query routes remain advisory. Semantic image-to-text retrieval can be explicitly enabled with the optional OpenCLIP provider; provider selection will move into the normal desktop configuration UI during Phase 8.
