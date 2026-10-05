"""Quality regression test suite covering Phase 12 specified test cases:
1. 'red cocktail dress'
2. 'black shoes for women'
3. 'winter jacket for men'
4. 'women\'s party outfit under $100'
5. 'casual outfit for college'
6. 'tops for leggings'
7. 'dinner date outfit'
8. 'red dress below 50 dollars'
"""

import pytest

from app.parser import QueryParser


@pytest.fixture(scope="module")
def parser() -> QueryParser:
    return QueryParser(llm_client=None)


class TestQueryParsingRegression:
    """Verifies that the layered parser correctly identifies key attributes and slots."""

    def test_red_cocktail_dress(self, parser: QueryParser) -> None:
        pq, _ = parser.parse("red cocktail dress")
        assert "red" in pq.colors
        assert pq.slots == ["full_body"] or "full_body" in pq.slots

    def test_black_shoes_for_women(self, parser: QueryParser) -> None:
        pq, _ = parser.parse("black shoes for women")
        assert "black" in pq.colors
        assert pq.gender == "women"
        assert pq.slots == ["footwear"] or "footwear" in pq.slots

    def test_winter_jacket_for_men(self, parser: QueryParser) -> None:
        pq, _ = parser.parse("winter jacket for men")
        assert pq.gender == "men"
        assert pq.slots == ["top"] or "top" in pq.slots
        assert pq.season == "winter"

    def test_womens_party_outfit_under_100(self, parser: QueryParser) -> None:
        pq, _ = parser.parse("women's party outfit under $100")
        assert pq.gender == "women"
        assert pq.max_price == 100.0
        assert pq.occasion == "party"

    def test_casual_outfit_for_college(self, parser: QueryParser) -> None:
        pq, _ = parser.parse("casual outfit for college")
        assert pq.occasion in ["casual", "college"]

    def test_tops_for_leggings(self, parser: QueryParser) -> None:
        pq, _ = parser.parse("tops for leggings")
        # Critical regression: "tops for leggings" must be parsed as TOP, not bottom
        assert pq.slots == ["top"]

    def test_dinner_date_outfit(self, parser: QueryParser) -> None:
        pq, _ = parser.parse("dinner date outfit")
        assert pq.occasion in ["date", "dinner", "party"]

    def test_red_dress_below_50_dollars(self, parser: QueryParser) -> None:
        pq, _ = parser.parse("red dress below 50 dollars")
        assert "red" in pq.colors
        assert pq.slots == ["full_body"] or "full_body" in pq.slots
        assert pq.max_price == 50.0
