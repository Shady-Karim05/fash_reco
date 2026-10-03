"""Search service orchestrating LLM query parsing, progressive widening, filtering, and scoring."""

import time
from typing import Any, Literal

from app.catalog import CatalogRepository
from app.config import settings
from app.filters import apply_candidate_filters
from app.index import HybridIndex
from app.parser import QueryParser
from app.schemas import SearchMeta, SearchRequest, SearchResponse, SearchResultItem


class SearchService:
    """Service layer handling query parsing, progressive hybrid retrieval, and scoring."""

    def __init__(
        self,
        catalog_repo: CatalogRepository,
        hybrid_index: HybridIndex,
        parser: QueryParser | None = None,
    ) -> None:
        """Initialize search service with catalog, index, and parser dependencies.

        Args:
            catalog_repo: Repository for product lookups.
            hybrid_index: Hybrid search index.
            parser: QueryParser for LLM and rule-based parsing.
        """
        self.catalog_repo = catalog_repo
        self.hybrid_index = hybrid_index
        self.parser = parser or QueryParser()
        self._llm_status: Literal["not_configured", "ok", "degraded"] = (
            "not_configured" if not self.parser.llm_client else "ok"
        )

    @property
    def llm_status(self) -> str:
        """Return current status of LLM parser component."""
        if not self.parser.llm_client:
            return "not_configured"
        return self._llm_status

    def search(self, request: SearchRequest) -> SearchResponse:
        """Execute structured search with progressive widening, filtering, and scoring.

        Args:
            request: Validated SearchRequest.

        Returns:
            SearchResponse containing ranked products, applied filters, and metadata.
        """
        start_time = time.perf_counter()

        # 1. Parse query intent and constraints
        parsed, used_fallback = self.parser.parse(request.query)

        # Update parser health status
        if self.parser.llm_client:
            self._llm_status = "degraded" if used_fallback else "ok"

        warnings = list(parsed.warnings)

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

        # 2. Progressive Candidate Widening
        pool_sizes = settings.progressive_pool_sizes
        survivors: list[tuple[Any, float, float]] = []
        total_excluded = 0
        applied_filters: dict[str, Any] = {}
        best_overall_similarity = 0.0

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

            # Fetch product models
            cand_ids = [c[0] for c in raw_candidates]
            product_map = self.catalog_repo.get_by_ids(cand_ids)

            paired_candidates = [
                (product_map[pid], fused_score, sim)
                for pid, fused_score, sim in raw_candidates
                if pid in product_map
            ]

            # Apply hard filters & soft boosts
            filtered_survivors, excluded_count, parsed_filters = apply_candidate_filters(
                paired_candidates,
                parsed,
                gender_include_unknown=settings.gender_include_unknown,
            )

            survivors = filtered_survivors
            total_excluded = excluded_count
            applied_filters = parsed_filters

            # Stop widening if we have enough surviving candidates
            if len(survivors) >= request.top_k:
                break

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        meta = SearchMeta(
            parsed_filters=applied_filters,
            used_fallback=used_fallback,
            latency_ms=round(elapsed_ms, 2),
            index_version=self.hybrid_index.index_version,
            excluded_by_filters=total_excluded,
            low_confidence=False,
            warnings=warnings,
        )

        # 3. Guardrail: Check optional minimum similarity threshold (default 0.0, disabled)
        if (
            settings.min_similarity_threshold > 0.0
            and best_overall_similarity < settings.min_similarity_threshold
        ):
            return SearchResponse(
                results=[],
                meta=meta,
                message="no_good_match",
                suggested_queries=settings.suggested_queries,
            )

        if not survivors:
            return SearchResponse(
                results=[],
                meta=meta,
                message="no_good_match" if total_excluded == 0 else None,
                suggested_queries=settings.suggested_queries,
            )

        # 4. Build final response list
        items: list[SearchResultItem] = []
        for product, adjusted_score, similarity in survivors[: request.top_k]:
            reason = f"Ranked via hybrid retrieval (similarity: {similarity:.2f})"
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

        # Check low confidence on returned items
        if items:
            best_returned_sim = max(item.similarity for item in items)
            meta.low_confidence = best_returned_sim < settings.low_confidence_similarity

        meta.latency_ms = round((time.perf_counter() - start_time) * 1000.0, 2)

        return SearchResponse(
            results=items,
            meta=meta,
        )
