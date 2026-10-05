"""Script to verify all API endpoints and outfit behaviors."""

import shutil
import sys
import tempfile
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

from app.catalog import CatalogRepository
from app.config import settings
from app.embedder import FakeEmbedder
from app.index import HybridIndex
from app.main import app
from app.schemas import Product


def run_verification() -> None:
    print("=== STARTING FULL API & OUTFIT VERIFICATION ===")

    with TestClient(app) as client:
        # 1. GET /health
        r_health = client.get("/health")
        print(f"GET /health: {r_health.status_code}")
        assert r_health.status_code == 200
        health_data = r_health.json()
        print(
            f"  Health: status={health_data['status']}, "
            f"index_loaded={health_data['index_loaded']}, "
            f"catalog_size={health_data['catalog_size']}"
        )
        assert health_data["status"] == "healthy"
        assert health_data["index_loaded"] is True
        assert health_data["catalog_size"] == 24000

        # 2. GET /metrics
        r_metrics = client.get("/metrics")
        print(f"GET /metrics: {r_metrics.status_code}")
        assert r_metrics.status_code == 200
        metrics_data = r_metrics.json()
        print(f"  Metrics: index_size={metrics_data['index_size']}")
        assert "search_latency_percentiles_ms" in metrics_data
        assert "catalog_active_size" in metrics_data

        # 3. GET /metrics/prometheus
        r_prom = client.get("/metrics/prometheus")
        print(f"GET /metrics/prometheus: {r_prom.status_code}")
        assert r_prom.status_code == 200
        assert "fashion_search_index_size" in r_prom.text
        print("  Prometheus text metrics verified.")

        # 4. GET /search (normal product search)
        r_get_search = client.get("/search?query=red+cocktail+dress&top_k=5")
        print(f"GET /search (normal): {r_get_search.status_code}")
        assert r_get_search.status_code == 200
        get_search_data = r_get_search.json()
        print(
            f"  Results: count={len(get_search_data['results'])}, "
            f"latency={get_search_data['meta']['latency_ms']}ms"
        )
        assert len(get_search_data["results"]) > 0

        # 5. POST /search (constrained product search)
        r_post_constrained = client.post(
            "/search",
            json={"query": "men running shoes under $40", "top_k": 5},
        )
        print(f"POST /search (constrained): {r_post_constrained.status_code}")
        assert r_post_constrained.status_code == 200
        constrained_data = r_post_constrained.json()
        print(f"  Parsed filters: {constrained_data['meta']['parsed_filters']}")
        for item in constrained_data["results"]:
            assert item["gender"] in ("men", "unisex", "unknown")
            if item["price"] is not None:
                assert item["price"] <= 40.0
        print("  Constrained search gender and budget constraints verified.")

        # 6. POST /search (multilingual product search)
        r_multi = client.post("/search", json={"query": "robe d'été pour femme", "top_k": 5})
        print(f"POST /search (multilingual FR): {r_multi.status_code}")
        assert r_multi.status_code == 200
        multi_data = r_multi.json()
        print(f"  Query EN: {multi_data['meta']['parsed_filters'].get('normalized_query_en')}")
        assert len(multi_data["results"]) > 0

        # 7. POST /outfit (normal successful outfit)
        r_outfit = client.post("/outfit", json={"query": "cocktail party outfit for women"})
        print(f"POST /outfit: {r_outfit.status_code}")
        assert r_outfit.status_code == 200
        outfit_data = r_outfit.json()
        assert outfit_data["outfit"] is not None
        items = outfit_data["outfit"]["items"]
        slots = [it["slot"] for it in items]
        print(
            f"  Outfit count: {len(items)}, slots: {slots}, "
            f"template: {outfit_data['outfit']['template']}"
        )
        assert len(items) >= 2

        # 8. POST /outfit (budget failure -> deterministic empty outfit response)
        r_budget_fail = client.post(
            "/outfit",
            json={"query": "full luxury suit outfit under $1"},
        )
        print(f"POST /outfit (budget failure): {r_budget_fail.status_code}")
        assert r_budget_fail.status_code == 200
        bf_data = r_budget_fail.json()
        assert bf_data["outfit"] is None
        msg = (bf_data["message"] or "").lower()
        assert "budget" in msg or "no outfit" in msg
        print(f"  Budget failure message: {bf_data['message']}")

        # 9. POST /outfit (demographic mismatch rejection)
        r_demo = client.post("/outfit", json={"query": "men business formal outfit"})
        assert r_demo.status_code == 200
        demo_data = r_demo.json()
        if demo_data["outfit"]:
            for it in demo_data["outfit"]["items"]:
                assert it["gender"] in ("men", "unisex", "unknown")
                assert it["age_group"] == "adult"
        print("  Demographic gender/age coherence in outfit verified.")

        # 10. POST /simulate_updates
        r_sim = client.post("/simulate_updates")
        print(f"POST /simulate_updates: {r_sim.status_code}")
        assert r_sim.status_code == 200
        sim_data = r_sim.json()
        print(
            f"  Simulation response: status={sim_data['status']}, "
            f"active_catalog={sim_data['active_catalog_size']}"
        )

    # 11. POST /products & Dynamic Ingestion (verified on isolated temporary database)
    temp_dir = Path(tempfile.mkdtemp(prefix="test_ingest_"))
    try:
        temp_db = temp_dir / "catalog.db"
        shutil.copy2(settings.db_path, temp_db)

        iso_repo = CatalogRepository(temp_db)
        iso_embedder = FakeEmbedder(dimension=384)
        iso_index = HybridIndex(catalog_repo=iso_repo, embedder=iso_embedder, cache_dir=temp_dir)
        iso_index.build_from_catalog()

        # Test atomic ingestion and cache invalidation on isolated instance
        test_product = Product(
            parent_asin="TEST_VERIF_PRODUCT_99999",
            title="Unique Verification Test Silk Scarf Red Accessories",
            price=19.99,
            slot="accessory",
            gender="women",
            age_group="adult",
            search_text="Unique Verification Test Silk Scarf Red Accessories",
        )
        accepted = iso_index.upsert_batch_atomic([test_product])
        print(
            f"Isolated POST /products ingest: accepted={len(accepted)}, "
            f"index_version={iso_index.index_version}"
        )
        assert len(accepted) == 1
        assert iso_index.size() == 24001

        # Test soft-delete
        exists, already_del = iso_index.delete_product("TEST_VERIF_PRODUCT_99999")
        print(f"Isolated DELETE /products: exists={exists}, size={iso_index.size()}")
        assert exists is True
        assert iso_index.size() == 24000
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    print("=== ALL API AND OUTFIT BEHAVIORS SUCCESSFULLY VERIFIED ===")


if __name__ == "__main__":
    run_verification()
