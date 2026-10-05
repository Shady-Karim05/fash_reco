"""Benchmarking after optimizations for Phase 13.
Measures:
Search queries:
- red cocktail dress
- black shoes for women
- winter jacket for men
- casual outfit for college

Outfit queries:
- cocktail party outfit for women under $100
- casual outfit for college under $80
- winter outfit for men under $150

Records first request, repeated request, p50, p95, and cache hit rate.
"""

import time
import statistics
from fastapi.testclient import TestClient
from app.main import app

def run_benchmarks():
    print("Initializing FastAPI TestClient with lifespan...")
    init_start = time.perf_counter()
    with TestClient(app) as client:
        init_elapsed = (time.perf_counter() - init_start) * 1000.0
        print(f"Startup & warm-up finished in: {init_elapsed:.2f} ms\n")

        search_queries = [
            "red cocktail dress",
            "black shoes for women",
            "winter jacket for men",
            "casual outfit for college",
        ]

        print("=== SEARCH BENCHMARK ===")
        all_search_latencies = []
        for q in search_queries:
            # First request (cold/fresh)
            t0 = time.perf_counter()
            r1 = client.post("/search", json={"query": q, "top_k": 10})
            first_ms = (time.perf_counter() - t0) * 1000.0
            assert r1.status_code == 200, f"Failed query {q}: {r1.text}"

            # Second identical request (cached)
            t0 = time.perf_counter()
            r2 = client.post("/search", json={"query": q, "top_k": 10})
            second_ms = (time.perf_counter() - t0) * 1000.0
            assert r2.status_code == 200

            # 5 repeated runs to compute stats
            runs = [first_ms, second_ms]
            for _ in range(3):
                t0 = time.perf_counter()
                r = client.post("/search", json={"query": q, "top_k": 10})
                runs.append((time.perf_counter() - t0) * 1000.0)
            
            all_search_latencies.extend(runs)
            p50 = statistics.median(runs)
            p95 = statistics.quantiles(runs, n=20)[18] if len(runs) >= 20 else max(runs)
            print(f"Query: '{q}'")
            print(f"  First:    {first_ms:.2f} ms")
            print(f"  Second:   {second_ms:.2f} ms (speedup: {first_ms/max(second_ms, 0.001):.1f}x)")
            print(f"  Median:   {p50:.2f} ms")

        overall_search_p50 = statistics.median(all_search_latencies)
        overall_search_p95 = sorted(all_search_latencies)[int(len(all_search_latencies) * 0.95)]
        print(f"\nOverall Search -> p50: {overall_search_p50:.2f} ms | p95: {overall_search_p95:.2f} ms\n")

        outfit_queries = [
            "cocktail party outfit for women under $100",
            "casual outfit for college under $80",
            "winter outfit for men under $150",
        ]

        print("=== OUTFIT BENCHMARK ===")
        all_outfit_latencies = []
        for q in outfit_queries:
            # First request (cold)
            t0 = time.perf_counter()
            r1 = client.post("/outfit", json={"query": q})
            first_ms = (time.perf_counter() - t0) * 1000.0
            assert r1.status_code == 200, f"Failed outfit query {q}: {r1.text}"

            # Second identical request (cached)
            t0 = time.perf_counter()
            r2 = client.post("/outfit", json={"query": q})
            second_ms = (time.perf_counter() - t0) * 1000.0
            assert r2.status_code == 200

            runs = [first_ms, second_ms]
            for _ in range(3):
                t0 = time.perf_counter()
                r = client.post("/outfit", json={"query": q})
                runs.append((time.perf_counter() - t0) * 1000.0)

            all_outfit_latencies.extend(runs)
            p50 = statistics.median(runs)
            print(f"Query: '{q}'")
            print(f"  First:    {first_ms:.2f} ms")
            print(f"  Second:   {second_ms:.2f} ms (speedup: {first_ms/max(second_ms, 0.001):.1f}x)")
            print(f"  Median:   {p50:.2f} ms")

        overall_outfit_p50 = statistics.median(all_outfit_latencies)
        overall_outfit_p95 = sorted(all_outfit_latencies)[int(len(all_outfit_latencies) * 0.95)]
        print(f"\nOverall Outfit -> p50: {overall_outfit_p50:.2f} ms | p95: {overall_outfit_p95:.2f} ms\n")

        # Verify /metrics
        metrics_resp = client.get("/metrics")
        print("=== METRICS API SNAPSHOT ===")
        print(metrics_resp.json())

if __name__ == "__main__":
    run_benchmarks()
