"""Pure functional filtering, soft ranking boosts, near-duplicate collapse, and explanations."""

import re
from typing import Any

from app.attribute_correction import (
    get_effective_age_group,
    get_effective_gender,
    get_effective_product_slots,
)
from app.attributes import COLOR_SYNONYMS
from app.config import settings
from app.parser import ParsedQuery
from app.schemas import Product


def passes_strict_filters(
    product: Product,
    parsed: ParsedQuery,
    gender_include_unknown: bool = False,
) -> bool:
    """Check if a product satisfies all strict hard constraints.

    Uses contextual attribute interpretation to handle slot collisions (e.g. pajamas shorts)
    and demographic false positives (e.g. CPR mask, Sweet 16 sash) while preserving
    stored baseline attributes.

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

    # 2. Gender Constraint (strictly enforced when explicitly requested by user)
    if parsed.gender is not None and getattr(parsed, "is_explicit_gender", True):
        target = parsed.gender
        p_gender = get_effective_gender(product)

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

    # 3. Age Group Constraint (using effective age group)
    if parsed.age_group:
        p_age = get_effective_age_group(product)
        if p_age != parsed.age_group.lower():
            return False

    # 4. Explicit Slot Constraints (strictly enforced when explicitly requested by user)
    if parsed.slots and getattr(parsed, "is_explicit_slot", True):
        allowed_slots = {s.lower() for s in parsed.slots}
        effective_slots = get_effective_product_slots(product)
        if not effective_slots.intersection(allowed_slots):
            return False

    return True


def is_innerwear_allowed(raw_query: str, parsed: ParsedQuery) -> bool:
    """Check if innerwear category is explicitly requested by query (B2).

    Args:
        raw_query: Raw search query text.
        parsed: Structured parsed query.

    Returns:
        True if innerwear was requested, False otherwise.
    """
    if parsed.slots and "innerwear" in [s.lower() for s in parsed.slots]:
        return True

    text_to_check = f"{raw_query} {parsed.normalized_query_en}".lower()
    for kw in settings.innerwear_keywords:
        if re.search(rf"\b{re.escape(kw)}\b", text_to_check):
            return True
    return False


def compute_soft_boost(
    product: Product,
    parsed: ParsedQuery,
    quality_norm: float = 0.0,
    quality_weight: float = settings.quality_weight,
    boost_weight_season: float = settings.boost_weight_season,
    boost_weight_occasion: float = settings.boost_weight_occasion,
    boost_weight_color: float = settings.boost_weight_color,
    boost_weight_brand: float = settings.boost_weight_brand,
) -> float:
    """Compute additive soft boost on normalized scale (B1).

    Args:
        product: Product entity.
        parsed: Structured query constraints.
        quality_norm: Min-max normalized Bayesian quality score [0, 1].
        quality_weight: Weight for quality boost.
        boost_weight_season: Weight for matching season.
        boost_weight_occasion: Weight for matching occasion.
        boost_weight_color: Weight for matching color.
        boost_weight_brand: Weight for matching brand.

    Returns:
        Total additive boost score.
    """
    boost = 0.0

    # Bayesian quality boost
    if quality_weight > 0.0:
        boost += quality_weight * quality_norm

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

    # Brand boost (A1c & B1)
    if parsed.brand:
        b_target = parsed.brand.strip().lower()
        store_lower = (product.store or "").strip().lower()
        title_lower = product.title.strip().lower()

        # Prioritize store match or title match starting with brand
        if store_lower.startswith(b_target) or title_lower.startswith(b_target):
            boost += boost_weight_brand
        elif re.search(rf"\b{re.escape(b_target)}\b", store_lower) or re.search(
            rf"\b{re.escape(b_target)}\b", title_lower
        ):
            boost += boost_weight_brand * 0.8

    return boost


def build_dedup_key(product: Product) -> str:
    """Generate near-duplicate deduplication key for a product (B3).

    Key = lowercase title with size tokens, parenthetical groups, and color words removed,
    plus brand. Pack-size differences (e.g. 'Pack of 5' vs 'Pack of 3') are preserved.

    Args:
        product: Product instance.

    Returns:
        Deduplication key string.
    """
    text = product.title.lower()

    # 1. Remove parenthetical expressions
    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(r"\[[^]]*\]", " ", text)

    # 2. Preserve pack phrases by replacing them with placeholder tokens
    pack_matches = re.findall(
        r"\b(?:\d+\s*-\s*pack|\d+\s*pack|pack\s+of\s+\d+|\d+\s*pairs?)\b", text
    )
    pack_str = " ".join(pack_matches)

    # 3. Remove size specifications
    size_regex = (
        r"\b(?:small|medium|large|x-large|xx-large|xxx-large|1x|2x|3x|4x|5x|"
        r"xs|xxs|s|m|l|xl|xxl|xxxl|size\s*[\d\.\-\/]+)\b"
    )
    text = re.sub(size_regex, " ", text)

    # 4. Remove color words
    for color_name in COLOR_SYNONYMS:
        text = re.sub(rf"\b{re.escape(color_name)}\b", " ", text)

    # 5. Clean whitespace and tokens
    clean_tokens = [w for w in re.findall(r"\w+", text) if len(w) > 1]
    base_title = " ".join(clean_tokens)

    brand_str = (product.store or "").strip().lower()
    return f"{brand_str}::{base_title}::{pack_str}"


def collapse_near_duplicates(
    candidates: list[tuple[Product, float, float]],
) -> tuple[list[tuple[Product, float, float]], int]:
    """Collapse near-duplicate items, keeping the highest-scoring item per dedup key (B3).

    Args:
        candidates: List of (Product, adjusted_score, similarity) sorted descending.

    Returns:
        Tuple of (deduped_candidates, collapsed_count).
    """
    seen_keys: set[str] = set()
    deduped: list[tuple[Product, float, float]] = []
    collapsed_count = 0

    for product, score, sim in candidates:
        key = build_dedup_key(product)
        if key in seen_keys:
            collapsed_count += 1
            continue
        seen_keys.add(key)
        deduped.append((product, score, sim))

    return deduped, collapsed_count


def generate_item_explanation(
    product: Product,
    parsed: ParsedQuery,
    raw_query: str,
    similarity: float,
    slot_role: str | None = None,
) -> str:
    """Build deterministic, fact-based explanation for why an item was recommended (B5).

    Only uses facts present in the product metadata and query.

    Args:
        product: Product domain entity.
        parsed: Parsed query.
        raw_query: User query text.
        similarity: Cosine similarity score.
        slot_role: Slot role if in outfit mode (e.g. 'top', 'bottom').

    Returns:
        Deterministic explanation string.
    """
    facts: list[str] = []

    # Slot role
    if slot_role:
        facts.append(f"Chosen as {slot_role}")

    # Brand match
    if parsed.brand and product.store and parsed.brand.lower() in product.store.lower():
        facts.append(f"Matches brand {product.store}")
    elif parsed.brand and parsed.brand.lower() in product.title.lower():
        facts.append(f"Features brand {parsed.brand}")

    # Color match
    if parsed.colors and product.colors:
        matching_colors = [
            c for c in parsed.colors if c.lower() in [pc.lower() for pc in product.colors]
        ]
        if matching_colors:
            facts.append(f"Matching color: {', '.join(matching_colors)}")

    # Season match
    if (
        parsed.season
        and product.seasons
        and parsed.season.lower() in [s.lower() for s in product.seasons]
    ):
        facts.append(f"Suited for {parsed.season}")

    # Occasion match
    if (
        parsed.occasion
        and product.occasions
        and parsed.occasion.lower() in [o.lower() for o in product.occasions]
    ):
        facts.append(f"Ideal for {parsed.occasion}")

    # Query terms found in title
    q_words = [w.lower() for w in re.findall(r"\w{4,}", raw_query)]
    matched_words = [w for w in q_words if w in product.title.lower()]
    if matched_words and not facts:
        facts.append(f"Matched keyword: {matched_words[0]}")

    if not facts:
        facts.append("High semantic relevance to query")

    return " | ".join(facts)


def apply_candidate_filters(
    candidates: list[tuple[Product, float, float]],
    parsed: ParsedQuery,
    gender_include_unknown: bool = settings.gender_include_unknown,
) -> tuple[list[tuple[Product, float, float]], int, dict[str, Any]]:
    """Filter candidates, normalize scores, and apply soft ranking boosts.

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

    max_fused = max((c[1] for c in candidates), default=1.0)
    if max_fused <= 0:
        max_fused = 1.0

    for product, fused_score, similarity in candidates:
        if passes_strict_filters(product, parsed, gender_include_unknown=gender_include_unknown):
            norm_fused = fused_score / max_fused
            boost = compute_soft_boost(product, parsed)
            adjusted_score = norm_fused + boost
            survivors.append((product, adjusted_score, similarity))
        else:
            excluded_count += 1

    survivors.sort(key=lambda item: item[1], reverse=True)
    return survivors, excluded_count, applied_filters
