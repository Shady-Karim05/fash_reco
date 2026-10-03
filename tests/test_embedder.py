"""Unit tests for SentenceTransformerEmbedder and FakeEmbedder."""

from unittest.mock import MagicMock, patch

import numpy as np

from app.embedder import FakeEmbedder, SentenceTransformerEmbedder


class TestEmbedderImplementations:
    """Tests for Embedder protocol implementations."""

    def test_fake_embedder_empty_input(self) -> None:
        """FakeEmbedder returns empty array for empty texts."""
        embedder = FakeEmbedder(dimension=128)
        res = embedder.encode([])
        assert res.shape == (0, 128)

    def test_fake_embedder_deterministic(self) -> None:
        """FakeEmbedder generates normalized deterministic unit vectors."""
        embedder = FakeEmbedder(dimension=384)
        vec1 = embedder.encode(["hello world"])
        vec2 = embedder.encode(["hello world"])
        assert np.allclose(vec1, vec2)
        norm = np.linalg.norm(vec1[0])
        assert abs(norm - 1.0) < 1e-5

    def test_sentence_transformer_embedder_empty_input(self) -> None:
        """SentenceTransformerEmbedder handles empty list without calling model."""
        embedder = SentenceTransformerEmbedder()
        res = embedder.encode([])
        assert res.shape == (0, 384)

    def test_sentence_transformer_embedder_mocked_model(self) -> None:
        """SentenceTransformerEmbedder encodes text and returns float32 ndarray."""
        embedder = SentenceTransformerEmbedder(model_name="mock-model")
        mock_st = MagicMock()
        mock_st.encode.return_value = np.ones((2, 384), dtype=np.float32)

        with patch("app.embedder.SentenceTransformer", return_value=mock_st):
            # Access lazy property
            _ = embedder.model
            res = embedder.encode(["text 1", "text 2"], batch_size=32)
            assert res.shape == (2, 384)
            assert res.dtype == np.float32
            mock_st.encode.assert_called_once()
