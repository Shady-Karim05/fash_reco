"""Unit tests for shared pipeline validation and transformation."""

from app.pipeline import transform_raw_record, validate_raw_record
from app.schemas import RawProductMetadata


class TestPipelineValidation:
    """Tests for raw metadata record validation."""

    def test_validate_valid_record(self) -> None:
        """Valid product with title and price passes validation."""
        valid_rec = {
            "parent_asin": "PROD_1",
            "title": "Comfortable Cotton Men's Shirt",
            "price": 24.99,
        }
        is_valid, reason = validate_raw_record(valid_rec, min_title_length=15, require_price=True)
        assert is_valid is True
        assert reason is None

    def test_validate_missing_title(self) -> None:
        """Missing title fails with 'no_title'."""
        rec = {"parent_asin": "PROD_1", "title": "", "price": 19.99}
        is_valid, reason = validate_raw_record(rec)
        assert is_valid is False
        assert reason == "no_title"

    def test_validate_short_title(self) -> None:
        """Title shorter than 15 characters fails with 'short_title'."""
        rec = {"parent_asin": "PROD_1", "title": "Short Tee", "price": 19.99}
        is_valid, reason = validate_raw_record(rec, min_title_length=15)
        assert is_valid is False
        assert reason == "short_title"

    def test_validate_missing_or_invalid_price(self) -> None:
        """Null or negative/zero price fails when require_price is True."""
        rec_null = {
            "parent_asin": "P1",
            "title": "Long Valid Product Title For Testing",
            "price": None,
        }
        is_valid, reason = validate_raw_record(rec_null, require_price=True)
        assert is_valid is False
        assert reason == "no_price"

        rec_zero = {
            "parent_asin": "P2",
            "title": "Long Valid Product Title For Testing",
            "price": 0.0,
        }
        is_valid, reason = validate_raw_record(rec_zero, require_price=True)
        assert is_valid is False
        assert reason == "invalid_price"

    def test_validate_non_fashion_keyword(self) -> None:
        """Titles with plush, stuffed animal, toy, or figurine are dropped."""
        rec_plush = {
            "parent_asin": "P_TOY",
            "title": "Line Friends Mini Plush Stuffed Animal Doll",
            "price": 14.99,
        }
        is_valid, reason = validate_raw_record(rec_plush)
        assert is_valid is False
        assert reason == "non_fashion_keyword"


class TestPipelineTransformation:
    """Tests for raw to Product model transformation."""

    def test_transform_raw_metadata_model(self) -> None:
        """RawProductMetadata model is transformed with derived attributes."""
        raw_model = RawProductMetadata(
            parent_asin="B08TEST",
            title="SunnyBreeze Women's Beach Sandals (Blue, Size 8)",
            price=29.81,
            store="SunnyBreeze",
            average_rating=4.5,
            rating_number=100,
            features=["Non-slip sole", "Waterproof"],
            description=["Great for beach vacations and pool days."],
            details={"Department": "womens"},
            images=[{"variant": "MAIN", "large": "https://example.com/sandal.jpg"}],
        )

        product = transform_raw_record(
            raw_model,
            global_mean_rating=4.2,
            review_snippets=["Super comfy beach shoes!"],
        )

        assert product.parent_asin == "B08TEST"
        assert product.slot == "footwear"
        assert product.gender == "women"
        assert product.age_group == "adult"
        assert "blue" in product.colors
        assert "summer" in product.seasons
        assert "beach" in product.occasions
        assert product.quality_score > 4.2
        assert product.image_url == "https://example.com/sandal.jpg"
        assert len(product.review_snippets) == 1
        assert "Beach Sandals (Blue)" in product.search_text
        assert "Brand: Sunny" in product.search_text
