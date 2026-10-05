"""Regression tests for outfit-specific progressive candidate expansion (Task 1)."""

import time
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np

from app.catalog import CatalogRepository
from app.embedder import Embedder
from app.index import HybridIndex
from app.outfit import compose_outfit
from app.parser import ParsedQuery
from app.pipeline import transform_raw_record
from app.schemas import Product, SearchRequest, SearchResponse
from app.service import SearchService


class DummyEmbedder(Embedder):
    """Deterministic dummy embedder for fast unit tests."""

    def __init__(self, dimension: int = 384, model_name: str = "dummy-model") -> None:
        self.dimension = dimension
        self.model_name = model_name

    def encode(self, texts: list[str], batch_size: int = 32) -> np.ndarray:
        vectors: list[np.ndarray] = []
        for t in texts:
            h = hash(t) % 10000
            vec = np.zeros(self.dimension, dtype=np.float32)
            for i in range(min(10, self.dimension)):
                vec[i] = (h + i) % 100 / 100.0
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec = vec / norm
            vectors.append(vec)
        return np.stack(vectors).astype(np.float32)


def make_product(pid: str, title: str, slot: str, price: float, gender: str = "men") -> Product:
    """Helper to transform and return a valid test product."""
    return transform_raw_record({
        "parent_asin": pid,
        "title": title,
        "price": price,
        "features": [f"Style: {slot}", f"Gender: {gender}"],
    })


class TestOutfitCandidateExpansion:
    """Test suite for progressive candidate expansion."""

    def test_case_1_top50_insufficient_top100_succeeds(self, tmp_path: Path) -> None:
        """Case 1: Top-50 has no valid footwear, but top-100 contains valid footwear.

        Expected: System expands pool to 100 and composes outfit with footwear.
        """
        db_file = tmp_path / "catalog.db"
        repo = CatalogRepository(db_file)
        embedder = DummyEmbedder()
        index = HybridIndex(catalog_repo=repo, embedder=embedder, cache_dir=tmp_path)

        p_top = make_product("T1", "Men Casual Cotton Polo Shirt", "top", 25.0)
        p_bot = make_product("B1", "Men Chino Stretch Shorts", "bottom", 30.0)
        p_acc = make_product("A1", "Men Classic Polarized Sunglasses", "accessory", 15.0)
        p_shoe = make_product("S1", "Men Leather Loafer Boat Shoes", "footwear", 45.0)

        index.upsert_batch_atomic([p_top, p_bot, p_acc, p_shoe])

        parsed = ParsedQuery(
            normalized_query_en="men summer outfit",
            gender="men",
            age_group="adult",
        )

        def mock_search(
            raw_query: str,
            normalized_query_en: str | None = None,
            retrieval_k: int = 50,
            rrf_k: int = 60,
        ) -> tuple[list[tuple[str, float, float]], bool]:
            if retrieval_k <= 50:
                # Top 50 has only top, bottom, accessory; no footwear
                return [("T1", 0.05, 0.8), ("B1", 0.04, 0.75), ("A1", 0.03, 0.7)], False
            # Top 100 reveals footwear
            return [
                ("T1", 0.05, 0.8),
                ("B1", 0.04, 0.75),
                ("A1", 0.03, 0.7),
                ("S1", 0.02, 0.65),
            ], False

        index.search = MagicMock(side_effect=mock_search)  # type: ignore[assignment]

        resp = compose_outfit(
            raw_query="men summer outfit",
            parsed=parsed,
            catalog_repo=repo,
            hybrid_index=index,
            used_fallback=False,
            start_time=time.perf_counter(),
            candidate_depths=[50, 100, 200, 400],
        )

        assert resp.outfit is not None
        assert len(resp.outfit.items) == 4
        slots = [it.slot for it in resp.outfit.items]
        assert "footwear" in slots
        assert "top" in slots
        assert "bottom" in slots
        assert "accessory" in slots
        # Verify index.search was called with 50 and then expanded to 100
        assert index.search.call_count >= 2

    def test_case_2_top100_insufficient_top400_succeeds(self, tmp_path: Path) -> None:
        """Case 2: Top-50 and top-100 are insufficient (no footwear), but top-400 contains footwear.

        Expected: System progressively expands through 50 -> 100 -> 200 -> 400
        and finds valid outfit.
        """
        db_file = tmp_path / "catalog.db"
        repo = CatalogRepository(db_file)
        embedder = DummyEmbedder()
        index = HybridIndex(catalog_repo=repo, embedder=embedder, cache_dir=tmp_path)

        p_top = make_product("T1", "Men Business Casual Button Down Shirt", "top", 35.0)
        p_bot = make_product("B1", "Men Slim Fit Chino Trousers Casual Pants", "bottom", 45.0)
        p_acc = make_product("A1", "Men Classic Leather Dress Belt", "accessory", 20.0)
        p_shoe = make_product("S1", "Men Formal Oxford Leather Shoes", "footwear", 65.0)

        index.upsert_batch_atomic([p_top, p_bot, p_acc, p_shoe])

        parsed = ParsedQuery(
            normalized_query_en="men casual business outfit",
            gender="men",
            age_group="adult",
        )

        def mock_search(
            raw_query: str,
            normalized_query_en: str | None = None,
            retrieval_k: int = 50,
            rrf_k: int = 60,
        ) -> tuple[list[tuple[str, float, float]], bool]:
            if retrieval_k < 400:
                # At 50, 100, 200: no footwear returned
                return [("T1", 0.05, 0.8), ("B1", 0.04, 0.75), ("A1", 0.03, 0.7)], False
            # At 400: footwear finally retrieved
            return [
                ("T1", 0.05, 0.8),
                ("B1", 0.04, 0.75),
                ("A1", 0.03, 0.7),
                ("S1", 0.01, 0.6),
            ], False

        index.search = MagicMock(side_effect=mock_search)  # type: ignore[assignment]

        resp = compose_outfit(
            raw_query="men casual business outfit",
            parsed=parsed,
            catalog_repo=repo,
            hybrid_index=index,
            used_fallback=False,
            start_time=time.perf_counter(),
            candidate_depths=[50, 100, 200, 400],
        )

        assert resp.outfit is not None
        assert len(resp.outfit.items) == 4
        slots = [it.slot for it in resp.outfit.items]
        assert "footwear" in slots
        assert "top" in slots
        assert "bottom" in slots
        assert "accessory" in slots
        # Check that search was called at all 4 depths: 50, 100, 200, 400
        assert index.search.call_count == 4

    def test_case_3_infeasible_budget_even_at_max_depth(self, tmp_path: Path) -> None:
        """Case 3: No valid combination exists within budget even at max candidate depth.

        Expected: Deterministic failure response 'no_outfit_within_budget'.
        """
        db_file = tmp_path / "catalog.db"
        repo = CatalogRepository(db_file)
        embedder = DummyEmbedder()
        index = HybridIndex(catalog_repo=repo, embedder=embedder, cache_dir=tmp_path)

        p_top = make_product("T1", "Men Formal Tuxedo Dress Shirt", "top", 30.0)
        p_bot = make_product("B1", "Men Formal Wedding Tuxedo Trousers", "bottom", 40.0)
        index.upsert_batch_atomic([p_top, p_bot])

        # Budget of $10 is impossible since min 2 items cost $70
        parsed = ParsedQuery(
            normalized_query_en="formal wedding outfit under $10",
            gender="men",
            age_group="adult",
            max_price=10.0,
        )

        resp = compose_outfit(
            raw_query="formal wedding outfit under $10",
            parsed=parsed,
            catalog_repo=repo,
            hybrid_index=index,
            used_fallback=False,
            start_time=time.perf_counter(),
            candidate_depths=[50, 100, 200, 400],
        )

        assert resp.outfit is None
        assert resp.message == "no_outfit_within_budget"

    def test_case_4_product_search_uses_efficient_single_retrieval(self, tmp_path: Path) -> None:
        """Case 4: Normal product search uses standard retrieval path and does not regress.

        Expected: SearchService uses single retrieval_top_k (k=50) and returns SearchResponse.
        """
        db_file = tmp_path / "catalog.db"
        repo = CatalogRepository(db_file)
        embedder = DummyEmbedder()
        index = HybridIndex(catalog_repo=repo, embedder=embedder, cache_dir=tmp_path)

        p1 = make_product(
            "D1", "Women Floral Print Summer Dress", "full_body", 35.0, gender="women"
        )
        index.upsert_batch_atomic([p1])

        index.search = MagicMock(return_value=([("D1", 0.05, 0.85)], False))  # type: ignore[assignment]

        service = SearchService(catalog_repo=repo, hybrid_index=index)
        req = SearchRequest(query="summer dress", mode="product", top_k=1)

        t0 = time.perf_counter()
        resp = service.search(req)
        latency = (time.perf_counter() - t0) * 1000.0

        assert isinstance(resp, SearchResponse)
        assert len(resp.results) == 1
        assert resp.results[0].product_id == "D1"
        # Product mode calls hybrid_index.search exactly once
        assert index.search.call_count == 1
        assert index.search.call_args.kwargs["retrieval_k"] == 50
        # Latency should be well under 100ms for unit test
        assert latency < 100.0
