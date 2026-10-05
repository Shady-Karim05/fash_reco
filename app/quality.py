"""Deterministic Data Cleaning & Quality Control Pipeline (QC).

Implements multi-signal validation, HTML entity normalization, price validation,
contextual fashion slot classification, fashion relevance checking, explainable
quality scoring, and three-tier triage:
1. ACCEPTED: Trusted products with confident fashion classification and complete data.
2. REVIEW / QUARANTINED: Ambiguous products, unknown slot, or low quality score.
3. REJECTED: Clearly non-fashion, corrupted, missing title/price, or unusable items.
"""

import html
import json
import logging
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.attributes import (
    derive_accessory_type,
    derive_age_group,
    derive_colors,
    derive_gender,
    derive_occasions,
    derive_seasons,
    derive_slot,
)
from app.cleaning import clean_text
from app.config import settings
from app.schemas import Product, QualityCheckResult, QuarantineRecord, RawProductMetadata

logger = logging.getLogger("fashion_search.quality")

# Regex for unhelpful symbols and decorative characters in Amazon titles
SYMBOL_PATTERN = re.compile(r"[✔➤★◆●■▲▼☆✓\u2700-\u27bf\ue000-\uf8ff\ufffd]")

# Pattern to detect repeated uninformative characters (e.g. "------", "?????", ".....")
MEANINGLESS_CHARS_PATTERN = re.compile(r"^[\W_0-9\s]+$")

# Strong fashion accessory / garment indicators that override false positives in non-fashion checks
FASHION_OVERRIDE_PATTERN = re.compile(
    r"\b(?:"
    r"watch\s+band|watch\s+strap|iwatch\s+band|apple\s+watch\s+band|"
    r"enamel\s+pin|lapel\s+pin|brooch|charm|pendant|necklace|bracelet|earrings?|"
    r"beanie|knitted\s+cap|costume|cosplay|heated\s+jacket|apron|keychain|key\s+ring|"
    r"shoe|sneaker|boot|sandal|loafer|heel|slipper|pump|flat|"
    r"shirt|tee|t-shirt|blouse|sweater|hoodie|jacket|coat|vest|top|tank|"
    r"dress|gown|romper|jumpsuit|bodysuit|pajamas?|pyjamas?|"
    r"pant|pants|jean|jeans|skirt|shorts?|leggings?|tights|trouser|"
    r"bag|handbag|purse|tote|backpack|satchel|wallet|clutch"
    r")\b",
    re.IGNORECASE,
)

# Multi-signal non-fashion detection patterns
STRONG_NON_FASHION_PATTERN = re.compile(
    r"\b(?:"
    # Electronics, mobile, computing parts
    r"usb\s+cable|phone\s+case|screen\s+protector|charger|earbuds|headphones|bluetooth\s+speaker|"
    r"camera\s+mount|stylus\s+pen|battery\s+pack|audio\s+cable|cell\s+phone\s+case|"
    # Automotive, mechanical & vehicle parts
    r"license\s+plate|car\s+seat\s+cover|steering\s+wheel\s+cover|floor\s+mat|bumper\s+sticker|"
    r"tire\s+pressure|valve\s+stem|spark\s+plug|oil\s+filter|"
    # Home improvement, plumbing, hardware & building supplies
    r"pipe\s+connector|brass\s+valve|pipe\s+fitting|pvc\s+fitting|shower\s+head|light\s+bulb|"
    r"screwdriver|wrench|drill\s+bit|door\s+knob|cabinet\s+pull|curtain\s+rod|switch\s+plate|"
    # Musical instruments & hardware
    r"guitar\s+strap|guitar\s+pick|guitar\s+cable|drum\s+stick|violin\s+bow|bell\s+incredibell|action\s+bell|"
    # Office, paper, books & paperweights
    r"paperweight|pen\s+holder|desk\s+organizer|bookmark|"
    # Raw crystals, uncut rough specimens (not jewelry settings)
    r"uncut\s+raw\s+rough|healing\s+crystal|mineral\s+specimen|geode\s+crystal|rough\s+aquamarine|"
    # Kitchenware, utensils & dining
    r"cutting\s+board|coffee\s+mug|water\s+bottle|wine\s+glass|spatula|cutlery\s+set|"
    # Pet products (non-human accessories)
    r"dog\s+collar|cat\s+harness|dog\s+leash|pet\s+carrier|dog\s+harness|"
    # Medical disposables & bulk chemicals
    r"disposable\s+blue\s+-\s*50\s+tablets|sanitizer"
    r")\b",
    re.IGNORECASE,
)

# Contextual secondary fashion slot heuristics
SECONDARY_BAG_PATTERN = re.compile(
    r"\b(?:satchel|crossbody|clutch|tote|backpack|handbag|shoulder\s+bag|wristlet|wallet|coin\s+purse|card\s+holder|duffel|messenger\s+bag)\b",
    re.IGNORECASE,
)
SECONDARY_FOOTWEAR_PATTERN = re.compile(
    r"\b(?:shoes?|sneakers?|boots?|sandals?|footwear|loafers?|heels?|slippers?|pumps?|flats?|mules?|clogs?|slides?|oxfords?|espadrilles?)\b",
    re.IGNORECASE,
)
SECONDARY_SOCKS_PATTERN = re.compile(
    r"\b(?:socks?|no[- ]shows?|booties?|stockings?|tights?|leg\s+warmers?|"
    r"crew\s+socks?|ankle\s+socks?)\b",
    re.IGNORECASE,
)
SECONDARY_FULL_BODY_PATTERN = re.compile(
    r"\b(?:gi|kimono|rashguard|singlet|swimsuit|bikini|cover[- ]up|costume|"
    r"romper|jumpsuit|bodysuit|pajamas?|pyjamas?|pjs?)\b",
    re.IGNORECASE,
)


def validate_and_clean_title(
    title: str | None, min_length: int = 10
) -> tuple[bool, str, str | None]:
    """Validate, sanitize, and normalize product title text.

    Args:
        title: Raw title string.
        min_length: Minimum acceptable title length in characters.

    Returns:
        Tuple of (is_valid, cleaned_title, failure_reason).
    """
    if not title or not str(title).strip():
        return False, "", "missing_title"

    # Decode HTML entities (e.g. &amp; -> &, &#39; -> ')
    normalized = html.unescape(str(title))

    # Strip decorative symbols and fix run-together casing
    normalized = clean_text(normalized)

    # Check for empty or purely non-alphanumeric content
    if not normalized or MEANINGLESS_CHARS_PATTERN.match(normalized):
        return False, "", "meaningless_title"

    # Count useful word tokens (at least 2 letters/digits)
    tokens = re.findall(r"\b[a-zA-Z0-9]{2,}\b", normalized)
    if len(tokens) < 2:
        return False, "", "meaningless_title"

    if len(normalized) < min_length:
        return False, normalized, "short_title"

    return True, normalized, None


def validate_price(
    price: Any, min_price: float = 0.20, max_price: float = 10000.0
) -> tuple[bool, float | None, str | None]:
    """Validate numeric product price.

    Args:
        price: Raw price input (float, int, str, or None).
        min_price: Minimum reasonable price floor.
        max_price: Maximum allowable price ceiling for outliers.

    Returns:
        Tuple of (is_valid, float_price, failure_reason).
    """
    if price is None:
        return False, None, "missing_price"

    try:
        p_float = float(price)
    except (ValueError, TypeError):
        return False, None, "invalid_price_format"

    if p_float <= 0.0:
        return False, None, "zero_or_negative_price"

    if p_float < min_price or p_float > max_price:
        return False, round(p_float, 2), "price_outlier"

    return True, round(p_float, 2), None


def check_fashion_relevance(
    title: str, description: str = "", features: str = "", store: str = ""
) -> tuple[bool, str | None]:
    """Determine whether an item is genuine fashion apparel vs. non-fashion product.

    Uses multi-signal contextual analysis with fashion override protections.

    Args:
        title: Normalized product title.
        description: Product description string.
        features: Combined feature bullets.
        store: Brand or merchant name.

    Returns:
        Tuple of (is_fashion, non_fashion_reason).
    """
    # Overrides: protect genuine fashion garments, jewelry, charms, and watches
    if FASHION_OVERRIDE_PATTERN.search(title):
        return True, None

    combined_text = f"{title} {store} {features} {description}".lower()
    match = STRONG_NON_FASHION_PATTERN.search(combined_text)
    if match:
        return False, f"non_fashion: {match.group(0)}"

    return True, None


def classify_fashion_slot(
    title: str,
    features: list[str] | None = None,
    description: str | None = None,
) -> tuple[str, str, str | None]:
    """Derive clothing slot and classification confidence using contextual priority.

    Args:
        title: Product title text.
        features: Optional feature bullets.
        description: Optional description text.

    Returns:
        Tuple of (slot, confidence, accessory_type), where confidence is 'high', 'medium', or 'low'.
    """
    # Primary derivation using rule priority
    primary_slot = derive_slot(title, features=features, description=description)

    if primary_slot != "unknown":
        acc_type = derive_accessory_type(title, primary_slot)
        return primary_slot, "high", acc_type

    # Secondary contextual derivation on title text
    if SECONDARY_BAG_PATTERN.search(title):
        acc_type = derive_accessory_type(title, "accessory") or "bag"
        return "accessory", "high", acc_type

    if SECONDARY_FOOTWEAR_PATTERN.search(title):
        return "footwear", "high", None

    if SECONDARY_SOCKS_PATTERN.search(title):
        acc_type = derive_accessory_type(title, "accessory") or "socks"
        return "accessory", "high", acc_type

    if SECONDARY_FULL_BODY_PATTERN.search(title):
        return "full_body", "high", None

    # If slot cannot be determined confidently
    return "unknown", "low", None


def compute_explainable_quality_score(
    title: str,
    price: float | None,
    slot: str,
    confidence: str,
    store: str | None = None,
    features: list[str] | None = None,
    description: str | None = None,
    colors: list[str] | None = None,
    avg_rating: float | None = None,
) -> float:
    """Compute an explainable, bounded quality score in range [0.0, 1.0].

    Weights:
    - Title clarity: 0.25
    - Price validity: 0.15
    - Slot confidence: 0.25
    - Metadata completeness: 0.20 (store, features, description, colors)
    - Rating availability: 0.15

    Returns:
        Calibrated score rounded to 3 decimal places.
    """
    # 1. Title quality (0.0 to 0.25)
    tokens = re.findall(r"\b[a-zA-Z0-9]{2,}\b", title)
    if len(title) >= 20 and len(tokens) >= 4:
        title_score = 0.25
    elif len(tokens) >= 3:
        title_score = 0.18
    else:
        title_score = 0.10

    # 2. Price validity (0.0 to 0.15)
    price_score = 0.15 if price is not None and price > 0 else 0.0

    # 3. Slot confidence (0.0 to 0.25)
    if slot != "unknown" and confidence == "high":
        slot_score = 0.25
    elif slot != "unknown" and confidence == "medium":
        slot_score = 0.15
    else:
        slot_score = 0.0

    # 4. Metadata completeness (0.0 to 0.20)
    meta_score = 0.0
    if store and store.lower() != "unknown":
        meta_score += 0.05
    if features and len(features) > 0:
        meta_score += 0.05
    if description and len(str(description).strip()) >= 15:
        meta_score += 0.05
    if colors and len(colors) > 0:
        meta_score += 0.05

    # 5. Rating availability (0.0 to 0.15)
    rating_score = 0.15 if avg_rating is not None and avg_rating > 0 else 0.05

    total = title_score + price_score + slot_score + meta_score + rating_score
    return round(min(max(total, 0.0), 1.0), 3)


def evaluate_record(
    record: dict[str, Any] | RawProductMetadata | Product,
    min_title_length: int = settings.qc_min_title_length,
    min_quality_score: float = settings.qc_min_quality_score,
    price_min: float = settings.qc_price_min,
    price_max: float = settings.qc_price_max,
) -> QualityCheckResult:
    """Run full validation, cleaning, and quality classification on a product record.

    Args:
        record: Raw dict, RawProductMetadata, or Product entity.
        min_title_length: Configurable title length threshold.
        min_quality_score: Minimum quality score threshold to accept.
        price_min: Minimum acceptable price.
        price_max: Maximum acceptable price.

    Returns:
        Structured QualityCheckResult with status ('accepted', 'quarantined', 'rejected').
    """
    if isinstance(record, (RawProductMetadata, Product)):
        data = record.model_dump()
    else:
        data = dict(record)

    parent_asin = str(data.get("parent_asin", "")).strip()
    raw_title = str(data.get("title", "") or "").strip()
    raw_price = data.get("price")
    store = str(data.get("store", "")).strip() if data.get("store") else None
    features = [str(f) for f in data.get("features") or [] if f]
    desc_val = data.get("description")
    if isinstance(desc_val, list):
        desc_text = " ".join(desc_val)
    elif desc_val:
        desc_text = str(desc_val)
    else:
        desc_text = None
    avg_rating = data.get("average_rating")
    details = data.get("details") if isinstance(data.get("details"), dict) else {}
    images = data.get("images") if isinstance(data.get("images"), list) else []

    rejection_reasons: list[str] = []

    # 1. Title Validation
    title_valid, clean_title, title_reason = validate_and_clean_title(
        raw_title, min_length=min_title_length
    )
    if not title_valid and title_reason:
        rejection_reasons.append(title_reason)

    # 2. Price Validation
    price_valid, clean_price, price_reason = validate_price(
        raw_price, min_price=price_min, max_price=price_max
    )
    if not price_valid and price_reason:
        rejection_reasons.append(price_reason)

    # 3. Fashion Relevance Check
    if title_valid:
        feat_str = " ".join(features)
        is_fashion, fashion_reason = check_fashion_relevance(
            clean_title, description=desc_text or "", features=feat_str, store=store or ""
        )
        if not is_fashion and fashion_reason:
            rejection_reasons.append(fashion_reason)

    # If critical hard failures occurred, immediately classify as REJECTED
    if rejection_reasons:
        return QualityCheckResult(
            parent_asin=parent_asin,
            original_title=raw_title,
            clean_title=clean_title or raw_title,
            price=clean_price,
            slot="unknown",
            status="rejected",
            rejection_reasons=rejection_reasons,
            quality_score=0.0,
            classification_confidence="low",
        )

    # 4. Contextual Slot Classification & Confidence
    slot, confidence, accessory_type = classify_fashion_slot(
        clean_title, features=features, description=desc_text
    )

    # Derive auxiliary metadata
    gender = derive_gender(details, clean_title)
    age_group = derive_age_group(clean_title)
    colors = derive_colors(clean_title)

    combined_context = f"{clean_title} {' '.join(features)} {desc_text or ''}"
    seasons = derive_seasons(combined_context)
    occasions = derive_occasions(combined_context)

    # 5. Quality Score
    quality_score = compute_explainable_quality_score(
        title=clean_title,
        price=clean_price,
        slot=slot,
        confidence=confidence,
        store=store,
        features=features,
        description=desc_text,
        colors=colors,
        avg_rating=avg_rating,
    )

    # 6. Image validation (does not reject product; flag for frontend fallback)
    has_valid_image = bool(images) or bool(data.get("image_url"))

    # 7. Triaging Decision
    if slot == "unknown" or confidence == "low":
        return QualityCheckResult(
            parent_asin=parent_asin,
            original_title=raw_title,
            clean_title=clean_title,
            price=clean_price,
            slot="unknown",
            accessory_type=accessory_type,
            gender=gender,
            age_group=age_group,
            colors=colors,
            seasons=seasons,
            occasions=occasions,
            quality_score=quality_score,
            classification_confidence="low",
            status="quarantined",
            rejection_reasons=["unknown_slot"],
            has_valid_image=has_valid_image,
        )

    if quality_score < min_quality_score:
        return QualityCheckResult(
            parent_asin=parent_asin,
            original_title=raw_title,
            clean_title=clean_title,
            price=clean_price,
            slot=slot,
            accessory_type=accessory_type,
            gender=gender,
            age_group=age_group,
            colors=colors,
            seasons=seasons,
            occasions=occasions,
            quality_score=quality_score,
            classification_confidence=confidence,
            status="quarantined",
            rejection_reasons=["low_quality_score"],
            has_valid_image=has_valid_image,
        )

    # Construct synthesized clean search text
    search_text = (
        f"{clean_title}. Brand: {store or 'Unknown'}. For: {gender}, {age_group}. "
        f"Type: {slot}. {' '.join(features[:3])}."
    )

    return QualityCheckResult(
        parent_asin=parent_asin,
        original_title=raw_title,
        clean_title=clean_title,
        price=clean_price,
        slot=slot,
        accessory_type=accessory_type,
        gender=gender,
        age_group=age_group,
        colors=colors,
        seasons=seasons,
        occasions=occasions,
        quality_score=quality_score,
        classification_confidence=confidence,
        status="accepted",
        rejection_reasons=[],
        search_text=search_text,
        has_valid_image=has_valid_image,
    )


class QuarantineManager:
    """Manages persistence of quarantined and rejected items in SQLite and JSONL."""

    def __init__(
        self,
        db_path: Path | str = settings.quarantine_db_path,
        jsonl_path: Path | str = settings.quarantine_jsonl_path,
    ) -> None:
        self.db_path = Path(db_path)
        self.jsonl_path = Path(jsonl_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS quarantine (
                    parent_asin TEXT PRIMARY KEY,
                    original_title TEXT,
                    price REAL,
                    category TEXT,
                    predicted_slot TEXT,
                    classification_confidence TEXT,
                    status TEXT,
                    reasons TEXT,
                    quality_score REAL,
                    created_at TEXT
                );
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_quarantine_status ON quarantine(status);")

    def record_quarantine(self, record: QuarantineRecord) -> None:
        """Persist a single quarantine/rejection record."""
        now_str = record.created_at or datetime.now(UTC).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO quarantine (
                    parent_asin, original_title, price, category, predicted_slot,
                    classification_confidence, status, reasons, quality_score, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.parent_asin,
                    record.original_title,
                    record.price,
                    record.category,
                    record.predicted_slot,
                    record.classification_confidence,
                    record.status,
                    json.dumps(record.reasons),
                    record.quality_score,
                    now_str,
                ),
            )

        with open(self.jsonl_path, "a", encoding="utf-8") as f:
            rec_dict = record.model_dump()
            rec_dict["created_at"] = now_str
            f.write(json.dumps(rec_dict, ensure_ascii=False) + "\n")

    def record_batch(self, records: list[QuarantineRecord]) -> None:
        """Batch persist multiple quarantine/rejection records."""
        if not records:
            return

        now_str = datetime.now(UTC).isoformat()
        db_rows = []
        jsonl_lines = []

        for r in records:
            t = r.created_at or now_str
            db_rows.append(
                (
                    r.parent_asin,
                    r.original_title,
                    r.price,
                    r.category,
                    r.predicted_slot,
                    r.classification_confidence,
                    r.status,
                    json.dumps(r.reasons),
                    r.quality_score,
                    t,
                )
            )
            r_dict = r.model_dump()
            r_dict["created_at"] = t
            jsonl_lines.append(json.dumps(r_dict, ensure_ascii=False) + "\n")

        with sqlite3.connect(self.db_path) as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO quarantine (
                    parent_asin, original_title, price, category, predicted_slot,
                    classification_confidence, status, reasons, quality_score, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                db_rows,
            )

        with open(self.jsonl_path, "a", encoding="utf-8") as f:
            f.writelines(jsonl_lines)

    def count(self, status: str | None = None) -> int:
        """Count records stored in quarantine database."""
        with sqlite3.connect(self.db_path) as conn:
            if status:
                row = conn.execute(
                    "SELECT COUNT(*) FROM quarantine WHERE status = ?", (status,)
                ).fetchone()
            else:
                row = conn.execute("SELECT COUNT(*) FROM quarantine").fetchone()
            return int(row[0]) if row else 0
