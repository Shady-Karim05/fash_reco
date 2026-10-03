"""Integration tests for FastAPI endpoints (/health and /search)."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.catalog import CatalogRepository
from app.embedder import FakeEmbedder
from app.index import HybridIndex
from app.main import app, get_catalog_repo, get_hybrid_index
from app.schemas import Product


@pytest.fixture
def test_app_client(tmp_path: Path) -> TestClient:
    """Fixture configuring FastAPI TestClient with isolated catalog and FakeEmbedder."""
    db_path = tmp_path / "test_api_catalog.db"
    repo = CatalogRepository(db_path)

    # Populate catalog with sample products
    sample_products: list[Product] = [
        Product(
            parent_asin="P_SANDAL",
            title="SunnyBreeze Beach Thong Sandals (Blue)",
            store="SunnyBreeze",
            price=29.81,
            slot="footwear",
            gender="women",
            age_group="adult",
            colors=["blue"],
            quality_score=4.5,
            search_text=(
                "SunnyBreeze Beach Thong Sandals (Blue). Brand: SunnyBreeze. Type: footwear."
            ),
        ),
        Product(
            parent_asin="P_SHIRT",
            title="Van Heusen Men's Classic Fit Dress Shirt",
            store="Van Heusen",
            price=24.99,
            slot="top",
            gender="men",
            age_group="adult",
            colors=["white"],
            quality_score=4.3,
            search_text="Van Heusen Men's Classic Fit Dress Shirt. Brand: Van Heusen. Type: top.",
        ),
        Product(
            parent_asin="P_SHORTS",
            title="Kanu Surf Men's Beach Swim Trunks Board Shorts",
            store="Kanu Surf",
            price=18.50,
            slot="bottom",
            gender="men",
            age_group="adult",
            colors=["navy"],
            quality_score=4.6,
            search_text=(
                "Kanu Surf Men's Beach Swim Trunks Board Shorts. Brand: Kanu Surf. Type: bottom."
            ),
        ),
    ]
    repo.upsert_products_batch(sample_products)

    embedder = FakeEmbedder(dimension=384)
    hybrid_index = HybridIndex(
        catalog_repo=repo,
        embedder=embedder,
        cache_dir=tmp_path,
    )
    hybrid_index.build_from_catalog(force_recompute=True)

    # Dependency overrides
    app.dependency_overrides[get_catalog_repo] = lambda: repo
    app.dependency_overrides[get_hybrid_index] = lambda: hybrid_index

    # Also pre-populate global module instances so lifespan doesn't trigger slow model load
    import app.main as main_mod

    main_mod.catalog_repo_instance = repo
    main_mod.embedder_instance = embedder
    main_mod.hybrid_index_instance = hybrid_index

    client = TestClient(app)
    return client


class TestApiEndpoints:
    """Integration tests for HTTP endpoints."""

    def test_health_check(self, test_app_client: TestClient) -> None:
        """GET /health reports liveness, readiness, and index size."""
        response = test_app_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["index_loaded"] is True
        assert data["catalog_reachable"] is True
        assert data["index_size"] == 3
        assert data["llm_status"] == "not_configured"

    def test_search_success(self, test_app_client: TestClient) -> None:
        """POST /search returns ranked results and search metadata."""
        payload = {
            "query": "beach sandals",
            "top_k": 2,
            "mode": "products",
        }
        response = test_app_client.post("/search", json=payload)
        assert response.status_code == 200
        data = response.json()

        assert "results" in data
        assert len(data["results"]) <= 2
        assert "meta" in data
        assert data["meta"]["used_fallback"] is True
        assert data["meta"]["latency_ms"] >= 0
        assert data["meta"]["excluded_by_filters"] == 0

        # Check result structure
        first_item = data["results"][0]
        assert "product_id" in first_item
        assert "title" in first_item
        assert "score" in first_item

    def test_search_validation_empty_query(self, test_app_client: TestClient) -> None:
        """Empty query returns 422 Unprocessable Entity."""
        response = test_app_client.post("/search", json={"query": ""})
        assert response.status_code == 422

    def test_search_validation_query_too_long(self, test_app_client: TestClient) -> None:
        """Query exceeding 500 characters returns 422."""
        long_query = "a" * 501
        response = test_app_client.post("/search", json={"query": long_query})
        assert response.status_code == 422

    def test_search_validation_top_k_exceeded(self, test_app_client: TestClient) -> None:
        """top_k exceeding 50 returns 422."""
        response = test_app_client.post("/search", json={"query": "sandals", "top_k": 51})
        assert response.status_code == 422

    def test_search_with_strict_filters(self, test_app_client: TestClient) -> None:
        """'men's shorts under $20' returns only matching products with applied filters."""
        response = test_app_client.post(
            "/search",
            json={"query": "men's shorts under $20", "top_k": 5},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) > 0
        for item in data["results"]:
            assert item["price"] <= 20.0
            assert item["gender"] in {"men", "unisex"}
            assert item["age_group"] == "adult"
            assert "similarity" in item

    def test_search_non_usd_currency_warning(self, test_app_client: TestClient) -> None:
        """Query with rupee price produces price_currency_not_supported warning."""
        response = test_app_client.post(
            "/search",
            json={"query": "men's shirt under 500 rupees", "top_k": 5},
        )
        assert response.status_code == 200
        data = response.json()
        assert "price_currency_not_supported" in data["meta"]["warnings"]
        assert data["meta"]["parsed_filters"].get("max_price") is None

    def test_lifespan_context_startup_shutdown(self, tmp_path: Path) -> None:
        """Lifespan context manager initializes and shuts down dependencies cleanly."""
        import app.main as main_mod
        from app.embedder import FakeEmbedder

        # Setup mock dependencies
        db_path = tmp_path / "lifespan_test.db"
        repo = CatalogRepository(db_path)
        p = Product(
            parent_asin="P_TEST",
            title="Lifespan Test Cotton Shirt",
            price=20.0,
            search_text="Lifespan Test Cotton Shirt",
        )
        repo.upsert_product(p)
        embedder = FakeEmbedder(dimension=384)

        main_mod.catalog_repo_instance = repo
        main_mod.embedder_instance = embedder
        main_mod.hybrid_index_instance = None

        with TestClient(main_mod.app) as client:
            resp = client.get("/health")
            assert resp.status_code == 200
            assert resp.json()["status"] == "healthy"

    def test_health_with_configured_fake_llm(self, test_app_client: TestClient) -> None:
        """Health check reflects LLM status when LLM client is configured."""
        import app.main as main_mod
        from app.llm.fake import FakeLLMClient
        from app.parser import QueryParser

        fake_llm = FakeLLMClient(default_response='{"normalized_query_en": "test"}')
        parser = QueryParser(fake_llm)
        main_mod.query_parser_instance = parser

        resp = test_app_client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["llm_status"] == "ok"

        # Search succeeds
        test_app_client.post("/search", json={"query": "test sandals"})
        resp2 = test_app_client.get("/health")
        assert resp2.json()["llm_status"] == "ok"

    def test_non_fashion_query_handling(self, test_app_client: TestClient) -> None:
        """Non-fashion query with is_fashion_query=False returns empty results with message."""
        import app.main as main_mod
        from app.llm.fake import FakeLLMClient
        from app.parser import QueryParser

        fake_llm = FakeLLMClient(
            default_response='{"is_fashion_query": false, "normalized_query_en": "guitar chords"}'
        )
        parser = QueryParser(fake_llm)
        main_mod.query_parser_instance = parser

        resp = test_app_client.post("/search", json={"query": "how to play acoustic guitar chords"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["results"] == []
        assert data["message"] == "not_a_fashion_query"
        assert len(data["suggested_queries"]) == 3
        assert data["meta"]["low_confidence"] is False

    def test_uninitialized_dependencies_raise_error(self) -> None:
        """Calling dependency getters without initialized instances raises domain errors."""
        import app.main as main_mod
        from app.exceptions import CatalogError, IndexingError

        orig_repo = main_mod.catalog_repo_instance
        orig_index = main_mod.hybrid_index_instance
        try:
            main_mod.catalog_repo_instance = None
            main_mod.hybrid_index_instance = None
            with pytest.raises(CatalogError):
                main_mod.get_catalog_repo()
            with pytest.raises(IndexingError):
                main_mod.get_hybrid_index()
        finally:
            main_mod.catalog_repo_instance = orig_repo
            main_mod.hybrid_index_instance = orig_index

    def test_lifespan_startup_with_fresh_instances(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Lifespan correctly initializes catalog, embedder, index, and parser if not pre-set."""
        import app.main as main_mod
        from app.embedder import FakeEmbedder

        db_file = tmp_path / "fresh_lifespan.db"
        repo = CatalogRepository(db_file)
        repo.upsert_product(
            Product(
                parent_asin="P1",
                title="Startup Test Item",
                search_text="Startup Test Item",
                price=10.0,
            )
        )

        monkeypatch.setattr(main_mod.settings, "db_path", db_file)
        monkeypatch.setattr(main_mod.settings, "data_dir", tmp_path)
        monkeypatch.setattr(
            main_mod,
            "SentenceTransformerEmbedder",
            lambda _: FakeEmbedder(dimension=384),
        )

        main_mod.app.dependency_overrides.clear()
        main_mod.catalog_repo_instance = None
        main_mod.embedder_instance = None
        main_mod.hybrid_index_instance = None
        main_mod.query_parser_instance = None

        with TestClient(main_mod.app) as client:
            resp = client.get("/health")
            assert resp.status_code == 200
            assert resp.json()["status"] == "healthy"
            assert resp.json()["index_size"] == 1


class TestAdminEndpoints:
    """Integration tests for Phase 4 admin endpoints (POST and DELETE /products)."""

    def test_admin_endpoints_disabled_when_key_unset(
        self, test_app_client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Endpoints return 503 admin_disabled when ADMIN_API_KEY is unset."""
        import app.main as main_mod

        monkeypatch.setattr(main_mod.settings, "admin_api_key", "")
        resp_post = test_app_client.post("/products", json={"products": []})
        assert resp_post.status_code == 503
        assert resp_post.json()["detail"] == "admin_disabled"

        resp_del = test_app_client.delete("/products/P_SANDAL")
        assert resp_del.status_code == 503
        assert resp_del.json()["detail"] == "admin_disabled"

    def test_admin_endpoints_unauthorized_with_wrong_key(
        self, test_app_client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Endpoints return 401 invalid_api_key on missing or incorrect X-API-Key."""
        import app.main as main_mod

        monkeypatch.setattr(main_mod.settings, "admin_api_key", "secret-admin-key")

        # Missing header
        resp1 = test_app_client.post("/products", json={"products": []})
        assert resp1.status_code == 401
        assert resp1.json()["detail"] == "invalid_api_key"

        # Wrong header
        resp2 = test_app_client.delete(
            "/products/P_SANDAL",
            headers={"X-API-Key": "wrong-key"},
        )
        assert resp2.status_code == 401
        assert resp2.json()["detail"] == "invalid_api_key"

    def test_batch_ingest_all_valid(
        self, test_app_client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """POST /products successfully ingests valid raw items with version 1."""
        import app.main as main_mod

        monkeypatch.setattr(main_mod.settings, "admin_api_key", "valid-admin-key")
        headers = {"X-API-Key": "valid-admin-key"}

        payload = {
            "products": [
                {
                    "parent_asin": "P_NEW_1",
                    "title": "Summer Beach Floral Sundress Long",
                    "price": 35.99,
                    "store": "BohoVibe",
                },
                {
                    "parent_asin": "P_NEW_2",
                    "title": "Men's Waterproof Trail Running Shoes",
                    "price": 89.99,
                    "store": "TrailPro",
                },
            ]
        }

        resp = test_app_client.post("/products", json=payload, headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["accepted_count"] == 2
        assert data["rejected_count"] == 0
        assert data["items"][0]["status"] == "created"
        assert data["items"][0]["version"] == 1
        assert data["items"][1]["status"] == "created"

        # Immediate searchability check without restart
        search_resp = test_app_client.post(
            "/search",
            json={"query": "Summer Beach Floral Sundress Long", "top_k": 5},
        )
        assert search_resp.status_code == 200
        found_ids = [item["product_id"] for item in search_resp.json()["results"]]
        assert "P_NEW_1" in found_ids

    def test_batch_ingest_mixed_valid_and_invalid(
        self, test_app_client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Valid records succeed while invalid ones are rejected with clear reasons."""
        import app.main as main_mod

        monkeypatch.setattr(main_mod.settings, "admin_api_key", "valid-admin-key")
        headers = {"X-API-Key": "valid-admin-key"}

        payload = {
            "products": [
                {
                    "parent_asin": "P_VALID",
                    "title": "Valid Men's Cotton Casual Shirt",
                    "price": 25.00,
                },
                {
                    "parent_asin": "P_NO_TITLE",
                    "title": "",
                    "price": 20.00,
                },
                {
                    "parent_asin": "P_SHORT_TITLE",
                    "title": "Short Tee",
                    "price": 20.00,
                },
                {
                    "parent_asin": "P_NO_PRICE",
                    "title": "Valid Long Enough Product Title",
                    "price": None,
                },
                {
                    "parent_asin": "P_INVALID_PRICE",
                    "title": "Valid Long Enough Product Title",
                    "price": -5.0,
                },
                {
                    "parent_asin": "P_PLUSH",
                    "title": "Cute Mini Plush Stuffed Animal Toy",
                    "price": 12.00,
                },
            ]
        }

        resp = test_app_client.post("/products", json=payload, headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["accepted_count"] == 1
        assert data["rejected_count"] == 5

        reasons = {
            item["parent_asin"]: item["reason"]
            for item in data["items"]
            if item["status"] == "rejected"
        }
        assert reasons["P_NO_TITLE"] == "no_title"
        assert reasons["P_SHORT_TITLE"] == "short_title"
        assert reasons["P_NO_PRICE"] == "no_price"
        assert reasons["P_INVALID_PRICE"] == "invalid_price"
        assert reasons["P_PLUSH"] == "non_fashion_keyword"

    def test_batch_ingest_duplicate_in_batch(
        self, test_app_client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Duplicate parent_asins within the same batch payload are rejected."""
        import app.main as main_mod

        monkeypatch.setattr(main_mod.settings, "admin_api_key", "valid-admin-key")
        headers = {"X-API-Key": "valid-admin-key"}

        payload = {
            "products": [
                {
                    "parent_asin": "P_DUP",
                    "title": "Valid Men's Cotton Casual Shirt 1",
                    "price": 25.00,
                },
                {
                    "parent_asin": "P_DUP",
                    "title": "Valid Men's Cotton Casual Shirt 2",
                    "price": 30.00,
                },
            ]
        }

        resp = test_app_client.post("/products", json=payload, headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["accepted_count"] == 1
        assert data["rejected_count"] == 1
        assert data["items"][1]["reason"] == "duplicate_in_batch"

    def test_batch_ingest_repost_increments_version(
        self, test_app_client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Re-posting an existing product increments version while index size stays constant."""
        import app.main as main_mod

        monkeypatch.setattr(main_mod.settings, "admin_api_key", "valid-admin-key")
        headers = {"X-API-Key": "valid-admin-key"}

        initial_size = test_app_client.get("/health").json()["index_size"]

        payload = {
            "products": [
                {
                    "parent_asin": "P_SANDAL",
                    "title": "Updated SunnyBreeze Beach Thong Sandals Blue",
                    "price": 32.50,
                }
            ]
        }

        resp = test_app_client.post("/products", json=payload, headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"][0]["status"] == "updated"
        assert data["items"][0]["version"] == 2

        new_size = test_app_client.get("/health").json()["index_size"]
        assert new_size == initial_size

    def test_delete_product_flow(
        self, test_app_client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Soft delete removes product immediately, is idempotent, and rejects non-existent IDs."""
        import app.main as main_mod

        monkeypatch.setattr(main_mod.settings, "admin_api_key", "valid-admin-key")
        headers = {"X-API-Key": "valid-admin-key"}

        # 1. 404 for missing ID
        resp_404 = test_app_client.delete("/products/NON_EXISTENT_ID", headers=headers)
        assert resp_404.status_code == 404

        # 2. First delete succeeds
        resp_del = test_app_client.delete("/products/P_SANDAL", headers=headers)
        assert resp_del.status_code == 200
        assert resp_del.json()["status"] == "deleted"

        # 3. Soft deleted product is never returned by search
        search_resp = test_app_client.post(
            "/search",
            json={"query": "SunnyBreeze Beach Thong Sandals", "top_k": 5},
        )
        res_ids = [item["product_id"] for item in search_resp.json()["results"]]
        assert "P_SANDAL" not in res_ids

        # 4. Repeat delete returns already_deleted
        resp_repeat = test_app_client.delete("/products/P_SANDAL", headers=headers)
        assert resp_repeat.status_code == 200
        assert resp_repeat.json()["status"] == "already_deleted"

        # 5. Re-posting deleted ID restores it with incremented version
        resp_restore = test_app_client.post(
            "/products",
            json={
                "products": [
                    {
                        "parent_asin": "P_SANDAL",
                        "title": "Restored SunnyBreeze Beach Thong Sandals",
                        "price": 29.81,
                    }
                ]
            },
            headers=headers,
        )
        assert resp_restore.status_code == 200
        assert resp_restore.json()["items"][0]["status"] == "updated"
        assert resp_restore.json()["items"][0]["version"] >= 2
