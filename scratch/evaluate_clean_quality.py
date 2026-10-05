"""Quality and latency evaluation on the cleaned catalog for Phase 14."""

import time
from fastapi.testclient import TestClient
from app.main import app

queries = [
    "red cocktail dress",
    "black shoes for women",
    "winter jacket for men",
    "casual outfit for college",
    "red dress below $50",
    "black shoes under $100",
]

outfit_queries = [
    "cocktail party outfit for women under $100",
    "winter outfit for men under $150",
]

with TestClient(app) as client:
    health = client.get("/health").json()
    print("Health response:", health)
    assert health["index_size"] == 22063
    assert health["catalog_size"] == 22063

    print("\n=== SEARCH QUALITY ON CLEAN CATALOG ===")
    for q in queries:
        t0 = time.perf_counter()
        resp = client.post("/search", json={"query": q, "top_k": 5})
        elapsed = (time.perf_counter() - t0) * 1000.0
        data = resp.json()
        results = data.get("results", [])
        print(f"\nQuery: '{q}' (Latency: {elapsed:.2f} ms)")
        print(f"  Count: {len(results)}")
        for i, item in enumerate(results[:3], 1):
            print(f"  Top {i}: [{item['slot']}] {item['title'][:60]} | ${item['price']}")
            # Check slot validity: no unknown slots should ever appear
            assert item["slot"] != "unknown", f"Unknown slot returned for {item['product_id']}"

    print("\n=== OUTFIT RECOMMENDATION ON CLEAN CATALOG ===")
    for q in outfit_queries:
        t0 = time.perf_counter()
        resp = client.post("/outfit", json={"query": q})
        elapsed = (time.perf_counter() - t0) * 1000.0
        data = resp.json()
        outfit = data.get("outfit", {})
        print(f"\nOutfit Query: '{q}' (Latency: {elapsed:.2f} ms)")
        print(f"  Total price: ${outfit.get('total_price')}")
        print(f"  Items:")
        for item in outfit.get("items", []):
            print(f"    - [{item['slot']}] {item['title'][:55]} | ${item['price']}")
            assert item["slot"] != "unknown"

    metrics = client.get("/metrics").json()
    print("\n=== METRICS SNAPSHOT ===")
    print("Index version:", metrics.get("index_version"))
    print("Catalog active size:", metrics.get("catalog_active_size"))
    print("Index size:", metrics.get("index_size"))
