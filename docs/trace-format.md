# Witness Trace Format

Witness Trace is a structured execution artifact, not a transcript of private reasoning.

## Query-run stages

The first Ask pipeline emits append-only events in sequence:

1. `query.received`
2. `retrieval.completed`
3. `evidence.reconciled`
4. `sufficiency.decided`
5. `context.built`
6. `generation.completed`
7. `answer.validated`
8. `run.completed`

Each persisted event contains:

- `run_id`
- monotonic `sequence`
- `stage`
- JSON `payload`
- UTC `created_at`

The SQLite primary key `(run_id, sequence)` makes events append-only for a run. Completed answers are persisted separately on the query-run row.

## Retrieval artifacts

`retrieval.completed` contains the transparent route plan plus the actual lexical, dense, temporal, hierarchical, and graph route artifacts that executed. Fusion and reranking retain their pre/post positions.

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
