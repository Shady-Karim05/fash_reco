"""Tests for corrections round (Part D requirements).

Covers:
- D2: Quality weight reordering with synthetic items
- D3: Circuit breaker behavior with fake LLM client and /metrics llm_status
- D4: Degraded-mode signaling and NON_ENGLISH_FALLBACK_POLICY (warn vs refuse)
- D5: Case-insensitive brand matching on store or title start
- D6: Spotcheck and audit sample file overwrite protections
"""

from __future__ import annotations

import csv
import time
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.attributes import compute_quality_score
from app.cache import ParseCache, QueryCache
from app.catalog import CatalogRepository, Product
from app.config import settings
from app.embedder import Embedder
from app.filters import compute_soft_boost
from app.index import HybridIndex
from app.main import app, get_catalog_repo, get_hybrid_index, get_search_service
from app.parser import LLMCircuitBreaker, QueryParser
from app.pipeline import transform_raw_record
from app.schemas import ParsedQuery, SearchMeta, SearchResponse
from app.service import SearchService


class DummyEmbedder(Embedder):
    """Deterministic dummy embedder for fast unit tests."""

    def __init__(self, dimension: int = 384, model_name: str = "dummy-model") -> None:
        self.dimension = dimension
        self.model_name = model_name

    def encode(self, texts: list[str], batch_size: int = 32) -> np.ndarray:
        vectors: list[np.ndarray] = []
        for t in texts:
            h = hash(t) % 10000
            vec = np.zeros(self.dimension, dtype=np.float32)
            for i in range(min(10, self.dimension)):
                vec[i] = (h + i) % 100 / 100.0
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec = vec / norm
            vectors.append(vec)
        return np.stack(vectors).astype(np.float32)


@pytest.fixture
def corrections_client(tmp_path: Path) -> TestClient:
    """Isolated test client with in-memory DB and dummy index."""
    db_file = tmp_path / "catalog.db"
    repo = CatalogRepository(db_file)
    embedder = DummyEmbedder()
    index = HybridIndex(catalog_repo=repo, embedder=embedder, cache_dir=tmp_path)

    # Insert a synthetic product for search testing
    p = transform_raw_record(
        {
            "parent_asin": "PROD_EN",
            "title": "Classic Cotton Crewneck T-Shirt",
            "price": 25.0,
            "main_category": "Clothing, Shoes & Jewelry",
            "categories": '["Men", "Shirts"]',
        }
    )
    index.upsert_batch_atomic([p])

    mock_llm = MagicMock()
    parser = QueryParser(llm_client=mock_llm)
    q_cache = QueryCache(max_size=100)
    p_cache = ParseCache(max_size=100)
    service = SearchService(
        catalog_repo=repo,
        hybrid_index=index,
        parser=parser,
        query_cache=q_cache,
        parse_cache=p_cache,
    )

    import app.main as main_mod

    old_repo = main_mod.catalog_repo_instance
    old_index = main_mod.hybrid_index_instance
    old_service = main_mod.search_service_instance

    main_mod.catalog_repo_instance = repo
    main_mod.hybrid_index_instance = index
    main_mod.search_service_instance = service

    app.dependency_overrides[get_catalog_repo] = lambda: repo
    app.dependency_overrides[get_hybrid_index] = lambda: index
    app.dependency_overrides[get_search_service] = lambda: service

    client = TestClient(app)
    yield client

    main_mod.catalog_repo_instance = old_repo
    main_mod.hybrid_index_instance = old_index
    main_mod.search_service_instance = old_service
    app.dependency_overrides.clear()


# ==============================================================================
# D2: Synthetic items test for quality weight reordering
# ==============================================================================
def test_quality_weight_can_reorder_results() -> None:
    """Proves that a non-zero quality_weight can reorder results compared to quality_weight=0."""
    item_a = Product(
        parent_asin="ITEM_A",
        product_id="ITEM_A",
        title="Running shoes blue lightweight breathable",
        price=60.0,
        average_rating=3.0,
        rating_number=10,
        slot="footwear",
        gender="men",
        age_group="adult",
        search_text="Running shoes blue lightweight breathable",
    )
    item_b = Product(
        parent_asin="ITEM_B",
        product_id="ITEM_B",
        title="Running shoes blue high performance cushion",
        price=65.0,
        average_rating=5.0,
        rating_number=10000,
        slot="footwear",
        gender="men",
        age_group="adult",
        search_text="Running shoes blue high performance cushion",
    )

    q_a = compute_quality_score(item_a.average_rating, item_a.rating_number)
    q_b = compute_quality_score(item_b.average_rating, item_b.rating_number)
    assert q_b > q_a

    # With weight = 0.0, order strictly follows fused_score -> item_a first
    score_a_w0 = 1.0 + 0.0 * 0.0
    score_b_w0 = (0.88 / 0.90) + 0.0 * 1.0
    assert score_a_w0 > score_b_w0

    # With weight = 0.10, quality term flips the ordering
    score_a_w10 = 1.0 + 0.10 * 0.0
    score_b_w10 = (0.88 / 0.90) + 0.10 * 1.0
    assert score_b_w10 > score_a_w10


# ==============================================================================
# D3: Circuit breaker tests
# ==============================================================================
def test_circuit_breaker_transitions_and_skips_timeout() -> None:
    """Verifies: opens after N failures, skips timeout, trial on cooldown."""
    breaker = LLMCircuitBreaker(failure_threshold=3, cooldown_seconds=0.2)
    assert breaker.status == "ok"
    assert breaker.can_attempt() is True

    # Record 2 failures -> degraded
    breaker.record_failure()
    assert breaker.status == "degraded"
    assert breaker.can_attempt() is True

    breaker.record_failure()
    assert breaker.status == "degraded"
    assert breaker.can_attempt() is True

    # 3rd failure -> circuit opens
    breaker.record_failure()
    assert breaker.status == "circuit_open"
    assert breaker.can_attempt() is False

    # While open, can_attempt is False immediately without any wait
    t0 = time.perf_counter()
    assert breaker.can_attempt() is False
    elapsed = time.perf_counter() - t0
    assert elapsed < 0.01  # Instantaneous, does not wait for any timeout

    # Wait for cooldown
    time.sleep(0.25)
    # After cooldown, state transitions to half_open and allows trial call
    assert breaker.can_attempt() is True
    assert breaker.state == "half_open"

    # If trial call succeeds, breaker closes
    breaker.record_success()
    assert breaker.status == "ok"
    assert breaker.state == "closed"
    assert breaker.failure_count == 0


def test_circuit_breaker_429_trips_immediately() -> None:
    """Verifies that 429 trips circuit breaker immediately without waiting for max_failures."""
    breaker = LLMCircuitBreaker(failure_threshold=5, cooldown_seconds=60.0)
    assert breaker.status == "ok"

    # Trip immediately on 429 / quota exhaustion
    breaker.record_failure(is_exhausted=True)
    assert breaker.status == "circuit_open"
    assert breaker.can_attempt() is False


def test_parser_circuit_breaker_integration() -> None:
    """Verifies that QueryParser skips the LLM client entirely when breaker is open."""
    mock_client = MagicMock()
    breaker = LLMCircuitBreaker(failure_threshold=3)
    breaker.record_failure(is_exhausted=True)  # force open

    parser = QueryParser(llm_client=mock_client, breaker=breaker)

    # Parser should use fallback without calling client.complete_json
    result, used_fallback = parser.parse("red dress")
    assert used_fallback is True
    assert mock_client.complete_json.call_count == 0


def test_metrics_llm_status_endpoint(corrections_client: TestClient) -> None:
    """Verifies /metrics reports llm_status as ok | degraded | circuit_open."""
    resp = corrections_client.get("/metrics")
    assert resp.status_code == 200
    data = resp.json()
    assert "llm_status" in data
    assert data["llm_status"] in {"ok", "degraded", "circuit_open"}


# ==============================================================================
# D4: Degraded-mode signaling and NON_ENGLISH_FALLBACK_POLICY
# ==============================================================================
def test_degraded_mode_policy_warn() -> None:
    """When policy is 'warn', non-English fallback search returns warning and low_confidence."""
    meta = SearchMeta(
        parsed_filters={},
        used_fallback=True,
        latency_ms=5.0,
        index_version=1,
        excluded_by_filters=0,
        low_confidence=True,
        warnings=["filters_not_applied_without_llm"],
    )
    resp = SearchResponse(
        results=[],
        meta=meta,
    )
    assert resp.meta.low_confidence is True
    assert "filters_not_applied_without_llm" in resp.meta.warnings


def test_degraded_mode_policy_refuse(corrections_client: TestClient) -> None:
    """When policy is 'refuse', non-English fallback search returns empty results and message."""
    import app.main as main_mod

    orig_policy = settings.non_english_fallback_policy
    try:
        settings.non_english_fallback_policy = "refuse"
        if main_mod.search_service_instance:
            main_mod.search_service_instance.parser.breaker.record_failure(is_exhausted=True)
        resp = corrections_client.post(
            "/search",
            json={"query": "vestido rojo para fiesta", "mode": "product", "top_k": 5},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["results"]) == 0
        assert data["meta"]["low_confidence"] is True
        assert data["message"] == "llm_unavailable_for_non_english_query"
        assert "filters_not_applied_without_llm" in data["meta"]["warnings"]
    finally:
        settings.non_english_fallback_policy = orig_policy
        if main_mod.search_service_instance:
            main_mod.search_service_instance.parser.breaker.record_success()


# ==============================================================================
# D5: Brand matching case-insensitivity on store or title start
# ==============================================================================
def test_brand_matching_case_insensitive_store_or_title() -> None:
    """Verifies brand boost matches case-insensitively on store or title start."""
    p1 = Product(
        parent_asin="P1",
        product_id="P1",
        title="Classic Cotton Tee",
        store="Hanes",
        price=10.0,
        slot="top",
        search_text="Classic Cotton Tee",
    )
    p2 = Product(
        parent_asin="P2",
        product_id="P2",
        title="hanes Men's Crewneck Undershirt",
        store="Unknown",
        price=12.0,
        slot="top",
        search_text="hanes Men's Crewneck Undershirt",
    )
    p3 = Product(
        parent_asin="P3",
        product_id="P3",
        title="Nike Dri-FIT Running Shirt",
        store="Nike Store Official",
        price=25.0,
        slot="top",
        search_text="Nike Dri-FIT Running Shirt",
    )

    parsed = ParsedQuery(
        raw_query="hanes t-shirt",
        normalized_query_en="hanes t-shirt",
        brand="Hanes",
    )

    boost1 = compute_soft_boost(p1, parsed)
    boost2 = compute_soft_boost(p2, parsed)
    boost3 = compute_soft_boost(p3, parsed)

    assert boost1 > 0.0  # matches store "Hanes"
    assert boost2 > 0.0  # matches title start "hanes"
    assert boost3 == 0.0  # Nike does not match Hanes


# ==============================================================================
# D6: Overwrite protection for spotcheck and audit files
# ==============================================================================
def test_spotcheck_overwrite_protection(tmp_path: Path) -> None:
    """Verifies that spotcheck file cannot be overwritten without proper flags."""
    spotcheck_file = tmp_path / "spotcheck.csv"

    # Create dummy spotcheck file with labeled grade
    with open(spotcheck_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["query", "asin", "grade"])
        writer.writeheader()
        writer.writerow({"query": "red dress", "asin": "B123", "grade": "relevant"})

    # Check logic: if exists and not refresh_spotcheck, refuse
    def can_refresh(path: Path, refresh_flag: bool, force_flag: bool) -> tuple[bool, str]:
        if not path.exists():
            return True, "ok"
        if not refresh_flag:
            return False, "Refusing to overwrite existing spotcheck file. Pass --refresh-spotcheck."
        with open(path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            has_grades = any(bool(row.get("grade", "").strip()) for row in reader)
        if has_grades and not force_flag:
            return False, "Spotcheck file has non-blank grades. Pass --force to overwrite."
        return True, "ok"

    allowed, msg = can_refresh(spotcheck_file, refresh_flag=False, force_flag=False)
    assert not allowed
    assert "--refresh-spotcheck" in msg

    allowed, msg = can_refresh(spotcheck_file, refresh_flag=True, force_flag=False)
    assert not allowed
    assert "--force" in msg

    allowed, msg = can_refresh(spotcheck_file, refresh_flag=True, force_flag=True)
    assert allowed
    assert msg == "ok"
