"""Query-Aware Multi-Signal Product Reranker (Phases 4, 5, 6).

Implements multi-feature relevance scoring, query archetype adaptation,
costume/novelty penalty guards, optional lightweight Cross-Encoder blending,
and bounded LRU caching.
"""

import logging
import re
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Literal

from app.config import settings
from app.parser import ParsedQuery
from app.schemas import Product

logger = logging.getLogger("fashion_search.reranker")

# Costume detection pattern to penalize novelty/costume products for standard fashion queries
COSTUME_PATTERN = re.compile(
    r"\b(?:"
    r"costume|halloween|cosplay|fancy\s+dress|party\s+costume|medieval\s+princess|"
    r"queen\s+costume|gangster\s+adult\s+costume|morphsuit|renaissance\s+costume|"
    r"pirate\s+costume|vampire\s+costume|witch\s+costume"
    r")\b",
    re.IGNORECASE,
)

# Color family mappings for contextual color matching and contradiction checking
COLOR_FAMILY_MAP: dict[str, set[str]] = {
    "red": {"red", "burgundy", "wine", "ruby", "maroon", "crimson", "scarlet", "cherry"},
    "black": {"black", "ebony", "onyx", "charcoal"},
    "blue": {"blue", "navy", "teal", "turquoise", "cobalt", "azure", "denim", "indigo"},
    "white": {"white", "ivory", "cream", "snow"},
    "green": {"green", "olive", "mint", "emerald", "sage", "lime", "forest"},
    "pink": {"pink", "rose", "blush", "coral", "magenta", "fuchsia"},
    "brown": {"brown", "tan", "beige", "khaki", "chocolate", "mocha", "camel"},
    "gray": {"gray", "grey", "silver", "slate", "charcoal"},
    "yellow": {"yellow", "gold", "mustard", "lemon"},
    "purple": {"purple", "violet", "lavender", "plum", "lilac"},
    "orange": {"orange", "peach", "rust", "tangerine"},
}

QueryArchetype = Literal["EXPLICIT_PRODUCT", "BUDGET_EXPLICIT", "DISCOVERY_STYLE", "STANDARD"]


def detect_query_archetype(query: str, parsed: ParsedQuery) -> QueryArchetype:
    """Classify query intent to dynamically assign feature weights (Phase 6).

    Archetypes:
    1. BUDGET_EXPLICIT: Has budget constraint plus specific product type or color.
       Prioritizes budget compliance, category, and color.
    2. EXPLICIT_PRODUCT: Has explicit slot, gender, or clothing product category.
       Prioritizes slot matching, exact phrase, color, and demographics.
    3. DISCOVERY_STYLE: Exploratory, occasion or style driven without rigid clothing slot.
       Prioritizes semantic similarity, occasion/style alignment, and aesthetic cohesion.
    4. STANDARD: General fashion search.
    """
    q_lower = query.lower()
    has_explicit_slot = bool(parsed.slots)
    has_color = bool(parsed.colors)
    has_price = parsed.max_price is not None or parsed.min_price is not None

    discovery_kws = {
        "something",
        "stylish",
        "elegant",
        "outfit",
        "ideas",
        "look",
        "what to wear",
        "aesthetic",
        "trendy",
        "classy",
        "cute",
        "cool",
        "vibes",
    }
    is_discovery = any(kw in q_lower for kw in discovery_kws)

    if has_price and (has_explicit_slot or has_color):
        return "BUDGET_EXPLICIT"
    elif has_explicit_slot:
        return "EXPLICIT_PRODUCT"
    elif is_discovery or parsed.occasion is not None:
        return "DISCOVERY_STYLE"
    return "STANDARD"


@dataclass
class RerankResult:
    """Detailed result of product reranking including explainable feature breakdown."""

    product: Product
    score: float
    similarity: float
    features: dict[str, float]


class RerankerCache:
    """Thread-safe bounded LRU cache for query candidate reranking results."""

    def __init__(self, max_size: int = 1000) -> None:
        self.max_size = max_size
        self._cache: OrderedDict[str, list[tuple[str, float, float]]] = OrderedDict()
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> list[tuple[str, float, float]] | None:
        with self._lock:
            if key in self._cache:
                self.hits += 1
                self._cache.move_to_end(key)
                return self._cache[key]
            self.misses += 1
            return None

    def put(self, key: str, value: list[tuple[str, float, float]]) -> None:
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            else:
                if len(self._cache) >= self.max_size:
                    self._cache.popitem(last=False)
            self._cache[key] = value

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return round(self.hits / total * 100.0, 2) if total > 0 else 0.0


class QueryAwareReranker:
    """Production-grade multi-signal fashion reranker with query archetype adaptation."""

    def __init__(
        self,
        enabled: bool = True,
        use_cross_encoder: bool = False,
        cross_encoder_model: str = "cross-encoder/ms-marco-TinyBERT-L-2-v2",
        cross_encoder_top_n: int = 20,
        cross_encoder_blend: float = 0.35,
        cache_size: int = 1000,
    ) -> None:
        self.enabled = enabled
        self.use_cross_encoder = use_cross_encoder
        self.cross_encoder_model_name = cross_encoder_model
        self.cross_encoder_top_n = cross_encoder_top_n
        self.cross_encoder_blend = cross_encoder_blend
        self.cache = RerankerCache(max_size=cache_size)

        self._cross_encoder_instance: Any = None
        self._cross_encoder_lock = threading.Lock()
        self.last_rerank_latency_ms: float = 0.0

    def _get_cross_encoder(self) -> Any:
        """Lazily load cross-encoder model with thread safety and graceful failure."""
        if not self.use_cross_encoder:
            return None
        if self._cross_encoder_instance is None:
            with self._cross_encoder_lock:
                if self._cross_encoder_instance is None:
                    try:
                        from sentence_transformers import CrossEncoder

                        logger.info("Loading CrossEncoder model: %s", self.cross_encoder_model_name)
                        self._cross_encoder_instance = CrossEncoder(self.cross_encoder_model_name)
                    except Exception as exc:
                        logger.warning("CrossEncoder load failed: %s; using feature reranker", exc)
                        self.use_cross_encoder = False
                        self._cross_encoder_instance = None
        return self._cross_encoder_instance

    def compute_features(
        self,
        product: Product,
        raw_query: str,
        parsed: ParsedQuery,
        fused_score: float,
        max_fused: float,
        sim: float,
    ) -> dict[str, float]:
        """Extract and normalize all 10 relevance feature signals into [0.0, 1.0]."""
        q_lower = raw_query.lower()
        title_lower = product.title.lower()
        features: dict[str, float] = {}

        # 1. Semantic Similarity: calibrated min-max from [0.20, 0.85] to [0.0, 1.0]
        norm_sim = max(0.0, min(1.0, (sim - 0.20) / 0.65))
        features["semantic"] = norm_sim

        # 2. Lexical / RRF Score: relative rank position normalized to max in pool
        norm_fused = fused_score / max_fused if max_fused > 0 else 0.0
        features["lexical"] = norm_fused

        # 3. Exact Phrase & N-gram Match
        phrase_score = 0.0
        clean_q = re.sub(r"\b(?:under|below|less\s+than|budget)\s*\$?\d+\b", "", q_lower).strip()
        if clean_q and clean_q in title_lower:
            phrase_score = 1.0
        else:
            q_words = [w for w in re.findall(r"\w+", clean_q) if len(w) > 2]
            if len(q_words) >= 2:
                bigrams = [f"{q_words[i]} {q_words[i + 1]}" for i in range(len(q_words) - 1)]
                matched_bigrams = sum(1 for bg in bigrams if bg in title_lower)
                phrase_score = min(0.8, (matched_bigrams / len(bigrams)) * 0.8)
            elif len(q_words) == 1:
                phrase_score = 0.5 if q_words[0] in title_lower else 0.0
        features["exact_phrase"] = phrase_score

        # 4. Slot / Product Category Fit
        slot_score = 0.5
        prod_slot = (product.slot or "").lower()
        if parsed.slots:
            target_slots = [s.lower() for s in parsed.slots]
            slot_score = 1.0 if prod_slot in target_slots else 0.1
        else:
            # Query mentions apparel category
            if (
                "dress" in q_lower
                and prod_slot == "full_body"
                or ("shoes" in q_lower or "footwear" in q_lower or "boots" in q_lower)
                and prod_slot == "footwear"
                or ("jacket" in q_lower or "coat" in q_lower or "blazer" in q_lower)
                and prod_slot == "top"
            ):
                slot_score = 1.0
        features["slot"] = slot_score

        # 5. Color Compatibility
        color_score = 1.0
        if parsed.colors:
            color_score = 0.1
            p_colors = {c.lower() for c in (product.colors or [])}
            for req_color in parsed.colors:
                req_lower = req_color.lower()
                family = COLOR_FAMILY_MAP.get(req_lower, {req_lower})
                if family.intersection(p_colors):
                    color_score = 1.0
                    break
                if any(re.search(rf"\b{re.escape(c)}\b", title_lower) for c in family):
                    color_score = 0.95
                    break
                # Penalize explicit contradictory color
                other_families = {
                    c for fname, f in COLOR_FAMILY_MAP.items() if fname != req_lower for c in f
                }
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
            if (
                occ_target in prod_occasions
                or occ_target in title_lower
                or occ_target == "party"
                and any(k in title_lower for k in ["cocktail", "party", "evening", "gala"])
            ):
                occ_score = 1.0
            elif occ_target == "casual" and any(
                k in title_lower for k in ["casual", "daily", "weekend", "relaxed"]
            ):
                occ_score = 0.9
            elif occ_target == "formal" and any(
                k in title_lower for k in ["formal", "tuxedo", "suit", "elegant", "oxford"]
            ):
                occ_score = 1.0
            elif occ_target == "date" and any(
                k in title_lower for k in ["elegant", "dinner", "evening", "date", "romantic"]
            ):
                occ_score = 0.95
            else:
                occ_score = 0.2
        elif any(w in q_lower for w in ["formal", "elegant", "classy"]) and any(
            w in title_lower for w in ["formal", "elegant", "oxford", "derby", "classy"]
        ):
            occ_score = 1.0
        features["occasion"] = occ_score

        # 8. Product Quality (Bayesian quality score)
        q_score = (product.quality_score or 4.0) / 5.0
        features["quality"] = max(0.0, min(1.0, q_score))

        # 9. Price Fitness
        price_score = 1.0
        if parsed.max_price and product.price:
            ratio = product.price / parsed.max_price
            price_score = max(0.0, 0.7 + 0.3 * (1.0 - ratio)) if ratio <= 1.0 else 0.0
        features["price"] = price_score

        # 10. Costume / Novelty Penalty
        costume_penalty = 0.0
        query_wants_costume = any(
            w in q_lower for w in ["costume", "halloween", "cosplay", "fancy dress"]
        )
        if not query_wants_costume and COSTUME_PATTERN.search(title_lower):
            costume_penalty = settings.reranker_costume_penalty
        features["costume_penalty"] = costume_penalty

        return features

    def get_weights_for_archetype(self, archetype: QueryArchetype) -> dict[str, float]:
        """Retrieve configurable weights calibrated for each query archetype (Phase 6)."""
        weight_maps: dict[QueryArchetype, dict[str, float]] = {
            "BUDGET_EXPLICIT": {
                "semantic": 0.20,
                "lexical": 0.10,
                "exact_phrase": 0.15,
                "slot": 0.20,
                "color": 0.15,
                "demographic": 0.05,
                "occasion": 0.05,
                "quality": 0.05,
                "price": 0.05,
            },
            "EXPLICIT_PRODUCT": {
                "semantic": settings.reranker_weight_semantic,
                "lexical": settings.reranker_weight_lexical,
                "exact_phrase": settings.reranker_weight_exact_phrase,
                "slot": settings.reranker_weight_slot,
                "color": settings.reranker_weight_color,
                "demographic": settings.reranker_weight_demographic,
                "occasion": settings.reranker_weight_occasion,
                "quality": settings.reranker_weight_quality,
                "price": 0.00,
            },
            "DISCOVERY_STYLE": {
                "semantic": 0.35,
                "lexical": 0.10,
                "exact_phrase": 0.05,
                "slot": 0.10,
                "color": 0.05,
                "demographic": 0.10,
                "occasion": 0.15,
                "quality": 0.10,
                "price": 0.00,
            },
            "STANDARD": {
                "semantic": 0.25,
                "lexical": 0.15,
                "exact_phrase": 0.10,
                "slot": 0.15,
                "color": 0.10,
                "demographic": 0.10,
                "occasion": 0.05,
                "quality": 0.10,
                "price": 0.00,
            },
        }
        return weight_maps.get(archetype, weight_maps["STANDARD"])

    def rerank(
        self,
        raw_query: str,
        parsed: ParsedQuery,
        candidates: list[tuple[Product, float, float]],
        top_k: int = 10,
        max_fused: float = 1.0,
    ) -> list[tuple[Product, float, float]]:
        """Rerank candidates using query-aware feature scoring and optional Cross-Encoder.

        Args:
            raw_query: Raw user query text.
            parsed: Structured ParsedQuery representation.
            candidates: List of (Product, fused_score, cosine_similarity) from hybrid search.
            top_k: Requested number of final items.
            max_fused: Maximum RRF score in retrieval pool for normalization.

        Returns:
            List of (Product, final_score, cosine_similarity) sorted descending by final_score.
        """
        if not candidates or not self.enabled:
            return candidates

        start_t = time.perf_counter()

        # Check Cache
        cand_ids_str = ",".join(p.parent_asin for p, _, _ in candidates[:25])
        cand_key = f"{raw_query}::{parsed.model_dump_json()}::{cand_ids_str}"
        cached_res = self.cache.get(cand_key)
        if cached_res is not None:
            prod_lookup = {p.parent_asin: p for p, _, _ in candidates}
            result: list[tuple[Product, float, float]] = []
            for pid, sc, sim in cached_res:
                if pid in prod_lookup:
                    result.append((prod_lookup[pid], sc, sim))
            if result:
                self.last_rerank_latency_ms = (time.perf_counter() - start_t) * 1000.0
                return result

        archetype = detect_query_archetype(raw_query, parsed)
        weights = self.get_weights_for_archetype(archetype)

        scored: list[tuple[Product, float, float, dict[str, float]]] = []
        for p, fused_score, sim in candidates:
            feats = self.compute_features(
                product=p,
                raw_query=raw_query,
                parsed=parsed,
                fused_score=fused_score,
                max_fused=max_fused,
                sim=sim,
            )
            raw_score = sum(weights[k] * feats[k] for k in weights) - feats["costume_penalty"]
            final_feat_score = max(0.0, min(1.0, raw_score))
            scored.append((p, final_feat_score, sim, feats))

        # Sort descending by feature score
        scored.sort(key=lambda x: x[1], reverse=True)

        # Optional Cross-Encoder Stage (Phase 5)
        cross_encoder = self._get_cross_encoder()
        if cross_encoder is not None and scored:
            try:
                top_n = min(len(scored), self.cross_encoder_top_n)
                top_items = scored[:top_n]
                pairs = [
                    (raw_query, f"{item[0].title} {item[0].store or ''}") for item in top_items
                ]
                ce_scores = cross_encoder.predict(pairs)

                # Min-max scale CE scores within batch
                min_ce = min(ce_scores)
                max_ce = max(ce_scores)
                range_ce = max(max_ce - min_ce, 1e-6)

                blended: list[tuple[Product, float, float, dict[str, float]]] = []
                for (p, feat_s, sim, feats), ce_s in zip(top_items, ce_scores, strict=False):
                    norm_ce = float((ce_s - min_ce) / range_ce)
                    combined_score = (
                        1.0 - self.cross_encoder_blend
                    ) * feat_s + self.cross_encoder_blend * norm_ce
                    blended.append((p, combined_score, sim, feats))

                # Append remaining items below top_n
                blended.extend(scored[top_n:])
                blended.sort(key=lambda x: x[1], reverse=True)
                scored = blended
            except Exception as exc:
                logger.warning(
                    "CrossEncoder execution failed: %s. Falling back to feature scoring.", exc
                )

        final_candidates = [(p, score, sim) for p, score, sim, _ in scored]
        self.last_rerank_latency_ms = (time.perf_counter() - start_t) * 1000.0

        # Save to cache
        cache_data = [(p.parent_asin, score, sim) for p, score, sim in final_candidates]
        self.cache.put(cand_key, cache_data)

        return final_candidates
