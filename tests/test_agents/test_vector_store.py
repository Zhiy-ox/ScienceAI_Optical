"""Tests for the vector store (unit tests using mock, no Qdrant needed)."""

from science_ai.storage.vector_store import VectorStore


def test_stable_uuid_deterministic():
    """Same key should always produce the same UUID."""
    uuid1 = VectorStore._stable_uuid("paper:123")
    uuid2 = VectorStore._stable_uuid("paper:123")
    assert uuid1 == uuid2


def test_stable_uuid_different_keys():
    """Different keys should produce different UUIDs."""
    uuid1 = VectorStore._stable_uuid("paper:123")
    uuid2 = VectorStore._stable_uuid("paper:456")
    assert uuid1 != uuid2


def test_stable_uuid_different_types():
    """Different prefixes should produce different UUIDs."""
    uuid1 = VectorStore._stable_uuid("paper:123")
    uuid2 = VectorStore._stable_uuid("method:123:cnn")
    uuid3 = VectorStore._stable_uuid("claim:123:some claim")
    assert len({uuid1, uuid2, uuid3}) == 3
