"""Pure functional filtering and soft ranking boosts for fashion search candidates."""

from typing import Any

from app.config import settings
from app.parser import ParsedQuery
from app.schemas import Product


def passes_strict_filters(
    product: Product,
    parsed: ParsedQuery,
    gender_include_unknown: bool = False,
) -> bool:
    """Check if a product satisfies all strict hard constraints.

    Args:
        product: Candidate product domain entity.
        parsed: Structured constraints parsed from query.
        gender_include_unknown: If True, keep products with unknown gender even when
            a gender filter is active. Defaults to False.

    Returns:
        True if all constraints are met; False otherwise.
    """
    if product.is_deleted:
        return False

    # 1. Price Bounds
    if parsed.max_price is not None and (product.price is None or product.price > parsed.max_price):
        return False

    if parsed.min_price is not None and (product.price is None or product.price < parsed.min_price):
        return False

    # 2. Gender Constraint
    if parsed.gender is not None:
        target = parsed.gender
        p_gender = (product.gender or "unknown").lower()

        if target == "men":
            if p_gender not in {"men", "unisex"} and not (
                gender_include_unknown and p_gender == "unknown"
            ):
                return False
        elif target == "women":
            if p_gender not in {"women", "unisex"} and not (
                gender_include_unknown and p_gender == "unknown"
            ):
                return False
        elif (
            target == "unisex"
            and p_gender != "unisex"
            and not (gender_include_unknown and p_gender == "unknown")
        ):
            return False

    # 3. Age Group Constraint
    if parsed.age_group:
        p_age = (product.age_group or "adult").lower()
        if p_age != parsed.age_group.lower():
            return False

    # 4. Explicit Slot Constraints
    if parsed.slots:
        allowed_slots = {s.lower() for s in parsed.slots}
        p_slot = (product.slot or "unknown").lower()
        if p_slot not in allowed_slots:
            return False

    return True


def compute_soft_boost(
    product: Product,
    parsed: ParsedQuery,
    boost_weight_season: float = settings.boost_weight_season,
    boost_weight_occasion: float = settings.boost_weight_occasion,
    boost_weight_color: float = settings.boost_weight_color,
) -> float:
    """Compute additive soft boost based on season, occasion, and color matches.

    Args:
        product: Product entity.
        parsed: Structured query constraints.
        boost_weight_season: Weight for matching season.
        boost_weight_occasion: Weight for matching occasion.
        boost_weight_color: Weight for matching color.

    Returns:
        Total additive boost score.
    """
    boost = 0.0

    # Season boost
    if (
        parsed.season
        and product.seasons
        and parsed.season.lower() in [s.lower() for s in product.seasons]
    ):
        boost += boost_weight_season

    # Occasion boost
    if (
        parsed.occasion
        and product.occasions
        and parsed.occasion.lower() in [o.lower() for o in product.occasions]
    ):
        boost += boost_weight_occasion

    # Color boost
    if parsed.colors and product.colors:
        p_colors = {c.lower() for c in product.colors}
        for q_color in parsed.colors:
            if q_color.lower() in p_colors:
                boost += boost_weight_color
                break

    return boost


def apply_candidate_filters(
    candidates: list[tuple[Product, float, float]],
    parsed: ParsedQuery,
    gender_include_unknown: bool = settings.gender_include_unknown,
) -> tuple[list[tuple[Product, float, float]], int, dict[str, Any]]:
    """Filter candidates and apply soft ranking boosts.

    Args:
        candidates: List of (Product, fused_score, cosine_similarity) tuples.
        parsed: Structured query constraints.
        gender_include_unknown: Whether to allow unknown gender products under gender filter.

    Returns:
        Tuple of (surviving_candidates_with_boosted_scores, excluded_count, parsed_filters_dict).
    """
    survivors: list[tuple[Product, float, float]] = []
    excluded_count = 0

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

    for product, fused_score, similarity in candidates:
        if passes_strict_filters(product, parsed, gender_include_unknown=gender_include_unknown):
            boost = compute_soft_boost(product, parsed)
            adjusted_score = fused_score + boost
            survivors.append((product, adjusted_score, similarity))
        else:
            excluded_count += 1

    # Re-sort survivors by adjusted fused score descending
    survivors.sort(key=lambda item: item[1], reverse=True)

    return survivors, excluded_count, applied_filters
