import pytest

from ensemble.engine.chunking import chunk_diff, chunk_markdown, chunk_text
from ensemble.engine.embeddings import CachedEmbeddings, HashEmbeddings, content_hash
from ensemble.engine.vectorstore import InMemoryVectorIndex, cosine_similarity


def test_hash_embeddings_are_deterministic_and_768_dimensional():
    embeddings = HashEmbeddings()

    first = embeddings.embed(["same text"], task_type="SEMANTIC_SIMILARITY")
    second = embeddings.embed(["same text"], task_type="SEMANTIC_SIMILARITY")

    assert first == second
    assert len(first[0]) == 768


def test_hash_embeddings_task_type_changes_cache_key_and_vector():
    embeddings = HashEmbeddings(dimensions=8)

    doc = embeddings.embed(["same text"], task_type="RETRIEVAL_DOCUMENT")
    query = embeddings.embed(["same text"], task_type="RETRIEVAL_QUERY")

    assert doc != query
    assert content_hash("same text", "RETRIEVAL_DOCUMENT") != content_hash(
        "same text", "RETRIEVAL_QUERY"
    )


def test_cached_embeddings_batches_only_misses():
    inner = HashEmbeddings(dimensions=8)
    cached = CachedEmbeddings(inner)

    first = cached.embed(["a", "b"], task_type="SEMANTIC_SIMILARITY")
    second = cached.embed(["a", "c"], task_type="SEMANTIC_SIMILARITY")

    assert second[0] == first[0]
    assert inner.calls == [
        (("a", "b"), "SEMANTIC_SIMILARITY"),
        (("c",), "SEMANTIC_SIMILARITY"),
    ]


def test_markdown_chunker_splits_on_headings_and_adds_metadata():
    chunks = chunk_markdown(
        "# Sprint 2\n\nT-15 embeddings.\n\n## Detay\n\nVectorStore cache.",
        path=".harness/tasks/T-15-ai.md",
    )

    assert [chunk.meta["section"] for chunk in chunks] == ["Sprint 2", "Detay"]
    assert chunks[0].meta["path"] == ".harness/tasks/T-15-ai.md"
    assert chunks[0].meta["type"] == "markdown"
    assert chunks[0].meta["task_id"] == "T-15"
    assert chunks[0].meta["sprint"] == "sprint-2"


def test_diff_chunker_splits_on_hunks():
    diff = "\n".join(
        [
            "@@ -1,2 +1,2 @@",
            "-old",
            "+new",
            "@@ -10,2 +10,2 @@",
            "-before",
            "+after",
        ]
    )

    chunks = chunk_diff(diff, path="src/backend/ensemble/engine/radar.py")

    assert len(chunks) == 2
    assert chunks[0].meta["section"] == "@@ -1,2 +1,2 @@"
    assert chunks[1].meta["section"] == "@@ -10,2 +10,2 @@"


def test_plain_chunker_rejects_invalid_size():
    with pytest.raises(ValueError, match="max_chars"):
        chunk_text("text", path="README.md", max_chars=0)


def vector_index_contract(index: InMemoryVectorIndex) -> None:
    index.upsert("near", [1.0, 0.0], {"path": "a.py"})
    index.upsert("far", [0.0, 1.0], {"path": "b.py"})
    index.upsert("also-near", [0.9, 0.1], {"path": "c.py"})

    results = index.query([1.0, 0.0], k=2)

    assert [id for id, _score in results] == ["near", "also-near"]


def test_in_memory_vector_index_contract():
    vector_index_contract(InMemoryVectorIndex())


def test_in_memory_vector_index_upsert_replaces_existing_id():
    index = InMemoryVectorIndex()
    index.upsert("doc", [0.0, 1.0], {"version": 1})
    index.upsert("doc", [1.0, 0.0], {"version": 2})

    assert index.query([1.0, 0.0], k=1) == [("doc", 1.0)]
    assert index.meta("doc") == {"version": 2}


def test_cosine_similarity_handles_zero_vector_and_dimension_mismatch():
    assert cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0

    with pytest.raises(ValueError, match="same dimensions"):
        cosine_similarity([1.0], [1.0, 0.0])
