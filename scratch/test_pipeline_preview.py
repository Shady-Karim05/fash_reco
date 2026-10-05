"""Full trial preview of Data Cleaning & Quality Control Pipeline on data/catalog.db."""

import sqlite3
import re
import html
from collections import Counter
from app.attributes import (
    derive_slot,
    derive_gender,
    derive_age_group,
    derive_colors,
    derive_seasons,
    derive_occasions,
    derive_accessory_type,
    compute_quality_score,
)
from app.cleaning import clean_text, strip_size_tokens, build_search_text

# 1. Non-Fashion Detection
FASHION_OVERRIDE_PATTERN = re.compile(
    r"\b(?:"
    r"watch\s+band|watch\s+strap|iwatch\s+band|apple\s+watch\s+band|"
    r"enamel\s+pin|lapel\s+pin|brooch|charm|pendant|necklace|bracelet|earrings?|"
    r"beanie|knitted\s+cap|costume|cosplay|heated\s+jacket|apron|keychain|key\s+ring"
    r")\b",
    re.IGNORECASE
)

STRONG_NON_FASHION = re.compile(
    r"\b(?:"
    r"usb\s+cable|phone\s+case|screen\s+protector|charger|earbuds|headphones|bluetooth\s+speaker|"
    r"camera\s+mount|stylus\s+pen|battery\s+pack|audio\s+cable|"
    r"license\s+plate|car\s+seat\s+cover|steering\s+wheel\s+cover|floor\s+mat|bumper\s+sticker|"
    r"tire\s+pressure|valve\s+stem|spark\s+plug|oil\s+filter|"
    r"pipe\s+connector|brass\s+valve|pipe\s+fitting|pvc\s+fitting|shower\s+head|light\s+bulb|"
    r"screwdriver|wrench|drill\s+bit|door\s+knob|cabinet\s+pull|curtain\s+rod|switch\s+plate|"
    r"guitar\s+strap|guitar\s+pick|guitar\s+cable|drum\s+stick|violin\s+bow|bell\s+incredibell|action\s+bell|"
    r"paperweight|pen\s+holder|desk\s+organizer|bookmark|"
    r"uncut\s+raw\s+rough|healing\s+crystal|mineral\s+specimen|geode\s+crystal|"
    r"cutting\s+board|coffee\s+mug|water\s+bottle|wine\s+glass|spatula|cutlery\s+set|"
    r"dog\s+collar|cat\s+harness|dog\s+leash|pet\s+carrier|dog\s+harness|"
    r"disposable\s+blue\s+-\s*50\s+tablets|sanitizer"
    r")\b",
    re.IGNORECASE
)

def evaluate_product(asin, title, price, slot, store, desc, feat, avg_rating, rating_num):
    # Rule 1: Title Validation
    if not title or not title.strip():
        return "rejected", ["missing_title"], "unknown", 0.0, "low"
    
    clean_t = clean_text(html.unescape(title))
    tokens = re.findall(r"\b[a-zA-Z0-9]{2,}\b", clean_t)
    if len(tokens) < 2:
        return "rejected", ["meaningless_title"], "unknown", 0.0, "low"
    if len(clean_t) < 10:
        return "rejected", ["short_title"], "unknown", 0.0, "low"
        
    # Rule 2: Price Validation
    if price is None:
        return "rejected", ["missing_price"], "unknown", 0.0, "low"
    try:
        p_val = float(price)
        if p_val <= 0:
            return "rejected", ["invalid_price"], "unknown", 0.0, "low"
        if p_val > 10000.0 or p_val < 0.20:
            return "rejected", ["price_outlier"], "unknown", 0.0, "low"
    except (ValueError, TypeError):
        return "rejected", ["invalid_price"], "unknown", 0.0, "low"
        
    # Rule 3: Fashion Relevance Check
    if not FASHION_OVERRIDE_PATTERN.search(clean_t):
        full_text = f"{clean_t} {desc or ''} {feat or ''}".lower()
        m = STRONG_NON_FASHION.search(full_text)
        if m:
            return "rejected", [f"non_fashion: {m.group(0)}"], "unknown", 0.0, "low"

    # Rule 4: Contextual Slot Derivation & Confidence
    derived = derive_slot(clean_t)
    effective_slot = slot
    confidence = "high"
    
    if derived != "unknown":
        effective_slot = derived
        confidence = "high"
    elif effective_slot == "unknown":
        # Check secondary patterns (satchel, shoes, socks, etc.)
        if re.search(r"\b(?:satchel|crossbody|clutch|tote|backpack|handbag|wallet)\b", clean_t, re.I):
            effective_slot = "accessory"
            confidence = "high"
        elif re.search(r"\b(?:shoes?|sneakers?|boots?|sandals?|footwear|loafers?|heels?|slippers?|pumps?)\b", clean_t, re.I):
            effective_slot = "footwear"
            confidence = "high"
        elif re.search(r"\b(?:socks?|no[- ]shows?|stockings?|tights?|leg\s+warmers?)\b", clean_t, re.I):
            effective_slot = "accessory"
            confidence = "high"
        else:
            confidence = "low"
            effective_slot = "unknown"

    # Rule 5: Quality Scoring (0.0 to 1.0)
    title_score = 0.25 if len(clean_t) >= 20 and len(tokens) >= 4 else (0.18 if len(tokens) >= 3 else 0.10)
    price_score = 0.15
    slot_score = 0.25 if confidence == "high" else (0.15 if confidence == "medium" else 0.0)
    
    meta_score = 0.0
    if store and store != "Unknown": meta_score += 0.05
    if feat and feat != "[]": meta_score += 0.05
    if desc and len(desc) > 10: meta_score += 0.05
    colors = derive_colors(clean_t)
    if colors: meta_score += 0.05
    
    rating_score = 0.15 if avg_rating is not None and avg_rating > 0 else 0.05
    quality_score = round(title_score + price_score + slot_score + meta_score + rating_score, 3)

    # Decision Matrix:
    if effective_slot == "unknown" or confidence == "low":
        return "quarantined", ["unknown_slot"], "unknown", quality_score, "low"
    
    if quality_score < 0.35:
        return "quarantined", ["low_quality_score"], effective_slot, quality_score, confidence
        
    return "accepted", [], effective_slot, quality_score, confidence

conn = sqlite3.connect('data/catalog.db')
cursor = conn.cursor()
cursor.execute('SELECT parent_asin, title, price, slot, store, description, features, average_rating, rating_number FROM products')
rows = cursor.fetchall()

status_counts = Counter()
rejection_reasons = Counter()
quarantine_reasons = Counter()
accepted_slots = Counter()
quality_buckets = Counter()

for r in rows:
    asin, title, price, slot, store, desc, feat, avg_r, r_num = r
    status, reasons, eff_slot, q_score, conf = evaluate_product(asin, title, price, slot, store, desc, feat, avg_r, r_num)
    status_counts[status] += 1
    
    q_bucket = f"{int(q_score * 10) / 10:.1f}-{int(q_score * 10) / 10 + 0.1:.1f}"
    quality_buckets[q_bucket] += 1
    
    if status == "rejected":
        for r_name in reasons:
            rejection_reasons[r_name.split(':')[0]] += 1
    elif status == "quarantined":
        for r_name in reasons:
            quarantine_reasons[r_name] += 1
    else:
        accepted_slots[eff_slot] += 1

print("=== PIPELINE EVALUATION RESULTS ===")
print("Total processed:", len(rows))
print("Status breakdown:", status_counts)
print("\nRejection reasons:", rejection_reasons)
print("Quarantine reasons:", quarantine_reasons)
print("\nAccepted products slot breakdown:", accepted_slots)
print("Total accepted:", sum(accepted_slots.values()))
print("\nQuality score distribution:", sorted(quality_buckets.items()))
