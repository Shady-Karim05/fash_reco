"""Vector index (FAISS), keyword index (BM25), and Reciprocal Rank Fusion."""

import hashlib
import re
import threading
from collections import defaultdict
from pathlib import Path

import faiss
import numpy as np
from rank_bm25 import BM25Okapi

from app.catalog import CatalogRepository
from app.config import settings
from app.embedder import Embedder
from app.schemas import Product


def tokenize(text: str) -> list[str]:
    """Tokenize text into lowercase alphanumeric tokens for BM25 indexing.

    Args:
        text: Input raw or clean text string.

    Returns:
        List of lowercase token strings.
    """
    return re.findall(r"\w+", text.lower())


def reciprocal_rank_fusion(
    rank_lists: list[list[str]],
    k: int = 60,
) -> list[tuple[str, float]]:
    """Merge ranked lists using Reciprocal Rank Fusion (RRF).

    Pure function. For each rank list, item at rank r (1-indexed) adds:
    1.0 / (k + r) to its cumulative score. Ties are broken deterministically by ID.

    Args:
        rank_lists: List of ranked ID lists (each ordered best to worst).
        k: Smoothing constant parameter (default 60).

    Returns:
        List of (id, fused_score) tuples sorted in descending order of fused_score.
    """
    scores: dict[str, float] = defaultdict(float)

    for rank_list in rank_lists:
        for rank, item_id in enumerate(rank_list, start=1):
            scores[item_id] += 1.0 / (k + rank)

    # Sort descending by score, breaking ties by item_id ascending
    sorted_items = sorted(scores.items(), key=lambda x: (-x[1], x[0]))
    return sorted_items


class VectorIndex:
    """FAISS Inner Product (Cosine similarity on L2-normalized vectors) Index."""

    def __init__(self, dimension: int = 384) -> None:
        """Initialize vector index.

        Args:
            dimension: Embedding vector dimension (default 384).
        """
        self.dimension = dimension
        self.index = faiss.IndexFlatIP(dimension)
        self.id_to_pos: dict[str, int] = {}
        self.pos_to_id: list[str] = []
        self._vectors: list[np.ndarray] = []

    def size(self) -> int:
        """Return total number of indexed vectors."""
        return self.index.ntotal

    def add(self, ids: list[str], vectors: np.ndarray) -> None:
        """Add or update vectors in index.

        Supports replacing existing IDs by maintaining an in-memory vector store
        and rebuilding the Flat index when replacements occur.

        Args:
            ids: List of unique product IDs.
            vectors: 2D float32 numpy array of shape (len(ids), dimension).
        """
        if len(ids) == 0:
            return

        if vectors.dtype != np.float32:
            vectors = vectors.astype(np.float32)

        has_existing = any(item_id in self.id_to_pos for item_id in ids)

        if has_existing:
            # Update existing positions and append new ones
            for item_id, vec in zip(ids, vectors, strict=False):
                if item_id in self.id_to_pos:
                    pos = self.id_to_pos[item_id]
                    self._vectors[pos] = vec
                else:
                    self.id_to_pos[item_id] = len(self._vectors)
                    self.pos_to_id.append(item_id)
                    self._vectors.append(vec)

            # Rebuild FAISS index
            self.index = faiss.IndexFlatIP(self.dimension)
            if self._vectors:
                stacked = np.stack(self._vectors).astype(np.float32)
                self.index.add(stacked)
        else:
            # Fast bulk append
            for item_id, vec in zip(ids, vectors, strict=False):
                self.id_to_pos[item_id] = len(self._vectors)
                self.pos_to_id.append(item_id)
                self._vectors.append(vec)
            self.index.add(vectors)

    def remove(self, product_id: str) -> bool:
        """Remove a product vector from the index.

        Args:
            product_id: Unique identifier to remove.

        Returns:
            True if removed, False if not present.
        """
        if product_id not in self.id_to_pos:
            return False

        pos = self.id_to_pos[product_id]
        del self.id_to_pos[product_id]
        self.pos_to_id.pop(pos)
        self._vectors.pop(pos)

        # Re-index position map
        self.id_to_pos = {pid: i for i, pid in enumerate(self.pos_to_id)}

        # Rebuild FAISS index
        self.index = faiss.IndexFlatIP(self.dimension)
        if self._vectors:
            stacked = np.stack(self._vectors).astype(np.float32)
            self.index.add(stacked)

        return True

    def get_vector(self, product_id: str) -> np.ndarray | None:
        """Retrieve stored normalized embedding vector for a product by ID.

        Args:
            product_id: Unique identifier.

        Returns:
            1D numpy array vector if found, else None.
        """
        if product_id in self.id_to_pos:
            return self._vectors[self.id_to_pos[product_id]]
        return None

    def search(self, query_vector: np.ndarray, top_k: int = 50) -> list[tuple[str, float]]:
        """Search vector index for nearest neighbors by inner product.

        Args:
            query_vector: 1D or 2D float32 normalized vector.
            top_k: Number of candidates to retrieve.

        Returns:
            List of (product_id, similarity_score) sorted descending by score.
        """
        if self.index.ntotal == 0:
            return []

        if query_vector.ndim == 1:
            q = query_vector.reshape(1, -1).astype(np.float32)
        else:
            q = query_vector.astype(np.float32)

        actual_k = min(top_k, self.index.ntotal)
        scores, indices = self.index.search(q, actual_k)

        results: list[tuple[str, float]] = []
        for score, idx in zip(scores[0], indices[0], strict=False):
            if idx != -1 and idx < len(self.pos_to_id):
                results.append((self.pos_to_id[idx], float(score)))

        return results


class KeywordIndex:
    """BM25 keyword search index built over tokenized search text."""

    def __init__(self) -> None:
        """Initialize keyword index."""
        self.ids: list[str] = []
        self.id_to_pos: dict[str, int] = {}
        self.tokenized_corpus: list[list[str]] = []
        self.vocab: set[str] = set()
        self._bm25: BM25Okapi | None = None

    def size(self) -> int:
        """Return number of documents in keyword index."""
        return len(self.ids)

    def build(self, ids: list[str], corpus_texts: list[str]) -> None:
        """Build BM25 index from scratch.

        Complexity: O(N * L) where N is number of documents and L is token length.

        Args:
            ids: List of product IDs.
            corpus_texts: List of corresponding search texts.
        """
        self.ids = list(ids)
        self.id_to_pos = {pid: i for i, pid in enumerate(self.ids)}
        self.tokenized_corpus = [tokenize(t) for t in corpus_texts]
        self.vocab = {tok for doc in self.tokenized_corpus for tok in doc}
        if self.tokenized_corpus:
            self._bm25 = BM25Okapi(self.tokenized_corpus)
        else:
            self._bm25 = None

    def add(self, product_id: str, search_text: str) -> None:
        """Add or update a single product document incrementally.

        Args:
            product_id: Unique product identifier.
            search_text: Product search text representation.
        """
        self.add_batch([(product_id, search_text)])

    def add_batch(self, items: list[tuple[str, str]]) -> None:
        """Batch add or update multiple product documents incrementally.

        Args:
            items: List of (product_id, search_text) tuples.
        """
        if not items:
            return

        for product_id, search_text in items:
            tokens = tokenize(search_text)
            self.vocab.update(tokens)
            if product_id in self.id_to_pos:
                pos = self.id_to_pos[product_id]
                self.tokenized_corpus[pos] = tokens
            else:
                self.id_to_pos[product_id] = len(self.ids)
                self.ids.append(product_id)
                self.tokenized_corpus.append(tokens)

        if self.tokenized_corpus:
            self._bm25 = BM25Okapi(self.tokenized_corpus)

    def remove(self, product_id: str) -> bool:
        """Remove a product from BM25 index.

        Args:
            product_id: Product ID to remove.

        Returns:
            True if removed, False if not found.
        """
        if product_id not in self.id_to_pos:
            return False

        pos = self.id_to_pos[product_id]
        self.ids.pop(pos)
        self.tokenized_corpus.pop(pos)
        self.id_to_pos = {pid: i for i, pid in enumerate(self.ids)}
        self.vocab = {tok for doc in self.tokenized_corpus for tok in doc}

        if self.tokenized_corpus:
            self._bm25 = BM25Okapi(self.tokenized_corpus)
        else:
            self._bm25 = None
        return True

    def search_tokens(self, tokens: list[str], top_k: int = 50) -> list[tuple[str, float]]:
        """Search BM25 index for pre-filtered query tokens.

        Args:
            tokens: Filtered token list.
            top_k: Max results to retrieve.

        Returns:
            List of (product_id, bm25_score) tuples sorted descending.
        """
        if not self._bm25 or not self.ids or not tokens:
            return []

        doc_scores = self._bm25.get_scores(tokens)
        top_indices = np.argsort(doc_scores)[::-1][:top_k]

        results: list[tuple[str, float]] = []
        for idx in top_indices:
            score = float(doc_scores[idx])
            if score > 0.0:
                results.append((self.ids[idx], score))

        return results

    def search(self, query: str, top_k: int = 50) -> list[tuple[str, float]]:
        """Search BM25 index for query tokens.

        Args:
            query: Query string.
            top_k: Max results to retrieve.

        Returns:
            List of (product_id, bm25_score) tuples sorted descending.
        """
        tokens = tokenize(query)
        return self.search_tokens(tokens, top_k=top_k)


class HybridIndex:
    """Hybrid search orchestrator fusing FAISS vector and BM25 keyword indexes via RRF."""

    def __init__(
        self,
        catalog_repo: CatalogRepository,
        embedder: Embedder,
        cache_dir: Path | str | None = None,
    ) -> None:
        """Initialize hybrid index with repositories and dependencies.

        Args:
            catalog_repo: SQLite catalog repository.
            embedder: Concrete Embedder instance.
            cache_dir: Storage path for caching embeddings on disk.
        """
        self.catalog_repo = catalog_repo
        self.embedder = embedder
        self.cache_dir = Path(cache_dir or settings.data_dir)
        self.vector_index = VectorIndex(dimension=384)
        self.keyword_index = KeywordIndex()
        self.index_version: int = self.catalog_repo.get_index_version()
        self._lock = threading.RLock()

    def size(self) -> int:
        """Return total active indexed products."""
        with self._lock:
            return self.vector_index.size()

    def build_from_catalog(self, force_recompute: bool = False) -> int:
        """Build vector and keyword indexes from active SQLite catalog items (A5).

        Loads precomputed vectors from SQLite embeddings table if search_text hash
        and model_name match. Only computes embeddings for missing or mismatched rows.

        Args:
            force_recompute: If True, ignore cached embeddings in SQLite and recompute all.

        Returns:
            Count of rows re-embedded.
        """
        with self._lock:
            products = self.catalog_repo.get_all_active()
            if not products:
                return 0

            model_name = getattr(self.embedder, "model_name", settings.embedding_model_name)
            stored_embeddings = (
                {} if force_recompute else self.catalog_repo.get_all_embeddings(model_name)
            )

            ids = [p.parent_asin for p in products]
            search_texts = [p.search_text for p in products]

            to_embed_indices: list[int] = []
            to_embed_texts: list[str] = []
            vectors_list: list[np.ndarray | None] = [None] * len(products)
            reembedded_count = 0

            for i, p in enumerate(products):
                text_hash = hashlib.sha256(p.search_text.encode("utf-8")).hexdigest()
                if p.parent_asin in stored_embeddings:
                    stored_hash, vblob = stored_embeddings[p.parent_asin]
                    if stored_hash == text_hash:
                        vec = np.frombuffer(vblob, dtype=np.float32)
                        vectors_list[i] = vec
                        continue

                to_embed_indices.append(i)
                to_embed_texts.append(p.search_text)

            if to_embed_texts:
                reembedded_count = len(to_embed_texts)
                new_vectors = self.embedder.encode(
                    to_embed_texts,
                    batch_size=settings.embedding_batch_size,
                )

                embeddings_to_save: list[tuple[str, str, str, bytes]] = []
                for idx, orig_idx in enumerate(to_embed_indices):
                    p = products[orig_idx]
                    vec = new_vectors[idx]
                    vectors_list[orig_idx] = vec
                    thash = hashlib.sha256(p.search_text.encode("utf-8")).hexdigest()
                    vblob = vec.astype(np.float32).tobytes()
                    embeddings_to_save.append((p.parent_asin, thash, model_name, vblob))

                self.catalog_repo.upsert_embeddings_batch(embeddings_to_save)

            # Build indexes
            all_vectors = np.stack([v for v in vectors_list if v is not None]).astype(np.float32)
            self.vector_index = VectorIndex(dimension=all_vectors.shape[1])
            self.vector_index.add(ids, all_vectors)
            self.keyword_index.build(ids, search_texts)
            self.index_version = self.catalog_repo.get_index_version()
            return reembedded_count

    def upsert_product(self, product: Product, vector: np.ndarray | None = None) -> None:
        """Incrementally upsert a single product into vector and keyword indexes."""
        self.upsert_batch_atomic(
            [product], raw_vectors=np.expand_dims(vector, axis=0) if vector is not None else None
        )

    def upsert_batch_atomic(
        self,
        products: list[Product],
        raw_vectors: np.ndarray | None = None,
    ) -> list[Product]:
        """Atomically persist products and embeddings into SQLite and update in-memory indexes.

        If any step fails, changes are rolled back to the previous state.

        Args:
            products: List of Product instances to persist.
            raw_vectors: Optional precomputed embeddings matching products order.

        Returns:
            List of successfully persisted products.
        """
        if not products:
            return []

        with self._lock:
            # 1. Snapshot previous state for affected IDs
            affected_ids = [p.parent_asin for p in products]
            old_vectors: dict[str, np.ndarray | None] = {
                pid: self.vector_index.get_vector(pid) for pid in affected_ids
            }
            old_tokens: dict[str, list[str] | None] = {}
            for pid in affected_ids:
                if pid in self.keyword_index.id_to_pos:
                    pos = self.keyword_index.id_to_pos[pid]
                    old_tokens[pid] = list(self.keyword_index.tokenized_corpus[pos])
                else:
                    old_tokens[pid] = None

            # 2. Compute embeddings if not provided
            if raw_vectors is None:
                search_texts = [p.search_text for p in products]
                vectors = self.embedder.encode(
                    search_texts,
                    batch_size=settings.embedding_batch_size,
                )
            else:
                vectors = raw_vectors

            model_name = getattr(self.embedder, "model_name", settings.embedding_model_name)
            embeddings_data: list[tuple[str, str, str, bytes]] = []
            for p, vec in zip(products, vectors, strict=False):
                thash = hashlib.sha256(p.search_text.encode("utf-8")).hexdigest()
                vblob = vec.astype(np.float32).tobytes()
                embeddings_data.append((p.parent_asin, thash, model_name, vblob))

            # 3. Persist products and embeddings to SQLite in a single transaction
            try:
                persisted_products = self.catalog_repo.upsert_products_and_embeddings_batch(
                    products, embeddings_data
                )
            except Exception:
                raise

            # 4. Update FAISS and BM25 in memory
            try:
                self.vector_index.add(affected_ids, vectors)
                self.keyword_index.add_batch(
                    [(p.parent_asin, p.search_text) for p in persisted_products]
                )
                self.index_version = self.catalog_repo.increment_index_version()
            except Exception as e:
                # Rollback in-memory index state
                for pid, vec in old_vectors.items():
                    if vec is not None:
                        self.vector_index.add([pid], np.expand_dims(vec, axis=0))
                    else:
                        self.vector_index.remove(pid)

                for pid, toks in old_tokens.items():
                    if toks is not None:
                        if pid in self.keyword_index.id_to_pos:
                            pos = self.keyword_index.id_to_pos[pid]
                            self.keyword_index.tokenized_corpus[pos] = toks
                    else:
                        self.keyword_index.remove(pid)
                raise e

            return persisted_products

    def delete_product(self, product_id: str) -> tuple[bool, bool]:
        """Soft delete product from SQLite and immediately remove from in-memory indexes.

        Args:
            product_id: Unique identifier to soft-delete.

        Returns:
            Tuple of (exists: bool, was_already_deleted: bool).
        """
        with self._lock:
            exists, already_deleted = self.catalog_repo.soft_delete_product(product_id)
            if exists and not already_deleted:
                self.vector_index.remove(product_id)
                self.keyword_index.remove(product_id)
                self.index_version = self.catalog_repo.increment_index_version()
            return exists, already_deleted

    def remove_product(self, parent_asin: str) -> None:
        """Remove product from in-memory indexes."""
        with self._lock:
            self.vector_index.remove(parent_asin)
            self.keyword_index.remove(parent_asin)
            self.index_version = self.catalog_repo.increment_index_version()

    def search(
        self,
        raw_query: str,
        normalized_query_en: str | None = None,
        retrieval_k: int = 50,
        rrf_k: int = 60,
    ) -> tuple[list[tuple[str, float, float]], bool]:
        """Perform progressive hybrid retrieval fusing raw query and normalized English query.

        Args:
            raw_query: Raw input query text.
            normalized_query_en: Optional English translated/normalized search text.
            retrieval_k: Number of candidates to retrieve from each sub-index list.
            rrf_k: RRF constant (default 60).

        Returns:
            Tuple of (candidates list, skipped_bm25 bool).
            Each candidate is (parent_asin, fused_score, max_cosine_similarity).
        """
        with self._lock:
            if self.size() == 0:
                return [], False

            # 1. Encode raw query
            raw_vec = self.embedder.encode([raw_query])[0]
            rank_lists: list[list[str]] = []

            # Vector search on raw query
            raw_vec_results = self.vector_index.search(raw_vec, top_k=retrieval_k)
            rank_lists.append([pid for pid, _ in raw_vec_results])

            # 2. If normalized English query differs from raw query, encode and search with it
            norm_text = normalized_query_en.strip() if normalized_query_en else ""
            norm_vec: np.ndarray | None = None
            if norm_text and norm_text.lower() != raw_query.strip().lower():
                norm_vec = self.embedder.encode([norm_text])[0]
                norm_vec_results = self.vector_index.search(norm_vec, top_k=retrieval_k)
                rank_lists.append([pid for pid, _ in norm_vec_results])
                kw_query = norm_text
            else:
                kw_query = raw_query

            # 3. BM25 keyword search with noise guard
            raw_tokens = tokenize(kw_query)
            filtered_tokens = [
                t for t in raw_tokens if len(t) >= 3 and t not in settings.multilingual_stopwords
            ]

            skipped_bm25 = False
            if not filtered_tokens:
                skipped_bm25 = True
            else:
                in_vocab_count = sum(1 for t in filtered_tokens if t in self.keyword_index.vocab)
                if in_vocab_count / len(filtered_tokens) < 0.5:
                    skipped_bm25 = True
                else:
                    kw_results = self.keyword_index.search_tokens(
                        filtered_tokens, top_k=retrieval_k
                    )
                    rank_lists.append([pid for pid, _ in kw_results])

            # 4. Merge rank lists with Reciprocal Rank Fusion
            fused = reciprocal_rank_fusion(rank_lists, k=rrf_k)

            # 5. Compute max cosine similarity over all embedded query variants (A1)
            # Optimization: FAISS IndexFlatIP scores are already dot products
            known_sim: dict[str, float] = {pid: float(s) for pid, s in raw_vec_results}
            if norm_vec is not None:
                for pid, s in norm_vec_results:
                    known_sim[pid] = max(known_sim.get(pid, -1.0), float(s))

            candidates: list[tuple[str, float, float]] = []
            for pid, fused_score in fused:
                if pid in known_sim:
                    sim = known_sim[pid]
                else:
                    p_vec = self.vector_index.get_vector(pid)
                    if p_vec is not None:
                        sim_raw = float(np.dot(raw_vec, p_vec))
                        if norm_vec is not None:
                            sim_norm = float(np.dot(norm_vec, p_vec))
                            sim = max(sim_raw, sim_norm)
                        else:
                            sim = sim_raw
                    else:
                        sim = 0.0
                candidates.append((pid, fused_score, sim))

            return candidates, skipped_bm25

    def is_non_english_noise(self, query: str) -> bool:
        """Check if a query triggers BM25 noise guard as non-English (D4).

        Args:
            query: Raw search query text.

        Returns:
            True if filtered tokens are empty or <50% in catalog vocab.
        """
        raw_tokens = tokenize(query)
        filtered_tokens = [
            t for t in raw_tokens if len(t) >= 3 and t not in settings.multilingual_stopwords
        ]
        if not filtered_tokens:
            return True
        in_vocab_count = sum(1 for t in filtered_tokens if t in self.keyword_index.vocab)
        return in_vocab_count / len(filtered_tokens) < 0.5
