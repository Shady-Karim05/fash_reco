"""Compare Feature-Based Reranker vs CrossEncoder Reranker on latency, memory, and ranking."""

import time
import json
from sentence_transformers import CrossEncoder
from app.catalog import CatalogRepository
from app.config import settings
from app.embedder import SentenceTransformerEmbedder
from app.index import HybridIndex
from app.parser import QueryParser
import sys
sys.path.append("scratch")
from test_prototype_reranker import (
    compute_feature_rerank_score,
    detect_query_archetype,
    passes_strict_filters,
    is_search_eligible_product,
)

def run_cross_encoder_comparison():
    repo = CatalogRepository(settings.db_path)
    embedder = SentenceTransformerEmbedder(settings.embedding_model_name)
    index = HybridIndex(repo, embedder)
    index.build_from_catalog()
    parser = QueryParser()

    print("Loading CrossEncoder...")
    t_ce_load = time.perf_counter()
    ce_model = CrossEncoder("cross-encoder/ms-marco-TinyBERT-L-2-v2")
    print(f"CrossEncoder loaded in {time.perf_counter() - t_ce_load:.2f}s")

    queries = [
        "red cocktail dress",
        "black shoes for women",
        "winter jacket for men",
        "casual outfit for college",
        "red dress below $50",
        "black formal shoes under $100",
        "something stylish for a dinner date",
        "summer outfit for women"
    ]

    print("\n=== BENCHMARKING FEATURE RERANKER VS CROSS-ENCODER ===")
    feature_latencies = []
    cross_latencies = []
    comparisons = []

    for q in queries:
        parsed, _ = parser.parse(q)
        arch = detect_query_archetype(q, parsed)
        cands, _ = index.search(q, parsed.normalized_query_en, retrieval_k=50)
        pids = [c[0] for c in cands]
        pmap = repo.get_by_ids(pids)

        max_fused = max((c[1] for c in cands), default=1.0)
        survivors = []
        for pid, fused_score, sim in cands:
            if pid not in pmap:
                continue
            p = pmap[pid]
            if not passes_strict_filters(p, parsed, gender_include_unknown=False):
                continue
            if not is_search_eligible_product(p, raw_query=q, parsed=parsed):
                continue
            survivors.append((p, fused_score, sim))

        # 1. Feature-based reranker
        t0 = time.perf_counter()
        feat_scored = []
        for p, fused_score, sim in survivors:
            score, feats = compute_feature_rerank_score(
                product=p,
                raw_query=q,
                parsed=parsed,
                fused_score=fused_score,
                max_fused=max_fused,
                sim=sim,
                archetype=arch,
            )
            feat_scored.append((p, score, sim, feats))
        feat_scored.sort(key=lambda x: x[1], reverse=True)
        feat_lat = (time.perf_counter() - t0) * 1000.0
        feature_latencies.append(feat_lat)

        # 2. CrossEncoder reranker on top 20 candidates
        t1 = time.perf_counter()
        top_20 = survivors[:20]
        pairs = [(q, f"{p.title} {p.store or ''}") for p, _, _ in top_20]
        ce_scores = ce_model.predict(pairs)
        ce_scored = []
        for (p, _, sim), ce_s in zip(top_20, ce_scores):
            ce_scored.append((p, float(ce_s), sim))
        ce_scored.sort(key=lambda x: x[1], reverse=True)
        ce_lat = (time.perf_counter() - t1) * 1000.0
        cross_latencies.append(ce_lat)

        comp = {
            "query": q,
            "feature_latency_ms": round(feat_lat, 2),
            "cross_encoder_latency_ms": round(ce_lat, 2),
            "feature_top1": feat_scored[0][0].title[:60] if feat_scored else "NONE",
            "cross_top1": ce_scored[0][0].title[:60] if ce_scored else "NONE",
            "feature_top1_slot": feat_scored[0][0].slot if feat_scored else "NONE",
            "cross_top1_slot": ce_scored[0][0].slot if ce_scored else "NONE",
        }
        comparisons.append(comp)
        print(f"Query: '{q}'")
        print(f"  Feature-Reranker (latency: {feat_lat:.2f}ms): {comp['feature_top1']}")
        print(f"  Cross-Encoder    (latency: {ce_lat:.2f}ms): {comp['cross_top1']}\n")

    avg_feat_lat = sum(feature_latencies) / len(feature_latencies)
    avg_ce_lat = sum(cross_latencies) / len(cross_latencies)

    print(f"Average Feature Reranker Latency: {avg_feat_lat:.3f} ms")
    print(f"Average Cross-Encoder Latency:    {avg_ce_lat:.3f} ms ({(avg_ce_lat/avg_feat_lat):.1f}x slower)")

    with open("scratch/reranker_comparison_results.json", "w") as f:
        json.dump({
            "avg_feature_latency_ms": round(avg_feat_lat, 3),
            "avg_cross_encoder_latency_ms": round(avg_ce_lat, 3),
            "comparisons": comparisons
        }, f, indent=2)

if __name__ == "__main__":
    run_cross_encoder_comparison()
