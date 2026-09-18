# Workspace recovery

Witness treats recovery as a provenance operation, not as an excuse to recreate
evidence from whatever happens to be on disk today.

## Protected state

Workspace repair must not rewrite canonical or historical state, including:

- source-version metadata;
- canonical text chunks;
- structured block hierarchy;
- immutable visual assets and visual evidence;
- Ask runs and append-only Trace events;
- Lab datasets/runs/case results;
- Attack Lab manifests/runs;
- other application tables that are not explicitly classified as disposable projections.

Before and after a repair, Witness fingerprints all protected application tables.
A repair fails if that fingerprint changes.

## Disposable projections

The following can be rebuilt from protected state:

- lexical FTS rows from canonical chunks;
- dense vectors for the active embedding provider from canonical chunk text;
- graph claims/entities/claim-evidence edges and graph FTS from canonical chunks;
- visual vectors for the active visual provider from immutable visual assets.

Health inspection also verifies SQLite quick-check status, source-version
provenance, structured-block references, visual asset content hashes, and active
provider vector shape/content identity.

## Fail-closed behavior

If protected evidence is damaged, Witness reports **attention** and refuses to
perform automatic repair. Examples include:

- a canonical chunk with missing source-version metadata;
- a chunk whose structured block is missing;
- visual evidence with missing source provenance;
- a visual asset whose bytes no longer match its immutable SHA-256 identity;
- SQLite reporting database-level integrity failure.

Witness does not reconstruct protected structure by re-reading the original
source path, because that path may now contain different bytes.

## Desktop flow

Opening a workspace performs a health check. The desktop shows one of:

- **HEALTHY** — protected state and derived projections are consistent;
- **REPAIRABLE** — only disposable projections are stale/corrupt and can be rebuilt safely;
- **ATTENTION** — protected state has an integrity problem and automatic repair is disabled.

`workspace.repair` is exposed only as a derived-index repair operation. It
returns the before/after reports, the performed actions, and whether protected
state remained unchanged.

## Destructive tests

The recovery test suite deliberately deletes lexical/graph projection data and
corrupts dense vector payloads, then proves that repair restores retrieval while
preserving the original source version and prior QueryRun/Trace. A second test
corrupts immutable visual asset bytes and proves automatic repair refuses to
rewrite the evidence.
