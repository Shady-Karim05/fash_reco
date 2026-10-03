"""Outfit composition engine with coherence, template selection, and budget optimization (B4)."""

import itertools
import re

from app.catalog import CatalogRepository
from app.config import settings
from app.filters import (
    collapse_near_duplicates,
    compute_soft_boost,
    generate_item_explanation,
    passes_strict_filters,
)
from app.index import HybridIndex
from app.parser import ParsedQuery
from app.schemas import (
    OutfitPayload,
    OutfitResponse,
    Product,
    SearchMeta,
    SearchResultItem,
)


def is_accessory_allowed_type(accessory_type: str | None, query_text: str) -> bool:
    """Check if accessory type is allowed for outfit inclusion.

    Accessory candidates exclude socks, gloves, body_jewelry, and hair unless
    explicitly requested in the query. Prefers hat, eyewear, bag, scarf, belt, watch, jewelry.
    """
    if not accessory_type:
        return True
    acc_lower = accessory_type.lower()
    restricted = {"socks", "gloves", "body_jewelry", "hair"}
    if acc_lower in restricted:
        q_lower = query_text.lower()
        # Check if query asks for this specific accessory
        if acc_lower == "socks" and re.search(r"\bsocks?\b", q_lower):
            return True
        if acc_lower == "gloves" and re.search(r"\bgloves?\b|\bmittens?\b", q_lower):
            return True
        if acc_lower == "body_jewelry" and re.search(
            r"\b(?:piercing|plugs|tunnels|gauges|barbell|nose bone)\b", q_lower
        ):
            return True
        if acc_lower == "hair":
            return bool(
                re.search(
                    r"\b(?:headband|hairpin|hair clip|hair tie|scrunchie|scrunchy)\b", q_lower
                )
            )
        return False
    return True


def fetch_slot_candidates(
    slot: str,
    raw_query: str,
    parsed: ParsedQuery,
    catalog_repo: CatalogRepository,
    hybrid_index: HybridIndex,
    quality_bounds: tuple[float, float],
    top_candidates_per_slot: int = 8,
) -> list[tuple[Product, float, float]]:
    """Retrieve and score top candidates for a specific outfit clothing slot.

    Never retrieves innerwear. Excludes restricted accessories. Enforces similarity floor.
    """
    if slot == "innerwear":
        return []

    # Slot-forced parse
    slot_parsed = parsed.model_copy(update={"slots": [slot]})

    raw_candidates, _ = hybrid_index.search(
        raw_query=raw_query,
        normalized_query_en=parsed.normalized_query_en,
        retrieval_k=50,
        rrf_k=settings.rrf_k,
    )

    if not raw_candidates:
        return []

    cand_ids = [c[0] for c in raw_candidates]
    product_map = catalog_repo.get_by_ids(cand_ids)

    valid_candidates: list[tuple[Product, float, float]] = []
    min_q, max_q = quality_bounds
    q_range = max(max_q - min_q, 1e-6)

    max_fused = max((c[1] for c in raw_candidates), default=1.0)
    if max_fused <= 0:
        max_fused = 1.0

    for pid, fused_score, sim in raw_candidates:
        if pid not in product_map:
            continue
        prod = product_map[pid]

        # Slot must match
        if (prod.slot or "").lower() != slot.lower():
            continue

        # Strict hard filters (slot, age_group, individual price bound)
        if not passes_strict_filters(
            prod, slot_parsed, gender_include_unknown=settings.gender_include_unknown
        ):
            continue

        # Enforce minimum item price in outfit mode (D7: OUTFIT_MIN_ITEM_PRICE)
        if prod.price is not None and prod.price < settings.outfit_min_item_price:
            continue

        # Accessory type exclusion rule
        if slot == "accessory" and not is_accessory_allowed_type(
            prod.accessory_type, raw_query + " " + parsed.normalized_query_en
        ):
            continue

        # Per-slot similarity floor
        if sim < settings.outfit_similarity_floor:
            continue

        # Score normalization to [0, 1] + soft boosts
        norm_fused = fused_score / max_fused
        q_norm = (prod.quality_score - min_q) / q_range
        boost = compute_soft_boost(
            prod,
            parsed,
            quality_norm=q_norm,
            quality_weight=settings.quality_weight,
            boost_weight_season=settings.boost_weight_season,
            boost_weight_occasion=settings.boost_weight_occasion,
            boost_weight_color=settings.boost_weight_color,
            boost_weight_brand=settings.boost_weight_brand,
        )
        final_score = norm_fused + boost
        valid_candidates.append((prod, final_score, sim))

    # Sort descending
    valid_candidates.sort(key=lambda x: x[1], reverse=True)

    # Near-duplicate collapse per slot
    deduped, _ = collapse_near_duplicates(valid_candidates)
    return deduped[:top_candidates_per_slot]


def compose_outfit(
    raw_query: str,
    parsed: ParsedQuery,
    catalog_repo: CatalogRepository,
    hybrid_index: HybridIndex,
    used_fallback: bool,
    start_time: float,
) -> OutfitResponse:
    """Compose a coherent, budget-compliant fashion outfit (B4).

    Templates:
    1. full_body + footwear + accessory
    2. top + bottom + footwear + accessory

    Enforces age_group coherence, gender compatibility, accessory rules, and total budget.
    """
    import time

    warnings = list(parsed.warnings)

    if not parsed.is_fashion_query:
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        meta = SearchMeta(
            parsed_filters={},
            used_fallback=used_fallback,
            latency_ms=round(elapsed_ms, 2),
            index_version=hybrid_index.index_version,
            excluded_by_filters=0,
            low_confidence=False,
            warnings=warnings,
        )
        return OutfitResponse(
            outfit=None,
            meta=meta,
            message="not_a_fashion_query",
        )

    quality_bounds = catalog_repo.get_quality_score_bounds()

    # Pre-fetch candidates for each potential outfit slot
    slots_to_fetch = ["full_body", "top", "bottom", "footwear", "accessory"]
    candidates_by_slot: dict[str, list[tuple[Product, float, float]]] = {}
    for s in slots_to_fetch:
        candidates_by_slot[s] = fetch_slot_candidates(
            s, raw_query, parsed, catalog_repo, hybrid_index, quality_bounds
        )

    # Determine Coherence: Gender & Age
    target_age = (parsed.age_group or "adult").lower()

    # Determine Target Gender
    if parsed.gender:
        target_gender = parsed.gender.lower()
    else:
        # Find best-scoring non-unisex item across all candidates
        best_cand: Product | None = None
        best_cand_score = -1.0
        for slot_cands in candidates_by_slot.values():
            for prod, score, _ in slot_cands:
                p_gen = (prod.gender or "unknown").lower()
                if p_gen in {"men", "women"} and score > best_cand_score:
                    best_cand_score = score
                    best_cand = prod
        target_gender = (best_cand.gender if best_cand else "unisex").lower()

    # Filter candidate pools for gender & age coherence
    coherent_cands: dict[str, list[tuple[Product, float, float]]] = {}
    for slot, cands in candidates_by_slot.items():
        coherent_list: list[tuple[Product, float, float]] = []
        for prod, score, sim in cands:
            p_age = (prod.age_group or "adult").lower()
            if p_age != target_age:
                continue

            p_gen = (prod.gender or "unknown").lower()
            if target_gender == "men" and p_gen not in {"men", "unisex"}:
                continue
            if target_gender == "women" and p_gen not in {"women", "unisex"}:
                continue
            if target_gender == "unisex" and p_gen != "unisex":
                continue

            coherent_list.append((prod, score, sim))
        coherent_cands[slot] = coherent_list

    # Templates to evaluate
    templates = [
        ("top_bottom_footwear_accessory", ["top", "bottom", "footwear", "accessory"]),
        ("full_body_footwear_accessory", ["full_body", "footwear", "accessory"]),
    ]

    best_outfit_items: list[SearchResultItem] | None = None
    best_outfit_template_name: str | None = None
    best_outfit_missing_slots: list[str] = []
    best_outfit_score = -1.0
    best_outfit_price = 0.0

    max_budget = parsed.max_price

    for template_name, template_slots in templates:
        # Check active slot availability with fallback dropping order: accessory -> footwear
        active_slots_sequence = [
            list(template_slots),
            [s for s in template_slots if s != "accessory"],
            [s for s in template_slots if s not in {"accessory", "footwear"}],
        ]
        # An outfit must have at least 2 items (SPEC 5.5)
        active_slots_sequence = [s for s in active_slots_sequence if len(s) >= 2]

        for current_slots in active_slots_sequence:
            # Check if all slots in current_slots have at least 1 candidate
            if not all(len(coherent_cands[s]) > 0 for s in current_slots):
                continue

            # Generate cartesian product of candidates
            pools = [coherent_cands[s] for s in current_slots]
            best_combo: list[tuple[Product, float, float]] | None = None
            best_combo_mean_score = -1.0
            best_combo_price = 0.0

            for combo in itertools.product(*pools):
                # Enforce combo-level age coherence from item attributes (SPEC D1c)
                ages = {p.age_group for p, _, _ in combo if p.age_group is not None}
                if len(ages) > 1:
                    continue

                # Enforce combo-level gender coherence from item attributes (SPEC D1c)
                genders = {
                    p.gender
                    for p, _, _ in combo
                    if p.gender not in {"unisex", "unknown", None}
                }
                if len(genders) > 1:
                    continue

                total_p = sum(prod.price or 0.0 for prod, _, _ in combo)
                if max_budget is not None and total_p > max_budget:
                    continue

                mean_score = sum(score for _, score, _ in combo) / len(combo)
                if mean_score > best_combo_mean_score:
                    best_combo_mean_score = mean_score
                    best_combo = list(combo)
                    best_combo_price = total_p

            if best_combo is not None:
                # Found valid outfit for this slot combination
                if best_combo_mean_score > best_outfit_score:
                    best_outfit_score = best_combo_mean_score
                    best_outfit_template_name = template_name
                    best_outfit_price = best_combo_price
                    best_outfit_missing_slots = [
                        s for s in template_slots if s not in current_slots
                    ]

                    # Build SearchResultItem objects
                    items: list[SearchResultItem] = []
                    for idx, (prod, score, sim) in enumerate(best_combo):
                        role = current_slots[idx]
                        reason = generate_item_explanation(
                            prod, parsed, raw_query, sim, slot_role=role
                        )
                        items.append(
                            SearchResultItem(
                                product_id=prod.parent_asin,
                                title=prod.title,
                                price=prod.price,
                                brand=prod.store,
                                image_url=prod.image_url,
                                slot=prod.slot,
                                gender=prod.gender,
                                age_group=prod.age_group,
                                score=round(score, 4),
                                similarity=round(sim, 4),
                                reason=reason,
                            )
                        )
                    best_outfit_items = items
                break  # Stop checking reduced slots for this template once satisfied

    elapsed_ms = (time.perf_counter() - start_time) * 1000.0

    meta = SearchMeta(
        parsed_filters={
            k: v
            for k, v in {
                "gender": parsed.gender,
                "age_group": parsed.age_group,
                "max_price": parsed.max_price,
                "min_price": parsed.min_price,
            }.items()
            if v is not None
        },
        used_fallback=used_fallback,
        latency_ms=round(elapsed_ms, 2),
        index_version=hybrid_index.index_version,
        excluded_by_filters=0,
        low_confidence=False,
        warnings=warnings,
    )

    if not best_outfit_items or len(best_outfit_items) < 2:
        # Check why outfit failed
        msg = (
            "no_outfit_within_budget" if max_budget is not None else "insufficient_items_for_outfit"
        )
        return OutfitResponse(
            outfit=None,
            meta=meta,
            message=msg,
        )

    is_complete = len(best_outfit_missing_slots) == 0

    outfit_payload = OutfitPayload(
        items=best_outfit_items,
        total_price=round(best_outfit_price, 2),
        complete=is_complete,
        missing_slots=best_outfit_missing_slots,
        template=best_outfit_template_name or "custom",
    )

    return OutfitResponse(
        outfit=outfit_payload,
        meta=meta,
        message=None,
    )
