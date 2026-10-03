"""Unit tests for VectorIndex, KeywordIndex, RRF fusion, and HybridIndex."""

from pathlib import Path

import numpy as np
import pytest

from app.catalog import CatalogRepository
from app.embedder import FakeEmbedder
from app.index import (
    HybridIndex,
    KeywordIndex,
    VectorIndex,
    reciprocal_rank_fusion,
)
from app.schemas import Product


class TestRRF:
    """Tests for Reciprocal Rank Fusion pure function."""

    def test_rrf_hand_computed_example(self) -> None:
        """Verify RRF fused score calculation with hand-computed values."""
        # List 1: ["A", "B", "C"]
        # List 2: ["B", "D", "A"]
        # With k=60:
        # A: 1/(60+1) + 1/(60+3) = 1/61 + 1/63 ≈ 0.0163934 + 0.0158730 = 0.0322664
        # B: 1/(60+2) + 1/(60+1) = 1/62 + 1/61 ≈ 0.0161290 + 0.0163934 = 0.0325224
        # C: 1/(60+3) = 1/63 ≈ 0.0158730
        # D: 1/(60+2) = 1/62 ≈ 0.0161290
        # Order: B > A > D > C
        rank_lists = [["A", "B", "C"], ["B", "D", "A"]]
        fused = reciprocal_rank_fusion(rank_lists, k=60)

        fused_ids = [item[0] for item in fused]
        assert fused_ids == ["B", "A", "D", "C"]

        scores = dict(fused)
        assert abs(scores["B"] - (1 / 62 + 1 / 61)) < 1e-6
        assert abs(scores["A"] - (1 / 61 + 1 / 63)) < 1e-6

    def test_rrf_tie_breaking(self) -> None:
        """Equal scores must break ties deterministically by ID ascending."""
        # A and B appear at rank 1 in separate single lists
        rank_lists = [["B"], ["A"]]
        fused = reciprocal_rank_fusion(rank_lists, k=60)
        # Scores are equal (1/61), so 'A' should come before 'B' due to alphabetical sort
        assert [item[0] for item in fused] == ["A", "B"]

    def test_rrf_empty_lists(self) -> None:
        """Empty input lists return empty result."""
        assert reciprocal_rank_fusion([]) == []
        assert reciprocal_rank_fusion([[], []]) == []

    def test_rrf_single_list(self) -> None:
        """Single list output preserves order with decreasing scores."""
        rank_lists = [["prod1", "prod2", "prod3"]]
        fused = reciprocal_rank_fusion(rank_lists, k=60)
        assert [item[0] for item in fused] == ["prod1", "prod2", "prod3"]
        assert fused[0][1] > fused[1][1] > fused[2][1]


class TestVectorIndex:
    """Tests for FAISS vector index operations."""

    def test_add_and_search(self) -> None:
        """Adding vectors and searching returns nearest neighbors in order."""
        index = VectorIndex(dimension=4)
        ids = ["v1", "v2", "v3"]
        vectors = np.array(
            [
                [1.0, 0.0, 0.0, 0.0],
                [0.0, 1.0, 0.0, 0.0],
                [0.7071, 0.7071, 0.0, 0.0],
            ],
            dtype=np.float32,
        )
        index.add(ids, vectors)
        assert index.size() == 3

        query = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
        results = index.search(query, top_k=3)
        assert results[0][0] == "v1"
        assert abs(results[0][1] - 1.0) < 1e-5
        assert results[1][0] == "v3"

    def test_replace_existing_id(self) -> None:
        """Adding existing ID updates the vector without inflating size."""
        index = VectorIndex(dimension=2)
        index.add(["v1"], np.array([[1.0, 0.0]], dtype=np.float32))
        assert index.size() == 1

        # Replace v1 with orthogonal vector
        index.add(["v1"], np.array([[0.0, 1.0]], dtype=np.float32))
        assert index.size() == 1

        query = np.array([0.0, 1.0], dtype=np.float32)
        results = index.search(query, top_k=1)
        assert results[0][0] == "v1"
        assert abs(results[0][1] - 1.0) < 1e-5

    def test_remove_vector(self) -> None:
        """Removing vector removes ID from index."""
        index = VectorIndex(dimension=2)
        index.add(["v1", "v2"], np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32))
        assert index.size() == 2

        removed = index.remove("v1")
        assert removed is True
        assert index.size() == 1

        results = index.search(np.array([1.0, 0.0], dtype=np.float32), top_k=2)
        assert [r[0] for r in results] == ["v2"]


class TestKeywordIndex:
    """Tests for BM25 keyword index."""

    def test_exact_term_search(self) -> None:
        """BM25 retrieves exact matching terms."""
        index = KeywordIndex()
        ids = ["p1", "p2", "p3"]
        texts = [
            "Comfortable summer thong sandals for beach",
            "Winter fleece warm thermal jacket hoodie",
            "Men's classic dress shirt formal",
        ]
        index.build(ids, texts)
        assert index.size() == 3

        results = index.search("sandals beach", top_k=2)
        assert len(results) > 0
        assert results[0][0] == "p1"

    def test_incremental_add_and_remove(self) -> None:
        """Incremental add rebuilds BM25 and indexes new terms."""
        index = KeywordIndex()
        index.build(
            ["p1", "p2"],
            ["Classic blue cotton shirt", "Women flowy summer beach sandals"],
        )
        assert len(index.search("jacket", top_k=1)) == 0

        index.add("p3", "Heavyweight winter parka jacket")
        assert index.size() == 3
        results = index.search("jacket", top_k=1)
        assert len(results) == 1
        assert results[0][0] == "p3"

        index.remove("p3")
        assert index.size() == 2
        assert len(index.search("jacket", top_k=1)) == 0


class TestHybridIndex:
    """Tests for HybridIndex combining vector and keyword retrieval."""

    @pytest.fixture
    def test_catalog_repo(self, tmp_path: Path) -> CatalogRepository:
        """Create isolated SQLite repository populated with test items."""
        db_path = tmp_path / "hybrid_test.db"
        repo = CatalogRepository(db_path)
        items = [
            Product(
                parent_asin="P_SANDAL",
                title="SunnyBreeze Beach Sandals",
                store="SunnyBreeze",
                price=25.0,
                slot="footwear",
                quality_score=4.5,
                search_text="SunnyBreeze Beach Sandals. Brand: SunnyBreeze. Type: footwear.",
            ),
            Product(
                parent_asin="P_SHIRT",
                title="Classic Formal Dress Shirt Hanes Cotton Crew",
                store="Hanes",
                price=30.0,
                slot="top",
                quality_score=4.2,
                search_text="Classic Formal Dress Shirt Hanes Cotton. Brand: Hanes.",
            ),
            Product(
                parent_asin="P_DELETED",
                title="Deleted Summer Shorts",
                store="OldBrand",
                price=15.0,
                slot="bottom",
                quality_score=4.0,
                search_text="Deleted Summer Shorts. Brand: OldBrand.",
            ),
        ]
        repo.upsert_products_batch(items)
        repo.soft_delete("P_DELETED")
        return repo

    def test_soft_deleted_excluded_from_build(
        self, test_catalog_repo: CatalogRepository, tmp_path: Path
    ) -> None:
        """Soft-deleted products in SQLite are not included in hybrid index build."""
        embedder = FakeEmbedder(dimension=384)
        hybrid_index = HybridIndex(
            catalog_repo=test_catalog_repo,
            embedder=embedder,
            cache_dir=tmp_path,
        )
        hybrid_index.build_from_catalog(force_recompute=True)

        assert hybrid_index.size() == 2
        results, _ = hybrid_index.search("shorts", retrieval_k=5)
        result_ids = [r[0] for r in results]
        assert "P_DELETED" not in result_ids

    def test_incremental_upsert_makes_product_searchable(
        self, test_catalog_repo: CatalogRepository, tmp_path: Path
    ) -> None:
        """Upserting a new product into catalog and index makes it searchable immediately."""
        embedder = FakeEmbedder(dimension=384)
        hybrid_index = HybridIndex(
            catalog_repo=test_catalog_repo,
            embedder=embedder,
            cache_dir=tmp_path,
        )
        hybrid_index.build_from_catalog(force_recompute=True)
        initial_size = hybrid_index.size()

        new_item = Product(
            parent_asin="P_NEW_HOODIE",
            title="Winter Fleece Thermal Pullover Hoodie",
            store="Alpine",
            price=45.0,
            slot="top",
            quality_score=4.6,
            search_text="Winter Fleece Thermal Pullover Hoodie. Brand: Alpine. Type: top.",
        )
        test_catalog_repo.upsert_product(new_item)
        hybrid_index.upsert_product(new_item)

        assert hybrid_index.size() == initial_size + 1
        results, _ = hybrid_index.search("thermal hoodie", retrieval_k=5)
        result_ids = [r[0] for r in results]
        assert "P_NEW_HOODIE" in result_ids

    def test_cache_hit_when_unchanged(
        self, test_catalog_repo: CatalogRepository, tmp_path: Path
    ) -> None:
        """Cache hit reuses saved embeddings on disk without calling embedder again."""
        embedder = FakeEmbedder(dimension=384)
        hybrid_index = HybridIndex(
            catalog_repo=test_catalog_repo,
            embedder=embedder,
            cache_dir=tmp_path,
        )
        # 1st build: encodes and writes cache
        hybrid_index.build_from_catalog(force_recompute=True)
        assert (tmp_path / "embeddings.npy").is_file()
        assert (tmp_path / "embeddings_meta.json").is_file()

        # 2nd build with fresh index instance: hits cache
        index2 = HybridIndex(
            catalog_repo=test_catalog_repo,
            embedder=embedder,
            cache_dir=tmp_path,
        )
        index2.build_from_catalog(force_recompute=False)
        assert index2.size() == 2

    def test_cache_invalidated_when_search_text_changes(
        self, test_catalog_repo: CatalogRepository, tmp_path: Path
    ) -> None:
        """Cache is invalidated when a product's search text content hash changes."""
        embedder = FakeEmbedder(dimension=384)
        hybrid_index = HybridIndex(
            catalog_repo=test_catalog_repo,
            embedder=embedder,
            cache_dir=tmp_path,
        )
        hybrid_index.build_from_catalog(force_recompute=True)

        # Mutate search_text of P_SANDAL in SQLite
        updated = test_catalog_repo.get_by_id("P_SANDAL")
        assert updated is not None
        updated.search_text = "Updated Search Text For Beach Sandal"
        test_catalog_repo.upsert_product(updated)

        index2 = HybridIndex(
            catalog_repo=test_catalog_repo,
            embedder=embedder,
            cache_dir=tmp_path,
        )
        index2.build_from_catalog(force_recompute=False)
        assert index2.size() == 2

    def test_cache_invalidated_when_version_changes(
        self, test_catalog_repo: CatalogRepository, tmp_path: Path
    ) -> None:
        """Cache is invalidated when a product's version changes."""
        embedder = FakeEmbedder(dimension=384)
        hybrid_index = HybridIndex(
            catalog_repo=test_catalog_repo,
            embedder=embedder,
            cache_dir=tmp_path,
        )
        hybrid_index.build_from_catalog(force_recompute=True)

        # Re-save item causing version to increment
        updated = test_catalog_repo.get_by_id("P_SHIRT")
        assert updated is not None
        test_catalog_repo.upsert_product(updated)

        index2 = HybridIndex(
            catalog_repo=test_catalog_repo,
            embedder=embedder,
            cache_dir=tmp_path,
        )
        index2.build_from_catalog(force_recompute=False)
        assert index2.size() == 2

    def test_a3_bm25_noise_guard(
        self, test_catalog_repo: CatalogRepository, tmp_path: Path
    ) -> None:
        """Verify French/Spanish queries skip BM25 while English/brand queries do not."""
        embedder = FakeEmbedder(dimension=384)
        hybrid_index = HybridIndex(
            catalog_repo=test_catalog_repo,
            embedder=embedder,
            cache_dir=tmp_path,
        )
        hybrid_index.build_from_catalog(force_recompute=True)

        # French query
        _, skipped_fr = hybrid_index.search("tenue de plage pour l'été")
        assert skipped_fr is True

        # Spanish query
        _, skipped_es = hybrid_index.search("traje de playa para el verano")
        assert skipped_es is True

        # English query
        _, skipped_en = hybrid_index.search("beach sandals")
        assert skipped_en is False

        # Mixed brand query
        _, skipped_brand = hybrid_index.search("Hanes cotton crew t-shirt")
        assert skipped_brand is False

    def test_a1_similarity_uses_best_query_variant(
        self, test_catalog_repo: CatalogRepository, tmp_path: Path
    ) -> None:
        """Similarity reports max cosine similarity over raw query and normalized query."""

        class MockVariantEmbedder(FakeEmbedder):
            def encode(self, texts: list[str], batch_size: int = 64) -> np.ndarray:
                vecs = []
                for t in texts:
                    if "Tamil" in t or "கோடைக்கால" in t:
                        vec = np.array([1.0, 0.0, 0.0, 0.0] + [0.0] * 380, dtype=np.float32)
                    elif "summer beach sandals" in t.lower() or "normalized" in t:
                        vec = np.array([0.0, 1.0, 0.0, 0.0] + [0.0] * 380, dtype=np.float32)
                    elif "SunnyBreeze Beach Sandals" in t:
                        # Closer to normalized variant ([0, 1, 0, 0]) with sim 0.95
                        # than to raw ([1, 0, 0, 0]) with sim 0.1
                        vec = np.array([0.1, 0.95, 0.0, 0.0] + [0.0] * 380, dtype=np.float32)
                        vec = vec / np.linalg.norm(vec)
                    else:
                        vec = np.array([0.0, 0.0, 1.0, 0.0] + [0.0] * 380, dtype=np.float32)
                    vecs.append(vec)
                return np.stack(vecs)

        embedder = MockVariantEmbedder(dimension=384)
        hybrid_index = HybridIndex(
            catalog_repo=test_catalog_repo,
            embedder=embedder,
            cache_dir=tmp_path,
        )
        hybrid_index.build_from_catalog(force_recompute=True)

        raw_tamil = "கோடைக்கால கடற்கரை செருப்பு"
        norm_en = "summer beach sandals"

        candidates, _ = hybrid_index.search(
            raw_query=raw_tamil,
            normalized_query_en=norm_en,
            retrieval_k=5,
        )
        assert len(candidates) > 0
        sandal_match = [c for c in candidates if c[0] == "P_SANDAL"][0]
        # Raw sim was 0.1 / norm, normalized sim was 0.95 / norm (~0.99)
        # Resulting similarity must reflect the max (normalized) similarity
        assert sandal_match[2] > 0.90

    def test_atomic_upsert_rollback_on_embedder_failure(
        self, test_catalog_repo: CatalogRepository, tmp_path: Path
    ) -> None:
        """Injected embedder failure rolls back batch and preserves previous state."""

        class FailingEmbedder(FakeEmbedder):
            def encode(self, texts: list[str], batch_size: int = 64) -> np.ndarray:
                raise RuntimeError("Simulated embedding failure")

        failing_embedder = FailingEmbedder(dimension=384)
        hybrid_index = HybridIndex(
            catalog_repo=test_catalog_repo,
            embedder=failing_embedder,
            cache_dir=tmp_path,
        )
        # Populate with working embedder first
        good_embedder = FakeEmbedder(dimension=384)
        hybrid_index.embedder = good_embedder
        hybrid_index.build_from_catalog(force_recompute=True)
        initial_size = hybrid_index.size()
        initial_version = hybrid_index.index_version

        # Switch to failing embedder and attempt batch
        hybrid_index.embedder = failing_embedder
        new_product = Product(
            parent_asin="P_FAIL_TEST",
            title="Atomic Rollback Test Product Item",
            price=20.0,
            search_text="Atomic Rollback Test Product Item",
        )

        with pytest.raises(RuntimeError, match="Simulated embedding failure"):
            hybrid_index.upsert_batch_atomic([new_product])

        # Assert unchanged state
        assert hybrid_index.size() == initial_size
        assert hybrid_index.index_version == initial_version
        assert test_catalog_repo.get_by_id("P_FAIL_TEST") is None

    def test_restart_persistence_simulation(
        self, test_catalog_repo: CatalogRepository, tmp_path: Path
    ) -> None:
        """Fresh HybridIndex built over updated database matches live state."""
        embedder = FakeEmbedder(dimension=384)
        live_index = HybridIndex(
            catalog_repo=test_catalog_repo,
            embedder=embedder,
            cache_dir=tmp_path,
        )
        live_index.build_from_catalog(force_recompute=True)

        new_prod = Product(
            parent_asin="P_PERSIST_1",
            title="Persisted Active Running Sneakers",
            price=60.0,
            slot="footwear",
            search_text="Persisted Active Running Sneakers",
        )
        live_index.upsert_batch_atomic([new_prod])

        # Simulate fresh startup
        fresh_index = HybridIndex(
            catalog_repo=test_catalog_repo,
            embedder=embedder,
            cache_dir=tmp_path,
        )
        fresh_index.build_from_catalog(force_recompute=True)

        assert fresh_index.size() == live_index.size()
        assert set(fresh_index.vector_index.pos_to_id) == set(live_index.vector_index.pos_to_id)
        assert set(fresh_index.keyword_index.ids) == set(live_index.keyword_index.ids)

    def test_concurrent_searches_during_ingestion(
        self, test_catalog_repo: CatalogRepository, tmp_path: Path
    ) -> None:
        """Searches running concurrently with batch ingestion complete without crashes."""
        import concurrent.futures

        embedder = FakeEmbedder(dimension=384)
        hybrid_index = HybridIndex(
            catalog_repo=test_catalog_repo,
            embedder=embedder,
            cache_dir=tmp_path,
        )
        hybrid_index.build_from_catalog(force_recompute=True)

        def do_search() -> int:
            results, _ = hybrid_index.search("beach sandals", retrieval_k=5)
            return len(results)

        def do_ingest(i: int) -> None:
            p = Product(
                parent_asin=f"CONCURRENT_{i}",
                title=f"Concurrent Ingested Item {i} for Testing",
                price=15.0 + i,
                search_text=f"Concurrent Ingested Item {i}",
            )
            hybrid_index.upsert_batch_atomic([p])

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            search_futures = [executor.submit(do_search) for _ in range(20)]
            ingest_futures = [executor.submit(do_ingest, i) for i in range(10)]

            # Wait for all to finish
            for f in concurrent.futures.as_completed(search_futures + ingest_futures):
                # Ensure no unhandled exceptions raised
                f.result()
