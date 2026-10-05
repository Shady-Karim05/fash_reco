"""Outfit composition engine with coherence, template selection, and budget optimization (B4)."""

import itertools
import re

import numpy as np

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
from app.reranker import QueryAwareReranker
from app.schemas import (
    OutfitPayload,
    OutfitResponse,
    Product,
    SearchMeta,
    SearchResultItem,
)

_outfit_reranker = QueryAwareReranker()


def compute_outfit_compatibility_score(
    combo: tuple[tuple[Product, float, float], ...] | list[tuple[Product, float, float]],
    hybrid_index: HybridIndex | None = None,
    pair_cache: dict[tuple[str, str], float] | None = None,
) -> float:
    """Compute semantic and style compatibility score for an outfit candidate combination (Fix 6).

    Signals:
    1. Occasion agreement: bonus when items share occasion tags (formal, casual, beach, etc.)
    2. Season agreement: bonus when items share season tags (summer, winter, etc.)
    3. Style conflict penalty: penalty for clashing styles (formal footwear with athletic gym wear)
    4. Pairwise embedding cohesion: average cosine similarity between item embedding vectors.

    Returns:
        Compatibility score adjustment (typically in range [-0.5, 1.5]).
    """
    if not combo or len(combo) < 2:
        return 0.0

    products = [p for p, _, _ in combo]
    n = len(products)

    # 1. Occasion Agreement
    occasion_counts: dict[str, int] = {}
    for p in products:
        for occ in p.occasions or []:
            occ_lower = occ.lower()
            occasion_counts[occ_lower] = occasion_counts.get(occ_lower, 0) + 1

    shared_occasions = sum(1 for cnt in occasion_counts.values() if cnt >= 2)
    occasion_bonus = 0.25 * shared_occasions

    # 2. Season Agreement
    season_counts: dict[str, int] = {}
    for p in products:
        for s in p.seasons or []:
            s_lower = s.lower()
            season_counts[s_lower] = season_counts.get(s_lower, 0) + 1

    shared_seasons = sum(1 for cnt in season_counts.values() if cnt >= 2)
    season_bonus = 0.15 * shared_seasons

    # 3. Style Conflict Penalty
    conflict_penalty = 0.0
    has_formal = False
    has_athletic = False
    has_novelty = False

    for p in products:
        t_lower = (p.title or "").lower()
        occ_set = {o.lower() for o in (p.occasions or [])}

        formal_kws = ("formal", "tuxedo", "suit", "cocktail", "gown", "blazer", "dress shoes")
        if "formal" in occ_set or any(kw in t_lower for kw in formal_kws):
            has_formal = True
        athletic_kws = ("gym", "workout", "athletic", "compression", "running shoes", "sweatpants")
        if "workout" in occ_set or any(kw in t_lower for kw in athletic_kws):
            has_athletic = True
        if any(kw in t_lower for kw in ("led", "festival", "costume", "rainbow", "light up")):
            has_novelty = True

    if has_formal and has_athletic:
        conflict_penalty += 0.5
    if has_formal and has_novelty:
        conflict_penalty += 0.7

    # 4. Pairwise Dense Embedding Cohesion
    cohesion = 0.0
    if hybrid_index is not None and getattr(hybrid_index, "vector_index", None) is not None:
        pair_sims: list[float] = []
        for i in range(n):
            for j in range(i + 1, n):
                pid_i = products[i].parent_asin
                pid_j = products[j].parent_asin
                cache_key = (pid_i, pid_j) if pid_i <= pid_j else (pid_j, pid_i)

                if pair_cache is not None and cache_key in pair_cache:
                    pair_sims.append(pair_cache[cache_key])
                else:
                    v_i = hybrid_index.vector_index.get_vector(pid_i)
                    v_j = hybrid_index.vector_index.get_vector(pid_j)
                    if v_i is not None and v_j is not None:
                        sim_val = float(np.dot(v_i, v_j))
                        pair_sims.append(sim_val)
                        if pair_cache is not None:
                            pair_cache[cache_key] = sim_val

        if pair_sims:
            cohesion = float(np.mean(pair_sims))

    compat_score = cohesion + occasion_bonus + season_bonus - conflict_penalty
    return round(compat_score, 4)


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
    retrieval_k: int = 50,
    raw_candidates: list[tuple[str, float, float]] | None = None,
    product_map: dict[str, Product] | None = None,
) -> list[tuple[Product, float, float]]:
    """Retrieve and score top candidates for a specific outfit clothing slot.

    Never retrieves innerwear. Excludes restricted accessories. Enforces similarity floor.
    """
    if slot == "innerwear":
        return []

    # Slot-forced parse
    slot_parsed = parsed.model_copy(update={"slots": [slot]})

    if raw_candidates is None:
        raw_candidates, _ = hybrid_index.search(
            raw_query=raw_query,
            normalized_query_en=parsed.normalized_query_en,
            retrieval_k=retrieval_k,
            rrf_k=settings.rrf_k,
        )

    if not raw_candidates:
        return []

    if product_map is None:
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

    # Rerank slot candidates using QueryAwareReranker
    if settings.reranker_enabled and valid_candidates:
        reranked = _outfit_reranker.rerank(
            raw_query=raw_query,
            parsed=slot_parsed,
            candidates=valid_candidates,
            top_k=top_candidates_per_slot,
            max_fused=max_fused,
        )
    else:
        valid_candidates.sort(key=lambda x: x[1], reverse=True)
        reranked = valid_candidates

    # Near-duplicate collapse per slot
    deduped, _ = collapse_near_duplicates(reranked)
    return deduped[:top_candidates_per_slot]


def compose_outfit(
    raw_query: str,
    parsed: ParsedQuery,
    catalog_repo: CatalogRepository,
    hybrid_index: HybridIndex,
    used_fallback: bool,
    start_time: float,
    candidate_depths: list[int] | None = None,
) -> OutfitResponse:
    """Compose a coherent, budget-compliant fashion outfit (B4).

    Templates:
    1. full_body + footwear + accessory
    2. top + bottom + footwear + accessory

    Enforces age_group coherence, gender compatibility, accessory rules, and total budget.
    Implements progressive candidate expansion across candidate pool depths [50, 100, 200, 400]
    without weakening any hard constraints.
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

    depths = candidate_depths or settings.outfit_candidate_depths
    quality_bounds = catalog_repo.get_quality_score_bounds()
    slots_to_fetch = ["full_body", "top", "bottom", "footwear", "accessory"]

    best_outfit_items: list[SearchResultItem] | None = None
    best_outfit_template_name: str | None = None
    best_outfit_missing_slots: list[str] = []
    best_outfit_score = -1.0
    best_outfit_price = 0.0

    max_budget = parsed.max_price
    pair_cache: dict[tuple[str, str], float] = {}
    cumulative_product_map: dict[str, Product] = {}

    for k in depths:
        # 1. Fetch raw hybrid candidates at depth k
        raw_candidates, _ = hybrid_index.search(
            raw_query=raw_query,
            normalized_query_en=parsed.normalized_query_en,
            retrieval_k=k,
            rrf_k=settings.rrf_k,
        )
        if not raw_candidates:
            continue

        cand_ids = [c[0] for c in raw_candidates]
        missing_ids = [cid for cid in cand_ids if cid not in cumulative_product_map]
        if missing_ids:
            cumulative_product_map.update(catalog_repo.get_by_ids(missing_ids))
        product_map = cumulative_product_map

        # 2. Extract valid candidates per slot
        candidates_by_slot: dict[str, list[tuple[Product, float, float]]] = {}
        for s in slots_to_fetch:
            candidates_by_slot[s] = fetch_slot_candidates(
                slot=s,
                raw_query=raw_query,
                parsed=parsed,
                catalog_repo=catalog_repo,
                hybrid_index=hybrid_index,
                quality_bounds=quality_bounds,
                top_candidates_per_slot=8,
                retrieval_k=k,
                raw_candidates=raw_candidates,
                product_map=product_map,
            )

        # 3. Determine Coherence: Gender & Age
        target_age = (parsed.age_group or "adult").lower()
        if parsed.gender:
            target_gender = parsed.gender.lower()
        else:
            best_cand: Product | None = None
            best_cand_score = -1.0
            for slot_cands in candidates_by_slot.values():
                for prod, score, _ in slot_cands:
                    p_gen = (prod.gender or "unknown").lower()
                    if p_gen in {"men", "women"} and score > best_cand_score:
                        best_cand_score = score
                        best_cand = prod
            target_gender = (best_cand.gender if best_cand else "unisex").lower()

        # 4. Filter candidate pools for gender & age coherence
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

        # 5. Evaluate templates
        templates = [
            ("top_bottom_footwear_accessory", ["top", "bottom", "footwear", "accessory"]),
            ("full_body_footwear_accessory", ["full_body", "footwear", "accessory"]),
        ]

        found_full_template = False

        for template_name, template_slots in templates:
            active_slots_sequence = [
                list(template_slots),
                [s for s in template_slots if s != "accessory"],
                [s for s in template_slots if s not in {"accessory", "footwear"}],
            ]
            active_slots_sequence = [s for s in active_slots_sequence if len(s) >= 2]

            for current_slots in active_slots_sequence:
                if not all(len(coherent_cands[s]) > 0 for s in current_slots):
                    continue

                pools = [coherent_cands[s] for s in current_slots]
                best_combo: list[tuple[Product, float, float]] | None = None
                best_combo_mean_score = -1.0
                best_combo_price = 0.0

                for combo in itertools.product(*pools):
                    ages = {p.age_group for p, _, _ in combo if p.age_group is not None}
                    if len(ages) > 1:
                        continue

                    genders = {
                        p.gender for p, _, _ in combo if p.gender not in {"unisex", "unknown", None}
                    }
                    if len(genders) > 1:
                        continue

                    total_p = sum(prod.price or 0.0 for prod, _, _ in combo)
                    if max_budget is not None and total_p > max_budget:
                        continue

                    mean_score = sum(score for _, score, _ in combo) / len(combo)
                    compat_score = compute_outfit_compatibility_score(
                        combo, hybrid_index, pair_cache=pair_cache
                    )
                    combo_score = mean_score + settings.outfit_compatibility_weight * compat_score
                    if combo_score > best_combo_mean_score:
                        best_combo_mean_score = combo_score
                        best_combo = list(combo)
                        best_combo_price = total_p

                if best_combo is not None:
                    cur_items: list[SearchResultItem] = []
                    for idx, (prod, score, sim) in enumerate(best_combo):
                        role = current_slots[idx]
                        reason = generate_item_explanation(
                            prod, parsed, raw_query, sim, slot_role=role
                        )
                        cur_items.append(
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

                    cur_missing = [s for s in template_slots if s not in current_slots]

                    update_outfit = (
                        best_outfit_items is None
                        or len(cur_items) > len(best_outfit_items)
                        or (
                            len(cur_items) == len(best_outfit_items)
                            and best_combo_mean_score > best_outfit_score
                        )
                    )

                    if update_outfit:
                        best_outfit_score = best_combo_mean_score
                        best_outfit_template_name = template_name
                        best_outfit_price = best_combo_price
                        best_outfit_missing_slots = cur_missing
                        best_outfit_items = cur_items

                    if len(current_slots) == len(template_slots):
                        found_full_template = True

                    # Break fallback sequence once valid combo for this template is found
                    break

        # Progressive expansion stopping criteria:
        # A. Full 4-item outfit found (cannot exceed 4 items)
        if best_outfit_items is not None and len(best_outfit_items) >= 4:
            break
        # B. Full 3-item dress template found (full_body + footwear + accessory)
        if found_full_template and best_outfit_items is not None and len(best_outfit_items) >= 3:
            break

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
