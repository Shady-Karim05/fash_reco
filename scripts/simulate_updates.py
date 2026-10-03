"""Simulate runtime catalog updates and evaluation via batch ingestion API."""

import argparse
import contextlib
import json
import random
import sys
import time
from pathlib import Path
from typing import Any

import requests
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.cleaning import clean_text
from app.config import settings
from app.main import app


class ApiClientWrapper:
    """Unified wrapper supporting either FastAPI TestClient or live HTTP server."""

    def __init__(self, base_url: str | None = None, admin_key: str = "secret-admin-key") -> None:
        self.base_url = base_url.rstrip("/") if base_url else None
        self.admin_key = admin_key
        self.headers = {"X-API-Key": self.admin_key}
        if not self.base_url:
            self._client_cm = TestClient(app)
            self.test_client = self._client_cm.__enter__()
        else:
            self._client_cm = None
            self.test_client = None

    def get_health(self) -> dict[str, Any]:
        if self.test_client:
            resp = self.test_client.get("/health")
        else:
            resp = requests.get(f"{self.base_url}/health", timeout=10)
        resp.raise_for_status()
        return resp.json()

    def post_products(self, products: list[dict[str, Any]]) -> dict[str, Any]:
        if self.test_client:
            resp = self.test_client.post(
                "/products", json={"products": products}, headers=self.headers
            )
        else:
            resp = requests.post(
                f"{self.base_url}/products",
                json={"products": products},
                headers=self.headers,
                timeout=60,
            )
        resp.raise_for_status()
        return resp.json()

    def delete_product(self, product_id: str) -> dict[str, Any]:
        if self.test_client:
            resp = self.test_client.delete(f"/products/{product_id}", headers=self.headers)
        else:
            resp = requests.delete(
                f"{self.base_url}/products/{product_id}", headers=self.headers, timeout=10
            )
        resp.raise_for_status()
        return resp.json()

    def search(self, query: str, top_k: int = 10) -> dict[str, Any]:
        payload = {"query": query, "top_k": top_k}
        if self.test_client:
            resp = self.test_client.post("/search", json=payload)
        else:
            resp = requests.post(f"{self.base_url}/search", json=payload, timeout=10)
        resp.raise_for_status()
        return resp.json()


def run_simulation(
    held_out_path: Path | str = settings.held_out_path,
    batch_size: int = 200,
    base_url: str | None = None,
    seed: int = 42,
) -> None:
    """Execute update simulation posting held-out products.

    Tests self-retrieval, re-post, and delete.
    """
    random.seed(seed)
    # Configure admin key for TestClient if in memory
    settings.admin_api_key = "secret-admin-key"

    client = ApiClientWrapper(base_url=base_url, admin_key=settings.admin_api_key)

    print("=== PHASE 4: RUNTIME CATALOG UPDATE SIMULATION ===")
    health_init = client.get_health()
    size_init = health_init["index_size"]
    print(f"Initial State -> Index Size: {size_init:,} | LLM Status: {health_init['llm_status']}\n")

    # 1. Read held-out records
    held_out_file = Path(held_out_path)
    if not held_out_file.is_file():
        print(f"Error: Held-out file not found at {held_out_file}")
        sys.exit(1)

    raw_held_out: list[dict[str, Any]] = []
    with open(held_out_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                with contextlib.suppress(json.JSONDecodeError):
                    raw_held_out.append(json.loads(line))

    print(f"Loaded {len(raw_held_out):,} raw held-out records from {held_out_file}")

    # 2. Post in batches
    total_accepted = 0
    total_rejected = 0
    rejected_reasons: dict[str, int] = {}
    newly_created_ids: list[str] = []
    newly_created_records: list[dict[str, Any]] = []

    batches = [raw_held_out[i : i + batch_size] for i in range(0, len(raw_held_out), batch_size)]

    print(
        f"\n--- Ingesting {len(raw_held_out):,} records in {len(batches)} batches "
        f"(max batch size: {batch_size}) ---"
    )
    start_ingest = time.perf_counter()

    for b_idx, batch in enumerate(batches, 1):
        t0 = time.perf_counter()
        resp_data = client.post_products(batch)
        elapsed = time.perf_counter() - t0

        acc = resp_data["accepted_count"]
        rej = resp_data["rejected_count"]
        curr_ver = resp_data["index_version"]
        total_accepted += acc
        total_rejected += rej

        for item in resp_data["items"]:
            if item["status"] in {"created", "updated"}:
                newly_created_ids.append(item["parent_asin"])
            elif item["status"] == "rejected":
                r = item.get("reason", "unknown")
                rejected_reasons[r] = rejected_reasons.get(r, 0) + 1

        print(
            f"  Batch {b_idx:>2}/{len(batches)}: {len(batch):>3} items -> "
            f"Accepted: {acc:>3}, Rejected: {rej:>3} in {elapsed:.2f}s | "
            f"Index Version: {curr_ver}"
        )

    ingest_time = time.perf_counter() - start_ingest
    health_after_ingest = client.get_health()
    size_after_ingest = health_after_ingest["index_size"]

    print("\n--- Ingestion Summary ---")
    print(f"  Total Ingest Time : {ingest_time:.2f}s ({ingest_time / 60:.2f} min)")
    print(f"  Total Accepted    : {total_accepted:,}")
    print(f"  Total Rejected    : {total_rejected:,}")
    if rejected_reasons:
        print(f"  Rejection Reasons : {rejected_reasons}")
    print(f"  Index Size Before : {size_init:,}")
    print(
        f"  Index Size After  : {size_after_ingest:,} "
        f"(Net added: {size_after_ingest - size_init:,})"
    )

    # Filter raw records to only those successfully accepted
    accepted_set = set(newly_created_ids)
    for rec in raw_held_out:
        asin = str(rec.get("parent_asin") or rec.get("asin") or "").strip()
        if asin in accepted_set:
            newly_created_records.append(rec)

    # 3. Searchability Check (50 random items)
    print("\n--- Self-Retrieval Check (50 random newly added products) ---")
    rand_inst = random.Random(seed)
    sample_50 = rand_inst.sample(newly_created_records, min(50, len(newly_created_records)))

    top_1_hits = 0
    top_10_hits = 0

    for _idx, rec in enumerate(sample_50, 1):
        target_asin = str(rec.get("parent_asin") or rec.get("asin")).strip()
        raw_title = str(rec.get("title", ""))
        search_query = clean_text(raw_title)

        s_resp = client.search(query=search_query, top_k=10)
        returned_ids = [item["product_id"] for item in s_resp.get("results", [])]

        if returned_ids and returned_ids[0] == target_asin:
            top_1_hits += 1
        if target_asin in returned_ids:
            top_10_hits += 1

    print(f"  Total Sample Checked : {len(sample_50)}")
    p1 = top_1_hits / len(sample_50) * 100
    p10 = top_10_hits / len(sample_50) * 100
    print(
        f"  Found in Top 1       : {top_1_hits}/{len(sample_50)} "
        f"({p1:.1f}%) [self-retrieval check]"
    )
    print(
        f"  Found in Top 10      : {top_10_hits}/{len(sample_50)} "
        f"({p10:.1f}%) [self-retrieval check]"
    )

    # 4. Re-posting 20 products
    print("\n--- Re-posting 20 products (Version increment & constant size check) ---")
    repost_sample = sample_50[:20]
    size_before_repost = client.get_health()["index_size"]

    repost_resp = client.post_products(repost_sample)
    size_after_repost = client.get_health()["index_size"]

    updated_items = [item for item in repost_resp["items"] if item["status"] == "updated"]
    print(f"  Re-posted Items      : {len(repost_sample)}")
    print(f"  Updated Items Count  : {len(updated_items)}")
    print(f"  Versions in Response : {[it['version'] for it in updated_items[:5]]} ...")
    print(f"  Index Size Before    : {size_before_repost:,}")
    print(
        f"  Index Size After     : {size_after_repost:,} "
        f"(Difference: {size_after_repost - size_before_repost})"
    )
    assert size_before_repost == size_after_repost, "Index size changed on re-posting!"

    # 5. Deleting 10 products
    print("\n--- Deleting 10 added products (Soft-delete & immediate search exclusion) ---")
    delete_sample = sample_50[20:30]
    size_before_del = client.get_health()["index_size"]

    for rec in delete_sample:
        p_id = str(rec.get("parent_asin") or rec.get("asin")).strip()
        del_resp = client.delete_product(p_id)
        assert del_resp["status"] == "deleted"

    size_after_del = client.get_health()["index_size"]
    print(f"  Deleted Items Count  : {len(delete_sample)}")
    print(f"  Index Size Before    : {size_before_del:,}")
    print(
        f"  Index Size After     : {size_after_del:,} "
        f"(Net reduction: {size_before_del - size_after_del:,})"
    )

    # Verify deleted items are never returned in search
    deleted_retrieved = 0
    for rec in delete_sample:
        target_asin = str(rec.get("parent_asin") or rec.get("asin")).strip()
        search_query = clean_text(str(rec.get("title", "")))
        s_resp = client.search(query=search_query, top_k=10)
        returned_ids = [item["product_id"] for item in s_resp.get("results", [])]
        if target_asin in returned_ids:
            deleted_retrieved += 1

    print(f"  Deleted Items Retrieved by Search: {deleted_retrieved}/10 (Expected: 0)")
    assert deleted_retrieved == 0, "Deleted product was returned by search!"
    print("\n=== SIMULATION COMPLETED SUCCESSFULLY ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Simulate runtime updates.")
    parser.add_argument("--held-out-path", default=str(settings.held_out_path))
    parser.add_argument("--batch-size", type=int, default=200)
    parser.add_argument("--base-url", type=str, default=None)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    run_simulation(
        held_out_path=args.held_out_path,
        batch_size=args.batch_size,
        base_url=args.base_url,
        seed=args.seed,
    )
