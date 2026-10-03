"""Evaluate query parsing accuracy and latency on real Gemini LLM."""

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.config import settings
from app.llm.gemini import GeminiClient
from app.parser import QueryParser


def run_parser_eval(cases_file: Path | str = "evals/parser_cases.json") -> None:
    """Run real LLM parser evaluation over benchmark cases.

    Prints per-field accuracy, mismatches, fallback rate, and latency percentiles.
    """
    api_key = settings.llm_api_key or os.getenv("LLM_API_KEY", "")
    model_name = settings.llm_model or os.getenv("LLM_MODEL", "")

    if not api_key or not model_name:
        print(
            "[Parser Eval] Error: LLM_API_KEY and LLM_MODEL must be set in .env "
            "to run real LLM parser evaluation."
        )
        print("Exiting without fabricating results.")
        sys.exit(0)

    cases_path = Path(cases_file)
    if not cases_path.is_file():
        print(f"[Parser Eval] Error: Cases file not found at {cases_path}")
        sys.exit(1)

    with open(cases_path, encoding="utf-8") as f:
        cases: list[dict[str, Any]] = json.load(f)

    print(f"=== REAL LLM PARSER ACCURACY EVALUATION (N={len(cases)}) ===")
    print(f"Model: {model_name}\n")

    client = GeminiClient(api_key=api_key, model=model_name)
    parser = QueryParser(client)

    field_correct: dict[str, int] = {
        "is_fashion_query": 0,
        "language": 0,
        "gender": 0,
        "age_group": 0,
        "max_price": 0,
        "min_price": 0,
        "slots": 0,
    }
    total_cases = len(cases)
    fallback_count = 0
    latencies: list[float] = []
    mismatches: list[dict[str, Any]] = []

    for i, case in enumerate(cases, 1):
        q = case["query"]
        expected = case["expected"]

        t0 = time.perf_counter()
        parsed, used_fallback = parser.parse(q)
        lat_ms = (time.perf_counter() - t0) * 1000.0
        latencies.append(lat_ms)

        if used_fallback:
            fallback_count += 1

        case_mismatch = {}

        # 1. is_fashion_query
        if parsed.is_fashion_query == expected.get("is_fashion_query", True):
            field_correct["is_fashion_query"] += 1
        else:
            case_mismatch["is_fashion_query"] = (
                parsed.is_fashion_query,
                expected.get("is_fashion_query"),
            )

        # 2. language
        if parsed.language == expected.get("language"):
            field_correct["language"] += 1
        else:
            case_mismatch["language"] = (parsed.language, expected.get("language"))

        # 3. gender
        if parsed.gender == expected.get("gender"):
            field_correct["gender"] += 1
        else:
            case_mismatch["gender"] = (parsed.gender, expected.get("gender"))

        # 4. age_group
        if parsed.age_group == expected.get("age_group"):
            field_correct["age_group"] += 1
        else:
            case_mismatch["age_group"] = (parsed.age_group, expected.get("age_group"))

        # 5. max_price
        if parsed.max_price == expected.get("max_price"):
            field_correct["max_price"] += 1
        else:
            case_mismatch["max_price"] = (parsed.max_price, expected.get("max_price"))

        # 6. min_price
        if parsed.min_price == expected.get("min_price"):
            field_correct["min_price"] += 1
        else:
            case_mismatch["min_price"] = (parsed.min_price, expected.get("min_price"))

        # 7. slots
        exp_slots = set(expected.get("slots") or [])
        got_slots = set(parsed.slots or [])
        if exp_slots == got_slots:
            field_correct["slots"] += 1
        else:
            case_mismatch["slots"] = (list(got_slots), list(exp_slots))

        if case_mismatch:
            mismatches.append({"query": q, "mismatches": case_mismatch})

        print(
            f"[{i:>2}/{total_cases}] Query: '{q[:35]}...' -> "
            f"Latency: {lat_ms:.1f}ms | Fallback: {used_fallback}"
        )

    p50_lat = np.percentile(latencies, 50) if latencies else 0.0
    p95_lat = np.percentile(latencies, 95) if latencies else 0.0
    fallback_rate = (fallback_count / total_cases * 100) if total_cases > 0 else 0.0

    print("\n--- PER-FIELD ACCURACY ---")
    for field, correct in field_correct.items():
        pct = (correct / total_cases * 100) if total_cases > 0 else 0.0
        print(f"  {field:<18}: {correct:>2}/{total_cases} ({pct:.1f}%)")

    print("\n--- OPERATIONAL METRICS ---")
    print(f"  Fallback Rate      : {fallback_count}/{total_cases} ({fallback_rate:.1f}%)")
    print(f"  Parse Latency p50  : {p50_lat:.2f} ms")
    print(f"  Parse Latency p95  : {p95_lat:.2f} ms")

    if mismatches:
        print(f"\n--- MISMATCH DETAILS ({len(mismatches)} queries with mismatches) ---")
        for m in mismatches:
            print(f"Query: '{m['query']}'")
            for f_name, (got, exp) in m["mismatches"].items():
                print(f"  - {f_name}: Got {got}, Expected {exp}")
    else:
        print("\nAll fields matched expected evaluations perfectly.")


if __name__ == "__main__":
    run_parser_eval()
