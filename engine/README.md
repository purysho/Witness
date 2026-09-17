# Witness engine

The Python engine owns all evidence-domain behavior.

Planned package areas:
- `domain` — immutable IDs, source/version/evidence/query models;
- `storage` — SQLite schema, migrations, blob store, atomic state;
- `ingest` — parser adapters and canonical document blocks;
- `chunking` — structure-aware chunk derivation;
- `indexing` — lexical/vector index construction;
- `retrieval` — lexical, dense, hierarchical, graph, temporal, multimodal contracts;
- `routing` — transparent retrieval route selection;
- `evidence` — reconciliation, contradiction handling, sufficiency;
- `answering` — context packs, structured generation, citation validation;
- `graph` — evidence graph persistence/traversal;
- `evaluation` — datasets, metrics, A/B runs;
- `attack` — isolated adversarial snapshots and comparisons;
- `providers` — embedding/rerank/generation/vision adapters;
- `rpc` — versioned IPC contracts;
- `cli` — development and headless test entry points.

The engine must be testable without the desktop app and without network/model-provider access.
