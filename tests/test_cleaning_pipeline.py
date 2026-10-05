"""Unit and integration tests for Data Cleaning & Product Quality Control Pipeline (Phase 19).

Tests:
1. Missing title rejection
2. Invalid price rejection
3. Non-fashion product detection and rejection
4. Unknown slot quarantine
5. Correct 'tops for leggings' contextual classification as top
6. Footwear classification
7. Valid product with missing optional metadata accepted
8. Duplicate detection
9. Image URL failure not causing product rejection
10. Quarantine behavior and record storage
11. Quality score calculation and thresholds
12. Index building strictly excluding rejected and quarantined products
"""

from pathlib import Path

from app.catalog import CatalogRepository
from app.embedder import FakeEmbedder
from app.index import HybridIndex
from app.quality import (
    QuarantineManager,
    check_fashion_relevance,
    classify_fashion_slot,
    compute_explainable_quality_score,
    evaluate_record,
    validate_and_clean_title,
    validate_price,
)
from app.schemas import Product, QuarantineRecord


class TestDataCleaningValidation:
    """Tests for field validation rules."""

    def test_missing_title(self) -> None:
        """Missing or empty title returns is_valid=False with missing_title."""
        assert validate_and_clean_title(None)[0] is False
        assert validate_and_clean_title("")[0] is False
        assert validate_and_clean_title("   ")[0] is False

    def test_meaningless_title(self) -> None:
        """Punctuation only or single character titles fail validation."""
        assert validate_and_clean_title("--- !!! ???")[0] is False
        assert validate_and_clean_title("A")[0] is False

    def test_title_html_unescape_and_clean(self) -> None:
        """HTML entities like &amp; are unescaped and whitespace is cleaned."""
        is_valid, clean_title, _ = validate_and_clean_title(
            "Men&#39;s &amp; Women&#39;s Running Shoes"
        )
        assert is_valid is True
        assert "Men's & Women's Running Shoes" in clean_title

    def test_invalid_price(self) -> None:
        """Negative, zero, and missing prices fail validation."""
        assert validate_price(None)[0] is False
        assert validate_price(0.0)[0] is False
        assert validate_price(-15.99)[0] is False
        assert validate_price("not_a_number")[0] is False

    def test_price_outlier(self) -> None:
        """Corrupted outlier prices (> $10,000) are flagged as outliers."""
        is_valid, _, reason = validate_price(50000.0, max_price=10000.0)
        assert is_valid is False
        assert reason == "price_outlier"

    def test_valid_expensive_price_accepted(self) -> None:
        """Legitimate luxury prices ($500 - $1500) are accepted."""
        is_valid, p_val, reason = validate_price(850.0)
        assert is_valid is True
        assert p_val == 850.0
        assert reason is None


class TestFashionRelevance:
    """Tests for non-fashion product detection and fashion override protections."""

    def test_non_fashion_products_rejected(self) -> None:
        """Items like license plates, bicycle bells, guitar straps, paperweights are non-fashion."""
        assert (
            check_fashion_relevance("NEONBLOND Metal License Plate Flag With Vintage Look")[0]
            is False
        )
        assert check_fashion_relevance("ACTION BELL INCREDIBELL DUET BRASS")[0] is False
        assert check_fashion_relevance("Vtar Vegan Guitar Strap With 6 Free Pics")[0] is False
        assert check_fashion_relevance("Crystal Diamond Jewel Paperweight by Tripact")[0] is False
        assert check_fashion_relevance("PVC Pipe Connector Fitting 1/2 Inch")[0] is False
        assert check_fashion_relevance("Dog Collar with Heavy Duty Leash")[0] is False

    def test_fashion_overrides_protect_clothing_and_accessories(self) -> None:
        """Charms, enamel pins, watch bands, and heated jackets are protected as fashion."""
        assert check_fashion_relevance("Rembrandt Pipe Wrench Charm - Sterling Silver")[0] is True
        assert check_fashion_relevance("These Are Things Coffee Mug Enamel Pin")[0] is True
        assert (
            check_fashion_relevance("Tan Replacement Genuine Leather Strap for Apple Watch Band")[0]
            is True
        )
        assert (
            check_fashion_relevance("Milwaukee Heated Jacket KIT M12 With Charger Included")[0]
            is True
        )


class TestSlotClassification:
    """Tests for contextual fashion slot classification."""

    def test_tops_for_leggings_classified_as_top(self) -> None:
        """'Tunic Tops for Leggings' must be classified as top, not bottom."""
        title = "Womens Halloween Tunic Tops for Leggings Short Sleeve Blouse"
        slot, conf, _ = classify_fashion_slot(title)
        assert slot == "top"
        assert conf == "high"

    def test_footwear_classification(self) -> None:
        """Paris Hilton Footwear and running shoes are classified as footwear."""
        slot1, conf1, _ = classify_fashion_slot(
            "Paris Hilton Footwear - Reese - Black Seashell Suede"
        )
        assert slot1 == "footwear"
        assert conf1 == "high"

        slot2, conf2, _ = classify_fashion_slot("Nike Men's Air Zoom Pegasus Running Shoes")
        assert slot2 == "footwear"
        assert conf2 == "high"

    def test_compound_dress_keywords(self) -> None:
        """Dress shirt is top, dress pants is bottom, dress shoes is footwear."""
        assert classify_fashion_slot("Van Heusen Men's Dress Shirt")[0] == "top"
        assert classify_fashion_slot("Kenneth Cole REACTION Men's Dress Pants")[0] == "bottom"
        assert classify_fashion_slot("Calvin Klein Men's Leather Dress Shoes")[0] == "footwear"

    def test_unknown_slot_handling(self) -> None:
        """Ambiguous products without identifiable slot are marked unknown with low confidence."""
        slot, conf, _ = classify_fashion_slot("District mens Dm136")
        assert slot == "unknown"
        assert conf == "low"


class TestEvaluationAndQuarantine:
    """Tests for full evaluation, quality scoring, and quarantine behavior."""

    def test_valid_product_with_missing_optional_metadata_accepted(self) -> None:
        """A product without season or occasion is still accepted if slot and price are valid."""
        rec = {
            "parent_asin": "B00TEST123",
            "title": "Levi's Men's 501 Original Fit Jeans (Dark Stonewash)",
            "price": 49.99,
            "store": "Levi's",
            "description": "Classic straight leg blue denim jeans.",
            "features": ["100% Cotton", "Button fly"],
        }
        res = evaluate_record(rec)
        assert res.status == "accepted"
        assert res.slot == "bottom"
        assert res.quality_score >= 0.50
        assert res.classification_confidence == "high"

    def test_unknown_slot_moved_to_quarantine(self) -> None:
        """Products with unknown slot are triaged to 'quarantined'."""
        rec = {
            "parent_asin": "B00AMBIG01",
            "title": "Generic Unbranded Item Model 4829",
            "price": 12.50,
        }
        res = evaluate_record(rec)
        assert res.status == "quarantined"
        assert "unknown_slot" in res.rejection_reasons

    def test_non_fashion_rejected(self) -> None:
        """Non-fashion product is triaged to 'rejected'."""
        rec = {
            "parent_asin": "B00BELL001",
            "title": "ACTION BELL INCREDIBELL DUET BRASS BICYCLE BELL",
            "price": 11.98,
        }
        res = evaluate_record(rec)
        assert res.status == "rejected"
        assert any("non_fashion" in r for r in res.rejection_reasons)

    def test_image_url_failure_does_not_reject(self) -> None:
        """Missing or unavailable image does NOT reject a valid product."""
        rec = {
            "parent_asin": "B00NOIMG01",
            "title": "Calvin Klein Women's Modern Cotton Bralette",
            "price": 28.00,
            "images": [],
        }
        res = evaluate_record(rec)
        assert res.status == "accepted"
        assert res.has_valid_image is False

    def test_quality_score_computation(self) -> None:
        """Quality score is bounded between 0.0 and 1.0."""
        score = compute_explainable_quality_score(
            title="Women's Floral Summer Cocktail Party Maxi Dress",
            price=39.99,
            slot="full_body",
            confidence="high",
            store="Grace Karin",
            features=["V-Neck", "Sleeveless", "Tiered hem"],
            description="Beautiful elegant summer cocktail dress.",
            colors=["blue", "floral"],
            avg_rating=4.5,
        )
        assert 0.80 <= score <= 1.0

    def test_quarantine_manager_persistence(self, tmp_path: Path) -> None:
        """QuarantineManager persists records to SQLite and JSONL."""
        db_file = tmp_path / "test_quarantine.db"
        jsonl_file = tmp_path / "test_quarantine.jsonl"

        mgr = QuarantineManager(db_path=db_file, jsonl_path=jsonl_file)
        rec = QuarantineRecord(
            parent_asin="B00QUAR01",
            original_title="Bicycle Handlebar Bell Duet",
            price=9.99,
            predicted_slot="unknown",
            classification_confidence="low",
            status="rejected",
            reasons=["non_fashion"],
            quality_score=0.0,
        )
        mgr.record_quarantine(rec)

        assert mgr.count() == 1
        assert mgr.count("rejected") == 1
        assert mgr.count("quarantined") == 0
        assert jsonl_file.is_file()
        assert "B00QUAR01" in jsonl_file.read_text(encoding="utf-8")


class TestIndexExcludesRejectedProducts:
    """Verifies that HybridIndex strictly excludes quarantined or rejected products."""

    def test_index_excludes_deleted_products(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test_index_qc.db"
        repo = CatalogRepository(db_file)

        # 1 Accepted Product (is_deleted = 0)
        accepted_prod = Product(
            parent_asin="P_ACCEPTED",
            title="Calvin Klein Men's Classic Leather Loafers",
            price=89.99,
            slot="footwear",
            gender="men",
            age_group="adult",
            is_deleted=False,
            search_text="Calvin Klein Men's Classic Leather Loafers. Type: footwear.",
        )
        # 1 Quarantined/Rejected Product (is_deleted = 1)
        rejected_prod = Product(
            parent_asin="P_REJECTED",
            title="ACTION BELL INCREDIBELL DUET BRASS",
            price=11.98,
            slot="unknown",
            gender="unknown",
            age_group="adult",
            is_deleted=True,
            search_text="ACTION BELL INCREDIBELL DUET BRASS.",
        )

        repo.upsert_product(accepted_prod)
        repo.upsert_product(rejected_prod)
        repo.soft_delete(rejected_prod.parent_asin)

        # Catalog repo should return only active (non-deleted) items
        active = repo.get_all_active()
        assert len(active) == 1
        assert active[0].parent_asin == "P_ACCEPTED"

        # HybridIndex built from catalog
        hybrid_index = HybridIndex(
            catalog_repo=repo,
            embedder=FakeEmbedder(),
            cache_dir=tmp_path,
        )
        hybrid_index.build_from_catalog()

        assert hybrid_index.size() == 1
        # Searching should only match the accepted product
        results, _ = hybrid_index.search(raw_query="shoes", retrieval_k=10)
        result_ids = [r[0] for r in results]
        assert "P_ACCEPTED" in result_ids
        assert "P_REJECTED" not in result_ids
