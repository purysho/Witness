# Witness

> Evidence-first RAG workbench for answers that can be inspected, challenged, reproduced, and tested.

Witness is not a chat wrapper over a vector database. It is a local-first retrieval and evidence system built around a stricter question: **what evidence supports this answer, what contradicts it, how was it retrieved, and is the available evidence actually sufficient?**

The project is designed to make the hidden parts of retrieval-augmented generation visible. Every answer should be traceable from sentence -> evidence span -> source version -> retrieval path -> ranking decision.

## Core ideas

- **Evidence before fluency.** The system may abstain when the corpus does not justify an answer.
- **Sentence-level provenance.** Important answer sentences point to exact source spans, not merely documents.
- **Inspectable retrieval.** Lexical, dense, graph, temporal, hierarchical, and multimodal retrieval paths are visible in a trace.
- **Contradictions are first-class.** Conflicting evidence is surfaced rather than silently collapsed.
- **Versions matter.** Newer and superseded source versions remain distinguishable.
- **Evaluation is part of the product.** Retrieval, citation, faithfulness, contradiction handling, and abstention can be benchmarked.
- **Documents are untrusted input.** Source text cannot instruct the application or model to ignore system rules.

## V1 surfaces

| Surface | Purpose |
| --- | --- |
| **Library** | Import, inspect, version, and manage sources. |
| **Ask** | Ask questions and receive evidence-backed answers with sufficiency states. |
| **Trace** | Inspect routing, retrieval candidates, fusion, reranking, exclusions, and citations. |
| **Graph** | Explore claims, entities, sources, support edges, contradiction edges, and temporal relationships. |
| **Lab** | Run repeatable retrieval/RAG evaluations and A/B configuration comparisons. |
| **Attack** | Test prompt injection, poisoning, distractors, stale evidence, and conflicting-source failure modes. |

## Retrieval pipeline

```text
query
  -> query understanding
  -> retrieval strategy router
      -> lexical / BM25
      -> dense vector
      -> graph expansion
      -> temporal retrieval
      -> hierarchical retrieval
      -> multimodal retrieval
  -> rank fusion
  -> reranker
  -> evidence reconciliation
  -> sufficiency gate
  -> answer synthesis
  -> sentence-level citations + full trace
```

## Product boundary

Witness is an **evidence and retrieval workbench**, not a general-purpose autonomous agent and not a document instruction executor. Its job is to ingest sources, retrieve evidence, reconcile it, answer within the evidence boundary, and make the process inspectable.

## Documents

- [`SPECIFICATION.md`](SPECIFICATION.md) — product and functional specification
- [`ARCHITECTURE.md`](ARCHITECTURE.md) — technical architecture and data flow
- [`ROADMAP.md`](ROADMAP.md) — staged implementation plan
- [`SECURITY.md`](SECURITY.md) — threat model and source-safety rules
- [`docs/evaluation.md`](docs/evaluation.md) — RAG Lab datasets, metrics, snapshots, comparison, and export semantics

## Status

**Phases 3, 4, and 5 complete.** Witness now has functional Library, Ask, Trace, Graph, and Lab desktop surfaces. Lab runs the same evidence pipeline under reproducible lexical, dense, hybrid, or routed configurations, persists configuration/corpus snapshots and per-case traces, compares objective retrieval/grounding metrics A/B, and exports JSON/CSV. Attack Lab, multimodal evidence, and release hardening remain.
