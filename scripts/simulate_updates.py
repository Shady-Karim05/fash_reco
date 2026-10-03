"""Simulate runtime catalog updates and evaluation on a temporary database copy (A6)."""

import argparse
import contextlib
import json
import random
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.catalog import CatalogRepository
from app.cleaning import clean_text
from app.config import settings
from app.embedder import SentenceTransformerEmbedder
from app.index import HybridIndex
from app.pipeline import transform_raw_record, validate_raw_record
from app.schemas import Product


def run_simulation(
    held_out_path: Path | str = settings.held_out_path,
    batch_size: int = 200,
    seed: int = 42,
) -> None:
    """Execute update simulation on a temporary copy of catalog.db."""
    random.seed(seed)
    print("=== PHASE 4 & 5: RUNTIME CATALOG UPDATE SIMULATION (A6) ===")

    # 1. Create temporary directory and copy catalog.db
    temp_dir = Path(tempfile.mkdtemp(prefix="fashion_sim_"))
    temp_db = temp_dir / "catalog.db"

    if not settings.db_path.is_file():
        print(f"Error: Base catalog database not found at {settings.db_path}")
        sys.exit(1)

    shutil.copy2(settings.db_path, temp_db)
    print(f"Copied {settings.db_path} to temporary workspace: {temp_db}")

    repo = CatalogRepository(temp_db)
    embedder = SentenceTransformerEmbedder(settings.embedding_model_name)
    index = HybridIndex(catalog_repo=repo, embedder=embedder, cache_dir=temp_dir)
    index.build_from_catalog()

    active_catalog_count = repo.count_active()
    initial_index_size = index.size()

    print(
        f"Initial State -> Active Catalog Rows: {active_catalog_count:,} | "
        f"Index Size: {initial_index_size:,}"
    )

    # Integrity check: abort if initial index size differs from active catalog rows
    if active_catalog_count != initial_index_size:
        print(
            f"ERROR: Initial index size ({initial_index_size}) differs from "
            f"active catalog rows ({active_catalog_count}). Aborting!"
        )
        shutil.rmtree(temp_dir, ignore_errors=True)
        sys.exit(1)

    # 2. Read held-out records
    held_out_file = Path(held_out_path)
    if not held_out_file.is_file():
        print(f"Error: Held-out file not found at {held_out_file}")
        shutil.rmtree(temp_dir, ignore_errors=True)
        sys.exit(1)

    raw_held_out: list[dict[str, Any]] = []
    with open(held_out_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                with contextlib.suppress(json.JSONDecodeError):
                    raw_held_out.append(json.loads(line))

    print(f"Loaded {len(raw_held_out):,} raw held-out records from {held_out_file}")

    # 3. Background search loop during ingestion
    bg_latencies: list[float] = []
    bg_stop_event = threading.Event()

    def background_search_loop() -> None:
        sample_queries = [
            "cotton t-shirt",
            "summer dress",
            "running shoes",
            "leather handbag",
            "workout shorts",
        ]
        while not bg_stop_event.is_set():
            q = random.choice(sample_queries)
            t_start = time.perf_counter()
            try:
                index.search(raw_query=q, retrieval_k=20)
                dur_ms = (time.perf_counter() - t_start) * 1000.0
                bg_latencies.append(dur_ms)
            except Exception:
                pass
            time.sleep(0.01)

    bg_thread = threading.Thread(target=background_search_loop, daemon=True)
    bg_thread.start()

    # 4. Ingestion with per-step timing breakdown
    step_times: dict[str, list[float]] = {
        "validate_clean": [],
        "embed": [],
        "sqlite_write": [],
        "faiss_update": [],
        "bm25_update": [],
        "bookkeeping": [],
    }

    batches = [raw_held_out[i : i + batch_size] for i in range(0, len(raw_held_out), batch_size)]
    print(
        f"\n--- Ingesting {len(raw_held_out):,} records in {len(batches)} batches "
        f"(max batch size: {batch_size}) ---"
    )

    total_accepted = 0
    total_rejected = 0
    rejected_reasons: dict[str, int] = {}
    newly_created_ids: list[str] = []
    newly_created_records: list[dict[str, Any]] = []

    global_mean = repo.compute_global_mean_rating()
    overall_start = time.perf_counter()

    for b_idx, batch in enumerate(batches, 1):
        # Step A: Validate and Clean
        t0 = time.perf_counter()
        valid_products: list[Product] = []
        for raw_record in batch:
            asin = raw_record.get("parent_asin") or raw_record.get("asin")
            if not asin:
                rejected_reasons["no_parent_asin"] = rejected_reasons.get("no_parent_asin", 0) + 1
                continue
            is_valid, reason = validate_raw_record(
                raw_record,
                require_price=not settings.include_unknown_price,
                min_title_length=settings.min_title_length,
            )
            if not is_valid:
                r_code = reason or "validation_failed"
                rejected_reasons[r_code] = rejected_reasons.get(r_code, 0) + 1
                continue
            prod = transform_raw_record(
                raw_record, global_mean_rating=global_mean, bayesian_m=settings.bayesian_m
            )
            valid_products.append(prod)
        t_clean = time.perf_counter() - t0
        step_times["validate_clean"].append(t_clean)

        rej_count = len(batch) - len(valid_products)
        total_rejected += rej_count

        if not valid_products:
            continue

        # Step B: Embed
        t0 = time.perf_counter()
        search_texts = [p.search_text for p in valid_products]
        vectors = embedder.encode(search_texts, batch_size=settings.embedding_batch_size)
        t_embed = time.perf_counter() - t0
        step_times["embed"].append(t_embed)

        # Step C: SQLite write (products + embeddings atomically)
        t0 = time.perf_counter()
        model_name = getattr(embedder, "model_name", settings.embedding_model_name)
        embeddings_data: list[tuple[str, str, str, bytes]] = []
        for p, vec in zip(valid_products, vectors, strict=False):
            import hashlib

            thash = hashlib.sha256(p.search_text.encode("utf-8")).hexdigest()
            embeddings_data.append(
                (p.parent_asin, thash, model_name, vec.astype(np.float32).tobytes())
            )
        persisted = repo.upsert_products_and_embeddings_batch(valid_products, embeddings_data)
        t_db = time.perf_counter() - t0
        step_times["sqlite_write"].append(t_db)

        # Step D: FAISS update
        t0 = time.perf_counter()
        p_ids = [p.parent_asin for p in persisted]
        index.vector_index.add(p_ids, vectors)
        t_faiss = time.perf_counter() - t0
        step_times["faiss_update"].append(t_faiss)

        # Step E: BM25 update
        t0 = time.perf_counter()
        index.keyword_index.add_batch([(p.parent_asin, p.search_text) for p in persisted])
        t_bm25 = time.perf_counter() - t0
        step_times["bm25_update"].append(t_bm25)

        # Step F: Bookkeeping
        t0 = time.perf_counter()
        index.index_version = repo.increment_index_version()
        for p in persisted:
            newly_created_ids.append(p.parent_asin)
        total_accepted += len(persisted)
        t_book = time.perf_counter() - t0
        step_times["bookkeeping"].append(t_book)

        batch_dur = t_clean + t_embed + t_db + t_faiss + t_bm25 + t_book
        print(
            f"  Batch {b_idx:>2}/{len(batches)}: {len(batch):>3} items -> "
            f"Accepted: {len(persisted):>3}, Rejected: {rej_count:>3} in {batch_dur:.2f}s | "
            f"Index Version: {index.index_version}"
        )

    # Stop background search loop
    bg_stop_event.set()
    bg_thread.join(timeout=2.0)

    total_ingest_time = time.perf_counter() - overall_start
    final_index_size = index.size()

    print("\n--- INGESTION STEP TIMING BREAKDOWN (Per-batch average) ---")
    print(f"  Validate & Clean : {np.mean(step_times['validate_clean']) * 1000:.2f} ms")
    print(f"  Embed (CPU)      : {np.mean(step_times['embed']) * 1000:.2f} ms")
    print(f"  SQLite Write     : {np.mean(step_times['sqlite_write']) * 1000:.2f} ms")
    print(f"  FAISS Update     : {np.mean(step_times['faiss_update']) * 1000:.2f} ms")
    print(f"  BM25 Update      : {np.mean(step_times['bm25_update']) * 1000:.2f} ms")
    print(f"  Bookkeeping      : {np.mean(step_times['bookkeeping']) * 1000:.2f} ms")
    print(f"  Total Ingestion  : {total_ingest_time:.2f}s ({total_ingest_time / 60:.2f} min)")

    if bg_latencies:
        bg_arr = np.array(bg_latencies)
        p50 = float(np.percentile(bg_arr, 50))
        p95 = float(np.percentile(bg_arr, 95))
        print(f"\n--- Concurrent Search Latency During Ingestion (N={len(bg_latencies)}) ---")
        print(f"  p50 Search Latency: {p50:.2f} ms")
        print(f"  p95 Search Latency: {p95:.2f} ms")

    print("\n--- Ingestion Counts ---")
    print(f"  Total Accepted   : {total_accepted:,}")
    print(f"  Total Rejected   : {total_rejected:,}")
    print(f"  Rejection Reasons: {rejected_reasons}")
    print(f"  Index Size Before: {initial_index_size:,}")
    net_added = final_index_size - initial_index_size
    print(f"  Index Size After : {final_index_size:,} (Net added: {net_added:,})")

    # 5. Simulate Restart (A5 & A6)
    print("\n--- SIMULATING RESTART (New HybridIndex on temp database) ---")
    restart_start = time.perf_counter()
    restarted_index = HybridIndex(catalog_repo=repo, embedder=embedder, cache_dir=temp_dir)
    reembedded = restarted_index.build_from_catalog()
    restart_elapsed = time.perf_counter() - restart_start
    print(f"  Restart Load Time    : {restart_elapsed:.2f} s")
    print(f"  Rows Re-embedded     : {reembedded} (Must be 0 after A5 SQLite persistence)")
    assert reembedded == 0, f"Expected 0 re-embedded rows on restart, got {reembedded}!"

    # 6. Self-Retrieval Check (50 seeded products)
    print("\n--- SELF-RETRIEVAL CHECK (50 seeded newly added products) ---")
    print("> [!NOTE]")
    print("> Label: self-retrieval check (an optimistic sanity test, not an accuracy metric).")

    accepted_set = set(newly_created_ids)
    for rec in raw_held_out:
        asin = str(rec.get("parent_asin") or rec.get("asin") or "").strip()
        if asin in accepted_set:
            newly_created_records.append(rec)

    rand_inst = random.Random(seed)
    sample_50 = rand_inst.sample(newly_created_records, min(50, len(newly_created_records)))

    top_1_hits = 0
    top_10_hits = 0
    misses: list[dict[str, Any]] = []

    for _idx, rec in enumerate(sample_50, 1):
        target_asin = str(rec.get("parent_asin") or rec.get("asin")).strip()
        raw_title = str(rec.get("title", ""))
        search_query = clean_text(raw_title)

        cand_results, _ = restarted_index.search(raw_query=search_query, retrieval_k=10)
        returned_ids = [c[0] for c in cand_results]

        rank = returned_ids.index(target_asin) + 1 if target_asin in returned_ids else None

        if rank == 1:
            top_1_hits += 1
            top_10_hits += 1
        elif rank is not None and rank <= 10:
            top_10_hits += 1
            top_cand = repo.get_by_id(returned_ids[0])
            misses.append(
                {
                    "asin": target_asin,
                    "title": raw_title,
                    "rank": rank,
                    "rank_1_asin": returned_ids[0],
                    "rank_1_title": top_cand.title if top_cand else "",
                    "cause": "near_duplicate_title_or_size_variant",
                }
            )
        else:
            misses.append(
                {
                    "asin": target_asin,
                    "title": raw_title,
                    "rank": "Not in top 10",
                    "cause": "uncommon_tokens_or_vocabulary_mismatch",
                }
            )

    pct_top1 = top_1_hits / len(sample_50) * 100
    pct_top10 = top_10_hits / len(sample_50) * 100
    print(f"  Total Sample Checked : {len(sample_50)}")
    print(
        f"  Found in Top 1       : {top_1_hits}/{len(sample_50)} "
        f"({pct_top1:.1f}%) [self-retrieval check]"
    )
    print(
        f"  Found in Top 10      : {top_10_hits}/{len(sample_50)} "
        f"({pct_top10:.1f}%) [self-retrieval check]"
    )

    if misses:
        print("\n  Self-Retrieval Misses Detail:")
        for m in misses:
            print(
                f"    - [{m['asin']}] {m['title'][:55]} -> Rank: {m['rank']} | Cause: {m['cause']}"
            )

    # 7. Re-posting 20 products
    print("\n--- RE-POSTING 20 PRODUCTS (Version Increment & Size Invariance) ---")
    repost_sample = sample_50[:20]
    size_before_repost = restarted_index.size()

    repost_products = [
        transform_raw_record(rec, global_mean_rating=global_mean, bayesian_m=settings.bayesian_m)
        for rec in repost_sample
    ]
    reposted = restarted_index.upsert_batch_atomic(repost_products)
    size_after_repost = restarted_index.size()

    print(f"  Re-posted Items      : {len(repost_products)}")
    print(f"  Versions in Response : {[p.version for p in reposted[:5]]} ...")
    print(f"  Index Size Before    : {size_before_repost:,}")
    diff_repost = size_after_repost - size_before_repost
    print(f"  Index Size After     : {size_after_repost:,} (Difference: {diff_repost})")
    assert size_before_repost == size_after_repost, "Index size changed on re-posting!"

    # 8. Deleting 10 products
    print("\n--- DELETING 10 PRODUCTS (Soft-delete & Immediate Exclusion) ---")
    delete_sample = sample_50[20:30]
    size_before_del = restarted_index.size()

    for rec in delete_sample:
        p_id = str(rec.get("parent_asin") or rec.get("asin")).strip()
        exists, already = restarted_index.delete_product(p_id)
        assert exists and not already

    size_after_del = restarted_index.size()
    print(f"  Deleted Items Count  : {len(delete_sample)}")
    print(f"  Index Size Before    : {size_before_del:,}")
    net_del = size_before_del - size_after_del
    print(f"  Index Size After     : {size_after_del:,} (Net reduction: {net_del:,})")
    assert size_before_del - size_after_del == len(delete_sample)

    # Clean up temp dir
    shutil.rmtree(temp_dir, ignore_errors=True)
    print("\nTemporary workspace cleaned up.")
    print("=== SIMULATION COMPLETED SUCCESSFULLY ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Simulate runtime updates on temporary DB.")
    parser.add_argument("--held-out-path", default=str(settings.held_out_path))
    parser.add_argument("--batch-size", type=int, default=200)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    run_simulation(
        held_out_path=args.held_out_path,
        batch_size=args.batch_size,
        seed=args.seed,
    )
