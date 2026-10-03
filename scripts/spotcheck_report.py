"""Manual spotcheck report generator analyzing graded search results (C3)."""

import csv
import sys
from collections import defaultdict
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
SPOTCHECK_CSV = ROOT_DIR / "evals" / "spotcheck.csv"


def run_spotcheck_report() -> None:
    """Read evals/spotcheck.csv and compute precision@5 for human graded results."""
    if not SPOTCHECK_CSV.is_file():
        print(f"Error: {SPOTCHECK_CSV} not found. Run evals/run_evals.py --mode oracle first.")
        sys.exit(1)

    rows: list[dict[str, str]] = []
    with open(SPOTCHECK_CSV, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)

    if not rows:
        print(f"Error: {SPOTCHECK_CSV} is empty.")
        sys.exit(1)

    # Check for empty grades
    blank_rows = [i + 2 for i, r in enumerate(rows) if not (r.get("grade") or "").strip()]
    if blank_rows:
        count = len(blank_rows)
        total = len(rows)
        print(f"[Spotcheck Report] Refusing to run: {count} of {total} rows have blank grades.")
        print(f"  First blank rows: {blank_rows[:10]}")
        print("\nPlease grade each row in evals/spotcheck.csv with 'relevant', 'borderline', etc.")
        sys.exit(1)

    # Group by query
    query_grades: dict[str, list[str]] = defaultdict(list)
    for r in rows:
        q = r["query"].strip()
        g = r["grade"].strip().lower()
        query_grades[q].append(g)

    print(f"=== MANUAL SPOT-CHECK REPORT (N={len(query_grades)} queries, 5 items each) ===")

    total_relevant = 0
    total_borderline = 0
    total_irrelevant = 0
    strict_p5_list: list[float] = []
    lenient_p5_list: list[float] = []

    for q, grades in query_grades.items():
        rel = grades.count("relevant")
        bord = grades.count("borderline")
        irrel = grades.count("irrelevant")
        total_relevant += rel
        total_borderline += bord
        total_irrelevant += irrel

        strict_p = rel / 5.0
        lenient_p = (rel + bord) / 5.0
        strict_p5_list.append(strict_p)
        lenient_p5_list.append(lenient_p)

        print(f'Query: "{q}"')
        print(f"  Relevant: {rel}/5 | Borderline: {bord}/5 | Irrelevant: {irrel}/5")
        print(f"  Strict P@5: {strict_p:.2f} | Lenient P@5 (rel+borderline): {lenient_p:.2f}\n")

    mean_strict_p5 = sum(strict_p5_list) / len(strict_p5_list) if strict_p5_list else 0.0
    mean_lenient_p5 = sum(lenient_p5_list) / len(lenient_p5_list) if lenient_p5_list else 0.0

    print("--- SUMMARY ---")
    print(f"  Overall Strict Precision@5  : {mean_strict_p5:.4f}")
    print(f"  Overall Lenient Precision@5 : {mean_lenient_p5:.4f}")
    print(f"  Total Relevant Items        : {total_relevant}")
    print(f"  Total Borderline Items      : {total_borderline}")
    print(f"  Total Irrelevant Items      : {total_irrelevant}")


if __name__ == "__main__":
    run_spotcheck_report()
