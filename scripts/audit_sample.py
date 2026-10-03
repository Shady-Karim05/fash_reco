import csv
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.catalog import CatalogRepository
from app.config import settings


def export_audit_sample(
    sample_size: int = 100,
    seed: int = 42,
    output_path: str = "data/audit_sample.csv",
) -> None:
    """Export random catalog products to CSV for manual attribute labeling.

    Args:
        sample_size: Number of products to sample (100).
        seed: Random seed for deterministic sample selection.
        output_path: Destination CSV filepath.
    """
    random.seed(seed)
    repo = CatalogRepository(settings.db_path)
    products = repo.get_all_active()
    sample = products if len(products) <= sample_size else random.sample(products, sample_size)

    fieldnames = [
        "parent_asin",
        "title",
        "derived_slot",
        "derived_gender",
        "derived_age_group",
        "true_slot",
        "true_gender",
        "true_age_group",
    ]

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for p in sample:
            writer.writerow(
                {
                    "parent_asin": p.parent_asin,
                    "title": p.title,
                    "derived_slot": p.slot,
                    "derived_gender": p.gender,
                    "derived_age_group": p.age_group,
                    "true_slot": "",
                    "true_gender": "",
                    "true_age_group": "",
                }
            )

    print(f"Exported {len(sample)} products to {output_path} (seed={seed})")


if __name__ == "__main__":
    export_audit_sample()
