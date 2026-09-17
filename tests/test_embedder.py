import math
import pytest
from src.embedding.embedder import (
    EMBEDDING_DIM,
    EmbeddingConfigurationError,
    cosine_similarity,
    embed_batch,
    mock_embed,
)
import src.embedding.embedder as embedder


def test_mock_embed_correct_dimension():
    vec = mock_embed("test text")
    assert len(vec) == EMBEDDING_DIM


def test_mock_embed_normalized():
    vec = mock_embed("some airline policy text")
    norm = math.sqrt(sum(x * x for x in vec))
    assert abs(norm - 1.0) < 1e-6


def test_mock_embed_deterministic():
    assert mock_embed("hello world") == mock_embed("hello world")


def test_mock_embed_different_texts_differ():
    assert mock_embed("baggage allowance") != mock_embed("flight delay compensation")


def test_cosine_similarity_identical_vectors():
    vec = mock_embed("test query")
    assert abs(cosine_similarity(vec, vec) - 1.0) < 1e-6


def test_cosine_similarity_in_range():
    vec1 = mock_embed("baggage policy indigo")
    vec2 = mock_embed("flight cancellation dgca")
    sim = cosine_similarity(vec1, vec2)
    assert -1.0 <= sim <= 1.0


def test_cosine_similarity_zero_vector():
    assert cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0


def test_cosine_similarity_orthogonal():
    assert abs(cosine_similarity([1.0, 0.0], [0.0, 1.0])) < 1e-9


def test_embed_batch_rejects_missing_key_without_override(monkeypatch):
    """Regression: a missing OPENAI_API_KEY in a real deployment used to
    silently fall back to semantically-meaningless mock embeddings —
    every search would run without error but return nonsense."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ISHA_ALLOW_MOCK_EMBEDDINGS", raising=False)
    monkeypatch.setattr(embedder, "_path_announced", False)

    with pytest.raises(EmbeddingConfigurationError):
        embed_batch(["baggage allowance"])


@pytest.mark.parametrize("override_value", ["true", "1", "yes", "TRUE"])
def test_embed_batch_allows_mock_with_explicit_override(monkeypatch, override_value):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("ISHA_ALLOW_MOCK_EMBEDDINGS", override_value)
    monkeypatch.setattr(embedder, "_path_announced", False)

    result = embed_batch(["baggage allowance"])

    assert result == [mock_embed("baggage allowance")]


def test_embed_batch_override_false_still_rejects(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("ISHA_ALLOW_MOCK_EMBEDDINGS", "false")
    monkeypatch.setattr(embedder, "_path_announced", False)

    with pytest.raises(EmbeddingConfigurationError):
        embed_batch(["baggage allowance"])
