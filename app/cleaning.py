"""Text cleaning utilities and search_text builder."""

import re
from typing import Any

# Regex for unhelpful symbols in Amazon descriptions
SYMBOL_PATTERN = re.compile(r"[✔➤★◆●■▲▼☆✓\u2700-\u27bf\ue000-\uf8ff\ufffd]")

# Regex for splitting run-together words/sentences at lowercase-uppercase boundary
RUN_TOGETHER_PATTERN = re.compile(r"([a-z0-9])([A-Z])")

# Common size tokens to remove from title copy used for embeddings
SIZE_TOKEN_PATTERN = re.compile(
    r"(?<!['\w])\b(?:size\s+\d+(?:[-/]\d+)?|"
    r"\d+\s*-\s*\d+\s*(?:years?|y|m|months?)?|"
    r"x{0,4}[sml]|small|medium|large|x-large|xx-large|"
    r"one\s+size|plus\s+size)\b(?!['\w])",
    re.IGNORECASE,
)


def clean_text(text: str) -> str:
    """Clean text by removing decorative symbols, fixing run-together sentences, and whitespace.

    Args:
        text: Raw text string.

    Returns:
        Cleaned text string.
    """
    if not text:
        return ""

    # Replace decorative symbols with space
    cleaned = SYMBOL_PATTERN.sub(" ", text)

    # Split run-together sentences: e.g. "beachComfortable" -> "beach. Comfortable"
    cleaned = RUN_TOGETHER_PATTERN.sub(r"\1. \2", cleaned)

    # Collapse repeated whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    return cleaned


def strip_size_tokens(title: str) -> str:
    """Remove size tokens from the title copy used for embedding generation.

    The original title remains unmodified for display purposes.

    Args:
        title: Original product title.

    Returns:
        Title with size tokens stripped and clean whitespace.
    """
    if not title:
        return ""

    # Strip size tokens
    stripped = SIZE_TOKEN_PATTERN.sub("", title)

    # Clean dangling commas inside brackets/parentheses, e.g. "(Blue, )" -> "(Blue)"
    stripped = re.sub(r",\s*\)", ")", stripped)
    stripped = re.sub(r"\(\s*,", "(", stripped)
    stripped = re.sub(r",\s*\]", "]", stripped)
    stripped = re.sub(r"\[\s*,", "[", stripped)

    # Clean up empty or broken parenthetical remnants: e.g. "()", "(, )"
    stripped = re.sub(r"\(\s*[,;\s]*\)", "", stripped)
    stripped = re.sub(r"\[\s*[,;\s]*\]", "", stripped)

    # Clean punctuation and whitespace
    stripped = re.sub(r"\s*,\s*,+", ",", stripped)
    stripped = re.sub(r"\s+", " ", stripped).strip()

    return stripped


def extract_main_image(images: list[dict[str, Any]] | None) -> str | None:
    """Extract MAIN large image URL for display according to spec.

    Args:
        images: List of image dictionaries from Amazon metadata.

    Returns:
        Large image URL string if available, else None.
    """
    if not images:
        return None

    # Check for MAIN variant first
    for img in images:
        if isinstance(img, dict) and img.get("variant") == "MAIN":
            large_url = img.get("large") or img.get("hi_res") or img.get("thumb")
            if large_url:
                return str(large_url)

    # Fallback to the first available image large URL
    for img in images:
        if isinstance(img, dict):
            large_url = img.get("large") or img.get("hi_res") or img.get("thumb")
            if large_url:
                return str(large_url)

    return None


def _ensure_trailing_period(text: str) -> str:
    """Ensure a sentence fragment terminates with punctuation."""
    t = text.strip()
    if not t:
        return ""
    return t if t.endswith((".", "!", "?")) else f"{t}."


def build_search_text(
    title: str,
    store: str | None,
    gender: str,
    age_group: str,
    slot: str,
    features: list[str] | None = None,
    description: str | list[str] | None = None,
    review_snippets: list[str] | None = None,
) -> str:
    """Build unified search_text representation for BM25 and embedding indexing.

    Format:
    `{title without size tokens}. Brand: {store}. For: {gender}, {age_group}.
     Type: {slot}. {features[:3] joined}. {cleaned description[:400]}. Reviews: {reviews}.`

    Args:
        title: Product title.
        store: Brand/Store name.
        gender: Gender classification.
        age_group: Age group classification.
        slot: Slot classification.
        features: Optional list of features.
        description: Optional description string or list.
        review_snippets: Optional list of review snippets.

    Returns:
        Search text string optimized for semantic retrieval.
    """
    clean_title = clean_text(strip_size_tokens(title))
    brand_text = clean_text(store) if store else "Unknown"

    parts: list[str] = [
        _ensure_trailing_period(clean_title),
        f"Brand: {brand_text}.",
        f"For: {gender}, {age_group}.",
        f"Type: {slot}.",
    ]

    # Features (up to 3)
    if features:
        feat_clean = [_ensure_trailing_period(clean_text(f)) for f in features[:3] if clean_text(f)]
        if feat_clean:
            parts.append(" ".join(feat_clean))

    # Description (up to 400 chars after cleaning)
    if description:
        desc_raw = " ".join(description) if isinstance(description, list) else str(description)
        desc_clean = clean_text(desc_raw)[:400].strip()
        if desc_clean:
            parts.append(_ensure_trailing_period(desc_clean))

    # Reviews
    if review_snippets:
        rev_clean = [
            _ensure_trailing_period(clean_text(r)) for r in review_snippets if clean_text(r)
        ]
        if rev_clean:
            parts.append("Reviews: " + " ".join(rev_clean))

    full_text = " ".join(p for p in parts if p)
    full_text = re.sub(r"\.+", ".", full_text)
    return re.sub(r"\s+", " ", full_text).strip()
