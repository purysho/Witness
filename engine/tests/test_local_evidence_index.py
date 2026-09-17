from pathlib import Path

from witness_engine.pipeline import index_text_document, search_evidence
from witness_engine.retrieval import LocalEvidenceIndex


def test_local_document_becomes_searchable_evidence(tmp_path: Path):
    source = tmp_path / "architecture notes.txt"
    source.write_text(
        "The authentication service uses rotating bearer tokens.\n\n"
        "The database stores audit events locally.",
        encoding="utf-8",
    )
    database = tmp_path / "witness-index.sqlite3"

    with LocalEvidenceIndex(database) as index:
        result = index_text_document(source, index, max_chars=80)
        hits = search_evidence("authentication bearer", index)

        assert result.chunk_count >= 1
        assert index.count() == result.chunk_count
        assert hits
        assert hits[0].method == "fts5-bm25"
        assert hits[0].source_version_id == result.source_version_id
        assert hits[0].locator == "line:1"
        assert "authentication" in hits[0].text.lower()


def test_index_survives_process_style_reopen(tmp_path: Path):
    source = tmp_path / "design.txt"
    source.write_text("Redis was proposed for the cache layer.", encoding="utf-8")
    database = tmp_path / "index.sqlite3"

    with LocalEvidenceIndex(database) as index:
        result = index_text_document(source, index)

    with LocalEvidenceIndex(database) as reopened:
        hits = reopened.search("Redis")
        assert len(hits) == 1
        assert hits[0].source_version_id == result.source_version_id


def test_identical_reindex_is_idempotent(tmp_path: Path):
    source = tmp_path / "notes.txt"
    source.write_text("Deployment requires the gateway service.", encoding="utf-8")
    database = tmp_path / "index.sqlite3"

    with LocalEvidenceIndex(database) as index:
        first = index_text_document(source, index)
        count_after_first = index.count()
        second = index_text_document(source, index)

        assert first.source_version_id == second.source_version_id
        assert index.count() == count_after_first
        assert len(index.search("gateway")) == 1


def test_modified_file_creates_new_source_version(tmp_path: Path):
    source = tmp_path / "notes.txt"
    database = tmp_path / "index.sqlite3"

    source.write_text("The API uses port 4100.", encoding="utf-8")
    with LocalEvidenceIndex(database) as index:
        first = index_text_document(source, index)
        source.write_text("The API uses port 4200.", encoding="utf-8")
        second = index_text_document(source, index)

        assert first.source_version_id != second.source_version_id
        # Historical evidence remains indexed until version policy explicitly
        # retires it; Witness must not silently rewrite prior evidence.
        assert index.count() == first.chunk_count + second.chunk_count
        assert index.search("4100")
        assert index.search("4200")


def test_user_query_cannot_inject_fts_syntax(tmp_path: Path):
    source = tmp_path / "notes.txt"
    source.write_text("alpha beta gamma", encoding="utf-8")

    with LocalEvidenceIndex(tmp_path / "index.sqlite3") as index:
        index_text_document(source, index)
        # Operator-looking punctuation is tokenized as data instead of being
        # executed as a raw MATCH expression.
        hits = index.search('alpha OR "broken')
        assert hits
        assert hits[0].chunk_id


def test_fts_projection_can_be_rebuilt(tmp_path: Path):
    source = tmp_path / "notes.txt"
    source.write_text("Witness preserves provenance.", encoding="utf-8")

    with LocalEvidenceIndex(tmp_path / "index.sqlite3") as index:
        index_text_document(source, index)
        index.connection.execute("DELETE FROM indexed_chunks_fts")
        index.connection.commit()
        assert index.search("provenance") == []

        index.rebuild_fts()
        assert index.search("provenance")
