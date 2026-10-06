"""Search service orchestrating parsing, retrieval widening, filtering, and scoring."""

import time
from typing import Any, Literal

from app.attribute_correction import is_search_eligible_product
from app.cache import ParseCache, QueryCache
from app.catalog import CatalogRepository
from app.config import settings
from app.filters import (
    collapse_near_duplicates,
    compute_soft_boost,
    generate_item_explanation,
    is_innerwear_allowed,
    passes_strict_filters,
)
from app.index import HybridIndex
from app.outfit import compose_outfit
from app.parser import QueryParser
from app.reranker import QueryAwareReranker
from app.schemas import (
    OutfitResponse,
    Product,
    SearchMeta,
    SearchRequest,
    SearchResponse,
    SearchResultItem,
)


class SearchService:
    """Service layer orchestrating the full fashion search and outfit pipeline (Phases 2-6).

    Pipeline Order:
    parse -> retrieve candidates (FAISS + BM25 + RRF) -> metadata & strict filters ->
    query-aware multi-feature reranker -> near-duplicate collapse -> final response.
    """

    def __init__(
        self,
        catalog_repo: CatalogRepository,
        hybrid_index: HybridIndex,
        parser: QueryParser | None = None,
        query_cache: QueryCache | None = None,
        parse_cache: ParseCache | None = None,
        reranker: QueryAwareReranker | None = None,
    ) -> None:
        """Initialize search service with dependencies, reranker, and caching."""
        self.catalog_repo = catalog_repo
        self.hybrid_index = hybrid_index
        self.parse_cache = parse_cache or ParseCache(
            max_size=settings.parse_cache_size,
            ttl_seconds=settings.parse_cache_ttl_seconds,
        )
        self.parser = parser or QueryParser(cache=self.parse_cache)
        if self.parser.cache is None:
            self.parser.cache = self.parse_cache

        self.query_cache = query_cache or QueryCache(max_size=settings.query_cache_size)
        self.reranker = reranker or QueryAwareReranker(
            enabled=settings.reranker_enabled,
            use_cross_encoder=settings.reranker_use_cross_encoder,
            cross_encoder_model=settings.reranker_cross_encoder_model,
            cross_encoder_top_n=settings.reranker_cross_encoder_top_n,
            cross_encoder_blend=settings.reranker_cross_encoder_blend,
            cache_size=settings.reranker_cache_size,
        )
        self._llm_status: Literal["not_configured", "ok", "degraded"] = (
            "not_configured" if not self.parser.llm_client else "ok"
        )

    @property
    def llm_status(self) -> str:
        """Return current status of LLM parser component (D3)."""
        if not self.parser.llm_client:
            return "not_configured"
        return self.parser.breaker.status

    def search(self, request: SearchRequest) -> SearchResponse | OutfitResponse:
        """Execute fashion search in either 'product' or 'outfit' mode.

        Args:
            request: Validated SearchRequest.

        Returns:
            SearchResponse for product mode or OutfitResponse for outfit mode.
        """
        start_time = time.perf_counter()

        # 1. Parse Query (with TTL ParseCache and Two-Layer Parser)
        parsed, used_fallback = self.parser.parse(request.query)

        # Degraded-mode check for non-English query under fallback (D4)
        is_non_eng_fallback = False
        fallback_warnings: list[str] = list(parsed.warnings)
        if used_fallback and self.hybrid_index.is_non_english_noise(request.query):
            is_non_eng_fallback = True
            if "filters_not_applied_without_llm" not in fallback_warnings:
                fallback_warnings.append("filters_not_applied_without_llm")

            if settings.non_english_fallback_policy == "refuse":
                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                meta = SearchMeta(
                    parsed_filters={},
                    used_fallback=True,
                    latency_ms=round(elapsed_ms, 2),
                    index_version=self.hybrid_index.index_version,
                    excluded_by_filters=0,
                    duplicates_collapsed=0,
                    low_confidence=True,
                    warnings=fallback_warnings,
                )
                if request.mode == "outfit":
                    return OutfitResponse(
                        outfit=None,
                        message="llm_unavailable_for_non_english_query",
                        meta=meta,
                    )
                return SearchResponse(
                    results=[],
                    meta=meta,
                    message="llm_unavailable_for_non_english_query",
                )

        # 2. Check Outfit Mode (B4)
        if request.mode == "outfit":
            cache_key = self.query_cache.make_key(
                normalized_query_en=parsed.normalized_query_en,
                filters={
                    k: v
                    for k, v in {
                        "gender": parsed.gender,
                        "age_group": parsed.age_group,
                        "max_price": parsed.max_price,
                        "min_price": parsed.min_price,
                    }.items()
                    if v is not None
                },
                brand=parsed.brand,
                top_k=request.top_k,
                mode="outfit",
                index_version=self.hybrid_index.index_version,
            )
            cached_outfit = self.query_cache.get(cache_key)
            if isinstance(cached_outfit, OutfitResponse):
                return cached_outfit

            outfit_resp = compose_outfit(
                raw_query=request.query,
                parsed=parsed,
                catalog_repo=self.catalog_repo,
                hybrid_index=self.hybrid_index,
                used_fallback=used_fallback,
                start_time=start_time,
            )
            if is_non_eng_fallback:
                outfit_resp.meta.low_confidence = True
                if "filters_not_applied_without_llm" not in outfit_resp.meta.warnings:
                    outfit_resp.meta.warnings.append("filters_not_applied_without_llm")
            self.query_cache.put(cache_key, outfit_resp)
            return outfit_resp

        # 3. Product Mode Pipeline
        warnings = fallback_warnings

        # Non-fashion query guardrail
        if not parsed.is_fashion_query:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            meta = SearchMeta(
                parsed_filters={},
                used_fallback=used_fallback,
                latency_ms=round(elapsed_ms, 2),
                index_version=self.hybrid_index.index_version,
                excluded_by_filters=0,
                low_confidence=False,
                warnings=warnings,
            )
            return SearchResponse(
                results=[],
                meta=meta,
                message="not_a_fashion_query",
                suggested_queries=settings.suggested_queries,
            )

        applied_filters: dict[str, Any] = {}
        if parsed.gender:
            applied_filters["gender"] = parsed.gender
        if parsed.age_group:
            applied_filters["age_group"] = parsed.age_group
        if parsed.max_price is not None:
            applied_filters["max_price"] = parsed.max_price
        if parsed.min_price is not None:
            applied_filters["min_price"] = parsed.min_price
        if parsed.slots:
            applied_filters["slots"] = parsed.slots

        # Query Cache Check
        cache_key = self.query_cache.make_key(
            normalized_query_en=parsed.normalized_query_en,
            filters=applied_filters,
            brand=parsed.brand,
            top_k=request.top_k,
            mode="product",
            index_version=self.hybrid_index.index_version,
        )
        cached_resp = self.query_cache.get(cache_key)
        if isinstance(cached_resp, SearchResponse):
            return cached_resp

        # 4. Progressive Candidate Widening & Filtering
        pool_sizes = settings.progressive_pool_sizes
        survivors: list[tuple[Product, float, float]] = []
        total_excluded = 0
        best_overall_similarity = 0.0
        total_collapsed = 0

        quality_bounds = self.catalog_repo.get_quality_score_bounds()
        min_q, max_q = quality_bounds
        q_range = max(max_q - min_q, 1e-6)

        innerwear_req = is_innerwear_allowed(request.query, parsed)

        for pool_k in pool_sizes:
            raw_candidates, skipped_bm25 = self.hybrid_index.search(
                raw_query=request.query,
                normalized_query_en=parsed.normalized_query_en,
                retrieval_k=pool_k,
                rrf_k=settings.rrf_k,
            )

            if skipped_bm25 and "keyword_search_skipped" not in warnings:
                warnings.append("keyword_search_skipped")

            if not raw_candidates:
                break

            max_sim_in_pool = max(c[2] for c in raw_candidates)
            if max_sim_in_pool > best_overall_similarity:
                best_overall_similarity = max_sim_in_pool

            # Fetch product models from DB
            cand_ids = [c[0] for c in raw_candidates]
            product_map = self.catalog_repo.get_by_ids(cand_ids)

            pool_survivors: list[tuple[Product, float, float]] = []
            pool_excluded = 0

            max_fused = max((c[1] for c in raw_candidates), default=1.0)
            if max_fused <= 0:
                max_fused = 1.0

            for pid, fused_score, sim in raw_candidates:
                if pid not in product_map:
                    continue
                prod = product_map[pid]

                # Strict Filters
                if not passes_strict_filters(
                    prod, parsed, gender_include_unknown=settings.gender_include_unknown
                ):
                    pool_excluded += 1
                    continue

                # Innerwear Policy (B2)
                if (
                    settings.innerwear_policy == "exclude_unless_requested"
                    and (prod.slot or "").lower() == "innerwear"
                    and not innerwear_req
                ):
                    pool_excluded += 1
                    continue

                # Search Eligibility Guard (Fix 3 / Problem A)
                if not is_search_eligible_product(prod, raw_query=request.query, parsed=parsed):
                    pool_excluded += 1
                    continue

                # Score Normalization & Soft Boosts (B1)
                norm_fused = fused_score / max_fused
                q_norm = (prod.quality_score - min_q) / q_range
                boost = compute_soft_boost(
                    prod,
                    parsed,
                    quality_norm=q_norm,
                    quality_weight=settings.quality_weight,
                    boost_weight_season=settings.boost_weight_season,
                    boost_weight_occasion=settings.boost_weight_occasion,
                    boost_weight_color=settings.boost_weight_color,
                    boost_weight_brand=settings.boost_weight_brand,
                )
                final_score = norm_fused + boost
                pool_survivors.append((prod, final_score, sim))

            # Rerank survivors with Query-Aware Multi-Signal Reranker (Phases 4, 5, 6)
            if self.reranker.enabled and pool_survivors:
                reranked_survivors = self.reranker.rerank(
                    raw_query=request.query,
                    parsed=parsed,
                    candidates=pool_survivors,
                    top_k=request.top_k,
                    max_fused=max_fused,
                )
            else:
                pool_survivors.sort(key=lambda x: x[1], reverse=True)
                reranked_survivors = pool_survivors

            # Near-duplicate collapse (B3)
            deduped_survivors, collapsed_cnt = collapse_near_duplicates(reranked_survivors)

            survivors = deduped_survivors
            total_excluded = pool_excluded
            total_collapsed = collapsed_cnt

            if len(survivors) >= request.top_k:
                break

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        # Check low confidence (D4: degraded non-English query sets low_confidence=True)
        low_conf = is_non_eng_fallback
        if survivors and not low_conf:
            best_returned_sim = max(c[2] for c in survivors[: request.top_k])
            low_conf = best_returned_sim < settings.low_confidence_similarity

        if low_conf and used_fallback and "low_confidence_results" not in warnings:
            warnings.append("low_confidence_results")

        meta = SearchMeta(
            parsed_filters=applied_filters,
            used_fallback=used_fallback,
            latency_ms=round(elapsed_ms, 2),
            index_version=self.hybrid_index.index_version,
            excluded_by_filters=total_excluded,
            duplicates_collapsed=total_collapsed,
            low_confidence=low_conf,
            warnings=warnings,
            candidate_pool_size=len(raw_candidates)
            if "raw_candidates" in locals() and raw_candidates
            else 0,
            reranker_latency_ms=round(self.reranker.last_rerank_latency_ms, 2),
        )

        # Build final response item list
        items: list[SearchResultItem] = []
        for product, adjusted_score, similarity in survivors[: request.top_k]:
            reason = generate_item_explanation(product, parsed, request.query, similarity)
            items.append(
                SearchResultItem(
                    product_id=product.parent_asin,
                    title=product.title,
                    price=product.price,
                    brand=product.store,
                    image_url=product.image_url,
                    slot=product.slot,
                    gender=product.gender,
                    age_group=product.age_group,
                    score=round(adjusted_score, 4),
                    similarity=round(similarity, 4),
                    reason=reason,
                )
            )

        if not items:
            response = SearchResponse(
                results=[],
                meta=meta,
                message="no_good_match" if total_excluded == 0 else None,
                suggested_queries=settings.suggested_queries,
            )
        else:
            response = SearchResponse(
                results=items,
                meta=meta,
            )

        self.query_cache.put(cache_key, response)
        return response
