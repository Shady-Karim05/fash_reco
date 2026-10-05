"""Comprehensive BEFORE vs AFTER regression quality benchmark (Phase 12)."""

import json
import time
from typing import Any
from app.catalog import CatalogRepository
from app.config import settings
from app.embedder import SentenceTransformerEmbedder
from app.filters import collapse_near_duplicates, is_innerwear_allowed, passes_strict_filters
from app.attribute_correction import is_search_eligible_product
from app.index import HybridIndex
from app.parser import QueryParser
from app.reranker import QueryAwareReranker
from app.schemas import Product

BENCHMARK_SPEC = [
    {
        "query": "red cocktail dress",
        "intent": "formal / party evening wear",
        "expected_slot": "full_body",
        "expected_gender": None,
        "expected_color": "red",
        "expected_budget": None,
    },
    {
        "query": "black shoes for women",
        "intent": "women's black footwear",
        "expected_slot": "footwear",
        "expected_gender": "women",
        "expected_color": "black",
        "expected_budget": None,
    },
    {
        "query": "winter jacket for men",
        "intent": "men's winter outerwear/coat",
        "expected_slot": "top",
        "expected_gender": "men",
        "expected_color": None,
        "expected_budget": None,
    },
    {
        "query": "casual outfit for college",
        "intent": "casual everyday apparel",
        "expected_slot": None,
        "expected_gender": None,
        "expected_color": None,
        "expected_budget": None,
    },
    {
        "query": "red dress under $50",
        "intent": "budget-compliant red dress",
        "expected_slot": "full_body",
        "expected_gender": None,
        "expected_color": "red",
        "expected_budget": 50.0,
    },
    {
        "query": "black formal shoes under $100",
        "intent": "budget-compliant formal black shoes",
        "expected_slot": "footwear",
        "expected_gender": None,
        "expected_color": "black",
        "expected_budget": 100.0,
    },
    {
        "query": "elegant outfit for dinner date",
        "intent": "evening date / elegant apparel",
        "expected_slot": None,
        "expected_gender": None,
        "expected_color": None,
        "expected_budget": None,
    },
    {
        "query": "summer outfit for women",
        "intent": "women's summer apparel",
        "expected_slot": None,
        "expected_gender": "women",
        "expected_color": None,
        "expected_budget": None,
    },
]

def evaluate_quality():
    repo = CatalogRepository(settings.db_path)
    embedder = SentenceTransformerEmbedder(settings.embedding_model_name)
    index = HybridIndex(repo, embedder)
    index.build_from_catalog()
    parser = QueryParser()
    reranker = QueryAwareReranker(enabled=True)

    report: list[dict[str, Any]] = []

    for spec in BENCHMARK_SPEC:
        q = spec["query"]
        parsed, _ = parser.parse(q)

        # Baseline: FAISS + BM25 + RRF (no query-aware reranker, simple RRF order)
        t_base_0 = time.perf_counter()
        raw_cands, _ = index.search(q, parsed.normalized_query_en, retrieval_k=50)
        base_pids = [c[0] for c in raw_cands]
        base_pmap = repo.get_by_ids(base_pids)
        base_items = [base_pmap[pid] for pid, _, _ in raw_cands if pid in base_pmap]
        base_deduped, _ = collapse_near_duplicates([(p, f, s) for p, f, s in zip(base_items, [c[1] for c in raw_cands], [c[2] for c in raw_cands])])
        base_lat = (time.perf_counter() - t_base_0) * 1000.0

        # New: FAISS + BM25 + RRF + Metadata Filtering + Query-Aware Reranking
        t_new_0 = time.perf_counter()
        cands, _ = index.search(q, parsed.normalized_query_en, retrieval_k=50)
        cand_pids = [c[0] for c in cands]
        pmap = repo.get_by_ids(cand_pids)
        innerwear_req = is_innerwear_allowed(q, parsed)
        survivors = []
        max_fused = max((c[1] for c in cands), default=1.0)
        for pid, fused_score, sim in cands:
            if pid not in pmap:
                continue
            p = pmap[pid]
            if not passes_strict_filters(p, parsed, gender_include_unknown=False):
                continue
            if (p.slot or "").lower() == "innerwear" and not innerwear_req:
                continue
            if not is_search_eligible_product(p, raw_query=q, parsed=parsed):
                continue
            survivors.append((p, fused_score, sim))

        reranked_cands = reranker.rerank(q, parsed, survivors, top_k=10, max_fused=max_fused)
        new_deduped, _ = collapse_near_duplicates(reranked_cands)
        new_lat = (time.perf_counter() - t_new_0) * 1000.0

        # Scoring relevance for top-1, top-5, top-10
        def evaluate_relevance(items: list[tuple[Product, float, float]]) -> dict[str, Any]:
            top10 = items[:10]
            top5 = items[:5]
            top1 = items[:1]

            def is_relevant(p: Product) -> bool:
                # Slot match
                if spec["expected_slot"] and (p.slot or "").lower() != spec["expected_slot"]:
                    return False
                # Gender match
                if spec["expected_gender"] and (p.gender or "unknown").lower() not in {spec["expected_gender"], "unisex"}:
                    return False
                # Budget match
                if spec["expected_budget"] and (p.price or 0.0) > spec["expected_budget"]:
                    return False
                # Costume check: standard queries should not have costumes
                if any(w in (p.title or "").lower() for w in ["costume", "halloween", "cosplay"]):
                    return False
                return True

            rel1 = 1 if (top1 and is_relevant(top1[0][0])) else 0
            rel5 = sum(1 for p, _, _ in top5 if is_relevant(p)) / max(len(top5), 1)
            rel10 = sum(1 for p, _, _ in top10 if is_relevant(p)) / max(len(top10), 1)

            return {
                "top1_title": top1[0][0].title[:55] if top1 else "NONE",
                "top1_slot": top1[0][0].slot if top1 else "NONE",
                "top1_price": top1[0][0].price if top1 else 0.0,
                "top1_rel": rel1,
                "top5_rel": round(rel5, 2),
                "top10_rel": round(rel10, 2),
                "titles_sample": [p.title[:45] for p, _, _ in top5],
            }

        base_eval = evaluate_relevance(base_deduped)
        new_eval = evaluate_relevance(new_deduped)

        report.append({
            "query": q,
            "spec": spec,
            "baseline": {
                "latency_ms": round(base_lat, 2),
                **base_eval,
            },
            "new_pipeline": {
                "latency_ms": round(new_lat, 2),
                **new_eval,
            }
        })

    with open("scratch/quality_benchmark_report.json", "w") as f:
        json.dump(report, f, indent=2)

    print("\n================ QUALITY BENCHMARK REPORT ================")
    print(f"{'Query':32} | {'Base Rel@5':10} | {'New Rel@5':10} | {'Base Top1':32} | {'New Top1':32}")
    print("-" * 130)
    for r in report:
        print(f"{r['query']:32} | {r['baseline']['top5_rel']:10.2f} | {r['new_pipeline']['top5_rel']:10.2f} | {r['baseline']['top1_title'][:32]:32} | {r['new_pipeline']['top1_title'][:32]:32}")
    print("=" * 130)

if __name__ == "__main__":
    evaluate_quality()
