"""Prototype and evaluate the feature-based query-aware reranker on benchmark queries."""

import re
import time
from typing import Any
from app.catalog import CatalogRepository
from app.config import settings
from app.embedder import SentenceTransformerEmbedder
from app.index import HybridIndex
from app.parser import QueryParser, ParsedQuery
from app.schemas import Product
from app.filters import passes_strict_filters, is_innerwear_allowed
from app.attribute_correction import is_search_eligible_product

# Costume detection pattern
COSTUME_PATTERN = re.compile(
    r"\b(?:costume|halloween|cosplay|fancy\s+dress|party\s+costume|medieval\s+princess|queen\s+costume|gangster\s+adult\s+costume|morphsuit)\b",
    re.IGNORECASE
)

COLOR_FAMILY_MAP = {
    "red": {"red", "burgundy", "wine", "ruby", "maroon", "crimson", "scarlet", "cherry"},
    "black": {"black", "ebony", "onyx", "charcoal"},
    "blue": {"blue", "navy", "teal", "turquoise", "cobalt", "azure", "denim", "indigo"},
    "white": {"white", "ivory", "cream", "snow"},
    "green": {"green", "olive", "mint", "emerald", "sage", "lime"},
    "pink": {"pink", "rose", "blush", "coral", "magenta"},
    "brown": {"brown", "tan", "beige", "khaki", "chocolate", "mocha", "camel"},
    "gray": {"gray", "grey", "silver", "slate", "charcoal"},
}

def detect_query_archetype(query: str, parsed: ParsedQuery) -> str:
    """Classify query into an archetype to dynamically adjust reranker weights."""
    q_lower = query.lower()
    has_explicit_slot = bool(parsed.slots)
    has_color = bool(parsed.colors)
    has_price = parsed.max_price is not None or parsed.min_price is not None
    is_discovery = any(w in q_lower for w in ["something", "stylish", "elegant", "outfit", "ideas", "look", "what to wear"])

    if has_price and (has_explicit_slot or has_color):
        return "BUDGET_EXPLICIT"
    elif has_explicit_slot:
        return "EXPLICIT_PRODUCT"
    elif is_discovery or not has_explicit_slot:
        return "DISCOVERY_STYLE"
    return "STANDARD"

def compute_feature_rerank_score(
    product: Product,
    raw_query: str,
    parsed: ParsedQuery,
    fused_score: float,
    max_fused: float,
    sim: float,
    bm25_score: float = 0.0,
    max_bm25: float = 1.0,
    archetype: str = "STANDARD",
) -> tuple[float, dict[str, float]]:
    """Compute multi-signal explainable reranking score."""
    q_lower = raw_query.lower()
    title_lower = product.title.lower()
    features: dict[str, float] = {}

    # 1. Semantic Similarity (normalized: min-max calibrated from [0.2, 0.85] to [0.0, 1.0])
    norm_sim = max(0.0, min(1.0, (sim - 0.20) / 0.65))
    features["semantic"] = norm_sim

    # 2. Lexical / RRF Score
    norm_fused = fused_score / max_fused if max_fused > 0 else 0.0
    features["lexical"] = norm_fused

    # 3. Exact Phrase & N-gram Match in Title
    phrase_score = 0.0
    # Clean query for phrase matching (without prices like "under $50")
    clean_q = re.sub(r"\b(?:under|below|less\s+than|budget)\s*\$?\d+\b", "", q_lower).strip()
    if clean_q and clean_q in title_lower:
        phrase_score = 1.0
    else:
        # Check 2-gram matches
        q_words = [w for w in re.findall(r"\w+", clean_q) if len(w) > 2]
        if len(q_words) >= 2:
            bigrams = [f"{q_words[i]} {q_words[i+1]}" for i in range(len(q_words) - 1)]
            matched_bigrams = sum(1 for bg in bigrams if bg in title_lower)
            phrase_score = min(0.8, (matched_bigrams / len(bigrams)) * 0.8)
        elif len(q_words) == 1:
            phrase_score = 0.5 if q_words[0] in title_lower else 0.0
    features["exact_phrase"] = phrase_score

    # 4. Slot / Product Category Fit
    slot_score = 0.5  # Neutral default
    prod_slot = (product.slot or "").lower()
    if parsed.slots:
        target_slots = [s.lower() for s in parsed.slots]
        if prod_slot in target_slots:
            slot_score = 1.0
        else:
            slot_score = 0.1
    else:
        # If query asks for dress/shoes/jacket via keyword
        if "dress" in q_lower and prod_slot == "full_body":
            slot_score = 1.0
        elif ("shoes" in q_lower or "footwear" in q_lower or "boots" in q_lower) and prod_slot == "footwear":
            slot_score = 1.0
        elif ("jacket" in q_lower or "coat" in q_lower or "blazer" in q_lower) and prod_slot == "top":
            slot_score = 1.0
    features["slot"] = slot_score

    # 5. Color Match
    color_score = 1.0  # Neutral if no color requested
    if parsed.colors:
        color_score = 0.1  # Default low if color requested but not found
        p_colors = {c.lower() for c in (product.colors or [])}
        for req_color in parsed.colors:
            req_color_lower = req_color.lower()
            family = COLOR_FAMILY_MAP.get(req_color_lower, {req_color_lower})
            # Check attribute match
            if family.intersection(p_colors):
                color_score = 1.0
                break
            # Check title word match
            if any(re.search(rf"\b{re.escape(c)}\b", title_lower) for c in family):
                color_score = 0.95
                break
            # Penalize if product has an explicitly different color
            other_families = {c for fam_name, fam in COLOR_FAMILY_MAP.items() if fam_name != req_color_lower for c in fam}
            if other_families.intersection(p_colors) and not family.intersection(p_colors):
                color_score = 0.05
    features["color"] = color_score

    # 6. Demographic Match
    demographic_score = 1.0
    if parsed.gender:
        prod_gender = (product.gender or "unknown").lower()
        if prod_gender == parsed.gender.lower():
            demographic_score = 1.0
        elif prod_gender == "unisex":
            demographic_score = 0.8
        elif prod_gender == "unknown":
            demographic_score = 0.5
        else:
            demographic_score = 0.0
    features["demographic"] = demographic_score

    # 7. Occasion & Style Match
    occ_score = 0.5
    prod_occasions = {o.lower() for o in (product.occasions or [])}
    if parsed.occasion:
        occ_target = parsed.occasion.lower()
        if occ_target in prod_occasions or occ_target in title_lower:
            occ_score = 1.0
        else:
            # Check style keywords
            if occ_target == "party" and any(k in title_lower for k in ["cocktail", "party", "evening", "gala"]):
                occ_score = 1.0
            elif occ_target == "casual" and any(k in title_lower for k in ["casual", "daily", "weekend", "relaxed"]):
                occ_score = 0.9
            elif occ_target == "formal" and any(k in title_lower for k in ["formal", "tuxedo", "suit", "elegant", "oxford"]):
                occ_score = 1.0
            elif occ_target == "date" and any(k in title_lower for k in ["elegant", "dinner", "evening", "date", "romantic"]):
                occ_score = 0.95
            else:
                occ_score = 0.2
    else:
        # Check style cues
        if any(w in q_lower for w in ["formal", "elegant", "classy"]):
            if any(w in title_lower for w in ["formal", "elegant", "oxford", "derby", "classy"]):
                occ_score = 1.0
    features["occasion"] = occ_score

    # 8. Product Quality Score (Bayesian quality)
    q_score = (product.quality_score or 4.0) / 5.0
    features["quality"] = max(0.0, min(1.0, q_score))

    # 9. Price Fitness
    price_score = 1.0
    if parsed.max_price and product.price:
        # Reward items comfortably within budget (e.g. between 25% and 95% of budget)
        ratio = product.price / parsed.max_price
        if ratio <= 1.0:
            price_score = 0.7 + 0.3 * (1.0 - ratio)
        else:
            price_score = 0.0
    features["price"] = price_score

    # 10. Costume / Novelty Penalty
    costume_penalty = 0.0
    query_wants_costume = any(w in q_lower for w in ["costume", "halloween", "cosplay", "fancy dress"])
    if not query_wants_costume and COSTUME_PATTERN.search(title_lower):
        costume_penalty = 0.40  # Significant penalty for costume items appearing in standard fashion searches
    features["costume_penalty"] = costume_penalty

    # Weight assignment based on Query Archetype
    if archetype == "BUDGET_EXPLICIT":
        w = {
            "semantic": 0.20,
            "lexical": 0.10,
            "exact_phrase": 0.15,
            "slot": 0.20,
            "color": 0.15,
            "demographic": 0.05,
            "occasion": 0.05,
            "quality": 0.05,
            "price": 0.05,
        }
    elif archetype == "EXPLICIT_PRODUCT":
        w = {
            "semantic": 0.22,
            "lexical": 0.10,
            "exact_phrase": 0.18,
            "slot": 0.22,
            "color": 0.12,
            "demographic": 0.08,
            "occasion": 0.03,
            "quality": 0.05,
            "price": 0.00,
        }
    elif archetype == "DISCOVERY_STYLE":
        w = {
            "semantic": 0.35,
            "lexical": 0.10,
            "exact_phrase": 0.05,
            "slot": 0.10,
            "color": 0.05,
            "demographic": 0.10,
            "occasion": 0.15,
            "quality": 0.10,
            "price": 0.00,
        }
    else:
        w = {
            "semantic": 0.25,
            "lexical": 0.15,
            "exact_phrase": 0.10,
            "slot": 0.15,
            "color": 0.10,
            "demographic": 0.10,
            "occasion": 0.05,
            "quality": 0.10,
            "price": 0.00,
        }

    raw_score = sum(w[k] * features[k] for k in w) - costume_penalty
    final_score = max(0.0, min(1.0, raw_score))
    return final_score, features


def test_prototype():
    repo = CatalogRepository(settings.db_path)
    embedder = SentenceTransformerEmbedder(settings.embedding_model_name)
    index = HybridIndex(repo, embedder)
    index.build_from_catalog()
    parser = QueryParser()

    queries = [
        "red cocktail dress",
        "black shoes for women",
        "winter jacket for men",
        "casual outfit for college",
        "red dress below $50",
        "black formal shoes under $100",
        "something stylish for a dinner date",
        "summer outfit for women"
    ]

    print("\n=== EVALUATING PROTOTYPE RERANKER ===")
    for q in queries:
        t0 = time.perf_counter()
        parsed, _ = parser.parse(q)
        arch = detect_query_archetype(q, parsed)
        cands, _ = index.search(q, parsed.normalized_query_en, retrieval_k=50)
        pids = [c[0] for c in cands]
        pmap = repo.get_by_ids(pids)

        max_fused = max((c[1] for c in cands), default=1.0)
        scored_items = []
        for pid, fused_score, sim in cands:
            if pid not in pmap:
                continue
            p = pmap[pid]
            if not passes_strict_filters(p, parsed, gender_include_unknown=False):
                continue
            if not is_search_eligible_product(p, raw_query=q, parsed=parsed):
                continue

            score, feats = compute_feature_rerank_score(
                product=p,
                raw_query=q,
                parsed=parsed,
                fused_score=fused_score,
                max_fused=max_fused,
                sim=sim,
                archetype=arch,
            )
            scored_items.append((p, score, sim, feats))

        scored_items.sort(key=lambda x: x[1], reverse=True)
        latency = (time.perf_counter() - t0) * 1000.0

        print(f"\nQUERY: '{q}' (Archetype: {arch}) | Latency: {latency:.2f}ms")
        for rank, (prod, score, sim, feats) in enumerate(scored_items[:3], 1):
            print(f"  #{rank} [Score: {score:.3f} | Sim: {sim:.3f}] {prod.title[:65]} (Slot: {prod.slot}, Price: ${prod.price})")

if __name__ == "__main__":
    test_prototype()
