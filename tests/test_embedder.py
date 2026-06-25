import math
import pytest
from src.embedding.embedder import EMBEDDING_DIM, cosine_similarity, mock_embed


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
