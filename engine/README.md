# Witness engine

The Python engine owns all evidence-domain behavior and is testable without the desktop app or network access.

Current Phase 2 capabilities:

- immutable source-version and chunk identities;
- structured local ingestion for text, Markdown, PDF, DOCX, and source code;
- SQLite FTS5/BM25 lexical retrieval with provenance;
- persistent dense vectors keyed by immutable chunk IDs and embedding-provider identity;
- exact cosine search as the deterministic vector baseline;
- BM25 + dense hybrid retrieval through Reciprocal Rank Fusion (RRF);
- serializable retrieval traces showing lexical ranks, dense ranks, raw route scores, and RRF contributions.

## Local semantic embeddings

Core tests use a dependency-free deterministic fixture provider. For real local semantic retrieval, install the optional embedding stack:

```bash
python -m pip install -e ".[embeddings]"
```

Then use `SentenceTransformerEmbeddingProvider`, which defaults to `sentence-transformers/all-MiniLM-L6-v2`. The model is loaded lazily; Witness never requires model downloads merely to run its core test suite.

```python
from witness_engine.pipeline import index_document, search_hybrid_evidence
from witness_engine.retrieval import (
    LocalEvidenceIndex,
    LocalVectorIndex,
    SentenceTransformerEmbeddingProvider,
)

provider = SentenceTransformerEmbeddingProvider()

with LocalEvidenceIndex("witness.sqlite3") as lexical, \
     LocalVectorIndex("witness.sqlite3") as vectors:
    index_document(
        "report.pdf",
        lexical,
        vector_index=vectors,
        embedding_provider=provider,
    )
    result = search_hybrid_evidence(
        "Why was deployment delayed?",
        lexical,
        vectors,
        provider,
    )

    print(result.candidates)
    print(result.trace.to_dict())
```

The exact vector scan is intentional at this stage. HNSW/ANN will be introduced as an optimization only after the Lab has a stable evaluation baseline that can quantify recall and latency changes.
