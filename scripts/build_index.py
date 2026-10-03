import contextlib
import json
import random
import re
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.catalog import CatalogRepository
from app.config import settings
from app.embedder import SentenceTransformerEmbedder
from app.index import HybridIndex
from app.pipeline import transform_raw_record, validate_raw_record
from app.schemas import Product
from scripts.generate_synthetic import generate_synthetic_catalog


def find_metadata_file() -> Path | None:
    """Locate the metadata JSONL file from configured paths."""
    candidates = [
        settings.raw_meta_path,
        Path("data/meta_Amazon_Fashion.jsonl"),
        Path("meta_Amazon_Fashion.jsonl"),
        Path("meta_Amazon_Fashion.jsonl/meta_Amazon_Fashion.jsonl"),
    ]
    for p in candidates:
        if p.is_file():
            return p
    return None


def find_reviews_file() -> Path | None:
    """Locate the reviews JSONL file from configured paths."""
    candidates = [
        settings.raw_reviews_path,
        Path("data/Amazon_Fashion.jsonl"),
        Path("Amazon_Fashion.jsonl"),
        Path("Amazon_Fashion.jsonl/Amazon_Fashion.jsonl"),
    ]
    for p in candidates:
        if p.is_file():
            return p
    return None


def run_ingestion(
    max_sample_size: int = settings.sample_size,
    held_out_fraction: float = settings.held_out_fraction,
    seed: int = settings.random_seed,
    build_vectors: bool = True,
) -> dict[str, Any]:
    """Execute streaming ingestion, attribute derivation, persistence, and vector indexing.

    Uses Reservoir Sampling to sample kept records without loading full dataset
    into memory. Stores active products in SQLite, computes coverage statistics,
    and builds FAISS and BM25 hybrid search indexes.

    Args:
        max_sample_size: Target number of kept records to sample (10,000).
        held_out_fraction: Fraction of sample to hold out for update tests (0.2).
        seed: Random seed for deterministic sampling.
        build_vectors: If True, also compute embeddings and build hybrid index.

    Returns:
        Dictionary containing counts, coverage statistics, and ingestion summary.
    """
    random.seed(seed)
    meta_path = find_metadata_file()

    if not meta_path:
        print("[Ingestion] Raw metadata file not found. Generating synthetic catalog...")
        synth_file = generate_synthetic_catalog(
            num_products=500,
            output_path=settings.data_dir / "meta_Amazon_Fashion.jsonl",
            seed=seed,
        )
        meta_path = synth_file

    print(f"[Ingestion] Streaming metadata from: {meta_path}")

    # Counters
    total_read = 0
    drop_counts: dict[str, int] = {
        "no_title": 0,
        "short_title": 0,
        "non_fashion_keyword": 0,
        "no_price": 0,
        "invalid_price": 0,
    }
    kept_count = 0

    # Reservoir sampling buffer of raw valid records
    reservoir: list[dict[str, Any]] = []

    with open(meta_path, encoding="utf-8") as f:
        for line in f:
            total_read += 1
            line = line.strip()
            if not line:
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                drop_counts["invalid_json"] = drop_counts.get("invalid_json", 0) + 1
                continue

            is_valid, reason = validate_raw_record(
                record,
                min_title_length=settings.min_title_length,
                require_price=not settings.include_unknown_price,
            )

            if not is_valid and reason:
                drop_counts[reason] = drop_counts.get(reason, 0) + 1
                continue

            kept_count += 1

            # Reservoir sampling to sample exactly max_sample_size items
            if len(reservoir) < max_sample_size:
                reservoir.append(record)
            else:
                j = random.randint(0, kept_count - 1)
                if j < max_sample_size:
                    reservoir[j] = record

            if total_read % 100000 == 0:
                print(
                    f"  Processed {total_read:,} rows... "
                    f"Kept: {kept_count:,} (Reservoir: {len(reservoir)})"
                )

    print(f"\n[Ingestion] Completed streaming {total_read:,} rows.")
    print(f"  Total kept: {kept_count:,}")
    print(f"  Sampled into reservoir: {len(reservoir):,}")
    for reason, count in drop_counts.items():
        pct = (count / total_read * 100) if total_read > 0 else 0
        print(f"  Dropped ({reason}): {count:,} ({pct:.2f}%)")

    # Shuffle reservoir with fixed seed
    random.shuffle(reservoir)

    # Split into indexed sample and held-out update test set
    held_out_count = int(len(reservoir) * held_out_fraction)
    catalog_sample = reservoir[held_out_count:]
    held_out_sample = reservoir[:held_out_count]

    print(f"\n[Ingestion] Catalog sample: {len(catalog_sample):,} products")
    print(f"[Ingestion] Held-out sample: {len(held_out_sample):,} products")

    # Save held-out sample
    settings.held_out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(settings.held_out_path, "w", encoding="utf-8") as f:
        for item in held_out_sample:
            f.write(json.dumps(item) + "\n")
    print(f"[Ingestion] Held-out products written to {settings.held_out_path}")

    # Process reviews if available (A1)
    catalog_asins = {
        str(r.get("parent_asin")).strip() for r in catalog_sample if r.get("parent_asin")
    }
    reviews_by_asin: dict[str, list[dict[str, Any]]] = {}

    reviews_path = find_reviews_file()
    if reviews_path and reviews_path.is_file():
        print(f"[Ingestion] Streaming reviews from {reviews_path}...")
        rev_count = 0
        with open(reviews_path, encoding="utf-8") as f:
            for line in f:
                rev_count += 1
                line = line.strip()
                if not line:
                    continue
                try:
                    rev = json.loads(line)
                    asin = str(rev.get("parent_asin", "")).strip()
                    if asin in catalog_asins:
                        text = str(rev.get("text", "")).strip()
                        if len(text) >= 40:
                            helpful = int(rev.get("helpful_vote") or 0)
                            if asin not in reviews_by_asin:
                                reviews_by_asin[asin] = []
                            reviews_by_asin[asin].append(
                                {"text": text[:150], "helpful_vote": helpful}
                            )
                except Exception:
                    continue
                if rev_count % 500000 == 0:
                    print(f"  Processed {rev_count:,} reviews...")
        print(f"[Ingestion] Matched reviews for {len(reviews_by_asin):,} products.")
    else:
        print("[Ingestion] No reviews file found. Review snippets will be omitted.")

    # Format 2 best reviews per product
    best_reviews: dict[str, list[str]] = {}
    for asin, revs in reviews_by_asin.items():
        revs.sort(key=lambda x: x["helpful_vote"], reverse=True)
        best_reviews[asin] = [r["text"] for r in revs[:2]]

    # Transform raw records into Product instances using shared pipeline
    print("[Ingestion] Transforming raw records with attribute derivation...")
    products = [
        transform_raw_record(
            rec,
            global_mean_rating=settings.global_mean_rating,
            review_snippets=best_reviews.get(str(rec.get("parent_asin", "")).strip()),
        )
        for rec in catalog_sample
    ]

    # Store products in SQLite
    print(f"[Ingestion] Persisting {len(products):,} products into SQLite at {settings.db_path}...")
    if settings.db_path.is_file():
        with contextlib.suppress(Exception):
            settings.db_path.unlink()
    repo = CatalogRepository(settings.db_path)
    repo.upsert_products_batch(products)
    active_count = repo.count_active()
    print(f"[Ingestion] SQLite catalog now contains {active_count:,} active products.")

    # A3: Compute Attribute Coverage Statistics
    cat_len = len(products)
    slot_counts = Counter(p.slot for p in products)
    gender_counts = Counter(p.gender for p in products)
    age_counts = Counter(p.age_group for p in products)

    empty_desc_count = sum(1 for p in products if not p.description or not p.description.strip())
    empty_feat_count = sum(1 for p in products if not p.features)
    no_color_count = sum(1 for p in products if not p.colors)
    with_reviews_count = sum(1 for p in products if p.review_snippets)

    coverage_report = {
        "slot": {
            k: {"count": v, "pct": round(v / cat_len * 100, 2)} for k, v in slot_counts.items()
        },
        "gender": {
            k: {"count": v, "pct": round(v / cat_len * 100, 2)} for k, v in gender_counts.items()
        },
        "age_group": {
            k: {"count": v, "pct": round(v / cat_len * 100, 2)} for k, v in age_counts.items()
        },
        "data_completeness": {
            "empty_description": {
                "count": empty_desc_count,
                "pct": round(empty_desc_count / cat_len * 100, 2),
            },
            "empty_features": {
                "count": empty_feat_count,
                "pct": round(empty_feat_count / cat_len * 100, 2),
            },
            "no_extracted_color": {
                "count": no_color_count,
                "pct": round(no_color_count / cat_len * 100, 2),
            },
            "with_review_snippets": {
                "count": with_reviews_count,
                "pct": round(with_reviews_count / cat_len * 100, 2),
            },
        },
    }

    # If unknown slot is > 30%, identify the top 20 title words
    unknown_slot_top_words: list[tuple[str, int]] = []
    unknown_pct = (slot_counts.get("unknown", 0) / cat_len) if cat_len > 0 else 0
    if unknown_pct > 0.30:
        stopwords = {
            "and",
            "for",
            "the",
            "with",
            "in",
            "of",
            "a",
            "an",
            "to",
            "by",
            "on",
            "women",
            "men",
            "womens",
            "mens",
            "women's",
            "men's",
            "size",
            "fit",
            "pack",
            "pairs",
            "set",
            "s",
            "2",
            "3",
            "4",
            "5",
            "6",
            "1",
            "10",
            "piece",
            "color",
            "style",
            "design",
            "new",
        }
        unknown_titles = [p.title for p in products if p.slot == "unknown"]
        word_counter: Counter[str] = Counter()
        for t in unknown_titles:
            tokens = re.findall(r"\b[a-zA-Z]{3,}\b", t.lower())
            tokens = [w for w in tokens if w not in stopwords]
            word_counter.update(tokens)
        unknown_slot_top_words = word_counter.most_common(20)

    # Sample 15 random products for review table
    sample_15_products = random.Random(42).sample(products, min(15, len(products)))
    sample_15_table = [
        {
            "title": p.title[:65] + ("..." if len(p.title) > 65 else ""),
            "slot": p.slot,
            "gender": p.gender,
            "age_group": p.age_group,
            "colors": p.colors,
        }
        for p in sample_15_products
    ]

    # Save complete ingestion report to data/ingestion_report.json
    dropped_with_pct = {
        k: {
            "count": v,
            "pct": round((v / total_read * 100), 2) if total_read > 0 else 0.0,
        }
        for k, v in drop_counts.items()
    }
    report = {
        "seed": seed,
        "total_rows_read": total_read,
        "dropped_by_reason": dropped_with_pct,
        "total_valid_kept": kept_count,
        "total_valid_kept_pct": round((kept_count / total_read * 100), 2)
        if total_read > 0
        else 0.0,
        "sample_size": len(reservoir),
        "catalog_size": len(products),
        "held_out_size": len(held_out_sample),
        "coverage": coverage_report,
        "unknown_slot_top_words": unknown_slot_top_words,
        "sample_15_products": sample_15_table,
    }

    report_file = settings.data_dir / "ingestion_report.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"\n[Ingestion] Ingestion report written to {report_file}")

    # Print coverage summary
    print("\n--- ATTRIBUTE COVERAGE SUMMARY ---")
    print(f"Slot Breakdown (Catalog N={cat_len}):")
    for s, data in coverage_report["slot"].items():
        print(f"  {s:<12}: {data['count']:>5} ({data['pct']}%)")
    print("\nGender Breakdown:")
    for g, data in coverage_report["gender"].items():
        print(f"  {g:<12}: {data['count']:>5} ({data['pct']}%)")
    print("\nAge Group Breakdown:")
    for a, data in coverage_report["age_group"].items():
        print(f"  {a:<12}: {data['count']:>5} ({data['pct']}%)")
    print("\nData Completeness:")
    for k, data in coverage_report["data_completeness"].items():
        print(f"  {k:<22}: {data['count']:>5} ({data['pct']}%)")

    if unknown_slot_top_words:
        print(
            f"\n[Warning] Slot 'unknown' is {unknown_pct * 100:.1f}% (>30%). "
            "Top 20 words in unknown-slot titles:"
        )
        for w, c in unknown_slot_top_words:
            print(f"  {w}: {c}")

    print("\n--- 15 SAMPLE CATALOG PRODUCTS (seed=42) ---")
    header = f"{'Title':<68} | {'Slot':<10} | {'Gender':<7} | {'Age':<6} | {'Colors'}"
    print(header)
    print("-" * len(header))
    for item in sample_15_table:
        print(
            f"{item['title']:<68} | {item['slot']:<10} | {item['gender']:<7} | "
            f"{item['age_group']:<6} | {item['colors']}"
        )

    # Phase 2: Build Hybrid Vector & BM25 Indexes
    if build_vectors:
        print("\n[Ingestion] Computing embeddings and building Hybrid Index (FAISS + BM25)...")
        embed_start = time.perf_counter()
        embedder = SentenceTransformerEmbedder(settings.embedding_model_name)
        hybrid_index = HybridIndex(
            catalog_repo=repo,
            embedder=embedder,
            cache_dir=settings.data_dir,
        )
        hybrid_index.build_from_catalog(force_recompute=True)
        embed_elapsed = time.perf_counter() - embed_start
        print(
            f"[Ingestion] Hybrid Index built successfully with {hybrid_index.size():,} items "
            f"in {embed_elapsed:.2f} seconds ({embed_elapsed / 60:.2f} minutes)."
        )

    # Sample 30 unknown-slot titles and 20 kids titles
    unknown_prods = [p for p in products if p.slot == "unknown"]
    kids_prods = [p for p in products if p.age_group == "kids"]

    rand_inst = random.Random(42)
    sampled_unknown = rand_inst.sample(unknown_prods, min(30, len(unknown_prods)))
    sampled_kids = rand_inst.sample(kids_prods, min(20, len(kids_prods)))

    print("\n--- 30 RANDOM UNKNOWN-SLOT TITLES ---")
    for i, p in enumerate(sampled_unknown, 1):
        print(f"{i:>2}. [{p.parent_asin}] {p.title}")

    print("\n--- 20 RANDOM KIDS TITLES ---")
    for i, p in enumerate(sampled_kids, 1):
        print(f"{i:>2}. [{p.parent_asin}] {p.title} (Gender: {p.gender})")

    # Regenerate data/audit_sample.csv ONCE as a stratified sample of 100 (A8)
    audit_file = settings.data_dir / "audit_sample.csv"
    force_audit = "--force" in sys.argv
    if not audit_file.is_file() or force_audit:
        print(f"\n[Ingestion] Generating stratified audit sample (N=100) -> {audit_file}")
        import csv

        strat_counts = {
            "footwear": 15,
            "bottom": 15,
            "top": 15,
            "full_body": 15,
            "innerwear": 10,
            "unknown": 10,
            "accessory": 20,
        }
        strat_rand = random.Random(42)
        audit_records: list[Product] = []
        for slot_name, count in strat_counts.items():
            pool = [p for p in products if p.slot == slot_name]
            sampled = strat_rand.sample(pool, min(count, len(pool)))
            audit_records.extend(sampled)

        with open(audit_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "parent_asin",
                    "title",
                    "derived_slot",
                    "derived_gender",
                    "derived_age_group",
                    "accessory_type",
                    "true_slot",
                    "true_gender",
                    "true_age_group",
                ]
            )
            for p in audit_records:
                writer.writerow(
                    [
                        p.parent_asin,
                        p.title,
                        p.slot,
                        p.gender,
                        p.age_group,
                        p.accessory_type or "",
                        "",
                        "",
                        "",
                    ]
                )
        print(f"[Ingestion] Saved {len(audit_records)} stratified items to {audit_file} (frozen).")
    else:
        print(f"\n[Ingestion] {audit_file} already exists. Retaining frozen sample.")

    return report


if __name__ == "__main__":
    import time

    overall_start = time.perf_counter()
    rep = run_ingestion()
    overall_elapsed = time.perf_counter() - overall_start
    print(
        f"\n[Build Summary] Total process time: {overall_elapsed:.2f} seconds "
        f"({overall_elapsed / 60:.2f} minutes)."
    )
