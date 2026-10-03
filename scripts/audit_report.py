"""Audit report generator analyzing derived attributes vs ground-truth annotations (A9)."""

import csv
import sys
from collections import Counter
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
SAMPLE_CSV = ROOT_DIR / "data" / "audit_sample.csv"
OUTPUT_MD = ROOT_DIR / "docs" / "audit_results.md"


def run_audit() -> None:
    """Read data/audit_sample.csv and compute precision and confusion matrices."""
    if not SAMPLE_CSV.is_file():
        print(f"Error: {SAMPLE_CSV} not found. Run scripts/build_index.py first.")
        sys.exit(1)

    rows: list[dict[str, str]] = []
    with open(SAMPLE_CSV, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)

    if not rows:
        print(f"Error: {SAMPLE_CSV} is empty.")
        sys.exit(1)

    # Check for empty true_* cells
    missing_counts = {"true_slot": 0, "true_gender": 0, "true_age_group": 0}
    incomplete_rows = 0

    for r in rows:
        row_incomplete = False
        for field in ("true_slot", "true_gender", "true_age_group"):
            val = (r.get(field) or "").strip()
            if not val:
                missing_counts[field] += 1
                row_incomplete = True
        if row_incomplete:
            incomplete_rows += 1

    if incomplete_rows > 0:
        total = len(rows)
        print(
            f"[Audit Report] Refusing to run: {incomplete_rows} of {total} rows "
            f"have unannotated true_* labels."
        )
        print(f"  Missing true_slot: {missing_counts['true_slot']}")
        print(f"  Missing true_gender: {missing_counts['true_gender']}")
        print(f"  Missing true_age_group: {missing_counts['true_age_group']}")
        print(
            "\nPlease fill in true_slot, true_gender, and true_age_group in "
            "data/audit_sample.csv before running this audit report."
        )
        sys.exit(1)

    print(f"[Audit Report] Processing {len(rows)} fully annotated sample rows...")

    # Calculate metrics
    # Note: State explicitly that sample is stratified, so overall accuracy is not extrapolated
    slot_confusion: Counter[tuple[str, str]] = Counter()
    gender_confusion: Counter[tuple[str, str]] = Counter()
    age_confusion: Counter[tuple[str, str]] = Counter()

    slot_misclassified: list[dict[str, str]] = []
    gender_misclassified: list[dict[str, str]] = []
    age_misclassified: list[dict[str, str]] = []

    derived_slot_counts: Counter[str] = Counter()
    derived_slot_correct: Counter[str] = Counter()

    gender_correct = 0
    age_correct = 0

    for r in rows:
        d_slot = r["derived_slot"].strip()
        t_slot = r["true_slot"].strip()
        d_gen = r["derived_gender"].strip()
        t_gen = r["true_gender"].strip()
        d_age = r["derived_age_group"].strip()
        t_age = r["true_age_group"].strip()

        # Slot
        derived_slot_counts[d_slot] += 1
        slot_confusion[(d_slot, t_slot)] += 1
        if d_slot == t_slot:
            derived_slot_correct[d_slot] += 1
        else:
            slot_misclassified.append(r)

        # Gender
        gender_confusion[(d_gen, t_gen)] += 1
        if d_gen == t_gen:
            gender_correct += 1
        else:
            gender_misclassified.append(r)

        # Age group
        age_confusion[(d_age, t_age)] += 1
        if d_age == t_age:
            age_correct += 1
        else:
            age_misclassified.append(r)

    # Output MD content
    strat_note = (
        "> [!IMPORTANT]\n"
        "> Note: The audited sample is stratified (footwear 15, bottom 15, top 15, "
        "full_body 15, innerwear 10, unknown 10, accessory 20).\n"
        "> Overall accuracy is NOT extrapolated to the catalog as a whole."
    )
    lines = [
        "# Attribute Derivation Audit Results",
        "",
        strat_note,
        "",
        f"**Sample Size**: {len(rows)} products",
        "",
        "## 1. Slot Classification Performance",
        "",
        "| Derived Slot | Audited Count | Correct Count | Precision |",
        "| :--- | :--- | :--- | :--- |",
    ]

    for s, cnt in derived_slot_counts.items():
        corr = derived_slot_correct[s]
        prec = (corr / cnt * 100) if cnt > 0 else 0.0
        lines.append(f"| {s} | {cnt} | {corr} | {prec:.1f}% |")

    lines.extend(
        [
            "",
            "### Slot Confusion Matrix (Derived \\ True)",
            "",
        ]
    )

    all_slots = sorted({d for d, _ in slot_confusion} | {t for _, t in slot_confusion})
    header_row = "| Derived \\ True | " + " | ".join(all_slots) + " |"
    sep_row = "| :--- | " + " | ".join([":---:" for _ in all_slots]) + " |"
    lines.append(header_row)
    lines.append(sep_row)
    for d in all_slots:
        row_cells = [f"**{d}**"]
        for t in all_slots:
            row_cells.append(str(slot_confusion[(d, t)]))
        lines.append("| " + " | ".join(row_cells) + " |")

    # Gender
    gender_acc = (gender_correct / len(rows) * 100) if rows else 0.0
    lines.extend(
        [
            "",
            "## 2. Gender Classification Performance",
            f"- **Sample Accuracy**: {gender_correct}/{len(rows)} ({gender_acc:.1f}%)",
            "",
            "### Gender Confusion Matrix (Derived \\ True)",
            "",
        ]
    )
    all_genders = sorted({d for d, _ in gender_confusion} | {t for _, t in gender_confusion})
    lines.append("| Derived \\ True | " + " | ".join(all_genders) + " |")
    lines.append("| :--- | " + " | ".join([":---:" for _ in all_genders]) + " |")
    for d in all_genders:
        row_cells = [f"**{d}**"]
        for t in all_genders:
            row_cells.append(str(gender_confusion[(d, t)]))
        lines.append("| " + " | ".join(row_cells) + " |")

    # Age Group
    age_acc = (age_correct / len(rows) * 100) if rows else 0.0
    lines.extend(
        [
            "",
            "## 3. Age Group Classification Performance",
            f"- **Sample Accuracy**: {age_correct}/{len(rows)} ({age_acc:.1f}%)",
            "",
            "### Age Group Confusion Matrix (Derived \\ True)",
            "",
        ]
    )
    all_ages = sorted({d for d, _ in age_confusion} | {t for _, t in age_confusion})
    lines.append("| Derived \\ True | " + " | ".join(all_ages) + " |")
    lines.append("| :--- | " + " | ".join([":---:" for _ in all_ages]) + " |")
    for d in all_ages:
        row_cells = [f"**{d}**"]
        for t in all_ages:
            row_cells.append(str(age_confusion[(d, t)]))
        lines.append("| " + " | ".join(row_cells) + " |")

    # Misclassified details
    lines.extend(
        [
            "",
            "## 4. Misclassified Items Details",
            "",
            "### Slot Misclassifications",
        ]
    )
    if not slot_misclassified:
        lines.append("None.")
    else:
        for item in slot_misclassified:
            asin = item["parent_asin"]
            tit = item["title"]
            d_s = item["derived_slot"]
            t_s = item["true_slot"]
            lines.append(f"- **[{asin}]** {tit} -> Derived: `{d_s}`, True: `{t_s}`")

    OUTPUT_MD.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"\n[Audit Report] Generated {OUTPUT_MD}")


if __name__ == "__main__":
    run_audit()
