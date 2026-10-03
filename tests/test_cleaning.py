"""Unit tests for text cleaning and search text construction."""

from app.cleaning import (
    build_search_text,
    clean_text,
    extract_main_image,
    strip_size_tokens,
)


class TestTextCleaning:
    """Tests for symbol removal and sentence boundary fixes."""

    def test_clean_text_removes_symbols(self) -> None:
        """Symbols like checkmarks, arrows, and stars are replaced with space."""
        raw = "✔ 100% Cotton ➤ Machine Washable ★ Top Rated"
        cleaned = clean_text(raw)
        assert "✔" not in cleaned
        assert "➤" not in cleaned
        assert "★" not in cleaned
        assert "100% Cotton Machine Washable Top Rated" in cleaned

    def test_clean_text_splits_run_together_sentences(self) -> None:
        """Lowercase-to-uppercase transitions are split with period and space."""
        raw = "Perfect for beachComfortable to wear all day"
        cleaned = clean_text(raw)
        assert "beach. Comfortable" in cleaned

    def test_clean_text_collapses_whitespace(self) -> None:
        """Multiple spaces and newlines are collapsed into a single space."""
        raw = "  Hello   \n\n  world \t test  "
        assert clean_text(raw) == "Hello world test"


class TestSizeTokenStripping:
    """Tests for stripping size patterns from embedding title copy."""

    def test_strip_size_from_parentheses(self) -> None:
        """Size specifications in parentheses are removed while keeping colors."""
        title = "YUEDGE 5 Pairs Men's Crew Socks (Blue, Size 9-12)"
        stripped = strip_size_tokens(title)
        assert "Size 9-12" not in stripped
        assert "Blue" in stripped

    def test_strip_alphanumeric_sizes(self) -> None:
        """XL, Large, Small size tokens are removed."""
        title = "Flowy Lounge Wide Leg Pants (Flower Mix Blue, XL)"
        stripped = strip_size_tokens(title)
        assert "XL" not in stripped
        assert "Flower Mix Blue" in stripped

    def test_strip_years_size(self) -> None:
        """Youth size indicators like 9-10 Years are stripped."""
        title = "Girls' Trapeze Dress (9-10 Years, Dark Floral Mint)"
        stripped = strip_size_tokens(title)
        assert "9-10 Years" not in stripped
        assert "Dark Floral Mint" in stripped


class TestImageExtraction:
    """Tests for extracting the MAIN large image URL."""

    def test_extract_main_large_image(self) -> None:
        """Image with variant MAIN and large URL is chosen."""
        images = [
            {"variant": "PT01", "large": "https://example.com/pt01.jpg"},
            {"variant": "MAIN", "large": "https://example.com/main_large.jpg"},
        ]
        assert extract_main_image(images) == "https://example.com/main_large.jpg"

    def test_extract_fallback_when_no_main(self) -> None:
        """First available large URL is used when MAIN variant is absent."""
        images = [
            {"variant": "PT01", "large": "https://example.com/pt01.jpg"},
        ]
        assert extract_main_image(images) == "https://example.com/pt01.jpg"

    def test_extract_empty_images(self) -> None:
        """Empty or None image list returns None."""
        assert extract_main_image([]) is None
        assert extract_main_image(None) is None


class TestSearchTextBuilder:
    """Tests for unified search_text generation."""

    def test_build_search_text_structure(self) -> None:
        """Verify full search text format matches specification."""
        text = build_search_text(
            title="Casual Summer T-Shirt (Blue, XL)",
            store="Nike",
            gender="men",
            age_group="adult",
            slot="top",
            features=["100% Organic Cotton", "Breathable mesh"],
            description="A comfortable summer tee for sports.",
            review_snippets=["Fits true to size.", "Great beach shirt."],
        )
        assert "Casual Summer T-Shirt (Blue)" in text
        assert "XL" not in text
        assert "Brand: Nike." in text
        assert "For: men, adult." in text
        assert "Type: top." in text
        assert "100% Organic Cotton" in text
        assert "A comfortable summer tee" in text
        assert "Reviews: Fits true to size. Great beach shirt." in text
