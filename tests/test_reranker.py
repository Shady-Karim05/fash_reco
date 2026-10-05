"""Comprehensive unit and integration tests for Query-Aware Reranker pipeline."""

from app.parser import ParsedQuery
from app.reranker import (
    QueryAwareReranker,
    RerankerCache,
    detect_query_archetype,
)
from app.schemas import Product


def _create_test_product(
    asin: str,
    title: str,
    price: float = 29.99,
    slot: str = "full_body",
    gender: str = "women",
    age_group: str = "adult",
    colors: list[str] | None = None,
    occasions: list[str] | None = None,
    quality_score: float = 4.2,
) -> Product:
    return Product(
        parent_asin=asin,
        title=title,
        price=price,
        slot=slot,
        gender=gender,
        age_group=age_group,
        colors=colors or [],
        occasions=occasions or [],
        quality_score=quality_score,
        search_text=f"{title} {slot} {gender} {' '.join(colors or [])}",
    )


class TestQueryArchetypeDetection:
    """Test query intent archetype classification (Phase 6)."""

    def test_explicit_product_archetype(self) -> None:
        pq = ParsedQuery(
            normalized_query_en="black shoes for women", slots=["footwear"], gender="women"
        )
        arch = detect_query_archetype("black shoes for women", pq)
        assert arch == "EXPLICIT_PRODUCT"

    def test_budget_explicit_archetype(self) -> None:
        pq = ParsedQuery(
            normalized_query_en="red dress under $50",
            slots=["full_body"],
            colors=["red"],
            max_price=50.0,
        )
        arch = detect_query_archetype("red dress under $50", pq)
        assert arch == "BUDGET_EXPLICIT"

    def test_discovery_style_archetype(self) -> None:
        pq = ParsedQuery(normalized_query_en="something stylish for a dinner date", occasion="date")
        arch = detect_query_archetype("something stylish for a dinner date", pq)
        assert arch == "DISCOVERY_STYLE"

    def test_standard_archetype(self) -> None:
        pq = ParsedQuery(normalized_query_en="warm fleece clothing")
        arch = detect_query_archetype("warm fleece clothing", pq)
        assert arch == "STANDARD"


class TestFeatureScoringAndPenalties:
    """Test individual feature extraction, color matching, and costume penalty."""

    def test_costume_penalty_applied_for_standard_fashion_query(self) -> None:
        reranker = QueryAwareReranker()
        costume_prod = _create_test_product(
            asin="C001",
            title="Royal Red Queen Costume Halloween Costume Medieval Princess",
            slot="full_body",
            colors=["red"],
        )
        real_prod = _create_test_product(
            asin="D001",
            title="Women Elegant Vintage Red Evening Cocktail Dress",
            slot="full_body",
            colors=["red"],
        )

        pq = ParsedQuery(
            normalized_query_en="red cocktail dress",
            slots=["full_body"],
            colors=["red"],
            occasion="party",
        )
        cands = [(costume_prod, 0.05, 0.70), (real_prod, 0.05, 0.70)]

        reranked = reranker.rerank("red cocktail dress", pq, cands)
        # Real dress should significantly outrank costume dress
        assert reranked[0][0].parent_asin == "D001"
        assert reranked[0][1] > reranked[1][1]

    def test_costume_allowed_when_query_requests_costume(self) -> None:
        reranker = QueryAwareReranker()
        costume_prod = _create_test_product(
            asin="C001",
            title="Royal Red Queen Costume Halloween Costume",
            slot="full_body",
        )
        pq = ParsedQuery(normalized_query_en="halloween costume dress", slots=["full_body"])
        feats = reranker.compute_features(
            costume_prod, "halloween costume dress", pq, 0.05, 0.05, 0.70
        )
        assert feats["costume_penalty"] == 0.0

    def test_color_match_and_family_synonyms(self) -> None:
        reranker = QueryAwareReranker()
        burgundy_prod = _create_test_product(
            asin="B001", title="Burgundy Velvet Dress", colors=["burgundy"]
        )
        blue_prod = _create_test_product(
            asin="B002", title="Cobalt Blue Silk Dress", colors=["blue"]
        )

        pq = ParsedQuery(normalized_query_en="red dress", colors=["red"], slots=["full_body"])
        feats_burgundy = reranker.compute_features(burgundy_prod, "red dress", pq, 0.05, 0.05, 0.70)
        feats_blue = reranker.compute_features(blue_prod, "red dress", pq, 0.05, 0.05, 0.70)

        # Burgundy is in red family -> color score should be near 1.0
        assert feats_burgundy["color"] >= 0.95
        # Blue has conflicting color -> color score should be penalized
        assert feats_blue["color"] <= 0.10

    def test_exact_phrase_matching(self) -> None:
        reranker = QueryAwareReranker()
        exact_prod = _create_test_product(
            asin="E001", title="Winter Warm Winter Jacket for Men Puffer Coat"
        )
        partial_prod = _create_test_product(asin="E002", title="Men Heavyweight Down Padded Coat")

        pq = ParsedQuery(normalized_query_en="winter jacket for men", slots=["top"], gender="men")
        feats_exact = reranker.compute_features(
            exact_prod, "winter jacket for men", pq, 0.05, 0.05, 0.75
        )
        feats_partial = reranker.compute_features(
            partial_prod, "winter jacket for men", pq, 0.05, 0.05, 0.75
        )

        assert feats_exact["exact_phrase"] > feats_partial["exact_phrase"]

    def test_price_fitness_score(self) -> None:
        reranker = QueryAwareReranker()
        in_budget_prod = _create_test_product(asin="P001", title="Floral Dress", price=35.00)
        over_budget_prod = _create_test_product(asin="P002", title="Floral Dress", price=75.00)

        pq = ParsedQuery(normalized_query_en="dress under $50", slots=["full_body"], max_price=50.0)
        feats_in = reranker.compute_features(
            in_budget_prod, "dress under $50", pq, 0.05, 0.05, 0.65
        )
        feats_over = reranker.compute_features(
            over_budget_prod, "dress under $50", pq, 0.05, 0.05, 0.65
        )

        assert feats_in["price"] > 0.7
        assert feats_over["price"] == 0.0


class TestRerankerCacheAndFallback:
    """Test LRU caching and failure-safe behavior."""

    def test_reranker_cache_hit_and_eviction(self) -> None:
        cache = RerankerCache(max_size=2)
        cache.put("key1", [("P1", 0.9, 0.8)])
        cache.put("key2", [("P2", 0.8, 0.7)])

        assert cache.get("key1") is not None
        assert cache.hits == 1

        # Add 3rd item to evict LRU (key2 was least recently used since key1 was accessed)
        cache.put("key3", [("P3", 0.7, 0.6)])
        assert cache.get("key2") is None
        assert cache.misses == 1
        assert cache.get("key1") is not None
        assert cache.get("key3") is not None

    def test_cross_encoder_graceful_fallback(self) -> None:
        # Cross-encoder with invalid model name falls back without raising HTTP 500
        reranker = QueryAwareReranker(
            enabled=True,
            use_cross_encoder=True,
            cross_encoder_model="invalid/non-existent-model-xyz-123",
        )
        p1 = _create_test_product("P1", "Casual Blue Summer Shirt", slot="top")
        pq = ParsedQuery(normalized_query_en="casual blue shirt")

        cands = [(p1, 0.05, 0.65)]
        # Must execute cleanly and fallback to feature reranker
        result = reranker.rerank("casual blue shirt", pq, cands)
        assert len(result) == 1
        assert result[0][0].parent_asin == "P1"
        assert reranker.use_cross_encoder is False
