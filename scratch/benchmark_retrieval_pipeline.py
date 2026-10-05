"""Benchmark retrieval candidate sizes (20, 50, 100) and reranker strategies."""

import time
import json
from app.catalog import CatalogRepository
from app.config import settings
from app.embedder import SentenceTransformerEmbedder
from app.index import HybridIndex
from app.parser import QueryParser
from app.filters import passes_strict_filters, is_innerwear_allowed
from app.attribute_correction import is_search_eligible_product

BENCHMARK_QUERIES = [
    {"query": "red cocktail dress", "slot": "full_body", "gender": None, "color": "red", "max_price": None},
    {"query": "black shoes for women", "slot": "footwear", "gender": "women", "color": "black", "max_price": None},
    {"query": "winter jacket for men", "slot": "top", "gender": "men", "color": None, "max_price": None},
    {"query": "casual outfit for college", "slot": None, "gender": None, "color": None, "max_price": None},
    {"query": "red dress under $50", "slot": "full_body", "gender": None, "color": "red", "max_price": 50.0},
    {"query": "black formal shoes under $100", "slot": "footwear", "gender": None, "color": "black", "max_price": 100.0},
    {"query": "elegant outfit for dinner date", "slot": None, "gender": None, "color": None, "max_price": None},
    {"query": "summer outfit for women", "slot": None, "gender": "women", "color": None, "max_price": None},
]

def run_candidate_pool_benchmark():
    repo = CatalogRepository(settings.db_path)
    embedder = SentenceTransformerEmbedder(settings.embedding_model_name)
    index = HybridIndex(repo, embedder)
    index.build_from_catalog()
    parser = QueryParser()

    print("=== BENCHMARKING CANDIDATE SIZES (20, 50, 100) ===")
    results_by_k = {}

    for k in [20, 50, 100]:
        t_start = time.perf_counter()
        query_stats = []
        for q_obj in BENCHMARK_QUERIES:
            raw_q = q_obj["query"]
            parsed, _ = parser.parse(raw_q)
            cands, skipped_bm25 = index.search(raw_q, parsed.normalized_query_en, retrieval_k=k)
            pids = [c[0] for c in cands]
            pmap = repo.get_by_ids(pids)

            # Metadata filtering
            survivors = []
            innerwear_req = is_innerwear_allowed(raw_q, parsed)
            for pid, fused_score, sim in cands:
                if pid not in pmap:
                    continue
                p = pmap[pid]
                if not passes_strict_filters(p, parsed, gender_include_unknown=False):
                    continue
                if (prod_slot := (p.slot or "").lower()) == "innerwear" and not innerwear_req:
                    continue
                if not is_search_eligible_product(p, raw_query=raw_q, parsed=parsed):
                    continue
                survivors.append((p, fused_score, sim))

            # Check target criteria
            exp_slot = q_obj["slot"]
            slot_matches = sum(1 for p, _, _ in survivors[:10] if not exp_slot or (p.slot or "").lower() == exp_slot)
            top10_count = min(len(survivors), 10)
            slot_precision = (slot_matches / top10_count) if top10_count > 0 else 0.0

            query_stats.append({
                "query": raw_q,
                "retrieved": len(cands),
                "survivors": len(survivors),
                "top10_slot_precision": round(slot_precision, 2),
                "top1_title": survivors[0][0].title[:50] if survivors else "NONE",
                "top1_slot": survivors[0][0].slot if survivors else "NONE",
                "top1_sim": round(survivors[0][2], 3) if survivors else 0.0,
            })

        elapsed_total = (time.perf_counter() - t_start) * 1000.0
        avg_latency = elapsed_total / len(BENCHMARK_QUERIES)
        avg_survivors = sum(s["survivors"] for s in query_stats) / len(query_stats)
        avg_precision = sum(s["top10_slot_precision"] for s in query_stats) / len(query_stats)

        results_by_k[k] = {
            "avg_latency_ms": round(avg_latency, 2),
            "avg_survivors": round(avg_survivors, 1),
            "avg_precision": round(avg_precision, 3),
            "details": query_stats,
        }
        print(f"\n[k={k}] Avg Latency: {avg_latency:.2f}ms | Avg Survivors: {avg_survivors:.1f} | Avg Slot Precision: {avg_precision:.3f}")
        for s in query_stats:
            print(f"  {s['query']:30} -> retrieved: {s['retrieved']:2d}, survivors: {s['survivors']:2d}, top1: {s['top1_title']} ({s['top1_slot']})")

    with open("scratch/candidate_benchmark_results.json", "w") as f:
        json.dump(results_by_k, f, indent=2)
    print("\nBenchmark saved to scratch/candidate_benchmark_results.json")

if __name__ == "__main__":
    run_candidate_pool_benchmark()
