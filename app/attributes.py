"""Attribute derivation rules for fashion products.

Extracts gender, age_group, slot, accessory_type, colors, seasons, occasions,
and computes Bayesian quality scores from product metadata.
"""

import re
from typing import Any

# Color vocabulary for extraction
COLOR_VOCABULARY = [
    "black",
    "white",
    "blue",
    "red",
    "green",
    "yellow",
    "pink",
    "purple",
    "orange",
    "brown",
    "grey",
    "gray",
    "beige",
    "navy",
    "khaki",
    "gold",
    "silver",
    "teal",
    "maroon",
    "olive",
    "burgundy",
    "cream",
    "tan",
    "coral",
    "mint",
    "turquoise",
    "floral",
]

COLOR_SYNONYMS: dict[str, str] = {
    "flower": "floral",
    "flowers": "floral",
    "grey": "gray",
}

# Non-fashion pattern for ingestion filter (A3)
NON_FASHION_PATTERN = re.compile(
    r"\b(?:plush|stuffed\s+animals?|toys?|figurines?|"
    r"waterproofing\s+spray|shoe\s+polish|nail\s+polish|shampoos?|"
    r"lotions?|perfumes?|pheromones?|colognes?|pomades?)\b",
    re.IGNORECASE,
)

# Regex patterns for age group
STRONG_KIDS_PATTERN = re.compile(
    r"\b(?:toddler|toddlers|baby|babies|infant|infants|newborn|newborns|children'?s?|child)\b|"
    r"\b\d+\s*-\s*\d+\s*(?:years?|yrs?|months?|mo)\b|"
    r"\b\d+[tT]\b|"
    r"\b(?:little|baby|toddler|young)\s+(?:girls?|boys?)\b|"
    r"\b(?:big\s+kids?|little\s+kids?)\b",
    re.IGNORECASE,
)

GENERAL_KIDS_PATTERN = re.compile(
    r"\b(?:girls?'?s?|boys?'?s?|kids?|youth|children'?s?|child)\b",
    re.IGNORECASE,
)

ADULT_PATTERN = re.compile(
    r"\b(?:women'?s?|men'?s?|adults?|ladies|womens?|mens?)\b",
    re.IGNORECASE,
)

SHARED_MARKETING_PATTERN = re.compile(
    r"\b(?:women\s*(?:and|&)?\s*girls?|womens?\s*girls?|men\s*(?:and|&)?\s*boys?|mens?\s*boys?|"
    r"for\s+women\s*,?\s*girls?|adult\s*kids?|kids?\s*(?:and|&)\s*adults?)\b",
    re.IGNORECASE,
)

WATCH_BAND_PATTERN = re.compile(
    r"\b(?:apple\s+watch|wristband|watch\s+band)\b",
    re.IGNORECASE,
)

# Regex patterns for slot keywords in ordered priority (A2)
SLOT_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "footwear",
        re.compile(
            r"\b(?:sandal|sandals|shoe|shoes|sneaker|sneakers|boot|boots|gumboot|gumboots|"
            r"slipper|slippers|flip[- ]flops?|loafer|loafers|clog|clogs|heel|heels|"
            r"ballet\s+flats?|flat\s+(?:shoes?|sandals?|boots?|heels?)|flats|thong\s+sandals?|"
            r"dress\s+(?:shoes?|boots?)|insole|insoles)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "full_body",
        re.compile(
            r"(?:\bdress(?:es)?\b(?!\s+(?:shirt|shirts|pants|shoes?|boots?|socks?|belts?|buckles?|watch(?:es)?|cloak\s+pin))|"
            r"\bcostumes?\b(?!\s+(?:fashion\s+)?(?:jewelry|jewellery|ring|rings|necklace|necklaces|earrings?|bracelets?|brooch|chain|pins?|mask|accessories|accessory))|"
            r"\b(?:jumpsuit|jumpsuits|romper|rompers|swimsuit|swimsuits|one[- ]piece|overalls?|"
            r"coveralls?|onesie|onesies|pajamas?|pyjamas?|pjs|nightgown|nightgowns|sleepwear|loungewear|"
            r"tracksuit|tracksuits|sweatsuit|sweatsuits|pant\s*suit|pantsuit|coat\s+dress\s+set|"
            r"(?:ski|snow)\b.*\b(?:jacket\s+and\s+pants|suit|set)|jacket\s+and\s+pants|"
            r"2[- ]piece\s+.*(?:pjs|pajamas|set|outfit))\b)",
            re.IGNORECASE,
        ),
    ),
    (
        "bottom",
        re.compile(
            r"\b(?:pants?|shorts?(?!\s*[- ]?sleeves?)|jeans|skirt|skirts|leggings?|jeggings?|"
            r"tights|trousers?|capris?|joggers?|swim\s+trunks|dress\s+pants?|breech(?:es)?|jods|"
            r"bikini\s+bottom)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "innerwear",
        re.compile(
            r"\b(?:bras?|bralettes?|panties|panty|briefs|boxers?|boxer\s+briefs|underwear|"
            r"shapewear|jock(?:strap)?|thong(?!\s+sandals?))\b",
            re.IGNORECASE,
        ),
    ),
    (
        "top",
        re.compile(
            r"\b(?:shirt|shirts|t[- ]shirt|t[- ]shirts|tee|tees|top|tops|blouse|blouses|"
            r"tank|tanks|sweater|sweaters|hoodie|hoodies|jacket|jackets|coat|coats|"
            r"cardigan|cardigans|polo|polos|undershirt|undershirts|pullover|pullovers|"
            r"sweatshirt|sweatshirts|vest|vests|henley|henleys|quarter[- ]zip|quarter[- ]zips|"
            r"1/4[- ]zip|1/4[- ]zips|camisole|camisoles|bodysuit|bodysuits|jersey|jerseys|"
            r"dress\s+shirts?)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "accessory",
        re.compile(
            r"\b(?:socks?|sleeves?|hat|hats|caps?|sunglasses|belt|belts|buckle|buckles|scarf|scarves|"
            r"bag|bags|purse|totes?|crossbody|backpack|backpacks|wallet|wallets|phone\s+case|"
            r"earrings?|necklace|necklaces|locket|lockets|watch|watches|chronographs?|gloves?|"
            r"bracelet|bracelets|wristbands?|rings?|charm|charms|pendant|pendants|chain|chains|"
            r"keychain|keychains|key\s+chain|key\s+chains|brooch|brooches|anklet|anklets|cufflinks?|"
            r"hair\s+clip|hair\s+clips|headband|headbands|jewelry|jewellery|mask|masks|neckties?|"
            r"neck\s+tie|bow\s+ties?|\btie\b(?!\s*[- ]?dye)|suspenders?|bandanas?|"
            r"goggles?|shoelaces?|"
            r"tiaras?|crowns?|patch(?:es)?|lapel\s+pins?|piercings?|nose\s+bones?|barbells?|"
            r"rosar(?:y|ies)|reading\s+glasses|glasses|lanyards?|scapulars?|plugs?|tunnels?|"
            r"earlets|gauges?|optical\s+frame|eyeglasses|"
            r"dress\s+(?:belts?|buckles?|watch(?:es)?|socks?))\b",
            re.IGNORECASE,
        ),
    ),
    (
        "accessory",
        re.compile(
            r"\b(?:pins?)\b",
            re.IGNORECASE,
        ),
    ),
]

# Patterns for accessory_type classification (A4)
ACCESSORY_TYPE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "eyewear",
        re.compile(
            r"\b(?:sunglasses|eyeglasses|glasses|optical\s+frame|goggles|reading\s+glasses|eyewear|shades)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "bag",
        re.compile(
            r"\b(?:purse|totes?|crossbody|backpacks?|wallets?|handbags?|satchels?|clutch(?:es)?|duffels?|bags?|phone\s+case)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "hat",
        re.compile(
            r"\b(?:hats?|caps?|beanies?|snapbacks?|visors?|berets?|fedoras?|tiaras?|crowns?)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "scarf",
        re.compile(
            r"\b(?:scarf|scarves|shawls?|bandanas?|keffiyehs?)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "belt",
        re.compile(
            r"\b(?:belts?|buckles?|suspenders?)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "watch",
        re.compile(
            r"\b(?:watch(?:es)?|chronographs?|wristbands?|watch\s+band)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "socks",
        re.compile(
            r"\b(?:socks?|shoelaces?)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "gloves",
        re.compile(
            r"\b(?:gloves?|mittens?)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "body_jewelry",
        re.compile(
            r"\b(?:plugs?|tunnels?|gauges?|nose\s+bones?|barbells?|piercings?|belly\s+plug|earlets)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "hair",
        re.compile(
            r"\b(?:hair\s+clips?|headbands?|scrunchies?|hair\s+accessories)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "jewelry",
        re.compile(
            r"\b(?:necklaces?|rings?|bracelets?|earrings?|pendants?|chains?|brooches?|lockets?|"
            r"anklets?|cufflinks?|rosar(?:y|ies)|scapulars?|jewelry|jewellery|pins?|lapel\s+pins?|"
            r"neckties?|bow\s+ties?|ties?|patches?)\b",
            re.IGNORECASE,
        ),
    ),
]

# Regex patterns for seasons
SEASON_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "summer",
        re.compile(
            r"\b(?:summer|beach|swim|sandal|tank|shorts|lightweight)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "winter",
        re.compile(
            r"\b(?:winter|fleece|thermal|wool|insulated|parka)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "spring",
        re.compile(
            r"\b(?:spring|breeze|pastel|floral)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "fall",
        re.compile(
            r"\b(?:fall|autumn|flannel|trench)\b",
            re.IGNORECASE,
        ),
    ),
]

# Regex patterns for occasions
OCCASION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "beach",
        re.compile(
            r"\b(?:beach|swim|thong|flip[- ]flop)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "workout",
        re.compile(
            r"\b(?:compression|athletic|running|workout|yoga)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "formal",
        re.compile(
            r"\b(?:dress\s+shirt|blazer|formal|tuxedo|suit)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "casual",
        re.compile(
            r"\b(?:casual|everyday|loungewear|lounge)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "party",
        re.compile(
            r"\b(?:party|cocktail|evening)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "travel",
        re.compile(
            r"\b(?:travel|packable)\b",
            re.IGNORECASE,
        ),
    ),
]


def derive_gender(details: dict[str, Any] | None = None, title: str = "") -> str:
    """Derive gender target from details department first, then title regex.

    Args:
        details: Product details dictionary (e.g. {"Department": "womens"}).
        title: Raw product title.

    Returns:
        One of 'men', 'women', 'unisex', or 'unknown'.
    """
    if details:
        dept = str(details.get("Department", "")).strip().lower()
        if dept:
            has_dept_men = bool(re.search(r"\b(?:men|mens|boys|boy)\b", dept))
            has_dept_women = bool(re.search(r"\b(?:women|womens|girls|girl)\b", dept))
            if "unisex" in dept or (has_dept_men and has_dept_women):
                return "unisex"
            if has_dept_women:
                return "women"
            if has_dept_men:
                return "men"

    # Title fallback
    title_lower = title.lower()
    has_men = bool(re.search(r"\b(?:men'?s?|mens|boys?'?s?)\b", title_lower))
    has_women = bool(re.search(r"\b(?:women'?s?|womens|girls?'?s?)\b", title_lower))
    has_unisex = bool(re.search(r"\bunisex\b", title_lower))

    if has_unisex or (has_men and has_women):
        return "unisex"
    if has_women:
        return "women"
    if has_men:
        return "men"

    return "unknown"


def derive_age_group(title: str) -> str:
    """Derive age group from product title.

    Args:
        title: Raw product title.

    Returns:
        'kids' if matching child/youth patterns, otherwise 'adult'.
    """
    if not title:
        return "adult"

    # 1. Explicit / strong kids patterns always resolve to kids
    if STRONG_KIDS_PATTERN.search(title):
        return "kids"

    # 2. Watch band / accessory sports themes without strong kids keywords resolve to adult
    if WATCH_BAND_PATTERN.search(title):
        return "adult"

    # 3. If adult context is explicitly present
    has_adult = bool(ADULT_PATTERN.search(title))
    has_shared = bool(SHARED_MARKETING_PATTERN.search(title))

    if has_shared or has_adult:
        return "adult"

    # 4. General kids keywords when no adult keywords are present
    if GENERAL_KIDS_PATTERN.search(title):
        return "kids"

    return "adult"


def find_matching_rule(text: str) -> tuple[str, str]:
    """Find the matched slot and exact matched regex rule/pattern string for diagnostics."""
    for slot_name, pattern in SLOT_PATTERNS:
        m = pattern.search(text)
        if m:
            return slot_name, f"Rule '{slot_name}' matched keyword '{m.group(0)}'"
    return "unknown", "No slot pattern matched (fallback to unknown)"


def _match_slot_in_text(text: str) -> str | None:
    """Check text against ordered slot patterns and return first match."""
    for slot_name, pattern in SLOT_PATTERNS:
        if pattern.search(text):
            return slot_name
    return None


def derive_slot(
    title: str,
    features: list[str] | None = None,
    description: str | list[str] | None = None,
) -> str:
    """Derive fashion slot (clothing category) by checked priority order.

    Checked against title first, then features, then description.

    Args:
        title: Product title.
        features: Optional list of feature bullet points.
        description: Optional product description string or list of strings.

    Returns:
        One of 'footwear', 'full_body', 'bottom', 'top', 'innerwear', 'accessory', or 'unknown'.
    """
    # 1. Check title first
    if title:
        matched = _match_slot_in_text(title)
        if matched:
            return matched

    # 2. Check features
    if features:
        features_text = " ".join(features)
        matched = _match_slot_in_text(features_text)
        if matched:
            return matched

    # 3. Check description
    if description:
        desc_text = " ".join(description) if isinstance(description, list) else str(description)
        matched = _match_slot_in_text(desc_text)
        if matched:
            return matched

    return "unknown"


def derive_accessory_type(title: str, slot: str) -> str | None:
    """Derive fine-grained accessory_type for products in the accessory slot.

    Args:
        title: Product title text.
        slot: Derived slot category.

    Returns:
        One of 'hat', 'eyewear', 'bag', 'scarf', 'belt', 'watch', 'jewelry',
        'body_jewelry', 'hair', 'socks', 'gloves', 'other', or None if not accessory.
    """
    if slot != "accessory" or not title:
        return None

    for acc_type, pattern in ACCESSORY_TYPE_PATTERNS:
        if pattern.search(title):
            return acc_type

    return "other"


def derive_colors(title: str) -> list[str]:
    """Extract colors from title and parenthesized tokens using fixed vocabulary."""
    found_colors: list[str] = []
    title_lower = title.lower()

    # Extract parenthesized parts first
    paren_matches = re.findall(r"\((.*?)\)", title_lower)
    combined_search_text = " ".join(paren_matches) + " " + title_lower

    for synonym, canonical in COLOR_SYNONYMS.items():
        pattern = rf"\b{re.escape(synonym)}\b"
        if re.search(pattern, combined_search_text) and canonical not in found_colors:
            found_colors.append(canonical)

    for color in COLOR_VOCABULARY:
        pattern = rf"\b{re.escape(color)}\b"
        if re.search(pattern, combined_search_text) and color not in found_colors:
            found_colors.append(color)

    return found_colors


def derive_seasons(text: str) -> list[str]:
    """Derive applicable seasons using keyword rules."""
    seasons: list[str] = []
    for season_name, pattern in SEASON_PATTERNS:
        if pattern.search(text):
            seasons.append(season_name)
    return seasons


def derive_occasions(text: str) -> list[str]:
    """Derive applicable occasions using keyword rules."""
    occasions: list[str] = []
    for occasion_name, pattern in OCCASION_PATTERNS:
        if pattern.search(text):
            occasions.append(occasion_name)
    return occasions


def compute_quality_score(
    average_rating: float | None,
    rating_number: int | None,
    global_mean: float = 4.2,
    m: float = 10.0,
) -> float:
    """Compute Bayesian average rating score."""
    v = float(rating_number) if rating_number is not None and rating_number > 0 else 0.0
    r = float(average_rating) if average_rating is not None and average_rating > 0 else global_mean

    if v <= 0:
        return round(global_mean, 4)

    score = (v / (v + m)) * r + (m / (v + m)) * global_mean
    return round(score, 4)
