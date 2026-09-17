# Witness engine

The Python engine owns all evidence-domain behavior and is testable without the desktop app or network access.

Current capabilities:

- immutable source-version and chunk identities;
- structured local ingestion for text, Markdown, PDF, DOCX, and source code;
- SQLite FTS5/BM25 lexical retrieval with provenance;
- persistent dense vectors keyed by immutable chunk IDs and embedding-provider identity;
- exact cosine search as the deterministic vector baseline;
- BM25 + dense hybrid retrieval through Reciprocal Rank Fusion (RRF);
- deterministic query understanding and transparent route selection;
- executable temporal retrieval over version-validity intervals and supersession chains;
- executable hierarchical retrieval that expands matched evidence through document structure;
- executable claim/evidence graph retrieval with deterministic claim extraction and entity expansion;
- provider-neutral reranking with deterministic and optional local cross-encoder implementations;
- serializable retrieval traces showing route reasons, specialized-route artifacts, RRF contributions, and pre/post-rerank positions.

## Specialized retrieval

Every import now builds several local projections from the same immutable evidence:

```text
SourceVersion
   ├── chunks -> FTS5 / BM25
   ├── chunks -> dense vectors
   ├── valid_from / valid_to / supersession -> temporal index
   ├── block parent/child structure -> hierarchy index
   └── deterministic claims -> claim/evidence graph
```

Temporal metadata is version-aware. `index_document(..., valid_from=...)` may supply an explicit validity start; otherwise Witness records the file modification time as the baseline. Later versions of the same source path form a supersession chain without deleting earlier evidence.

The graph baseline treats sentence-level propositions as claims and records explicit `claim -> supporting chunk` edges plus extracted entity anchors. This is intentionally deterministic. Future model-backed claim extraction can replace extraction while preserving the graph storage and retrieval contract.

Hierarchical retrieval preserves parser structure. Markdown headings, for example, can retrieve their child paragraphs as coherent context rather than forcing every answer to rely on isolated chunks.

## Local semantic embeddings

Core tests use dependency-free deterministic fixture providers. For real local semantic retrieval and optional cross-encoder reranking, install the optional embedding stack:

```bash
python -m pip install -e ".[embeddings]"
```

Then use `SentenceTransformerEmbeddingProvider`, which defaults to `sentence-transformers/all-MiniLM-L6-v2`. The model is loaded lazily; Witness never requires model downloads merely to run its core test suite.

```python
from witness_engine.pipeline import index_document, search_routed_evidence
from witness_engine.retrieval import (
    CrossEncoderReranker,
    LocalEvidenceIndex,
    LocalVectorIndex,
    SentenceTransformerEmbeddingProvider,
)

provider = SentenceTransformerEmbeddingProvider()
reranker = CrossEncoderReranker()

with LocalEvidenceIndex("witness.sqlite3") as lexical, \
     LocalVectorIndex("witness.sqlite3") as vectors:
    index_document(
        "report.pdf",
        lexical,
        vector_index=vectors,
        embedding_provider=provider,
        valid_from="2026-09-01T00:00:00+00:00",
    )
    result = search_routed_evidence(
        "Summarize how deployment dependencies changed after 2025 across all documents",
        lexical,
        vectors,
        provider,
        reranker=reranker,
    )

    print(result.candidates)
    print(result.trace.to_dict())
```

For a compact exact lookup such as `What port is "auth-api"?`, the transparent router can execute lexical retrieval alone. Explanatory, relational, comparison, broad-summary, or temporal questions activate the relevant specialized routes. Trace records the exact route plan, temporal source selection, hierarchy expansion, claim/entity graph expansion, fusion contributions, and reranking movement.

The exact vector scan is intentional at this stage. HNSW/ANN will be introduced as an optimization only after the Lab has a stable evaluation baseline that can quantify recall and latency changes.
