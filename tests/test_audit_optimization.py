"""Unit and integration tests for the Gemini query-understanding audit and optimization.

Covers:
- Layer 1 obvious queries (deterministic fast path)
- Layer 2 subjective queries (Gemini routing)
- Parser cache hit and miss
- Query normalization in cache
- Gemini success
- Gemini 429 quota exhaustion & circuit breaker
- Gemini timeout & fallback
- Malformed / invalid JSON responses
- Uncertain subjective occasion / slot retention in strict filters
- Explicit budget, gender, slot strict enforcement
- Mixed semantic + metadata queries
- Repeated identical queries & metrics
"""

from typing import Any

import pytest

from app.cache import ParseCache
from app.exceptions import LLMError
from app.filters import passes_strict_filters
from app.llm.fake import FakeLLMClient
from app.parser import LLMCircuitBreaker, ParsedQuery, QueryParser
from app.schemas import Product


class TestAuditLayer1AndLayer2Routing:
    """Tests for two-layer query routing: Layer 1 deterministic vs Layer 2 LLM."""

    @pytest.mark.parametrize(
        "query,expected_gender,expected_slot,expected_max_price",
        [
            ("red dress under $50", None, "full_body", 50.0),
            ("black shoes for women", "women", "footwear", None),
            ("winter jacket for men", "men", "top", None),
            ("running shorts under $25", None, "bottom", 25.0),
        ],
    )
    def test_layer1_handles_obvious_queries_without_llm(
        self,
        query: str,
        expected_gender: str | None,
        expected_slot: str | None,
        expected_max_price: float | None,
    ) -> None:
        """Obvious queries with explicit slots/demographics/prices bypass LLM completely."""
        fake_client = FakeLLMClient()
        fake_client.is_gemini = True  # Marks client as production Gemini
        parser = QueryParser(llm_client=fake_client)

        parsed, used_fallback = parser.parse(query)

        assert fake_client.call_count == 0  # Zero Gemini API calls
        assert parser.layer1_count == 1
        assert parser.gemini_count == 0

        if expected_gender:
            assert parsed.gender == expected_gender
            assert parsed.is_explicit_gender is True
        if expected_slot:
            assert expected_slot in parsed.slots
            assert parsed.is_explicit_slot is True
        if expected_max_price:
            assert parsed.max_price == expected_max_price

    @pytest.mark.parametrize(
        "query",
        [
            "something stylish for a dinner date",
            "what should I wear for a Parisian dinner?",
            "something casual but stylish for college",
            "what would look good for a summer party?",
            "outfit idea for first date",
            "how to dress for a gallery opening",
        ],
    )
    def test_layer2_routes_subjective_queries_to_llm(self, query: str) -> None:
        """Subjective, ambiguous, styling queries route to Layer 2 Gemini."""
        fake_response: dict[str, Any] = {
            "is_fashion_query": True,
            "normalized_query_en": query,
            "language": "en",
            "gender": None,
            "age_group": "adult",
            "min_price": None,
            "max_price": None,
            "colors": [],
            "slots": ["full_body", "top"],
            "season": "summer" if "summer" in query else None,
            "occasion": "party" if "party" in query else "date",
            "warnings": [],
        }
        fake_client = FakeLLMClient(default_response=fake_response)
        parser = QueryParser(llm_client=fake_client)

        parsed, used_fallback = parser.parse(query)

        assert used_fallback is False  # Successfully parsed by LLM
        assert fake_client.call_count == 1  # Called Gemini
        assert parser.gemini_count == 1
        assert parsed.is_explicit_slot is False  # Marked as inferred/subjective slot
        assert parsed.is_explicit_gender is False


class TestAuditIntentCaching:
    """Tests for bounded, thread-safe intent caching and normalization."""

    def test_cache_miss_then_cache_hit(self) -> None:
        """First call misses and populates cache; second call hits cache with 0 LLM calls."""
        fake_response: dict[str, Any] = {
            "is_fashion_query": True,
            "normalized_query_en": "dinner date outfit",
            "language": "en",
            "gender": None,
            "age_group": "adult",
            "min_price": None,
            "max_price": None,
            "colors": [],
            "slots": ["full_body"],
            "season": None,
            "occasion": "date",
            "warnings": [],
        }
        fake_client = FakeLLMClient(default_response=fake_response)
        cache = ParseCache(max_size=50, ttl_seconds=60.0)
        parser = QueryParser(llm_client=fake_client, cache=cache)

        # 1. Miss
        parsed1, used_fallback1 = parser.parse("dinner date outfit")
        assert not used_fallback1
        assert fake_client.call_count == 1
        assert cache.hits == 0
        assert cache.misses == 1

        # 2. Hit
        parsed2, used_fallback2 = parser.parse("dinner date outfit")
        assert not used_fallback2
        assert fake_client.call_count == 1  # No additional call!
        assert cache.hits == 1
        assert parsed1.slots == parsed2.slots
        assert parsed1.occasion == parsed2.occasion

    def test_cache_query_normalization(self) -> None:
        """Punctuation, casing, and spacing variations hit identical cache entry."""
        cache = ParseCache(max_size=50, ttl_seconds=60.0)
        parsed = ParsedQuery(normalized_query_en="red cocktail dress", max_price=50.0)
        cache.put("red cocktail dress", parsed, used_fallback=False)

        # Variations should normalize and match
        assert cache.get("  Red Cocktail Dress!  ") is not None
        assert cache.get("red cocktail dress?") is not None
        assert cache.get(' "red cocktail dress" ') is not None
        assert cache.hits == 3

    def test_transient_failure_is_not_cached(self) -> None:
        """429 or timeout failures are never persisted to the intent cache."""
        cache = ParseCache(max_size=50, ttl_seconds=60.0)
        parsed = ParsedQuery(normalized_query_en="rate limited query")

        # Record transient failure
        cache.put("rate limited query", parsed, is_transient_failure=True)
        assert cache.get("rate limited query") is None

        # Record deterministic fallback without explicit cache_deterministic
        cache.put("rate limited query", parsed, used_fallback=True, cache_deterministic=False)
        assert cache.get("rate limited query") is None


class TestCircuitBreakerAndFailures:
    """Tests for LLMCircuitBreaker behavior on 429, timeouts, and malformed JSON."""

    def test_gemini_429_trips_breaker_and_falls_back(self) -> None:
        """429 RESOURCE_EXHAUSTED immediately trips breaker to OPEN and returns fallback."""
        fake_client = FakeLLMClient(raise_error_times=5)
        # Configure error with 429 / quota signature
        breaker = LLMCircuitBreaker(failure_threshold=2, cooldown_seconds=60.0)
        parser = QueryParser(llm_client=fake_client, breaker=breaker)

        # Force the error to mention quota exhaustion
        def raise_429(system: str, user: str, timeout: float = 3.0) -> str:
            raise LLMError("ResourceExhausted: 429 Quota exceeded for quota metric")

        fake_client.complete_json = raise_429  # type: ignore[method-assign]

        parsed, used_fallback = parser.parse("something stylish for a dinner date")

        assert used_fallback is True
        assert breaker.state == "open"
        assert breaker.status == "circuit_open"
        assert parser.fallback_count == 1

        # Next call immediately uses fallback without touching LLM client
        call_count_before = fake_client.call_count
        parsed2, used_fallback2 = parser.parse("another subjective query for a party")
        assert used_fallback2 is True
        assert fake_client.call_count == call_count_before

    def test_gemini_timeout_falls_back_gracefully(self) -> None:
        """TimeoutError triggers fallback and does not raise an unhandled exception."""
        fake_client = FakeLLMClient(raise_timeout_times=2)
        parser = QueryParser(llm_client=fake_client)

        parsed, used_fallback = parser.parse("what to wear to a summer wedding?")

        assert used_fallback is True
        assert isinstance(parsed, ParsedQuery)

    def test_malformed_json_falls_back(self) -> None:
        """Malformed JSON string triggers fallback without crashing."""
        fake_client = FakeLLMClient(return_invalid_json=True)
        parser = QueryParser(llm_client=fake_client)

        parsed, used_fallback = parser.parse("what should I wear to an art gallery?")

        assert used_fallback is True
        assert isinstance(parsed, ParsedQuery)

    def test_incomplete_json_schema_falls_back(self) -> None:
        """Valid JSON but incompatible schema falls back safely."""
        fake_client = FakeLLMClient(default_response='{"completely_unrelated_key": 123}')
        parser = QueryParser(llm_client=fake_client)

        parsed, used_fallback = parser.parse("stylish dinner date outfit")

        assert used_fallback is True
        assert isinstance(parsed, ParsedQuery)


class TestUncertaintyAndStrictFilters:
    """Tests for soft filtering on uncertain attributes vs hard filtering on constraints."""

    def test_subjective_occasion_does_not_eliminate_products(self) -> None:
        """Subjective queries like 'dinner date' do NOT eliminate products on slot/gender."""
        parsed = ParsedQuery(
            normalized_query_en="dinner date outfit",
            slots=["full_body"],
            is_explicit_slot=False,  # Subjective inference
            gender=None,
            is_explicit_gender=False,
        )

        product_top = Product(
            parent_asin="TOP1",
            title="Silk Evening Blouse",
            slot="top",  # Different from full_body, but slot wasn't explicit!
            price=45.0,
        )

        # passes_strict_filters should NOT reject product_top on slot mismatch
        assert passes_strict_filters(product_top, parsed) is True

    def test_explicit_slot_strictly_filters(self) -> None:
        """Explicit slot (e.g. 'dress' -> full_body) strictly filters non-matching items."""
        parsed = ParsedQuery(
            normalized_query_en="red dress",
            slots=["full_body"],
            is_explicit_slot=True,  # Explicitly stated in query
        )

        dress = Product(parent_asin="D1", title="Red A-Line Dress", slot="full_body", price=40.0)
        shoes = Product(parent_asin="S1", title="Red High Heels", slot="footwear", price=40.0)

        assert passes_strict_filters(dress, parsed) is True
        assert passes_strict_filters(shoes, parsed) is False

    def test_explicit_gender_strictly_filters(self) -> None:
        """Explicit gender strictly rejects opposing gender items."""
        parsed = ParsedQuery(
            normalized_query_en="women running shoes",
            gender="women",
            is_explicit_gender=True,
        )

        women_shoe = Product(
            parent_asin="W1",
            title="Women's Running Shoe",
            slot="footwear",
            gender="women",
            price=50.0,
        )
        men_shoe = Product(
            parent_asin="M1",
            title="Men's Running Shoe",
            slot="footwear",
            gender="men",
            price=50.0,
        )

        assert passes_strict_filters(women_shoe, parsed) is True
        assert passes_strict_filters(men_shoe, parsed) is False

    def test_explicit_budget_strictly_filters(self) -> None:
        """Explicit budget strictly eliminates items over max_price."""
        parsed = ParsedQuery(
            normalized_query_en="dress under $50",
            max_price=50.0,
            slots=["full_body"],
            is_explicit_slot=True,
        )

        cheap_dress = Product(
            parent_asin="D1", title="Summer Dress", slot="full_body", price=45.0
        )
        expensive_dress = Product(
            parent_asin="D2", title="Evening Dress", slot="full_body", price=55.0
        )

        assert passes_strict_filters(cheap_dress, parsed) is True
        assert passes_strict_filters(expensive_dress, parsed) is False

    def test_mixed_semantic_and_metadata_query(self) -> None:
        """Query with both explicit constraints and semantic flavor handles both accurately."""
        # Query: "stylish red cocktail dress under $50"
        parsed = QueryParser.fallback_parse("stylish red cocktail dress under $50")

        assert parsed.max_price == 50.0
        assert "full_body" in parsed.slots
        assert parsed.is_explicit_slot is True
        assert "red" in parsed.colors
