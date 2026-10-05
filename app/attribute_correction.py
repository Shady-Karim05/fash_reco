"""Contextual attribute interpretation and search eligibility guard layer.

Provides non-destructive, runtime contextual interpretation of product attributes
(slot collisions, demographic false positives) and deterministic search eligibility
filtering for unknown-slot peripheral products without mutating data/catalog.db or
app/attributes.py.
"""

import re

from app.parser import ParsedQuery
from app.schemas import Product

# Non-apparel / peripheral noise patterns commonly found in unknown slot
PERIPHERAL_NOISE_PATTERN = re.compile(
    r"\b(?:"
    r"vinyl\s+decals?|car\s+(?:window\s+)?decals?|bumper\s+stickers?|wall\s+stickers?|"
    r"zipper\s+pulls?|replacement\s+buttons?|ribbon\s+spools?|sewing\s+threads?|patch\s+kits?|"
    r"cpr\s+(?:training\s+)?(?:pocket\s+)?masks?|training\s+pocket\s+masks?|industrial\s+(?:eye\s+)?shields?|"
    r"face\s+shields?|tool\s+holsters?|gift\s+bags?|party\s+favor\s+bags?|favor\s+boxes?|"
    r"badge\s+holders?|lanyard\s+keychains?"
    r")\b",
    re.IGNORECASE,
)

# Explicit terms that allow matching peripheral items when user specifically requests them
PERIPHERAL_QUERY_EXEMPTIONS = re.compile(
    r"\b(?:"
    r"decal|decals|sticker|stickers|zipper\s+pull|zipper\s+pulls|replacement\s+button|"
    r"replacement\s+buttons|spool|spools|cpr|face\s+shield|holster|gift\s+bag|gift\s+bags|"
    r"charms?|shoe\s+charms?|clog\s+pins?|pins?|sash|sashes|lanyard|lanyards"
    r")\b",
    re.IGNORECASE,
)

# Patterns for slot collision detection
_PAJAMAS_SHORTS_PATTERN = re.compile(
    r"\b(?:shorts?\s+pajamas?|pajama\s+shorts?|shorts?\s+set|pjs?\s+shorts?)\b",
    re.IGNORECASE,
)

_COSTUME_JEWELRY_PATTERN = re.compile(
    r"\b(?:costume\s+jewelry|costume\s+jewellery|pendant\s+costume|costume\s+pendant)\b",
    re.IGNORECASE,
)

_CPR_PATTERN = re.compile(
    r"\b(?:cpr(?:\s+training)?|\btraining\s+pocket\s+mask)\b",
    re.IGNORECASE,
)

_SASH_PATTERN = re.compile(
    r"\b(?:sweet\s+16|16th\s+birthday|birthday\s+sash|party\s+sash)\b",
    re.IGNORECASE,
)


def get_effective_product_slots(product: Product) -> set[str]:
    """Derive effective functional clothing slots for search filtering.

    Preserves stored product.slot while contextually expanding multi-intent garments
    (e.g. pajamas shorts set) or correcting priority collisions (costume jewelry).

    Args:
        product: Domain Product entity.

    Returns:
        Set of lowercase effective slot strings.
    """
    raw_slot = (product.slot or "unknown").lower()
    title = product.title or ""

    # Slot Collision 1: "American Trends Shorts Pajamas Set"
    # Stored as full_body due to "pajamas" priority, but is also a "bottom" (shorts)
    is_pajamas_shorts = _PAJAMAS_SHORTS_PATTERN.search(title) or (
        "short" in title.lower()
        and any(p in title.lower() for p in ("pajama", "pyjama", "pjs", "loungewear"))
    )
    if is_pajamas_shorts:
        return {raw_slot, "bottom", "full_body"}

    # Slot Collision 2: "Humaira Pendant Costume Jewelry"
    # Stored as full_body due to "costume", but is an accessory/jewelry item
    if _COSTUME_JEWELRY_PATTERN.search(title) or (
        "pendant" in title.lower() and "costume" in title.lower()
    ):
        return {"accessory"}

    return {raw_slot}


def get_effective_age_group(product: Product) -> str:
    """Derive effective age group demographic for search filtering.

    Corrects superficial token collisions (e.g. 'infant CPR mask', 'Sweet 16 sash').

    Args:
        product: Domain Product entity.

    Returns:
        'adult' or 'kids'.
    """
    raw_age = (product.age_group or "adult").lower()
    title = product.title or ""

    # Demographic False Positive 1: "infant CPR training mask"
    if _CPR_PATTERN.search(title):
        return "adult"

    # Demographic False Positive 2: "Sweet 16 Birthday Sash"
    if _SASH_PATTERN.search(title):
        return "adult"

    # Shoe charms / clog pins without baby/toddler apparel sizing
    is_charm = "shoe charm" in title.lower() or "clog pin" in title.lower()
    if is_charm and not re.search(r"\b(?:toddler|infant|baby)\b", title, re.IGNORECASE):
        return "adult"

    return raw_age


def get_effective_gender(product: Product) -> str:
    """Derive effective gender demographic for search filtering."""
    raw_gender = (product.gender or "unknown").lower()
    return raw_gender


def is_search_eligible_product(
    product: Product,
    raw_query: str = "",
    parsed: ParsedQuery | None = None,
) -> bool:
    """Determine if a candidate product is eligible for search results.

    Filters out obvious non-apparel peripheral items (vinyl decals, car stickers,
    zipper pulls, CPR masks) from unconstrained fashion searches, while:
    1. Always keeping classified fashion products (slot != 'unknown').
    2. Keeping peripheral items when explicitly requested by user query.
    3. Retaining legitimate fashion items residing in 'unknown'.

    Args:
        product: Candidate product domain entity.
        raw_query: Raw user query string.
        parsed: Optional parsed query constraints.

    Returns:
        True if product should be retained; False if filtered as peripheral noise.
    """
    raw_slot = (product.slot or "unknown").lower()

    # Rule 1: Recognized fashion categories are always eligible
    if raw_slot != "unknown":
        # Check if medical equipment accidentally passed slot
        if _CPR_PATTERN.search(product.title):
            # Only allow CPR items if query explicitly asks for CPR / medical training
            q_text = f"{raw_query} {parsed.normalized_query_en if parsed else ''}"
            cpr_match = re.search(r"\b(?:cpr|first\s*aid|training\s*mask)\b", q_text, re.IGNORECASE)
            return bool(cpr_match)
        return True

    # Rule 2: Unknown slot check for peripheral noise
    title = product.title or ""
    metadata_text = f"{title} {product.search_text}"

    is_peripheral = bool(PERIPHERAL_NOISE_PATTERN.search(metadata_text))
    if not is_peripheral:
        # Rule 4: Legitimate unclassified fashion wearable in unknown slot
        return True

    # Rule 3: Query awareness exemption
    # If the user specifically searches for this peripheral item, retain it
    q_text = f"{raw_query} {parsed.normalized_query_en if parsed else ''}"
    return bool(PERIPHERAL_QUERY_EXEMPTIONS.search(q_text))
