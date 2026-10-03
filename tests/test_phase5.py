"""Comprehensive tests for Part A (A5, A7) and Part B Phase 5 features (B1-B9)."""

import concurrent.futures
import sqlite3
import time
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.cache import ParseCache, QueryCache
from app.catalog import CatalogRepository
from app.config import settings
from app.embedder import Embedder
from app.exceptions import CatalogError
from app.filters import (
    collapse_near_duplicates,
    generate_item_explanation,
    is_innerwear_allowed,
)
from app.index import HybridIndex
from app.main import app, get_catalog_repo, get_hybrid_index
from app.outfit import compose_outfit, fetch_slot_candidates, is_accessory_allowed_type
from app.parser import ParsedQuery
from app.pipeline import transform_raw_record
from app.schemas import SearchResponse


@pytest.fixture
def phase5_client(tmp_path: Path) -> TestClient:
    db_file = tmp_path / "catalog.db"
    repo = CatalogRepository(db_file)
    embedder = DummyEmbedder()
    index = HybridIndex(catalog_repo=repo, embedder=embedder, cache_dir=tmp_path)
    index.build_from_catalog(force_recompute=True)

    import app.main as main_mod

    old_repo = main_mod.catalog_repo_instance
    old_index = main_mod.hybrid_index_instance
    main_mod.catalog_repo_instance = repo
    main_mod.hybrid_index_instance = index

    app.dependency_overrides[get_catalog_repo] = lambda: repo
    app.dependency_overrides[get_hybrid_index] = lambda: index

    client = TestClient(app)
    yield client

    main_mod.catalog_repo_instance = old_repo
    main_mod.hybrid_index_instance = old_index
    app.dependency_overrides.clear()


class DummyEmbedder(Embedder):
    """Deterministic dummy embedder for fast unit tests."""

    def __init__(self, dimension: int = 384, model_name: str = "dummy-model") -> None:
        self.dimension = dimension
        self.model_name = model_name

    def encode(self, texts: list[str], batch_size: int = 32) -> np.ndarray:
        vectors: list[np.ndarray] = []
        for t in texts:
            # Deterministic hash-based vector
            h = hash(t) % 10000
            vec = np.zeros(self.dimension, dtype=np.float32)
            for i in range(min(10, self.dimension)):
                vec[i] = (h + i) % 100 / 100.0
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec = vec / norm
            vectors.append(vec)
        return np.stack(vectors).astype(np.float32)


# =====================================================================
# A5. SQLite Embeddings Persistence Tests
# =====================================================================
class TestSQLiteEmbeddingsPersistence:
    """Tests for SQLite-backed vector persistence and conditional re-embedding (A5)."""

    def test_restart_embeds_zero_rows_when_unchanged(self, tmp_path: Path) -> None:
        db_file = tmp_path / "catalog.db"
        repo = CatalogRepository(db_file)
        embedder = DummyEmbedder(model_name="test-model")

        # Ingest 2 products
        prod1 = transform_raw_record(
            {"parent_asin": "P1", "title": "Blue Summer Beach Dress", "price": 25.0}
        )
        prod2 = transform_raw_record(
            {"parent_asin": "P2", "title": "Men's Running Athletic Shorts", "price": 20.0}
        )

        index = HybridIndex(catalog_repo=repo, embedder=embedder, cache_dir=tmp_path)
        index.upsert_batch_atomic([prod1, prod2])
        assert index.size() == 2

        # Simulate restart with new index instance over same DB
        restarted_index = HybridIndex(catalog_repo=repo, embedder=embedder, cache_dir=tmp_path)
        reembedded = restarted_index.build_from_catalog()
        assert reembedded == 0
        assert restarted_index.size() == 2

    def test_changing_one_search_text_reembeds_exactly_one_row(self, tmp_path: Path) -> None:
        db_file = tmp_path / "catalog.db"
        repo = CatalogRepository(db_file)
        embedder = DummyEmbedder(model_name="test-model")

        prod1 = transform_raw_record(
            {"parent_asin": "P1", "title": "Blue Summer Beach Dress", "price": 25.0}
        )
        prod2 = transform_raw_record(
            {"parent_asin": "P2", "title": "Men's Running Athletic Shorts", "price": 20.0}
        )

        index = HybridIndex(catalog_repo=repo, embedder=embedder, cache_dir=tmp_path)
        index.upsert_batch_atomic([prod1, prod2])

        # Modify search_text of P1 directly in SQLite to simulate updated text
        with repo._get_connection() as conn:
            conn.execute(
                "UPDATE products SET search_text = 'Modified Text' WHERE parent_asin = 'P1'"
            )

        # Restart
        restarted_index = HybridIndex(catalog_repo=repo, embedder=embedder, cache_dir=tmp_path)
        reembedded = restarted_index.build_from_catalog()
        assert reembedded == 1
        assert restarted_index.size() == 2

    def test_changing_model_name_reembeds_all(self, tmp_path: Path) -> None:
        db_file = tmp_path / "catalog.db"
        repo = CatalogRepository(db_file)
        embedder1 = DummyEmbedder(model_name="model-v1")

        prod1 = transform_raw_record(
            {"parent_asin": "P1", "title": "Blue Summer Beach Dress", "price": 25.0}
        )
        prod2 = transform_raw_record(
            {"parent_asin": "P2", "title": "Men's Running Athletic Shorts", "price": 20.0}
        )

        index = HybridIndex(catalog_repo=repo, embedder=embedder1, cache_dir=tmp_path)
        index.upsert_batch_atomic([prod1, prod2])

        # Restart with model-v2
        embedder2 = DummyEmbedder(model_name="model-v2")
        restarted_index = HybridIndex(catalog_repo=repo, embedder=embedder2, cache_dir=tmp_path)
        reembedded = restarted_index.build_from_catalog()
        assert reembedded == 2
        assert restarted_index.size() == 2

    def test_failed_write_leaves_no_orphan_embedding(self, tmp_path: Path) -> None:
        db_file = tmp_path / "catalog.db"
        repo = CatalogRepository(db_file)

        # Intentionally invalid SQL or constraint failure
        with pytest.raises((sqlite3.DatabaseError, CatalogError)), repo._get_connection() as conn:
            # Force an invalid insert
            conn.execute("INSERT INTO products (parent_asin) VALUES (NULL);")

        stored = repo.get_all_embeddings("dummy-model")
        assert len(stored) == 0


# =====================================================================
# A7. Missing API and Index Tests
# =====================================================================
class TestAdminAndIndexEdgeCases:
    """Tests for edge cases specified in A7."""

    def test_over_limit_batch_returns_422(self, phase5_client: TestClient) -> None:
        client = phase5_client
        settings.admin_api_key = "secret-admin-key"
        # 501 items exceeds max 500
        items = [
            {"parent_asin": f"B{i:05d}", "title": f"Product Title Number {i}", "price": 10.0}
            for i in range(501)
        ]
        resp = client.post(
            "/products", json={"products": items}, headers={"X-API-Key": "secret-admin-key"}
        )
        assert resp.status_code == 422

    def test_missing_x_api_key_header_returns_401(self, phase5_client: TestClient) -> None:
        client = phase5_client
        settings.admin_api_key = "secret-admin-key"
        resp = client.post(
            "/products",
            json={
                "products": [{"parent_asin": "B123", "title": "Test Title Valid", "price": 10.0}]
            },
        )
        assert resp.status_code == 401

    def test_delete_of_unknown_id_returns_404(self, phase5_client: TestClient) -> None:
        client = phase5_client
        settings.admin_api_key = "secret-admin-key"
        resp = client.delete(
            "/products/NON_EXISTENT_ID_99999", headers={"X-API-Key": "secret-admin-key"}
        )
        assert resp.status_code == 404

    def test_repeated_delete_returns_already_deleted(self, tmp_path: Path) -> None:
        db_file = tmp_path / "catalog.db"
        repo = CatalogRepository(db_file)
        embedder = DummyEmbedder()
        index = HybridIndex(catalog_repo=repo, embedder=embedder, cache_dir=tmp_path)

        p = transform_raw_record(
            {"parent_asin": "DEL_ITEM_1", "title": "Item To Be Deleted Twice", "price": 15.0}
        )
        index.upsert_batch_atomic([p])

        # First delete
        exists1, already1 = index.delete_product("DEL_ITEM_1")
        assert exists1 is True
        assert already1 is False

        # Second delete
        exists2, already2 = index.delete_product("DEL_ITEM_1")
        assert exists2 is True
        assert already2 is True

    def test_re_post_restores_deleted_product(self, tmp_path: Path) -> None:
        db_file = tmp_path / "catalog.db"
        repo = CatalogRepository(db_file)
        embedder = DummyEmbedder()
        index = HybridIndex(catalog_repo=repo, embedder=embedder, cache_dir=tmp_path)

        p = transform_raw_record(
            {
                "parent_asin": "RESTORE_ITEM",
                "title": "Item To Be Deleted And Restored",
                "price": 15.0,
            }
        )
        index.upsert_batch_atomic([p])
        assert index.size() == 1

        # Delete
        index.delete_product("RESTORE_ITEM")
        assert index.size() == 0
        assert repo.get_by_id("RESTORE_ITEM") is None

        # Re-post
        p_repost = transform_raw_record(
            {
                "parent_asin": "RESTORE_ITEM",
                "title": "Item To Be Deleted And Restored (Version 2)",
                "price": 15.0,
            }
        )
        index.upsert_batch_atomic([p_repost])
        assert index.size() == 1
        restored = repo.get_by_id("RESTORE_ITEM")
        assert restored is not None
        assert restored.version == 2
        assert restored.is_deleted is False

    def test_index_version_survives_restart(self, tmp_path: Path) -> None:
        db_file = tmp_path / "catalog.db"
        repo = CatalogRepository(db_file)
        embedder = DummyEmbedder()
        index = HybridIndex(catalog_repo=repo, embedder=embedder, cache_dir=tmp_path)

        p = transform_raw_record(
            {"parent_asin": "VER_ITEM", "title": "Item Version Check Title", "price": 20.0}
        )
        index.upsert_batch_atomic([p])
        v1 = index.index_version
        assert v1 >= 2

        # Restart
        restarted_index = HybridIndex(catalog_repo=repo, embedder=embedder, cache_dir=tmp_path)
        restarted_index.build_from_catalog()
        assert restarted_index.index_version == v1


# =====================================================================
# B1, B2, B3, B5. Filters, Dedup, Explanations
# =====================================================================
class TestPhase5FiltersAndDeduplication:
    """Tests for B1, B2, B3, and B5."""

    def test_near_duplicate_collapse_athletic_shorts_pair(self) -> None:
        """Required test: Athletic Works Men's Active Shorts (Large) and (Medium) pair collapsed."""
        p_large = transform_raw_record(
            {
                "parent_asin": "B01",
                "title": "Athletic Works Men's Active Shorts (Large, Black)",
                "store": "Athletic Works",
                "price": 14.99,
            }
        )
        p_medium = transform_raw_record(
            {
                "parent_asin": "B02",
                "title": "Athletic Works Men's Active Shorts (Medium, Navy)",
                "store": "Athletic Works",
                "price": 14.99,
            }
        )

        candidates = [(p_large, 0.95, 0.90), (p_medium, 0.92, 0.88)]
        deduped, collapsed = collapse_near_duplicates(candidates)

        assert len(deduped) == 1
        assert collapsed == 1
        assert deduped[0][0].parent_asin == "B01"

    def test_pack_size_differences_not_collapsed(self) -> None:
        """Required test: 'Pack of 5' vs 'Pack of 3' must NOT be collapsed."""
        p_pack5 = transform_raw_record(
            {
                "parent_asin": "P5",
                "title": "Hanes Men's Crew T-Shirts Pack of 5",
                "store": "Hanes",
                "price": 25.0,
            }
        )
        p_pack3 = transform_raw_record(
            {
                "parent_asin": "P3",
                "title": "Hanes Men's Crew T-Shirts Pack of 3",
                "store": "Hanes",
                "price": 18.0,
            }
        )

        candidates = [(p_pack5, 0.90, 0.85), (p_pack3, 0.88, 0.84)]
        deduped, collapsed = collapse_near_duplicates(candidates)

        assert len(deduped) == 2
        assert collapsed == 0

    def test_innerwear_policy_exclusion(self) -> None:
        parsed_general = ParsedQuery(normalized_query_en="comfortable clothes", slots=[])
        assert is_innerwear_allowed("comfortable clothes", parsed_general) is False

        parsed_innerwear = ParsedQuery(
            normalized_query_en="boxer briefs for men", slots=["innerwear"]
        )
        assert is_innerwear_allowed("boxer briefs for men", parsed_innerwear) is True

    def test_explanation_deterministic_facts_only(self) -> None:
        p = transform_raw_record(
            {
                "parent_asin": "EXP1",
                "title": "Nike Men's Summer Running Shorts Black",
                "store": "Nike",
                "price": 30.0,
                "features": ["Lightweight breathable fabric"],
            }
        )
        parsed = ParsedQuery(
            normalized_query_en="Nike shorts",
            brand="Nike",
            season="summer",
            colors=["black"],
        )
        reason = generate_item_explanation(
            p, parsed, raw_query="Nike shorts", similarity=0.85, slot_role="bottom"
        )
        assert "Chosen as bottom" in reason
        assert "Matches brand Nike" in reason
        assert "Matching color: black" in reason
        assert "Suited for summer" in reason


# =====================================================================
# B4. Outfit Mode Tests
# =====================================================================
class TestOutfitMode:
    """Tests for outfit templates, coherence, and budget semantics (B4)."""

    def test_outfit_templates_and_budget(self, tmp_path: Path) -> None:
        db_file = tmp_path / "catalog.db"
        repo = CatalogRepository(db_file)
        embedder = DummyEmbedder()
        index = HybridIndex(catalog_repo=repo, embedder=embedder, cache_dir=tmp_path)

        # Ingest full outfit components
        top = transform_raw_record(
            {"parent_asin": "T1", "title": "Men's Cotton Summer T-Shirt", "price": 20.0}
        )
        bot = transform_raw_record(
            {"parent_asin": "B1", "title": "Men's Casual Chino Shorts", "price": 25.0}
        )
        shoe = transform_raw_record(
            {"parent_asin": "S1", "title": "Men's Canvas Boat Shoes", "price": 30.0}
        )
        acc = transform_raw_record(
            {"parent_asin": "A1", "title": "Men's Polarized Sunglasses", "price": 15.0}
        )
        index.upsert_batch_atomic([top, bot, shoe, acc])

        parsed = ParsedQuery(
            normalized_query_en="summer beach outfit",
            gender="men",
            age_group="adult",
            max_price=100.0,
            season="summer",
        )

        resp = compose_outfit(
            raw_query="summer beach outfit under $100",
            parsed=parsed,
            catalog_repo=repo,
            hybrid_index=index,
            used_fallback=False,
            start_time=time.perf_counter(),
        )

        assert resp.outfit is not None
        assert resp.outfit.total_price <= 100.0
        assert len(resp.outfit.items) >= 2
        assert all(it.gender in {"men", "unisex"} for it in resp.outfit.items)
        assert all(it.age_group == "adult" for it in resp.outfit.items)

    def test_outfit_budget_too_small_returns_no_outfit_within_budget(self, tmp_path: Path) -> None:
        db_file = tmp_path / "catalog.db"
        repo = CatalogRepository(db_file)
        embedder = DummyEmbedder()
        index = HybridIndex(catalog_repo=repo, embedder=embedder, cache_dir=tmp_path)

        top = transform_raw_record(
            {"parent_asin": "T1", "title": "Men's Cotton Summer T-Shirt", "price": 20.0}
        )
        bot = transform_raw_record(
            {"parent_asin": "B1", "title": "Men's Casual Chino Shorts", "price": 25.0}
        )
        index.upsert_batch_atomic([top, bot])

        parsed = ParsedQuery(
            normalized_query_en="summer beach outfit",
            gender="men",
            age_group="adult",
            max_price=15.0,  # Total min price is 20+25=45 > 15
        )

        resp = compose_outfit(
            raw_query="summer beach outfit under $15",
            parsed=parsed,
            catalog_repo=repo,
            hybrid_index=index,
            used_fallback=False,
            start_time=time.perf_counter(),
        )

        assert resp.outfit is None
        assert resp.message == "no_outfit_within_budget"

    def test_is_accessory_allowed_type(self) -> None:
        assert is_accessory_allowed_type(None, "beach outfit") is True
        assert is_accessory_allowed_type("sunglasses", "beach outfit") is True
        # Restricted types
        assert is_accessory_allowed_type("socks", "beach outfit") is False
        assert is_accessory_allowed_type("socks", "athletic socks outfit") is True
        assert is_accessory_allowed_type("gloves", "winter outfit") is False
        assert is_accessory_allowed_type("gloves", "winter gloves outfit") is True
        assert is_accessory_allowed_type("body_jewelry", "outfit") is False
        assert is_accessory_allowed_type("body_jewelry", "nose bone piercing") is True
        assert is_accessory_allowed_type("hair", "outfit") is False
        assert is_accessory_allowed_type("hair", "outfit with hair clip") is True

    def test_outfit_mode_non_fashion_query(self, tmp_path: Path) -> None:
        db_file = tmp_path / "catalog.db"
        repo = CatalogRepository(db_file)
        embedder = DummyEmbedder()
        index = HybridIndex(catalog_repo=repo, embedder=embedder, cache_dir=tmp_path)

        parsed = ParsedQuery(
            is_fashion_query=False,
            normalized_query_en="python programming tutorials",
        )
        resp = compose_outfit(
            raw_query="python programming tutorials",
            parsed=parsed,
            catalog_repo=repo,
            hybrid_index=index,
            used_fallback=False,
            start_time=time.perf_counter(),
        )
        assert resp.outfit is None
        assert resp.message == "not_a_fashion_query"

    def test_fetch_slot_candidates_innerwear_returns_empty(self, tmp_path: Path) -> None:
        db_file = tmp_path / "catalog.db"
        repo = CatalogRepository(db_file)
        embedder = DummyEmbedder()
        index = HybridIndex(catalog_repo=repo, embedder=embedder, cache_dir=tmp_path)

        parsed = ParsedQuery(normalized_query_en="men underwear boxers")
        cands = fetch_slot_candidates(
            slot="innerwear",
            raw_query="men underwear boxers",
            parsed=parsed,
            catalog_repo=repo,
            hybrid_index=index,
            quality_bounds=(1.0, 5.0),
        )
        assert cands == []


# =====================================================================
# B6. Cache Behavior Tests
# =====================================================================
class TestCaches:
    """Tests for QueryCache and TTL ParseCache (B6)."""

    def test_query_cache_hit_and_version_invalidation(self) -> None:
        qc = QueryCache(max_size=10)
        key1 = qc.make_key("blue dress", {"gender": "women"}, None, 10, "product", 1)
        resp = SearchResponse(
            results=[],
            meta={
                "parsed_filters": {},
                "used_fallback": False,
                "latency_ms": 1.0,
                "index_version": 1,
                "excluded_by_filters": 0,
            },
        )

        qc.put(key1, resp)
        assert qc.get(key1) is not None
        assert qc.hits == 1

        # Key at version 2 naturally misses
        key2 = qc.make_key("blue dress", {"gender": "women"}, None, 10, "product", 2)
        assert qc.get(key2) is None
        assert qc.misses == 1

    def test_parse_cache_no_fallback_and_ttl(self) -> None:
        pc = ParseCache(max_size=10, ttl_seconds=0.1)
        parsed = ParsedQuery(normalized_query_en="test query")

        # Fallback parse must not be cached
        pc.put("fallback query", parsed, used_fallback=True)
        assert pc.get("fallback query") is None

        # LLM parse is cached
        pc.put("llm query", parsed, used_fallback=False)
        assert pc.get("llm query") is not None
        assert pc.hits == 1

        # Expire after TTL
        time.sleep(0.15)
        assert pc.get("llm query") is None
        assert pc.misses == 2

    def test_concurrent_cache_access(self) -> None:
        qc = QueryCache(max_size=100)
        resp = SearchResponse(
            results=[],
            meta={
                "parsed_filters": {},
                "used_fallback": False,
                "latency_ms": 1.0,
                "index_version": 1,
                "excluded_by_filters": 0,
            },
        )

        def worker(idx: int) -> None:
            key = qc.make_key(f"query_{idx % 10}", {}, None, 10, "product", 1)
            qc.put(key, resp)
            qc.get(key)

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
            futures = [ex.submit(worker, i) for i in range(100)]
            concurrent.futures.wait(futures)

        assert qc.hits > 0


# =====================================================================
# B7. Observability & Metrics Tests
# =====================================================================
class TestObservability:
    """Tests for request-id header, metrics endpoint JSON and Prometheus (B7)."""

    def test_x_request_id_generated_and_returned(self, phase5_client: TestClient) -> None:
        client = phase5_client
        resp = client.get("/health")
        assert resp.status_code == 200
        assert "X-Request-ID" in resp.headers

    def test_metrics_json_and_prometheus_shape(self, phase5_client: TestClient) -> None:
        client = phase5_client
        # JSON
        resp_json = client.get("/metrics")
        assert resp_json.status_code == 200
        data = resp_json.json()
        assert "search_latency_percentiles_ms" in data
        assert "fallback_rate" in data
        assert "query_cache_hit_rate" in data
        assert "index_size" in data

        # Prometheus
        resp_prom = client.get("/metrics/prometheus")
        assert resp_prom.status_code == 200
        assert "fashion_search_index_size" in resp_prom.text
        assert "fashion_search_latency_p50_ms" in resp_prom.text
