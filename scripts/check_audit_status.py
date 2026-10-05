"""Check human annotation status of data/audit_sample.csv in read-only mode (Fix 7).

Validates completion rates and flag any invalid labels according to the schema:
- Slots: top, bottom, full_body, footwear, accessory, innerwear, unknown
- Genders: men, women, unisex, unknown
- Age groups: adult, kids

Never mutates data/audit_sample.csv.
"""

import csv
import sys
from pathlib import Path

ALLOWED_SLOTS = {"top", "bottom", "full_body", "footwear", "accessory", "innerwear", "unknown"}
ALLOWED_GENDERS = {"men", "women", "unisex", "unknown"}
ALLOWED_AGE_GROUPS = {"adult", "kids"}


def check_audit_status(csv_path: Path | str = Path("data/audit_sample.csv")) -> int:
    """Analyze and print annotation progress for data/audit_sample.csv."""
    path = Path(csv_path)
    if not path.is_file():
        print(f"[Error] File not found: {path}")
        return 1

    total_rows = 0
    slot_annotated = 0
    gender_annotated = 0
    age_annotated = 0
    fully_annotated = 0

    invalid_slots: list[tuple[int, str, str]] = []
    invalid_genders: list[tuple[int, str, str]] = []
    invalid_ages: list[tuple[int, str, str]] = []

    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row_idx, row in enumerate(reader, start=2):  # 1-indexed, line 2 is first data row
            total_rows += 1
            t_slot = (row.get("true_slot") or "").strip().lower()
            t_gender = (row.get("true_gender") or "").strip().lower()
            t_age = (row.get("true_age_group") or "").strip().lower()

            has_slot = bool(t_slot)
            has_gender = bool(t_gender)
            has_age = bool(t_age)

            if has_slot:
                slot_annotated += 1
                if t_slot not in ALLOWED_SLOTS:
                    invalid_slots.append((row_idx, row.get("parent_asin", ""), t_slot))

            if has_gender:
                gender_annotated += 1
                if t_gender not in ALLOWED_GENDERS:
                    invalid_genders.append((row_idx, row.get("parent_asin", ""), t_gender))

            if has_age:
                age_annotated += 1
                if t_age not in ALLOWED_AGE_GROUPS:
                    invalid_ages.append((row_idx, row.get("parent_asin", ""), t_age))

            if has_slot and has_gender and has_age:
                fully_annotated += 1

    print("================================================================================")
    print(f"AUDIT SAMPLE ANNOTATION STATUS [{path}]")
    print("================================================================================")
    print(f"Total Rows Evaluated   : {total_rows}")
    if total_rows == 0:
        print("[Notice] File is completely empty.")
        return 0

    slot_pct = (slot_annotated / total_rows) * 100.0
    gender_pct = (gender_annotated / total_rows) * 100.0
    age_pct = (age_annotated / total_rows) * 100.0
    full_pct = (fully_annotated / total_rows) * 100.0

    print(f"true_slot completion   : {slot_annotated}/{total_rows} ({slot_pct:.1f}%)")
    print(f"true_gender completion : {gender_annotated}/{total_rows} ({gender_pct:.1f}%)")
    print(f"true_age_group comp.   : {age_annotated}/{total_rows} ({age_pct:.1f}%)")
    print(f"Overall complete rows  : {fully_annotated}/{total_rows} ({full_pct:.1f}%)")
    print("--------------------------------------------------------------------------------")

    if fully_annotated == 0:
        print("[Status] The audit sample is currently BLANK (awaiting human labeling).")
        print("         Valid label options:")
        print(f"         - true_slot      : {sorted(ALLOWED_SLOTS)}")
        print(f"         - true_gender    : {sorted(ALLOWED_GENDERS)}")
        print(f"         - true_age_group : {sorted(ALLOWED_AGE_GROUPS)}")
    else:
        print(f"[Status] Annotation in progress: {fully_annotated}/{total_rows} rows labeled.")

    total_invalid = len(invalid_slots) + len(invalid_genders) + len(invalid_ages)
    if total_invalid > 0:
        print(f"[Warning] Found {total_invalid} invalid annotations:")
        for r_idx, asin, val in invalid_slots:
            print(f"  Row {r_idx} ({asin}): Invalid true_slot '{val}' (allowed: {ALLOWED_SLOTS})")
        for r_idx, asin, val in invalid_genders:
            print(
                f"  Row {r_idx} ({asin}): Invalid true_gender '{val}' (allowed: {ALLOWED_GENDERS})"
            )
        for r_idx, asin, val in invalid_ages:
            print(
                f"  Row {r_idx} ({asin}): Invalid true_age_group '{val}' "
                f"(allowed: {ALLOWED_AGE_GROUPS})"
            )
    else:
        print("[Validation] No invalid label values found.")

    print("================================================================================")
    return 0


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "data/audit_sample.csv"
    sys.exit(check_audit_status(target))
