"""Shared product processing pipeline for ingestion, updates, and batch indexing."""

from typing import Any

from app.attributes import (
    NON_FASHION_PATTERN,
    compute_quality_score,
    derive_age_group,
    derive_colors,
    derive_gender,
    derive_occasions,
    derive_seasons,
    derive_slot,
)
from app.cleaning import build_search_text, extract_main_image
from app.schemas import Product, RawProductMetadata


def validate_raw_record(
    record: dict[str, Any] | RawProductMetadata,
    min_title_length: int = 15,
    require_price: bool = True,
) -> tuple[bool, str | None]:
    """Validate a raw metadata record against catalog entry criteria.

    Args:
        record: Raw metadata dictionary or model.
        min_title_length: Minimum acceptable title length in characters.
        require_price: If True, reject records without a positive float price.

    Returns:
        Tuple of (is_valid, drop_reason).
    """
    if isinstance(record, RawProductMetadata):
        title = record.title
        price = record.price
    else:
        title = record.get("title")
        price = record.get("price")

    if not title or not str(title).strip():
        return False, "no_title"

    title_str = str(title).strip()
    if len(title_str) < min_title_length:
        return False, "short_title"

    if NON_FASHION_PATTERN.search(title_str):
        return False, "non_fashion_keyword"

    if require_price:
        if price is None:
            return False, "no_price"
        try:
            p_val = float(price)
            if p_val <= 0:
                return False, "invalid_price"
        except (ValueError, TypeError):
            return False, "invalid_price"

    return True, None


def transform_raw_record(
    record: dict[str, Any] | RawProductMetadata,
    global_mean_rating: float = 4.2,
    bayesian_m: float = 10.0,
    review_snippets: list[str] | None = None,
) -> Product:
    """Transform a raw metadata record into an indexed Product entity.

    Performs attribute derivation (gender, age_group, slot, colors, seasons,
    occasions), quality score calculation, image extraction, and search text synthesis.

    Args:
        record: Raw product dictionary or model.
        global_mean_rating: Mean rating used as Bayesian prior.
        bayesian_m: Minimum rating count threshold prior weight.
        review_snippets: Optional list of review texts for context.

    Returns:
        Populated Product domain instance ready for catalog and vector indexing.
    """
    data = record.model_dump() if isinstance(record, RawProductMetadata) else dict(record)

    parent_asin = str(data.get("parent_asin", "")).strip()
    title = str(data.get("title", "")).strip()
    store = str(data.get("store", "")).strip() if data.get("store") else None

    price: float | None = None
    if data.get("price") is not None:
        try:
            price = round(float(data["price"]), 2)
        except (ValueError, TypeError):
            price = None

    avg_rating = data.get("average_rating")
    rating_num = data.get("rating_number")

    features = [str(f) for f in data.get("features") or [] if f]
    desc_val = data.get("description")
    if isinstance(desc_val, list):
        desc_text = " ".join(str(d) for d in desc_val if d)
    elif desc_val:
        desc_text = str(desc_val)
    else:
        desc_text = None

    details = data.get("details") if isinstance(data.get("details"), dict) else {}
    images = data.get("images") if isinstance(data.get("images"), list) else []

    # Derive attributes
    gender = derive_gender(details, title)
    age_group = derive_age_group(title)
    slot = derive_slot(title, features, desc_text)
    colors = derive_colors(title)

    # Combined text for seasons and occasions
    combined_texts = [title] + features
    if desc_text:
        combined_texts.append(desc_text)
    if review_snippets:
        combined_texts.extend(review_snippets)
    full_context = " ".join(combined_texts)

    seasons = derive_seasons(full_context)
    occasions = derive_occasions(full_context)

    # Bayesian quality score
    quality_score = compute_quality_score(
        avg_rating,
        rating_num,
        global_mean=global_mean_rating,
        m=bayesian_m,
    )

    # Extract display image URL
    image_url = extract_main_image(images)

    # Synthesize unified search text
    search_text = build_search_text(
        title=title,
        store=store,
        gender=gender,
        age_group=age_group,
        slot=slot,
        features=features,
        description=desc_text,
        review_snippets=review_snippets,
    )

    return Product(
        parent_asin=parent_asin,
        title=title,
        store=store,
        price=price,
        average_rating=float(avg_rating) if avg_rating is not None else None,
        rating_number=int(rating_num) if rating_num is not None else None,
        quality_score=quality_score,
        image_url=image_url,
        gender=gender,
        age_group=age_group,
        slot=slot,
        colors=colors,
        seasons=seasons,
        occasions=occasions,
        features=features,
        description=desc_text,
        review_snippets=review_snippets or [],
        search_text=search_text,
    )
