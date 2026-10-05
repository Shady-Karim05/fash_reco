"""Embedding interface and model implementations for vector representation."""

import threading
from collections import OrderedDict
from typing import Protocol

import numpy as np
import torch
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


class EmbeddingCache:
    """Thread-safe bounded LRU cache for query text embeddings (Phase 2)."""

    def __init__(self, max_size: int = 2000) -> None:
        self.max_size = max_size
        self._cache: OrderedDict[str, np.ndarray] = OrderedDict()
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, text: str) -> np.ndarray | None:
        key = text.strip().lower()
        with self._lock:
            if key in self._cache:
                self.hits += 1
                self._cache.move_to_end(key)
                return self._cache[key]
            self.misses += 1
            return None

    def put(self, text: str, vector: np.ndarray) -> None:
        key = text.strip().lower()
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                self._cache[key] = vector
            else:
                if len(self._cache) >= self.max_size:
                    self._cache.popitem(last=False)
                self._cache[key] = vector

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
            self.hits = 0
            self.misses = 0

    @property
    def hit_rate(self) -> float:
        with self._lock:
            total = self.hits + self.misses
            return round((self.hits / total * 100.0), 2) if total > 0 else 0.0


class SentenceTransformerEmbedder:
    """Concrete Embedder wrapping sentence-transformers with bounded LRU embedding cache."""

    def __init__(self, model_name: str | None = None, cache_size: int = 2000) -> None:
        """Initialize sentence-transformer embedder.

        Args:
            model_name: Name of the huggingface model or local path.
            cache_size: Maximum entries in query embedding LRU cache.
        """
        self.model_name = model_name or settings.embedding_model_name
        self._model: SentenceTransformer | None = None
        self._lock = threading.Lock()
        self.cache = EmbeddingCache(max_size=cache_size)

    @property
    def model(self) -> SentenceTransformer:
        """Thread-safe lazy loader for SentenceTransformer model instance."""
        if self._model is None:
            with self._lock:
                if self._model is None:
                    # Optimize CPU threads if not configured
                    if torch.get_num_threads() > 4:
                        torch.set_num_threads(4)
                    loaded = SentenceTransformer(self.model_name)
                    loaded.eval()
                    self._model = loaded
        return self._model

    def warm_up(self) -> None:
        """Eagerly load model weights and warm up inference engine."""
        _ = self.model
        self.encode(["warm up query"])

    def encode(self, texts: list[str], batch_size: int = 64) -> np.ndarray:
        """Encode texts into L2-normalized embeddings using sentence-transformers.

        Checks embedding cache first; only encodes uncached texts through PyTorch.

        Args:
            texts: List of text strings.
            batch_size: Batch size for model encoding.

        Returns:
            2D numpy array of float32 embeddings normalized to unit length.
        """
        if not texts:
            return np.empty((0, 384), dtype=np.float32)

        # For single text query (most common in search/outfit runtime)
        if len(texts) == 1:
            cached_vec = self.cache.get(texts[0])
            if cached_vec is not None:
                return np.expand_dims(cached_vec, axis=0)

        results: list[np.ndarray | None] = [None] * len(texts)
        missing_indices: list[int] = []
        missing_texts: list[str] = []

        for i, text in enumerate(texts):
            cached = self.cache.get(text)
            if cached is not None:
                results[i] = cached
            else:
                missing_indices.append(i)
                missing_texts.append(text)

        if missing_texts:
            with torch.inference_mode():
                embeddings = self.model.encode(
                    missing_texts,
                    batch_size=batch_size,
                    show_progress_bar=False,
                    normalize_embeddings=True,
                    convert_to_numpy=True,
                )
            new_vectors = np.asarray(embeddings, dtype=np.float32)

            for idx, orig_idx in enumerate(missing_indices):
                vec = new_vectors[idx]
                results[orig_idx] = vec
                self.cache.put(missing_texts[idx], vec)

        return np.stack([v for v in results if v is not None]).astype(np.float32)


class FakeEmbedder:
    """Deterministic hash-based Embedder for tests without network or model weights."""

    def __init__(self, dimension: int = 384, model_name: str = "fake-model") -> None:
        """Initialize fake embedder.

        Args:
            dimension: Dimensionality of generated fake embeddings.
            model_name: Optional model name identifier for persistence.
        """
        self.dimension = dimension
        self.model_name = model_name
        self.cache = EmbeddingCache(max_size=100)

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
