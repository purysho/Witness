# Witness engine

The Python engine owns all evidence-domain behavior and is testable without the desktop app or network access.

Current Phase 2 capabilities:

- immutable source-version and chunk identities;
- structured local ingestion for text, Markdown, PDF, DOCX, and source code;
- SQLite FTS5/BM25 lexical retrieval with provenance;
- persistent dense vectors keyed by immutable chunk IDs and embedding-provider identity;
- exact cosine search as the deterministic vector baseline;
- BM25 + dense hybrid retrieval through Reciprocal Rank Fusion (RRF);
- deterministic query understanding and transparent route selection;
- explicit advisory detection for future temporal, graph, and hierarchical routes;
- provider-neutral reranking with deterministic and optional local cross-encoder implementations;
- serializable retrieval traces showing route reasons, lexical/dense candidates, RRF contributions, and pre/post-rerank positions.

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
    )
    result = search_routed_evidence(
        "Why was deployment delayed?",
        lexical,
        vectors,
        provider,
        reranker=reranker,
    )

    print(result.candidates)
    print(result.trace.to_dict())
```

For a compact exact lookup such as `What port is "auth-api"?`, the transparent router can execute lexical retrieval alone. Explanatory, relational, comparison, broad-summary, or temporal queries retain dense retrieval. Requests that appear to need graph, temporal, or hierarchical retrieval are recorded as advisory routes in Trace until those engines exist; Witness does not pretend an unavailable route ran.

The exact vector scan is intentional at this stage. HNSW/ANN will be introduced as an optimization only after the Lab has a stable evaluation baseline that can quantify recall and latency changes.
