"""Tests for pure filtering functions, soft boosts, and progressive widening."""

import random

from app.catalog import CatalogRepository
from app.embedder import FakeEmbedder
from app.filters import apply_candidate_filters, compute_soft_boost, passes_strict_filters
from app.index import HybridIndex
from app.parser import ParsedQuery, QueryParser
from app.schemas import Product, SearchRequest
from app.service import SearchService


def _make_product(
    asin: str,
    title: str = "Test Product",
    price: float | None = 25.0,
    gender: str = "women",
    age_group: str = "adult",
    slot: str = "full_body",
    colors: list[str] | None = None,
    seasons: list[str] | None = None,
    occasions: list[str] | None = None,
    is_deleted: bool = False,
) -> Product:
    return Product(
        parent_asin=asin,
        title=title,
        price=price,
        gender=gender,
        age_group=age_group,
        slot=slot,
        colors=colors or [],
        seasons=seasons or [],
        occasions=occasions or [],
        is_deleted=is_deleted,
    )


class TestStrictFiltering:
    """Test passes_strict_filters across all constraint dimensions."""

    def test_price_filtering(self) -> None:
        p_cheap = _make_product("1", price=15.0)
        p_expensive = _make_product("2", price=55.0)
        p_unpriced = _make_product("3", price=None)

        pq = ParsedQuery(normalized_query_en="test", max_price=30.0, min_price=10.0)
        assert passes_strict_filters(p_cheap, pq)
        assert not passes_strict_filters(p_expensive, pq)
        assert not passes_strict_filters(p_unpriced, pq)

    def test_gender_filtering_men_allows_men_and_unisex(self) -> None:
        p_men = _make_product("1", gender="men")
        p_unisex = _make_product("2", gender="unisex")
        p_women = _make_product("3", gender="women")
        p_unknown = _make_product("4", gender="unknown")

        pq = ParsedQuery(normalized_query_en="test", gender="men")
        assert passes_strict_filters(p_men, pq)
        assert passes_strict_filters(p_unisex, pq)
        assert not passes_strict_filters(p_women, pq)
        assert not passes_strict_filters(p_unknown, pq, gender_include_unknown=False)
        assert passes_strict_filters(p_unknown, pq, gender_include_unknown=True)

    def test_gender_filtering_women_allows_women_and_unisex(self) -> None:
        p_men = _make_product("1", gender="men")
        p_unisex = _make_product("2", gender="unisex")
        p_women = _make_product("3", gender="women")

        pq = ParsedQuery(normalized_query_en="test", gender="women")
        assert passes_strict_filters(p_women, pq)
        assert passes_strict_filters(p_unisex, pq)
        assert not passes_strict_filters(p_men, pq)

    def test_age_group_filtering(self) -> None:
        p_adult = _make_product("1", age_group="adult")
        p_kids = _make_product("2", age_group="kids")

        pq_adult = ParsedQuery(normalized_query_en="test", age_group="adult")
        assert passes_strict_filters(p_adult, pq_adult)
        assert not passes_strict_filters(p_kids, pq_adult)

        pq_kids = ParsedQuery(normalized_query_en="test", age_group="kids")
        assert passes_strict_filters(p_kids, pq_kids)
        assert not passes_strict_filters(p_adult, pq_kids)

    def test_slot_filtering(self) -> None:
        p_top = _make_product("1", slot="top")
        p_bottom = _make_product("2", slot="bottom")

        pq = ParsedQuery(normalized_query_en="test", slots=["top"])
        assert passes_strict_filters(p_top, pq)
        assert not passes_strict_filters(p_bottom, pq)

    def test_soft_deleted_product_always_fails(self) -> None:
        p_deleted = _make_product("1", is_deleted=True)
        pq = ParsedQuery(normalized_query_en="test")
        assert not passes_strict_filters(p_deleted, pq)


class TestSoftBoosts:
    """Test soft boost score computation for season, occasion, and color."""

    def test_season_and_occasion_boost(self) -> None:
        p = _make_product("1", seasons=["summer"], occasions=["beach"])
        pq = ParsedQuery(normalized_query_en="test", season="summer", occasion="beach")

        boost = compute_soft_boost(
            p,
            pq,
            boost_weight_season=0.05,
            boost_weight_occasion=0.05,
        )
        assert round(boost, 2) == 0.10

    def test_color_boost(self) -> None:
        p = _make_product("1", colors=["black", "red"])
        pq = ParsedQuery(normalized_query_en="test", colors=["red"])

        boost = compute_soft_boost(p, pq, boost_weight_color=0.03)
        assert round(boost, 2) == 0.03


class TestRandomizedConstraintIntegrity:
    """Randomized property test asserting no filtered result violates constraints."""

    def test_seeded_randomized_candidates(self) -> None:
        random.seed(42)
        slots = ["top", "bottom", "full_body", "footwear", "accessory", "unknown"]
        genders = ["men", "women", "unisex", "unknown"]
        ages = ["adult", "kids"]

        products: list[Product] = []
        for i in range(200):
            p = _make_product(
                asin=f"B00{i:03d}",
                price=round(random.uniform(5.0, 150.0), 2),
                gender=random.choice(genders),
                age_group=random.choice(ages),
                slot=random.choice(slots),
                colors=["black"] if i % 2 == 0 else ["blue"],
            )
            products.append(p)

        candidates = [(p, 0.03 - i * 0.0001, 0.5) for i, p in enumerate(products)]

        # Test with strict constraints
        pq = ParsedQuery(
            normalized_query_en="test query",
            gender="men",
            age_group="adult",
            max_price=45.0,
            slots=["top", "bottom"],
        )

        survivors, excluded_count, _ = apply_candidate_filters(candidates, pq)
        assert len(survivors) + excluded_count == len(candidates)

        for product, _, _ in survivors:
            assert product.price is not None and product.price <= 45.0
            assert product.gender in {"men", "unisex"}
            assert product.age_group == "adult"
            assert product.slot in {"top", "bottom"}


class TestProgressiveWidening:
    """Test candidate widening behavior in SearchService."""

    def test_widening_satisfies_top_k(self, tmp_path: str) -> None:
        db_file = f"{tmp_path}/widening.db"
        repo = CatalogRepository(db_file)
        embedder = FakeEmbedder(dimension=384)
        hybrid_index = HybridIndex(repo, embedder, cache_dir=str(tmp_path))

        # Add 50 products: only the last 10 match max_price <= 15
        products: list[Product] = []
        for i in range(50):
            price = 10.0 if i >= 40 else 80.0
            p = _make_product(
                asin=f"B000{i:02d}",
                title=f"Running athletic item number {i}",
                price=price,
                gender="men",
                age_group="adult",
                slot="bottom",
            )
            p.search_text = p.title
            products.append(p)

        repo.upsert_products_batch(products)
        hybrid_index.build_from_catalog(force_recompute=True)

        parser = QueryParser(None)
        service = SearchService(repo, hybrid_index, parser=parser)

        # Query requiring price under $15 with top_k=5
        req = SearchRequest(query="men's running shorts under $15", top_k=5)
        response = service.search(req)

        assert len(response.results) == 5
        for item in response.results:
            assert item.price is not None and item.price <= 15.0
