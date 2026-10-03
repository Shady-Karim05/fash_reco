"""Comprehensive evaluation benchmark suite for Semantic Fashion Search."""

import argparse
import csv
import json
import random
import re
import shutil
import sys
import tempfile
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.catalog import CatalogRepository
from app.config import settings
from app.embedder import SentenceTransformerEmbedder
from app.index import HybridIndex
from app.llm.base import LLMClient
from app.llm.gemini import GeminiClient
from app.parser import (
    QueryParser,
    load_real_parses,
)
from app.pipeline import transform_raw_record
from app.schemas import SearchRequest
from app.service import SearchService


class OracleLLMClient(LLMClient):
    """Mock LLM client returning ground-truth hand-crafted oracle parses."""

    def __init__(self, oracle_map: dict[str, dict[str, Any]]) -> None:
        self.oracle_map = dict(oracle_map)

    def complete_json(self, system: str, user: str, timeout: float = 5.0) -> str:
        q = user.strip()
        if q in self.oracle_map:
            return json.dumps(self.oracle_map[q])
        fallback = QueryParser.fallback_parse(q)
        return fallback.model_dump_json()


class ForcedFailingLLMClient(LLMClient):
    """Client that simulates LLM timeout and 429 quota exhaustion (D1d)."""

    def __init__(self) -> None:
        self.call_count = 0

    def complete_json(self, system: str, user: str, timeout: float = 5.0) -> str:
        self.call_count += 1
        if self.call_count % 2 == 1:
            raise TimeoutError("Simulated LLM call timeout")
        raise RuntimeError("Gemini API error: 429 RESOURCE_EXHAUSTED")


class ReplayLLMClient(LLMClient):
    """Client that replays recorded real LLM parses from evals/real_parses.jsonl (D3)."""

    def __init__(self, recorded_map: dict[str, dict[str, Any]]) -> None:
        self.recorded_map = recorded_map

    def complete_json(self, system: str, user: str, timeout: float = 5.0) -> str:
        q = user.strip()
        if q in self.recorded_map:
            return json.dumps(self.recorded_map[q]["parse"])
        fallback = QueryParser.fallback_parse(q)
        return fallback.model_dump_json()


def check_spotcheck_overwrite_protection(
    spotcheck_file: Path,
    refresh_spotcheck: bool,
    force: bool,
) -> bool:
    """Validate overwrite protection for evals/spotcheck.csv (D6)."""
    if not spotcheck_file.is_file():
        return True
    if not refresh_spotcheck:
        print(
            f"[Spotcheck] Existing {spotcheck_file} preserved "
            "(pass --refresh-spotcheck to refresh)."
        )
        return False

    has_non_blank_grade = False
    with open(spotcheck_file, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if (row.get("grade") or "").strip():
                has_non_blank_grade = True
                break

    if has_non_blank_grade and not force:
        print(
            f"[Spotcheck] Refusing to refresh {spotcheck_file}: annotated grades exist. "
            "Pass --force to overwrite."
        )
        return False
    return True


def evaluate_search(
    queries_data: list[dict[str, Any]],
    service: SearchService,
    mode_label: str,
    measure_latency: bool = True,
) -> dict[str, Any]:
    """Run search benchmark over queries and compute retrieval and constraint metrics."""
    p_at_5_list: list[float] = []
    r_at_5_list: list[float] = []
    mrr_at_10_list: list[float] = []
    latencies: list[float] = []

    price_violations = 0
    gender_violations = 0
    age_violations = 0
    slot_violations = 0
    english_violations = 0
    degraded_mode_violations = 0

    kids_leakages = 0
    innerwear_leakages = 0
    zero_result_count = 0
    low_conf_count = 0

    duplicate_count_top5 = 0
    total_evaluated_top5_items = 0

    intent_results: dict[str, dict[str, list[str]]] = {}
    zero_relevant_queries: list[dict[str, Any]] = []
    all_evaluated_triples: list[dict[str, Any]] = []

    # Filter to search queries (skip outfit-only queries)
    search_queries = [q for q in queries_data if q.get("mode") != "outfit"]

    # Verify cache is bypassed during measurement loop (D2)
    initial_cache_hits = service.query_cache.hits

    for q_item in search_queries:
        q_id = q_item["id"]
        q_text = q_item["query"]
        lang = q_item.get("language", "en")
        intent_id = q_item.get("intent_id", q_id)
        re_pat = re.compile(q_item["relevance_regex"], re.IGNORECASE)
        constraints = q_item.get("constraints", {})

        # Clear query cache to guarantee un-cached measurements
        service.query_cache.clear()

        t0 = time.perf_counter()
        resp = service.search(SearchRequest(query=q_text, top_k=10, mode="product"))
        lat_ms = (time.perf_counter() - t0) * 1000.0
        if measure_latency:
            latencies.append(lat_ms)

        if resp.meta.low_confidence:
            low_conf_count += 1

        top5 = resp.results[:5]
        top10 = resp.results[:10]

        if not top5:
            zero_result_count += 1

        if intent_id not in intent_results:
            intent_results[intent_id] = {}
        intent_results[intent_id][lang] = [it.product_id for it in top5]

        # Near-duplicate check in top 5
        seen_keys = set()
        for item in top5:
            total_evaluated_top5_items += 1
            key = f"{item.brand}::{item.title.lower()}"
            if key in seen_keys:
                duplicate_count_top5 += 1
            seen_keys.add(key)

        # Precision@5 and constraint checks
        relevant_top5 = 0
        expected_fashion = q_item.get("oracle_parse", {}).get("is_fashion_query", True)

        for rank, item in enumerate(top5, 1):
            is_rel = bool(re_pat.search(item.title))
            if is_rel:
                relevant_top5 += 1

            all_evaluated_triples.append(
                {
                    "mode": mode_label,
                    "query": q_text,
                    "language": lang,
                    "rank": rank,
                    "title": item.title,
                    "slot": item.slot,
                    "gender": item.gender,
                    "age_group": item.age_group,
                    "price": item.price,
                    "relevant": is_rel,
                }
            )

            if not expected_fashion:
                continue

            item_violation = False
            # Price
            if (
                constraints.get("max_price") is not None
                and item.price is not None
                and item.price > constraints["max_price"]
            ):
                price_violations += 1
                item_violation = True
            if (
                constraints.get("min_price") is not None
                and item.price is not None
                and item.price < constraints["min_price"]
            ):
                price_violations += 1
                item_violation = True

            # Gender
            if constraints.get("gender") == "men" and item.gender not in {"men", "unisex"}:
                gender_violations += 1
                item_violation = True
            if constraints.get("gender") == "women" and item.gender not in {"women", "unisex"}:
                gender_violations += 1
                item_violation = True

            # Age group & Kids leakage
            is_kids_query = constraints.get("age_group") == "kids"
            if is_kids_query and item.age_group != "kids":
                age_violations += 1
                item_violation = True
            if not is_kids_query and item.age_group == "kids":
                kids_leakages += 1

            # Slot
            if constraints.get("slot") and item.slot != constraints["slot"]:
                slot_violations += 1
                item_violation = True

            # Innerwear leakage
            if constraints.get("slot") != "innerwear" and item.slot == "innerwear":
                innerwear_leakages += 1

            if item_violation:
                if lang == "en":
                    english_violations += 1
                else:
                    degraded_mode_violations += 1

        p_at_5 = relevant_top5 / 5.0
        p_at_5_list.append(p_at_5)
        r_at_5 = 1.0 if relevant_top5 > 0 else 0.0
        r_at_5_list.append(r_at_5)

        if relevant_top5 == 0 and expected_fashion:
            zero_relevant_queries.append(
                {
                    "query": q_text,
                    "language": lang,
                    "top5_titles": [it.title for it in top5],
                    "low_confidence": resp.meta.low_confidence,
                    "warnings": resp.meta.warnings,
                }
            )

        # MRR@10
        mrr = 0.0
        for rank, item in enumerate(top10, 1):
            if re_pat.search(item.title):
                mrr = 1.0 / rank
                break
        mrr_at_10_list.append(mrr)

    assert service.query_cache.hits == initial_cache_hits, (
        f"Cache hit counter increased during un-cached loop! Hits: {service.query_cache.hits}"
    )

    # Multilingual Consistency (mean pairwise top-5 Jaccard overlap)
    jaccard_scores: list[float] = []
    for _intent, lang_map in intent_results.items():
        lang_list = list(lang_map.keys())
        for i in range(len(lang_list)):
            for j in range(i + 1, len(lang_list)):
                s1 = set(lang_map[lang_list[i]])
                s2 = set(lang_map[lang_list[j]])
                if s1 or s2:
                    jacc = len(s1 & s2) / len(s1 | s2)
                    jaccard_scores.append(jacc)

    mean_multilingual_overlap = float(np.mean(jaccard_scores)) if jaccard_scores else 0.0

    # Uniform random sampling of triples (D2)
    rng = random.Random(42)
    sample_triples = (
        rng.sample(all_evaluated_triples, min(10, len(all_evaluated_triples)))
        if all_evaluated_triples
        else []
    )

    return {
        "mode": mode_label,
        "precision_at_5": round(float(np.mean(p_at_5_list)), 4) if p_at_5_list else 0.0,
        "recall_at_5": round(float(np.mean(r_at_5_list)), 4) if r_at_5_list else 0.0,
        "mrr_at_10": round(float(np.mean(mrr_at_10_list)), 4) if mrr_at_10_list else 0.0,
        "latency_p50_ms": round(float(np.percentile(np.array(latencies), 50)), 2)
        if latencies
        else 0.0,
        "latency_p95_ms": round(float(np.percentile(np.array(latencies), 95)), 2)
        if latencies
        else 0.0,
        "price_violations": price_violations,
        "gender_violations": gender_violations,
        "age_violations": age_violations,
        "slot_violations": slot_violations,
        "total_constraint_violations": price_violations
        + gender_violations
        + age_violations
        + slot_violations,
        "english_violations": english_violations,
        "degraded_mode_violations": degraded_mode_violations,
        "kids_leakage": kids_leakages,
        "innerwear_leakage": innerwear_leakages,
        "duplicate_rate_top5": round(
            duplicate_count_top5 / max(total_evaluated_top5_items, 1) * 100.0, 2
        ),
        "zero_result_rate": round(zero_result_count / max(len(search_queries), 1) * 100.0, 2),
        "low_confidence_rate": round(low_conf_count / max(len(search_queries), 1) * 100.0, 2),
        "multilingual_top5_overlap": round(mean_multilingual_overlap * 100.0, 2),
        "zero_relevant_queries": zero_relevant_queries,
        "sample_triples": sample_triples,
    }


def evaluate_cached_latency(
    queries_data: list[dict[str, Any]],
    service: SearchService,
) -> tuple[float, float]:
    """Measure cached latency from its own labeled run (D2)."""
    search_queries = [q for q in queries_data if q.get("mode") != "outfit"][:20]
    service.query_cache.clear()

    # Pass 1: warm cache
    for q in search_queries:
        service.search(SearchRequest(query=q["query"], top_k=5, mode="product"))

    # Pass 2: measure cached hits
    cached_latencies: list[float] = []
    initial_hits = service.query_cache.hits
    for q in search_queries:
        t0 = time.perf_counter()
        _ = service.search(SearchRequest(query=q["query"], top_k=5, mode="product"))
        cached_latencies.append((time.perf_counter() - t0) * 1000.0)

    hits_diff = service.query_cache.hits - initial_hits
    assert hits_diff > 0, f"Expected cache hits during cached latency run, got {hits_diff}"

    p50 = float(np.percentile(np.array(cached_latencies), 50))
    p95 = float(np.percentile(np.array(cached_latencies), 95))
    return round(p50, 2), round(p95, 2)


def evaluate_outfits(
    queries_data: list[dict[str, Any]],
    service: SearchService,
) -> dict[str, Any]:
    """Evaluate outfit composition on all outfit benchmark queries (D1c)."""
    outfit_items = [q for q in queries_data if q.get("mode") == "outfit"]
    if not outfit_items:
        outfit_items = [
            {"query": "beach outfit for summer under $80", "budget": 80.0},
            {"query": "men's outfit for a winter wedding", "budget": None},
            {"query": "casual outfit for a 5 year old girl", "budget": None},
            {"query": "gym outfit for women", "budget": None},
            {"query": "complete beach outfit under $15", "budget": 15.0},
        ]

    total_queries = len(outfit_items)
    composed_count = 0
    at_least_3_slots = 0
    budget_compliant_count = 0
    coherent_gender_count = 0
    coherent_age_count = 0
    innerwear_count = 0
    composed_outfit_details = []

    for q_item in outfit_items:
        q_text = q_item["query"]
        budget = q_item.get("budget", q_item.get("constraints", {}).get("max_price"))
        resp = service.search(SearchRequest(query=q_text, top_k=10, mode="outfit"))

        if resp.outfit is None:
            # Check if this was a valid budget refusal (budget too small)
            if budget is not None and budget <= 15.0 and resp.message == "no_outfit_within_budget":
                budget_compliant_count += 1
            continue

        composed_count += 1
        items = resp.outfit.items
        if len(items) >= 3:
            at_least_3_slots += 1

        # Budget compliance
        if budget is not None:
            if resp.outfit.total_price <= budget:
                budget_compliant_count += 1
        else:
            budget_compliant_count += 1

        # Coherence
        ages = {it.age_group for it in items if it.age_group is not None}
        is_age_coherent = len(ages) <= 1
        if is_age_coherent:
            coherent_age_count += 1

        genders = {it.gender for it in items if it.gender not in {"unisex", "unknown", None}}
        is_gender_coherent = len(genders) <= 1
        if is_gender_coherent:
            coherent_gender_count += 1

        for it in items:
            if it.slot == "innerwear":
                innerwear_count += 1

        composed_outfit_details.append(
            {
                "query": q_text,
                "total_price": resp.outfit.total_price,
                "items": [it.title for it in items],
                "ages": [it.age_group for it in items],
                "genders": [it.gender for it in items],
                "slots": [it.slot for it in items],
            }
        )

    return {
        "outfit_queries_total": total_queries,
        "outfits_composed": composed_count,
        "completeness_k_of_n": f"{at_least_3_slots} of {total_queries}",
        "completeness_pct": round(at_least_3_slots / max(total_queries, 1) * 100.0, 2),
        "budget_compliance_k_of_n": f"{budget_compliant_count} of {total_queries}",
        "budget_compliance_pct": round(budget_compliant_count / max(total_queries, 1) * 100.0, 2),
        "age_coherence_k_of_n": f"{coherent_age_count} of {composed_count}",
        "age_coherence_pct": round(coherent_age_count / max(composed_count, 1) * 100.0, 2),
        "gender_coherence_k_of_n": f"{coherent_gender_count} of {composed_count}",
        "gender_coherence_pct": round(coherent_gender_count / max(composed_count, 1) * 100.0, 2),
        "innerwear_in_outfits": innerwear_count,
        "composed_outfits": composed_outfit_details,
    }


def evaluate_forced_fallback_pass(
    queries_data: list[dict[str, Any]],
    catalog_repo: CatalogRepository,
    hybrid_index: HybridIndex,
) -> dict[str, Any]:
    """Test forced fallback resilience across all queries with timeout and 429 errors (D1d)."""
    failing_client = ForcedFailingLLMClient()
    failing_parser = QueryParser(failing_client)
    failing_service = SearchService(
        catalog_repo=catalog_repo,
        hybrid_index=hybrid_index,
        parser=failing_parser,
    )

    per_lang_total: dict[str, int] = Counter()
    per_lang_success: dict[str, int] = Counter()

    for q in queries_data:
        lang = q.get("language", "en")
        per_lang_total[lang] += 1
        try:
            mode = "outfit" if q.get("mode") == "outfit" else "product"
            resp = failing_service.search(SearchRequest(query=q["query"], top_k=5, mode=mode))
            if resp is not None and resp.meta.used_fallback:
                per_lang_success[lang] += 1
        except Exception:
            pass

    total_queries = len(queries_data)
    total_success = sum(per_lang_success.values())
    per_lang_pct = {
        lang: round(per_lang_success[lang] / max(per_lang_total[lang], 1) * 100.0, 2)
        for lang in per_lang_total
    }

    return {
        "total_queries": total_queries,
        "total_success": total_success,
        "overall_success_pct": round(total_success / max(total_queries, 1) * 100.0, 2),
        "per_language_success": per_lang_pct,
        "per_language_counts": {
            lang: f"{per_lang_success[lang]} of {per_lang_total[lang]}" for lang in per_lang_total
        },
    }


def evaluate_quality_ablation_mode(
    queries_data: list[dict[str, Any]],
    catalog_repo: CatalogRepository,
    hybrid_index: HybridIndex,
    mode: str,
    oracle_map: dict[str, Any],
) -> dict[str, Any]:
    """Run quality weight 0 vs 0.05 comparison inside each mode on that mode's own results (D2)."""
    search_queries = [q for q in queries_data if q.get("mode") != "outfit"]

    def build_service(q_weight: float) -> SearchService:
        settings.quality_weight = q_weight
        if mode == "oracle":
            parser = QueryParser(OracleLLMClient(oracle_map))
        elif mode == "real":
            recorded = load_real_parses()
            parser = QueryParser(ReplayLLMClient(recorded))
        else:
            parser = QueryParser(None)
        return SearchService(
            catalog_repo=catalog_repo,
            hybrid_index=hybrid_index,
            parser=parser,
        )

    # 1. Evaluate with 0.05
    svc_005 = build_service(0.05)
    res_005 = evaluate_search(search_queries, svc_005, f"{mode}_q005", measure_latency=False)

    # 2. Evaluate with 0.00
    svc_000 = build_service(0.00)
    res_000 = evaluate_search(search_queries, svc_000, f"{mode}_q000", measure_latency=False)

    # Order change detection in top 5
    reordered_query_count = 0
    for q in search_queries:
        r_005 = svc_005.search(SearchRequest(query=q["query"], top_k=5, mode="product"))
        r_000 = svc_000.search(SearchRequest(query=q["query"], top_k=5, mode="product"))
        ids_005 = [it.product_id for it in r_005.results]
        ids_000 = [it.product_id for it in r_000.results]
        if ids_005 != ids_000:
            reordered_query_count += 1

    # Restore default
    settings.quality_weight = 0.05

    return {
        "mode": mode,
        "quality_weight_0_05": {
            "precision_at_5": res_005["precision_at_5"],
            "recall_at_5": res_005["recall_at_5"],
        },
        "quality_weight_0_00": {
            "precision_at_5": res_000["precision_at_5"],
            "recall_at_5": res_000["recall_at_5"],
        },
        "queries_with_top5_order_change": f"{reordered_query_count} of {len(search_queries)}",
    }


def evaluate_catalog_update_check(temp_dir: Path) -> bool:
    """Validate catalog update check on temporary database copy (C2)."""
    temp_db = temp_dir / "update_check.db"
    shutil.copy2(settings.db_path, temp_db)
    repo = CatalogRepository(temp_db)
    embedder = SentenceTransformerEmbedder(settings.embedding_model_name)
    index = HybridIndex(catalog_repo=repo, embedder=embedder, cache_dir=temp_dir)
    index.build_from_catalog()
    service = SearchService(catalog_repo=repo, hybrid_index=index, parser=QueryParser(None))

    test_item = transform_raw_record(
        {
            "parent_asin": "TEST_UPDATE_ASIN_999",
            "title": "Zirconia Synthetic Test Update Crystal Ring Accessory",
            "price": 29.99,
            "average_rating": 4.8,
            "rating_number": 50,
            "features": ["Synthetic test ring"],
        }
    )

    # Add product
    index.upsert_batch_atomic([test_item])

    # Confirm product is returned
    resp1 = service.search(
        SearchRequest(query="Zirconia Synthetic Test Update Crystal Ring", top_k=5)
    )
    ids1 = [it.product_id for it in resp1.results]
    if "TEST_UPDATE_ASIN_999" not in ids1:
        return False

    # Delete product
    index.delete_product("TEST_UPDATE_ASIN_999")

    # Confirm product is gone
    resp2 = service.search(
        SearchRequest(query="Zirconia Synthetic Test Update Crystal Ring", top_k=5)
    )
    ids2 = [it.product_id for it in resp2.results]
    return "TEST_UPDATE_ASIN_999" not in ids2


def run_evals(
    mode: str = "fallback",
    replay: bool = False,
    refresh_spotcheck: bool = False,
    force: bool = False,
) -> None:
    """Main evaluation orchestrator (D1, D2, D3, D4, D6)."""
    print(f"=== PHASE 6: EVALUATION SUITE [Mode: {mode.upper()}] ===")
    if mode == "oracle":
        label_msg = (
            "Label: oracle parse (upper bound only; multilingual overlap 100% by construction)\n"
        )
    elif mode == "real":
        label_msg = f"Label: real LLM (recorded parses={replay})\n"
    else:
        label_msg = (
            "Label: forced fallback (degraded-mode; plumbing and error handling verification)\n"
        )
    print(label_msg)

    queries_file = Path("evals/queries.json")
    if not queries_file.is_file():
        print(f"Error: {queries_file} not found.")
        sys.exit(1)

    with open(queries_file, encoding="utf-8") as f:
        queries_data: list[dict[str, Any]] = json.load(f)

    print(f"Loaded {len(queries_data)} benchmark queries from {queries_file}")

    oracle_map = {q["query"].strip(): q.get("oracle_parse", {}) for q in queries_data}

    # Initialize Repo and Hybrid Index
    repo = CatalogRepository(settings.db_path)
    embedder = SentenceTransformerEmbedder(settings.embedding_model_name)
    hybrid_index = HybridIndex(catalog_repo=repo, embedder=embedder, cache_dir=settings.data_dir)
    hybrid_index.build_from_catalog()

    if mode == "oracle":
        client: LLMClient = OracleLLMClient(oracle_map)
        parser = QueryParser(client)
    elif mode == "real":
        if replay:
            recorded = load_real_parses()
            print(
                f"[Real LLM Replay] Loaded {len(recorded)} recorded parses "
                "from evals/real_parses.jsonl"
            )
            client = ReplayLLMClient(recorded)
            parser = QueryParser(client)
        else:
            if not settings.llm_api_key or not settings.llm_model:
                print("Error: LLM_API_KEY and LLM_MODEL are not configured for real LLM.")
                sys.exit(1)
            client = GeminiClient(api_key=settings.llm_api_key, model=settings.llm_model)
            parser = QueryParser(client)
    else:  # fallback
        parser = QueryParser(None)

    service = SearchService(
        catalog_repo=repo,
        hybrid_index=hybrid_index,
        parser=parser,
    )

    # 1. Search Benchmark Evaluation
    print(f"\n--- RUNNING SEARCH EVALUATION [{mode.upper()}] ---")
    search_metrics = evaluate_search(queries_data, service, mode, measure_latency=True)

    # 2. Cached Latency Evaluation (D2: separate labeled run)
    cached_p50, cached_p95 = evaluate_cached_latency(queries_data, service)
    print(f"  [Cached Latency] p50: {cached_p50} ms | p95: {cached_p95} ms")

    # 3. Forced Fallback Resilience Pass (D1d)
    print("\n--- RUNNING FORCED FALLBACK RESILIENCE PASS (Timeout & 429) ---")
    fallback_resilience = evaluate_forced_fallback_pass(queries_data, repo, hybrid_index)
    tot_s = fallback_resilience["total_success"]
    tot_q = fallback_resilience["total_queries"]
    ov_pct = fallback_resilience["overall_success_pct"]
    print(f"  Forced Fallback Success: {tot_s}/{tot_q} ({ov_pct}%)")
    for lang, counts in fallback_resilience["per_language_counts"].items():
        print(f"    - {lang}: {counts} ({fallback_resilience['per_language_success'][lang]}%)")

    # 4. Outfit Evaluation (D1c)
    print("\n--- RUNNING OUTFIT BENCHMARK ---")
    outfit_metrics = evaluate_outfits(queries_data, service)
    comp_k = outfit_metrics["completeness_k_of_n"]
    comp_pct = outfit_metrics["completeness_pct"]
    print(f"  Completeness        : {comp_k} ({comp_pct}%)")
    budg_k = outfit_metrics["budget_compliance_k_of_n"]
    budg_pct = outfit_metrics["budget_compliance_pct"]
    print(f"  Budget Compliance   : {budg_k} ({budg_pct}%)")
    age_k = outfit_metrics["age_coherence_k_of_n"]
    age_pct = outfit_metrics["age_coherence_pct"]
    print(f"  Age Coherence       : {age_k} ({age_pct}%)")
    gend_k = outfit_metrics["gender_coherence_k_of_n"]
    gend_pct = outfit_metrics["gender_coherence_pct"]
    print(f"  Gender Coherence    : {gend_k} ({gend_pct}%)")
    print(f"  Innerwear in Outfits: {outfit_metrics['innerwear_in_outfits']}")

    # 5. Quality Weight Ablation within Current Mode (D2)
    print(f"\n--- QUALITY WEIGHT ABLATION [Mode: {mode.upper()}] ---")
    quality_comp = evaluate_quality_ablation_mode(
        queries_data, repo, hybrid_index, mode, oracle_map
    )
    w05_p5 = quality_comp["quality_weight_0_05"]["precision_at_5"]
    w00_p5 = quality_comp["quality_weight_0_00"]["precision_at_5"]
    print(f"  Weight 0.05 Precision@5 : {w05_p5:.4f}")
    print(f"  Weight 0.00 Precision@5 : {w00_p5:.4f}")
    print(f"  Top-5 Order Changes     : {quality_comp['queries_with_top5_order_change']}")

    # 6. Catalog Update Check
    print("\n--- CATALOG UPDATE CHECK ---")
    with tempfile.TemporaryDirectory() as tmp_dir:
        update_check_passed = evaluate_catalog_update_check(Path(tmp_dir))
    print(f"  Update Check Passed: {update_check_passed}")

    # 7. Ingestion Report Summary
    ingestion_summary = {}
    ingest_report_file = Path("data/ingestion_report.json")
    if ingest_report_file.is_file():
        with open(ingest_report_file, encoding="utf-8") as f:
            ingestion_summary = json.load(f)

    # 8. Spotcheck file generation with overwrite protection (D6)
    spotcheck_file = Path("evals/spotcheck.csv")
    can_write_spotcheck = check_spotcheck_overwrite_protection(
        spotcheck_file, refresh_spotcheck, force
    )
    if can_write_spotcheck:
        spotcheck_queries = [q for q in queries_data if q.get("mode") != "outfit"][:10]
        spotcheck_rows: list[dict[str, Any]] = []
        for q_obj in spotcheck_queries:
            q_text = q_obj["query"]
            resp = service.search(SearchRequest(query=q_text, top_k=5, mode="product"))
            for rank, it in enumerate(resp.results, 1):
                spotcheck_rows.append(
                    {
                        "query": q_text,
                        "rank": rank,
                        "parent_asin": it.product_id,
                        "title": it.title,
                        "grade": "",
                    }
                )
        spotcheck_file.parent.mkdir(parents=True, exist_ok=True)
        with open(spotcheck_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f, fieldnames=["query", "rank", "parent_asin", "title", "grade"]
            )
            writer.writeheader()
            writer.writerows(spotcheck_rows)
        print(f"[Spotcheck] Wrote {len(spotcheck_rows)} rows to {spotcheck_file}")

    # Build results payload
    results_payload = {
        "metadata": {
            "timestamp": datetime.now(UTC).isoformat(),
            "mode": mode,
            "label": label_msg.strip(),
            "catalog_size": repo.count_active(),
            "index_size": hybrid_index.size(),
            "embedding_model": settings.embedding_model_name,
            "quality_weight": settings.quality_weight,
            "seed": settings.random_seed,
        },
        "search_metrics": search_metrics,
        "cached_latency_ms": {"p50": cached_p50, "p95": cached_p95},
        "forced_fallback_resilience": fallback_resilience,
        "outfit_metrics": outfit_metrics,
        "quality_weight_comparison": quality_comp,
        "catalog_update_check_passed": update_check_passed,
        "ingestion_summary": ingestion_summary,
    }

    # Save to evals/results.json
    results_path = Path("evals/results.json")
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(results_payload, f, indent=2)
    mode_path = Path(f"evals/results_{mode}.json")
    with open(mode_path, "w", encoding="utf-8") as f:
        json.dump(results_payload, f, indent=2)
    print(f"\n[Evals] Wrote complete results to {results_path} and {mode_path}")

    # Gates and Honesty Evaluation (D1a)
    print("\n=======================================================")
    print(f"EVALUATION GATES TABLE [Mode: {mode.upper()}]")
    print("=======================================================")

    gates_passed = True
    gate_records: list[tuple[str, str, str, str]] = []

    if mode == "oracle":
        # Oracle Gates: zero violations, zero kids leakage, 100% coherence, update check
        # Gate 1: Violations
        v_val = search_metrics["total_constraint_violations"]
        g1_pass = v_val == 0
        gate_records.append(
            ("Zero Constraint Violations", f"{v_val}", "0", "PASS" if g1_pass else "FAIL")
        )
        if not g1_pass:
            gates_passed = False

        # Gate 2: Kids Leakage
        k_val = search_metrics["kids_leakage"]
        g2_pass = k_val == 0
        gate_records.append(
            ("Zero Kids Leakage", f"{k_val}", "0", "PASS" if g2_pass else "FAIL")
        )
        if not g2_pass:
            gates_passed = False

        # Gate 3: Outfit Age Coherence
        ac_val = outfit_metrics["age_coherence_pct"]
        g3_pass = ac_val == 100.0
        gate_records.append(
            ("Outfit Age Coherence", f"{ac_val}%", "100.0%", "PASS" if g3_pass else "FAIL")
        )
        if not g3_pass:
            gates_passed = False

        # Gate 4: Outfit Gender Coherence
        gc_val = outfit_metrics["gender_coherence_pct"]
        g4_pass = gc_val == 100.0
        gate_records.append(
            ("Outfit Gender Coherence", f"{gc_val}%", "100.0%", "PASS" if g4_pass else "FAIL")
        )
        if not g4_pass:
            gates_passed = False

        # Gate 5: Outfit Budget Compliance
        bc_val = outfit_metrics["budget_compliance_pct"]
        g5_pass = bc_val == 100.0
        gate_records.append(
            ("Outfit Budget Compliance", f"{bc_val}%", "100.0%", "PASS" if g5_pass else "FAIL")
        )
        if not g5_pass:
            gates_passed = False

        g6_pass = update_check_passed is True
        stat_str = "PASS" if g6_pass else "FAIL"
        gate_records.append(
            ("Catalog Update Check", f"{update_check_passed}", "True", stat_str)
        )
        if not g6_pass:
            gates_passed = False

    else:
        # Fallback Gates:
        # (i) zero violations on English queries
        en_v_val = search_metrics["english_violations"]
        g1_pass = en_v_val == 0
        gate_records.append(
            ("Zero English Violations", f"{en_v_val}", "0", "PASS" if g1_pass else "FAIL")
        )
        if not g1_pass:
            gates_passed = False

        # (ii) non-English reported separately as degraded-mode violations
        deg_v_val = search_metrics["degraded_mode_violations"]
        gate_records.append(
            ("Degraded-Mode Violations (Non-Eng)", f"{deg_v_val}", "Reported separately", "INFO")
        )

        # (iii) outfit coherence 100%
        ac_val = outfit_metrics["age_coherence_pct"]
        gc_val = outfit_metrics["gender_coherence_pct"]
        g3_pass = (ac_val == 100.0) and (gc_val == 100.0)
        gate_records.append(
            (
                "Outfit Age & Gender Coherence",
                f"Age: {ac_val}%, Gender: {gc_val}%",
                "100.0%",
                "PASS" if g3_pass else "FAIL",
            )
        )
        if not g3_pass:
            gates_passed = False

        # Forced Fallback Resilience Gate
        ff_val = fallback_resilience["overall_success_pct"]
        g4_pass = ff_val == 100.0
        gate_records.append(
            ("Forced Fallback Resilience", f"{ff_val}%", "100.0%", "PASS" if g4_pass else "FAIL")
        )
        if not g4_pass:
            gates_passed = False

    print(f"{'Gate Name':<35} | {'Measured Value':<25} | {'Required':<20} | {'Status':<6}")
    print("-" * 92)
    for name, m_val, req_val, status in gate_records:
        print(f"{name:<35} | {m_val:<25} | {req_val:<20} | {status:<6}")
    print("=" * 92)

    if gates_passed:
        print(f"\n=== ALL EVALUATION GATES PASSED [Mode: {mode.upper()}] ===")
    else:
        print(f"\nFAILURE: ONE OR MORE EVALUATION GATES FAILED [Mode: {mode.upper()}]!")
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run evaluation benchmark suite.")
    parser.add_argument(
        "--mode",
        choices=["fallback", "oracle", "real"],
        default="fallback",
        help="Evaluation mode (default: fallback)",
    )
    parser.add_argument(
        "--replay",
        action="store_true",
        help="Use recorded real LLM parses from evals/real_parses.jsonl (D3)",
    )
    parser.add_argument(
        "--refresh-spotcheck",
        action="store_true",
        help="Allow refreshing evals/spotcheck.csv (D6)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force overwrite of spotcheck/audit even if annotated (D6)",
    )
    args = parser.parse_args()

    run_evals(
        mode=args.mode,
        replay=args.replay,
        refresh_spotcheck=args.refresh_spotcheck,
        force=args.force,
    )


if __name__ == "__main__":
    main()
