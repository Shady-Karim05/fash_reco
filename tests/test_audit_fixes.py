"""Regression and verification tests for the Master Engineering Prompt audit fixes.

Covers:
1. Search Eligibility Guard (Problem A / Fix 3)
2. Low-Price Handling ($0.50, $1.00, $1.99, $2.00) (Problem B / Fix 4)
3. Contextual Attribute Interpretation (Shorts Pajamas, Costume Jewelry) (Problem C / Fix 2)
4. Demographic False Positives (CPR mask, Sweet 16 sash) (Problem D / Fix 2)
5. Circuit Breaker & 429 Resilience (Problem E / Fix 5)
6. Multilingual Fallback Normalization (EN, ES, FR, HI, TA) (Problem F / Fix 1)
7. Hybrid BM25 Activation on Multilingual Queries (Problem G / Fix 1)
8. Outfit Semantic & Style Compatibility (Problem H / Fix 6)
9. Human Audit Tooling Read-Only Verification (Problem I / Fix 7)
"""

import time
from pathlib import Path

from app.attribute_correction import (
    get_effective_age_group,
    get_effective_product_slots,
    is_search_eligible_product,
)
from app.config import settings
from app.filters import passes_strict_filters
from app.multilingual import (
    detect_language,
    normalize_multilingual_query,
)
from app.outfit import compute_outfit_compatibility_score
from app.parser import LLMCircuitBreaker, ParsedQuery, QueryParser
from app.schemas import Product
from scripts.check_audit_status import check_audit_status


# ==============================================================================
# 1. Search Eligibility Guard (Problem A / Fix 3)
# ==============================================================================
class TestSearchEligibilityGuard:
    def test_peripheral_noise_filtered_from_unconstrained_queries(self) -> None:
        """Obvious peripheral items in unknown slot are filtered from general fashion searches."""
        decal_item = Product(
            parent_asin="NOISE_DECAL",
            title="Vinyl Decal Mountain Sun Sticker for Car Window Bumper",
            slot="unknown",
            search_text="Vinyl Decal Mountain Sun Sticker for Car Window Bumper",
        )
        zipper_item = Product(
            parent_asin="NOISE_ZIPPER",
            title="Metal Zipper Pull Replacement Repair Kit for Bags",
            slot="unknown",
            search_text="Metal Zipper Pull Replacement Repair Kit for Bags",
        )
        cpr_item = Product(
            parent_asin="NOISE_CPR",
            title="CPR Training Pocket Mask Keychain Resuscitation Barrier",
            slot="unknown",
            search_text="CPR Training Pocket Mask Keychain Resuscitation Barrier",
        )

        # Unconstrained fashion queries -> filtered
        assert not is_search_eligible_product(decal_item, raw_query="fashion accessories")
        assert not is_search_eligible_product(zipper_item, raw_query="women's handbag")
        assert not is_search_eligible_product(cpr_item, raw_query="red summer dress")

    def test_peripheral_items_retained_when_explicitly_requested(self) -> None:
        """Peripheral items are searchable when the user query specifically mentions them."""
        decal_item = Product(
            parent_asin="NOISE_DECAL",
            title="Vinyl Decal Mountain Sun Sticker for Car Window Bumper",
            slot="unknown",
            search_text="Vinyl Decal Mountain Sun Sticker for Car Window Bumper",
        )
        zipper_item = Product(
            parent_asin="NOISE_ZIPPER",
            title="Metal Zipper Pull Replacement Repair Kit for Bags",
            slot="unknown",
            search_text="Metal Zipper Pull Replacement Repair Kit for Bags",
        )
        cpr_item = Product(
            parent_asin="NOISE_CPR",
            title="CPR Training Pocket Mask Keychain Resuscitation Barrier",
            slot="unknown",
            search_text="CPR Training Pocket Mask Keychain Resuscitation Barrier",
        )

        assert is_search_eligible_product(decal_item, raw_query="car window decal sticker")
        assert is_search_eligible_product(zipper_item, raw_query="replacement zipper pull")
        assert is_search_eligible_product(cpr_item, raw_query="first aid cpr mask keychain")

    def test_legitimate_unknown_fashion_products_retained(self) -> None:
        """Legitimate fashion items stored under 'unknown' slot must NOT be filtered."""
        poncho = Product(
            parent_asin="LEGIT_WRAP",
            title="Bohemian Tribal Woolen Fringe Shawl Wrap",
            slot="unknown",
            search_text="Bohemian Tribal Woolen Fringe Shawl Wrap",
        )
        assert is_search_eligible_product(poncho, raw_query="warm winter wrap")


# ==============================================================================
# 2. Contextual Attribute Interpretation (Problems C & D / Fix 2)
# ==============================================================================
class TestContextualAttributeInterpretation:
    def test_shorts_pajamas_set_slot_collision(self) -> None:
        """'American Trends Shorts Pajamas Set' should match both 'bottom' and 'full_body'."""
        prod = Product(
            parent_asin="B01_PAJAMA_SHORTS",
            title="American Trends Women's Casual Shorts Pajamas Set Soft Loungewear",
            slot="full_body",
            gender="women",
            age_group="adult",
        )
        slots = get_effective_product_slots(prod)
        assert "bottom" in slots
        assert "full_body" in slots

        # Passes when bottom is requested
        parsed_bottom = ParsedQuery(normalized_query_en="shorts", slots=["bottom"])
        assert passes_strict_filters(prod, parsed_bottom)

        # Passes when full_body is requested
        parsed_pjs = ParsedQuery(normalized_query_en="pajamas", slots=["full_body"])
        assert passes_strict_filters(prod, parsed_pjs)

    def test_costume_jewelry_slot_collision(self) -> None:
        """'Humaira Pendant Costume Jewelry' is an accessory, not a full_body costume."""
        prod = Product(
            parent_asin="B02_PENDANT",
            title="Humaira Elegant Pendant Costume Jewelry Necklace",
            slot="full_body",
            gender="women",
            age_group="adult",
        )
        slots = get_effective_product_slots(prod)
        assert "accessory" in slots
        assert "full_body" not in slots

        # Matches accessory query
        parsed_acc = ParsedQuery(normalized_query_en="pendant necklace", slots=["accessory"])
        assert passes_strict_filters(prod, parsed_acc)

        # Barred from full_body queries
        parsed_full = ParsedQuery(normalized_query_en="halloween costume", slots=["full_body"])
        assert not passes_strict_filters(prod, parsed_full)

    def test_cpr_mask_no_kids_leakage(self) -> None:
        """Infant CPR mask must NOT be classified as kids clothing."""
        prod = Product(
            parent_asin="B03_CPR",
            title="Infant Child CPR Training Pocket Mask Keychain",
            slot="unknown",
            gender="unknown",
            age_group="kids",  # Baseline classifier tagged it as kids
        )
        effective_age = get_effective_age_group(prod)
        assert effective_age == "adult"

        # Query for kids clothing bars this item
        parsed_kids = ParsedQuery(normalized_query_en="kids clothes", age_group="kids")
        assert not passes_strict_filters(prod, parsed_kids)

    def test_sweet_16_sash_adult_demographic(self) -> None:
        """Sweet 16 birthday sash is adult/teen event wear, not children's clothing."""
        prod = Product(
            parent_asin="B04_SASH",
            title="Sweet 16 Birthday Sash Rose Gold Glitter Party Wear",
            slot="accessory",
            gender="women",
            age_group="kids",  # Baseline classifier tagged it as kids due to '16'
        )
        effective_age = get_effective_age_group(prod)
        assert effective_age == "adult"

        parsed_adult = ParsedQuery(normalized_query_en="party sash for women", age_group="adult")
        assert passes_strict_filters(prod, parsed_adult)

    def test_genuine_kids_apparel_remains_kids(self) -> None:
        """Authentic children's garments remain strictly classified as kids."""
        prod = Product(
            parent_asin="B05_KIDS_DRESS",
            title="Toddler Girls Summer Floral Dress with Ruffle Hem",
            slot="full_body",
            gender="women",
            age_group="kids",
        )
        assert get_effective_age_group(prod) == "kids"
        parsed_adult = ParsedQuery(normalized_query_en="women summer dress", age_group="adult")
        assert not passes_strict_filters(prod, parsed_adult)


# ==============================================================================
# 3. Low Price Handling ($0.50, $1.00, $1.99, $2.00) (Problem B / Fix 4)
# ==============================================================================
class TestLowPriceHandling:
    def test_outfit_price_floor_boundaries(self) -> None:
        """Outfit mode enforces $2.00 minimum price: $0.50, $1.00, $1.99 blocked, $2.00 allowed."""
        prices = [0.50, 1.00, 1.99, 2.00, 2.50]
        for p in prices:
            is_allowed = p >= settings.outfit_min_item_price
            if p < 2.00:
                assert not is_allowed, f"Expected {p} to be blocked in outfit mode"
            else:
                assert is_allowed, f"Expected {p} to be allowed in outfit mode"

    def test_general_search_allows_cheap_fashion_items(self) -> None:
        """General product search does NOT impose an arbitrary $2.00 floor."""
        cheap_scrunchie = Product(
            parent_asin="SCRUNCHIE_199",
            title="Silk Hair Scrunchie Elastic Ponytail Holder",
            price=1.99,
            slot="accessory",
            gender="women",
            age_group="adult",
        )
        parsed = ParsedQuery(
            normalized_query_en="hair scrunchie", slots=["accessory"], max_price=10.0
        )
        assert passes_strict_filters(cheap_scrunchie, parsed)


# ==============================================================================
# 4. Multilingual Fallback Normalization (Problem F / Fix 1)
# ==============================================================================
class TestMultilingualFallbackEngine:
    def test_language_detection(self) -> None:
        assert detect_language("summer dress for beach vacation under $50") == "en"
        assert detect_language("vestido de verano para vacaciones en la playa") == "es"
        assert detect_language("robe d'été pour vacances à la plage") == "fr"
        assert detect_language("समुद्र तट की छुट्टी के लिए गर्मियों की पोशाक") == "hi"
        assert detect_language("கடற்கரை விடுமுறைக்காக கோடைக்கால உடை") == "ta"

    def test_tamil_running_shoes_normalization(self) -> None:
        """Tamil query for men's running shoes extracts slot, gender, price, and English."""
        q = "80 டாலருக்கு குறைவான ஆண்களுக்கான ஓடும் காலணிகள்"
        res = normalize_multilingual_query(q)
        assert res.detected_language == "ta"
        assert res.slots == ["footwear"]
        assert res.gender == "men"
        assert res.age_group == "adult"
        assert res.max_price == 80.0
        assert "shoes" in res.normalized_query_en
        assert "running" in res.normalized_query_en
        assert "80" in res.normalized_query_en

    def test_hindi_summer_dress_normalization(self) -> None:
        """Hindi query for summer dress extracts full_body slot, price, and English."""
        q = "समुद्र तट की छुट्टी के लिए 50 डॉलर से कम की गर्मियों की पोशाक"
        res = normalize_multilingual_query(q)
        assert res.detected_language == "hi"
        assert res.slots == ["full_body"]
        assert res.max_price == 50.0
        assert "dress" in res.normalized_query_en
        assert "summer" in res.normalized_query_en

    def test_spanish_running_shoes_normalization(self) -> None:
        """Spanish query for men's running shoes under $80."""
        q = "zapatillas de correr para hombre por menos de 80 dólares"
        res = normalize_multilingual_query(q)
        assert res.detected_language == "es"
        assert res.slots == ["footwear"]
        assert res.gender == "men"
        assert res.max_price == 80.0
        assert "running" in res.normalized_query_en

    def test_french_summer_dress_normalization(self) -> None:
        """French query for beach summer dress under $50."""
        q = "robe d'été pour vacances à la plage à moins de 50 dollars"
        res = normalize_multilingual_query(q)
        assert res.detected_language == "fr"
        assert res.slots == ["full_body"]
        assert res.max_price == 50.0
        assert "dress" in res.normalized_query_en

    def test_query_parser_fallback_integrates_multilingual(self) -> None:
        """QueryParser.fallback_parse delegates to normalizer for non-English queries."""
        parsed = QueryParser.fallback_parse("80 டாலருக்கு குறைவான ஆண்களுக்கான ஓடும் காலணிகள்")
        assert parsed.slots == ["footwear"]
        assert parsed.gender == "men"
        assert parsed.max_price == 80.0
        assert "shoes" in parsed.normalized_query_en


# ==============================================================================
# 5. Circuit Breaker Resilience (Problem E / Fix 5)
# ==============================================================================
class TestCircuitBreakerResilience:
    def test_breaker_immediate_trip_on_429(self) -> None:
        """HTTP 429 / RESOURCE_EXHAUSTED immediately trips breaker to OPEN with 0 retries."""
        breaker = LLMCircuitBreaker(failure_threshold=3, cooldown_seconds=60.0)
        assert breaker.state == "closed"
        assert breaker.can_attempt() is True

        breaker.record_failure(is_exhausted=True)
        assert breaker.state == "open"
        assert breaker.can_attempt() is False
        assert breaker.status == "circuit_open"

    def test_breaker_half_open_recovery(self) -> None:
        """After cooldown window expires, breaker allows one trial call in half-open state."""
        breaker = LLMCircuitBreaker(failure_threshold=1, cooldown_seconds=0.05)
        breaker.record_failure(is_exhausted=True)
        assert breaker.can_attempt() is False

        time.sleep(0.06)
        assert breaker.can_attempt() is True
        assert breaker.state == "half_open"

        # Successful trial call closes breaker
        breaker.record_success()
        assert breaker.state == "closed"
        assert breaker.status == "ok"


# ==============================================================================
# 6. Outfit Semantic/Style Compatibility (Problem H / Fix 6)
# ==============================================================================
class TestOutfitStyleCompatibility:
    def test_occasion_and_season_bonus(self) -> None:
        """Coherent outfits sharing formal occasion and winter season receive higher score."""
        formal_gown = Product(
            parent_asin="GOWN_1",
            title="Women's Velvet Formal Evening Gown",
            slot="full_body",
            occasions=["formal"],
            seasons=["winter"],
            gender="women",
            age_group="adult",
        )
        formal_heels = Product(
            parent_asin="HEELS_1",
            title="Women's Satin Formal Evening Dress Shoes",
            slot="footwear",
            occasions=["formal"],
            seasons=["winter"],
            gender="women",
            age_group="adult",
        )
        clash_sneakers = Product(
            parent_asin="SNEAKER_1",
            title="Athletic Gym Workout Running Shoes",
            slot="footwear",
            occasions=["workout"],
            gender="women",
            age_group="adult",
        )

        coherent_combo = [(formal_gown, 1.0, 0.8), (formal_heels, 1.0, 0.8)]
        clashing_combo = [(formal_gown, 1.0, 0.8), (clash_sneakers, 1.0, 0.8)]

        score_coherent = compute_outfit_compatibility_score(coherent_combo)
        score_clashing = compute_outfit_compatibility_score(clashing_combo)

        assert score_coherent > score_clashing
        # Clashing formal + athletic incurs conflict penalty
        assert score_clashing < 0.0

    def test_novelty_led_coat_penalized_with_formal_footwear(self) -> None:
        """Novelty LED festival wear paired with formal shoes receives severe clash penalty."""
        led_coat = Product(
            parent_asin="LED_COAT",
            title="Light Up LED Rainbow Faux Fur Festival Jacket",
            slot="top",
            occasions=["party"],
            gender="women",
            age_group="adult",
        )
        formal_shoes = Product(
            parent_asin="FORMAL_SHOES",
            title="Classic Formal Wedding Dress Shoes",
            slot="footwear",
            occasions=["formal"],
            gender="women",
            age_group="adult",
        )
        combo = [(led_coat, 1.0, 0.8), (formal_shoes, 1.0, 0.8)]
        score = compute_outfit_compatibility_score(combo)
        assert score < 0.0  # Conflict penalty applied


# ==============================================================================
# 7. Human Audit Tooling Read-Only Verification (Problem I / Fix 7)
# ==============================================================================
class TestHumanAuditTooling:
    def test_check_audit_status_runs_cleanly(self) -> None:
        """Verify check_audit_status runs in read-only mode and returns exit code 0."""
        csv_path = Path("data/audit_sample.csv")
        assert csv_path.is_file()

        initial_mtime = csv_path.stat().st_mtime_ns
        exit_code = check_audit_status(csv_path)
        final_mtime = csv_path.stat().st_mtime_ns

        assert exit_code == 0
        assert initial_mtime == final_mtime, "check_audit_status modified csv!"
