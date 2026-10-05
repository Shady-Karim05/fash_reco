"""Baseline latency instrumentation for Semantic Fashion Search & Outfit Recommendation."""

import time
import numpy as np
from app.config import settings
from app.catalog import CatalogRepository
from app.embedder import SentenceTransformerEmbedder
from app.index import HybridIndex
from app.parser import QueryParser
from app.cache import QueryCache, ParseCache
from app.service import SearchService
from app.schemas import SearchRequest
from app.outfit import compose_outfit

def run_benchmark():
    print("Initializing components for baseline measurement...")
    t0 = time.perf_counter()
    catalog_repo = CatalogRepository(settings.db_path)
    embedder = SentenceTransformerEmbedder()
    hybrid_index = HybridIndex(catalog_repo=catalog_repo, embedder=embedder, cache_dir=settings.data_dir)
    hybrid_index.build_from_catalog()
    parser = QueryParser()  # Fallback rule-based parser active
    query_cache = QueryCache(max_size=1000)
    parse_cache = ParseCache(max_size=1000)
    service = SearchService(
        catalog_repo=catalog_repo,
        hybrid_index=hybrid_index,
        parser=parser,
        query_cache=query_cache,
        parse_cache=parse_cache,
    )
    init_time = (time.perf_counter() - t0) * 1000.0
    print(f"Components initialized in {init_time:.2f} ms. Catalog size: {catalog_repo.count_active()}")

    test_queries = [
        "red cocktail dress",
        "black shoes for women",
        "winter jacket for men",
        "casual outfit for college",
    ]

    outfit_queries = [
        "cocktail party outfit for women under $100",
        "casual outfit for college under $80",
        "winter outfit for men under $150",
    ]

    print("\n================== PHASE 1: SEARCH LATENCY BREAKDOWN ==================")
    for q in test_queries:
        # 1. Parsing
        t_p0 = time.perf_counter()
        parsed, used_fallback = parser.parse(q)
        t_parse = (time.perf_counter() - t_p0) * 1000.0

        # 2. Embedding
        t_e0 = time.perf_counter()
        query_vec = embedder.encode([q])[0]
        t_embed = (time.perf_counter() - t_e0) * 1000.0

        # 3. FAISS search
        t_f0 = time.perf_counter()
        faiss_results = hybrid_index.vector_index.search(query_vec, top_k=50)
        t_faiss = (time.perf_counter() - t_f0) * 1000.0

        # 4. BM25 search
        t_b0 = time.perf_counter()
        bm25_results = hybrid_index.keyword_index.search(q, top_k=50)
        t_bm25 = (time.perf_counter() - t_b0) * 1000.0

        # 5. RRF Fusion
        t_r0 = time.perf_counter()
        from app.index import reciprocal_rank_fusion
        fused = reciprocal_rank_fusion([[p for p, _ in faiss_results], [p for p, _ in bm25_results]], k=60)
        t_rrf = (time.perf_counter() - t_r0) * 1000.0

        # 6. Database lookup
        cand_ids = [c[0] for c in fused[:50]]
        t_db0 = time.perf_counter()
        product_map = catalog_repo.get_by_ids(cand_ids)
        t_db = (time.perf_counter() - t_db0) * 1000.0

        # 7. Total End-to-End Search (Cold / Uncached)
        t_tot0 = time.perf_counter()
        resp_cold = service.search(SearchRequest(query=q, top_k=10, mode="product"))
        t_tot_cold = (time.perf_counter() - t_tot0) * 1000.0

        # 8. Repeated Search (Cached)
        t_tot1 = time.perf_counter()
        resp_cached = service.search(SearchRequest(query=q, top_k=10, mode="product"))
        t_tot_cached = (time.perf_counter() - t_tot1) * 1000.0

        print(f"\nQuery: '{q}'")
        print(f"  - Query Parsing:      {t_parse:6.2f} ms")
        print(f"  - Query Embedding:    {t_embed:6.2f} ms")
        print(f"  - FAISS Vector Search:{t_faiss:6.2f} ms")
        print(f"  - BM25 Keyword Search:{t_bm25:6.2f} ms")
        print(f"  - RRF Fusion:         {t_rrf:6.2f} ms")
        print(f"  - SQLite DB Batch:    {t_db:6.2f} ms ({len(product_map)} items)")
        print(f"  -> Total Search (Cold):  {t_tot_cold:6.2f} ms (results: {len(resp_cold.results)})")
        print(f"  -> Total Search (Cached):{t_tot_cached:6.2f} ms")

    print("\n================== PHASE 1: OUTFIT LATENCY BREAKDOWN ==================")
    for oq in outfit_queries:
        parsed_outfit, _ = parser.parse(oq)

        # Cold Outfit Run
        t_o0 = time.perf_counter()
        outfit_resp_cold = compose_outfit(
            raw_query=oq,
            parsed=parsed_outfit,
            catalog_repo=catalog_repo,
            hybrid_index=hybrid_index,
            used_fallback=True,
            start_time=t_o0,
        )
        t_outfit_cold = (time.perf_counter() - t_o0) * 1000.0

        items_count = len(outfit_resp_cold.outfit.items) if outfit_resp_cold.outfit else 0
        total_price = outfit_resp_cold.outfit.total_price if outfit_resp_cold.outfit else 0.0

        print(f"\nOutfit Query: '{oq}'")
        print(f"  -> Cold Outfit Time:  {t_outfit_cold:6.2f} ms (items: {items_count}, total: ${total_price:.2f})")

if __name__ == "__main__":
    run_benchmark()
