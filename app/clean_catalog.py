"""CLI Command and Catalog Quality Auditor (Phase 13).

Usage:
    python -m app.clean_catalog [--rebuild-indexes] [--dry-run]

Executes the Data Cleaning and Product Quality Control Pipeline across all catalog products,
stores quarantined/rejected items in data/quarantine.db and data/quarantine.jsonl,
updates catalog active statuses, regenerates hybrid indexes, and outputs an audit report.
"""

import argparse
import json
import logging
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from app.catalog import CatalogRepository
from app.config import settings
from app.embedder import SentenceTransformerEmbedder
from app.index import HybridIndex
from app.quality import QuarantineManager, evaluate_record
from app.schemas import CleaningReport, QuarantineRecord

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("clean_catalog")


def run_catalog_cleaning(
    catalog_db_path: Path | str = settings.db_path,
    quarantine_db_path: Path | str = settings.quarantine_db_path,
    quarantine_jsonl_path: Path | str = settings.quarantine_jsonl_path,
    report_path: Path | str = settings.cleaning_report_path,
    rebuild_indexes: bool = True,
    dry_run: bool = False,
) -> CleaningReport:
    """Run data quality evaluation and cleaning on the catalog products."""
    catalog_path = Path(catalog_db_path)
    if not catalog_path.is_file():
        logger.error("Catalog database not found at %s", catalog_path)
        sys.exit(1)

    repo = CatalogRepository(catalog_path)
    quarantine_mgr = QuarantineManager(db_path=quarantine_db_path, jsonl_path=quarantine_jsonl_path)

    logger.info("Loading catalog products from %s...", catalog_path)
    # Load all products including any previously deleted for a clean audit
    with repo._get_connection() as conn:
        rows = conn.execute("SELECT * FROM products").fetchall()
        all_products = [repo._row_to_product(r) for r in rows]

    total_count = len(all_products)
    logger.info("Evaluating %d products through Quality Control Pipeline...", total_count)

    accepted_records = []
    quarantined_records: list[QuarantineRecord] = []
    rejected_records: list[QuarantineRecord] = []

    rejection_reasons_counter: Counter[str] = Counter()
    quarantine_reasons_counter: Counter[str] = Counter()
    slot_dist_all: Counter[str] = Counter()
    slot_dist_accepted: Counter[str] = Counter()
    gender_dist_accepted: Counter[str] = Counter()
    confidence_counter: Counter[str] = Counter()
    quality_score_buckets: Counter[str] = Counter()

    # Track seen titles to identify exact duplicates
    seen_asin_keys: set[str] = set()
    seen_product_signatures: dict[str, str] = {}

    products_to_update_active = []
    products_to_update_deleted = []

    for prod in all_products:
        slot_dist_all[prod.slot] += 1

        # Check exact duplicate asin
        if prod.parent_asin in seen_asin_keys:
            res = evaluate_record(prod)
            res.status = "rejected"
            res.rejection_reasons = ["duplicate_id"]
        else:
            seen_asin_keys.add(prod.parent_asin)
            res = evaluate_record(prod)

        # Duplicate product signature check (same store, identical clean title, same price)
        sig = f"{prod.store or 'unknown'}|{res.clean_title.lower()}|{res.price}"
        if res.status == "accepted" and sig in seen_product_signatures:
            # We keep canonical first item and flag identical duplicates
            res.status = "rejected"
            res.rejection_reasons = ["duplicate_product"]
        elif res.status == "accepted":
            seen_product_signatures[sig] = prod.parent_asin

        low_b = int(res.quality_score * 10) / 10
        q_bucket = f"{low_b:.1f}-{low_b + 0.1:.1f}"
        quality_score_buckets[q_bucket] += 1

        if res.status == "accepted":
            accepted_records.append(res)
            slot_dist_accepted[res.slot] += 1
            gender_dist_accepted[res.gender] += 1
            products_to_update_active.append(
                (res.clean_title, res.slot, res.accessory_type, res.quality_score, prod.parent_asin)
            )
        elif res.status == "quarantined":
            for r in res.rejection_reasons:
                quarantine_reasons_counter[r] += 1
            q_rec = QuarantineRecord(
                parent_asin=res.parent_asin,
                original_title=res.original_title,
                price=res.price,
                predicted_slot=res.slot,
                classification_confidence=res.classification_confidence,
                status="quarantined",
                reasons=res.rejection_reasons,
                quality_score=res.quality_score,
            )
            quarantined_records.append(q_rec)
            products_to_update_deleted.append((prod.parent_asin,))
        else:  # rejected
            for r in res.rejection_reasons:
                key = r.split(":")[0].strip()
                rejection_reasons_counter[key] += 1
            r_rec = QuarantineRecord(
                parent_asin=res.parent_asin,
                original_title=res.original_title,
                price=res.price,
                predicted_slot=res.slot,
                classification_confidence=res.classification_confidence,
                status="rejected",
                reasons=res.rejection_reasons,
                quality_score=res.quality_score,
            )
            rejected_records.append(r_rec)
            products_to_update_deleted.append((prod.parent_asin,))

    # Format cleaning report
    report = CleaningReport(
        total_products_evaluated=total_count,
        accepted_count=len(accepted_records),
        quarantined_count=len(quarantined_records),
        rejected_count=len(rejected_records),
        rejection_reasons=dict(rejection_reasons_counter),
        quarantine_reasons=dict(quarantine_reasons_counter),
        slot_distribution_accepted=dict(slot_dist_accepted),
        slot_distribution_all=dict(slot_dist_all),
        gender_distribution_accepted=dict(gender_dist_accepted),
        confidence_distribution=dict(confidence_counter),
        quality_score_distribution=dict(sorted(quality_score_buckets.items())),
        timestamp=datetime.now(UTC).isoformat(),
    )

    # Output detailed report to terminal
    print("\n" + "=" * 65)
    print("      DATA CLEANING & PRODUCT QUALITY CONTROL REPORT")
    print("=" * 65)
    print(f"Total raw products:        {total_count:,}")
    pct_acc = report.accepted_count / total_count * 100
    print(f"Accepted:                  {report.accepted_count:,} ({pct_acc:.1f}%)")
    pct_quar = report.quarantined_count / total_count * 100
    print(f"Review / Quarantined:      {report.quarantined_count:,} ({pct_quar:.1f}%)")
    pct_rej = report.rejected_count / total_count * 100
    print(f"Rejected:                  {report.rejected_count:,} ({pct_rej:.1f}%)")
    print("-" * 65)

    print("Rejection Reasons Breakdown:")
    for reason, count in report.rejection_reasons.items():
        print(f"  {reason.replace('_', ' ').capitalize():<28} {count:>6}")

    print("\nQuarantine Reasons Breakdown:")
    for reason, count in report.quarantine_reasons.items():
        print(f"  {reason.replace('_', ' ').capitalize():<28} {count:>6}")

    print("-" * 65)
    print("Slot Distribution (Accepted Products):")
    for slot_name, count in sorted(report.slot_distribution_accepted.items(), key=lambda x: -x[1]):
        print(f"  {slot_name.upper():<28} {count:>6}")

    print("\nGender Distribution (Accepted Products):")
    for g_name, count in sorted(report.gender_distribution_accepted.items(), key=lambda x: -x[1]):
        print(f"  {g_name.capitalize():<28} {count:>6}")

    print("\nClassification Confidence Distribution:")
    for conf, count in sorted(report.confidence_distribution.items(), key=lambda x: -x[1]):
        print(f"  {conf.upper():<28} {count:>6}")

    print("\nQuality Score Distribution:")
    for bucket, count in sorted(report.quality_score_distribution.items()):
        print(f"  [{bucket}]: {count:>6}")
    print("=" * 65 + "\n")

    if not dry_run:
        logger.info(
            "Persisting quarantine records to %s and %s...",
            quarantine_db_path,
            quarantine_jsonl_path,
        )
        all_quarantine = quarantined_records + rejected_records
        quarantine_mgr.record_batch(all_quarantine)

        logger.info("Updating SQLite catalog status...")
        with repo._get_connection() as conn:
            # Mark quarantined & rejected products as deleted from active index
            conn.executemany(
                "UPDATE products SET is_deleted = 1, updated_at = datetime('now') "
                "WHERE parent_asin = ?",
                products_to_update_deleted,
            )
            # Update clean titles, slots, and quality scores for accepted products
            conn.executemany(
                """
                UPDATE products
                SET title = ?, slot = ?, accessory_type = ?, quality_score = ?,
                    is_deleted = 0, updated_at = datetime('now')
                WHERE parent_asin = ?
                """,
                products_to_update_active,
            )

        new_version = repo.increment_index_version()
        logger.info("Catalog updated. Monotonic index version incremented to v%d.", new_version)

        # Save JSON report
        report_file = Path(report_path)
        report_file.parent.mkdir(parents=True, exist_ok=True)
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(report.model_dump(), f, indent=2)
        logger.info("Saved audit report to %s", report_file)

        if rebuild_indexes:
            logger.info("Rebuilding FAISS and BM25 indexes from accepted products...")
            embedder = SentenceTransformerEmbedder()
            hybrid_index = HybridIndex(
                catalog_repo=repo,
                embedder=embedder,
                cache_dir=settings.data_dir,
            )
            recomputed = hybrid_index.build_from_catalog(force_recompute=False)
            logger.info(
                "Hybrid index rebuilt with %d active products (recomputed vectors: %d).",
                hybrid_index.size(),
                recomputed,
            )
    else:
        logger.info("Dry-run mode: no changes persisted.")

    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Data Cleaning & Quality Control Pipeline CLI")
    parser.add_argument("--db-path", default=str(settings.db_path), help="Path to catalog.db")
    parser.add_argument(
        "--quarantine-db",
        default=str(settings.quarantine_db_path),
        help="Path to quarantine.db",
    )
    parser.add_argument(
        "--quarantine-jsonl",
        default=str(settings.quarantine_jsonl_path),
        help="Path to quarantine.jsonl",
    )
    parser.add_argument(
        "--report-path",
        default=str(settings.cleaning_report_path),
        help="Path to output JSON report",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Evaluate without modifying catalog or index"
    )
    parser.add_argument(
        "--rebuild-indexes",
        action="store_true",
        default=True,
        help="Rebuild FAISS/BM25 indexes",
    )

    args = parser.parse_args()
    run_catalog_cleaning(
        catalog_db_path=args.db_path,
        quarantine_db_path=args.quarantine_db,
        quarantine_jsonl_path=args.quarantine_jsonl,
        report_path=args.report_path,
        rebuild_indexes=args.rebuild_indexes,
        dry_run=args.dry_run,
    )
