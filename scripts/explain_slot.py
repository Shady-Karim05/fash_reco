"""Explain ordered slot classification rule trace for a given product title (D5d)."""

import argparse
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.attributes import SLOT_PATTERNS


def explain_slot_trace(title: str) -> None:
    """Print ordered rule-by-rule evaluation trace for slot classification."""
    print("=" * 80)
    print("SLOT CLASSIFICATION TRACE")
    print(f"Title: {title}")
    print("=" * 80)

    matched_slot = None
    for step, (slot_name, pattern) in enumerate(SLOT_PATTERNS, 1):
        match = pattern.search(title)
        if match:
            print(f"[Step {step:02d}] MATCH -> Slot: '{slot_name}'")
            print(f"           Matched substring : '{match.group(0)}'")
            print(f"           Matched span      : {match.span()}")
            print(f"           Regex pattern     : {pattern.pattern[:80]}...")
            matched_slot = slot_name
            break
        else:
            print(f"[Step {step:02d}] NO MATCH for slot '{slot_name}'")

    print("-" * 80)
    if matched_slot:
        print(f"FINAL RESULT: Slot = '{matched_slot}'")
    else:
        print("FINAL RESULT: Slot = 'unknown' (no rules matched)")
    print("=" * 80)


def main() -> None:
    parser = argparse.ArgumentParser(description="Explain slot rule trace for a title.")
    parser.add_argument("title", nargs="?", help="Product title to trace")
    args = parser.parse_args()

    if not args.title:
        # Default test cases from D5(d)
        titles = [
            (
                "Humaira Nautical Brass Sand Timer Pendant Necklace Key Ring Maritime "
                "Nautical Key chain, Necklaces Fashion Costume Womens Mothers "
                "Women's Necklace Pendant"
            ),
            (
                "American Trends Men's Workout Shorts Athletic Pajamas Shorts "
                "Elastic Waist Gym Shorts Casual Jogger Shorts with Zip Pockets"
            ),
        ]
        for t in titles:
            explain_slot_trace(t)
            print()
    else:
        explain_slot_trace(args.title)


if __name__ == "__main__":
    main()
