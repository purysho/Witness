# Witness Trace Format

Witness Trace is a structured execution artifact, not a transcript of private reasoning.

## Query-run stages

The first Ask pipeline emits append-only events in sequence:

1. `query.received`
2. `query.normalized`
3. `route.decided`
4. `retrieval.lexical.completed`
5. `retrieval.dense.completed`
6. `retrieval.temporal.completed`
7. `retrieval.hierarchical.completed`
8. `retrieval.graph.completed`
9. `fusion.completed`
10. `rerank.completed`
11. `evidence.reconciled`
12. `sufficiency.decided`
13. `context.built`
14. `generation.completed`
15. `answer.validated`
16. `run.completed`

Each persisted event contains:

- stable `event_id`
- `run_id`
- monotonic `sequence`
- `schema_version`
- `stage`
- JSON `payload`
- UTC `created_at`

The SQLite primary key `(run_id, sequence)` makes events append-only for a run. Completed answers are persisted separately on the query-run row.

## Retrieval artifacts

Retrieval is emitted as separate route/fusion/rerank events. The route decision, each raw candidate list, temporal selection, hierarchy expansion, graph paths, RRF contributions, and pre/post-rerank positions remain separately inspectable.

## Evidence reconciliation

`evidence.reconciled` records inspectable relationships:

- `DUPLICATE`
- `CORROBORATES`
- `CONTRADICTS`
- `SUPERSEDES`

An unresolved `CONTRADICTS` relation is never silently flattened into a single answer.

## Sufficiency

`sufficiency.decided` emits one of:

- `SUFFICIENT`
- `PARTIAL`
- `CONFLICTED`
- `INSUFFICIENT`

The payload includes query-term coverage, evidence count, independent logical-source count, unresolved conflict count, temporal-requirement status, and explicit reasons.

## Generation and citation validation

Generation receives a context pack containing only selected evidence IDs and source metadata. A generated citation ID must exist in that pack. Unknown IDs are rejected before a final answer can be returned.

Material answer sentences in non-`INSUFFICIENT` states must cite at least one context evidence ID. The final answer contains sentence-level evidence IDs and citation objects resolving to chunk, source version, and locator.

## Non-goal

Trace intentionally does not store hidden chain-of-thought or free-form model reasoning. It stores reproducible system decisions and artifacts needed to audit retrieval, evidence selection, and answer grounding.
