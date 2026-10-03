"""Embedding interface and model implementations for vector representation."""

from typing import Protocol

import numpy as np
from sentence_transformers import SentenceTransformer

from app.config import settings


class Embedder(Protocol):
    """Protocol defining the interface for text embedding models."""

    def encode(self, texts: list[str], batch_size: int = 64) -> np.ndarray:
        """Encode a list of text strings into L2-normalized float32 vectors.

        Args:
            texts: List of input text strings to embed.
            batch_size: Batch size for model inference.

        Returns:
            2D numpy array of shape (len(texts), embedding_dim) with float32 dtype.
        """
        ...


class SentenceTransformerEmbedder:
    """Concrete Embedder wrapping sentence-transformers with lazy loading."""

    def __init__(self, model_name: str | None = None) -> None:
        """Initialize sentence-transformer embedder.

        Args:
            model_name: Name of the huggingface model or local path.
        """
        self.model_name = model_name or settings.embedding_model_name
        self._model: SentenceTransformer | None = None

    @property
    def model(self) -> SentenceTransformer:
        """Lazy loader for SentenceTransformer model instance."""
        if self._model is None:
            self._model = SentenceTransformer(self.model_name)
        return self._model

    def encode(self, texts: list[str], batch_size: int = 64) -> np.ndarray:
        """Encode texts into L2-normalized embeddings using sentence-transformers.

        Args:
            texts: List of text strings.
            batch_size: Batch size for model encoding.

        Returns:
            2D numpy array of float32 embeddings normalized to unit length.
        """
        if not texts:
            return np.empty((0, 384), dtype=np.float32)

        embeddings = self.model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=False,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
        return np.asarray(embeddings, dtype=np.float32)


class FakeEmbedder:
    """Deterministic hash-based Embedder for tests without network or model weights."""

    def __init__(self, dimension: int = 384) -> None:
        """Initialize fake embedder.

        Args:
            dimension: Dimensionality of generated fake embeddings.
        """
        self.dimension = dimension

    def encode(self, texts: list[str], batch_size: int = 64) -> np.ndarray:
        """Deterministically map strings to float32 normalized vectors.

        Args:
            texts: List of strings.
            batch_size: Ignored in fake implementation.

        Returns:
            2D numpy array of shape (len(texts), dimension).
        """
        if not texts:
            return np.empty((0, self.dimension), dtype=np.float32)

        vectors = np.zeros((len(texts), self.dimension), dtype=np.float32)
        for i, text in enumerate(texts):
            # Seed deterministic PRNG with text hash
            seed = abs(hash(text)) % (2**32)
            rng = np.random.default_rng(seed)
            vec = rng.standard_normal(self.dimension).astype(np.float32)
            norm = np.linalg.norm(vec)
            vectors[i] = vec / (norm if norm > 0 else 1.0)

        return vectors
