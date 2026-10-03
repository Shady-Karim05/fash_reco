"""Execute queries across parsing modes (FakeLLM, Forced Fallback, and Real LLM if configured)."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.catalog import CatalogRepository
from app.config import settings
from app.embedder import SentenceTransformerEmbedder
from app.index import HybridIndex
from app.llm.fake import FakeLLMClient
from app.llm.gemini import GeminiClient
from app.parser import QueryParser
from app.schemas import SearchRequest
from app.service import SearchService

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

EVAL_QUERIES = [
    # Original 12
    ("English - Occasion", "beach outfit for summer"),
    ("English - Men's Athletic", "men's running shorts"),
    ("English - Footwear", "women's sandals"),
    ("English - Winter Outerwear", "warm jacket for winter"),
    ("English - Formal", "formal wedding dress"),
    ("English - Accessory", "compression socks"),
    ("English - Sunglasses", "sunglasses"),
    ("English - Kids", "kids dress"),
    ("Hindi - Beach Variant", "गर्मियों के लिए समुद्र तट के कपड़े"),
    ("Tamil - Beach Variant", "கோடைக்கால கடற்கரை உடை"),
    ("Brand - Under Armour", "Under Armour workout athletic tank"),
    ("Brand - Hanes", "Hanes cotton crew t-shirt"),
    # Phase 3 additions
    ("Filter - Men's Price Constrained", "men's shorts under $20"),
    ("Filter - Girls Dress", "girls dress"),
    ("Demographic - 5yo Boy", "something for my 5 year old boy"),
    ("Multilingual - French USD", "tenue de plage pour l'été sous 30 dollars"),
    ("Multilingual - Hindi USD", "गर्मियों के लिए समुद्र तट के कपड़े 50 डॉलर से कम"),
    ("Multilingual - Tamil USD", "கோடைக்கால கடற்கரை உடை 50 டாலருக்கு கீழ்"),
    ("Currency - Unsupported Rupee", "cotton t-shirt under 500 rupees"),
]

# Configured expected parses for FakeLLMClient mode
FAKE_LLM_RESPONSES = {
    "beach outfit for summer": {
        "normalized_query_en": "beach outfit summer",
        "language": "en",
        "gender": None,
        "age_group": "adult",
        "min_price": None,
        "max_price": None,
        "colors": [],
        "slots": [],
        "season": "summer",
        "occasion": "beach",
        "warnings": [],
    },
    "men's running shorts": {
        "normalized_query_en": "running shorts",
        "language": "en",
        "gender": "men",
        "age_group": "adult",
        "min_price": None,
        "max_price": None,
        "colors": [],
        "slots": ["bottom"],
        "season": None,
        "occasion": "workout",
        "warnings": [],
    },
    "women's sandals": {
        "normalized_query_en": "sandals",
        "language": "en",
        "gender": "women",
        "age_group": "adult",
        "min_price": None,
        "max_price": None,
        "colors": [],
        "slots": ["footwear"],
        "season": "summer",
        "occasion": None,
        "warnings": [],
    },
    "warm jacket for winter": {
        "normalized_query_en": "warm jacket",
        "language": "en",
        "gender": None,
        "age_group": "adult",
        "min_price": None,
        "max_price": None,
        "colors": [],
        "slots": ["top"],
        "season": "winter",
        "occasion": None,
        "warnings": [],
    },
    "formal wedding dress": {
        "normalized_query_en": "formal wedding dress",
        "language": "en",
        "gender": "women",
        "age_group": "adult",
        "min_price": None,
        "max_price": None,
        "colors": [],
        "slots": ["full_body"],
        "season": None,
        "occasion": "formal",
        "warnings": [],
    },
    "compression socks": {
        "normalized_query_en": "compression socks",
        "language": "en",
        "gender": None,
        "age_group": "adult",
        "min_price": None,
        "max_price": None,
        "colors": [],
        "slots": ["accessory"],
        "season": None,
        "occasion": "workout",
        "warnings": [],
    },
    "sunglasses": {
        "normalized_query_en": "sunglasses",
        "language": "en",
        "gender": None,
        "age_group": "adult",
        "min_price": None,
        "max_price": None,
        "colors": [],
        "slots": ["accessory"],
        "season": "summer",
        "occasion": None,
        "warnings": [],
    },
    "kids dress": {
        "normalized_query_en": "dress",
        "language": "en",
        "gender": "women",
        "age_group": "kids",
        "min_price": None,
        "max_price": None,
        "colors": [],
        "slots": ["full_body"],
        "season": None,
        "occasion": None,
        "warnings": [],
    },
    "गर्मियों के लिए समुद्र तट के कपड़े": {
        "normalized_query_en": "beach clothes for summer",
        "language": "hi",
        "gender": None,
        "age_group": "adult",
        "min_price": None,
        "max_price": None,
        "colors": [],
        "slots": [],
        "season": "summer",
        "occasion": "beach",
        "warnings": [],
    },
    "கோடைக்கால கடற்கரை உடை": {
        "normalized_query_en": "summer beach outfit",
        "language": "ta",
        "gender": None,
        "age_group": "adult",
        "min_price": None,
        "max_price": None,
        "colors": [],
        "slots": [],
        "season": "summer",
        "occasion": "beach",
        "warnings": [],
    },
    "Under Armour workout athletic tank": {
        "normalized_query_en": "Under Armour workout athletic tank top",
        "language": "en",
        "gender": None,
        "age_group": "adult",
        "min_price": None,
        "max_price": None,
        "colors": [],
        "slots": ["top"],
        "season": None,
        "occasion": "workout",
        "warnings": [],
    },
    "Hanes cotton crew t-shirt": {
        "normalized_query_en": "Hanes cotton crew t-shirt",
        "language": "en",
        "gender": None,
        "age_group": "adult",
        "min_price": None,
        "max_price": None,
        "colors": [],
        "slots": ["top"],
        "season": None,
        "occasion": "casual",
        "warnings": [],
    },
    "men's shorts under $20": {
        "normalized_query_en": "shorts",
        "language": "en",
        "gender": "men",
        "age_group": "adult",
        "min_price": None,
        "max_price": 20.0,
        "colors": [],
        "slots": ["bottom"],
        "season": None,
        "occasion": None,
        "warnings": [],
    },
    "girls dress": {
        "normalized_query_en": "dress",
        "language": "en",
        "gender": "women",
        "age_group": "kids",
        "min_price": None,
        "max_price": None,
        "colors": [],
        "slots": ["full_body"],
        "season": None,
        "occasion": None,
        "warnings": [],
    },
    "something for my 5 year old boy": {
        "normalized_query_en": "boys clothing",
        "language": "en",
        "gender": "men",
        "age_group": "kids",
        "min_price": None,
        "max_price": None,
        "colors": [],
        "slots": [],
        "season": None,
        "occasion": None,
        "warnings": [],
    },
    "tenue de plage pour l'été sous 30 dollars": {
        "normalized_query_en": "beach outfit summer",
        "language": "fr",
        "gender": None,
        "age_group": "adult",
        "min_price": None,
        "max_price": 30.0,
        "colors": [],
        "slots": [],
        "season": "summer",
        "occasion": "beach",
        "warnings": [],
    },
    "गर्मियों के लिए समुद्र तट के कपड़े 50 डॉलर से कम": {
        "normalized_query_en": "summer beach clothes",
        "language": "hi",
        "gender": None,
        "age_group": "adult",
        "min_price": None,
        "max_price": 50.0,
        "colors": [],
        "slots": [],
        "season": "summer",
        "occasion": "beach",
        "warnings": [],
    },
    "கோடைக்கால கடற்கரை உடை 50 டாலருக்கு கீழ்": {
        "normalized_query_en": "summer beach outfit",
        "language": "ta",
        "gender": None,
        "age_group": "adult",
        "min_price": None,
        "max_price": 50.0,
        "colors": [],
        "slots": [],
        "season": "summer",
        "occasion": "beach",
        "warnings": [],
    },
    "cotton t-shirt under 500 rupees": {
        "normalized_query_en": "cotton t-shirt",
        "language": "en",
        "gender": None,
        "age_group": "adult",
        "min_price": None,
        "max_price": None,
        "colors": [],
        "slots": ["top"],
        "season": None,
        "occasion": "casual",
        "warnings": ["price_currency_not_supported"],
    },
}


def run_query_suite(service: SearchService, mode_name: str) -> None:
    """Execute evaluation queries for a given service configuration."""
    print("\n=======================================================")
    print(f"MODE: {mode_name}")
    print("=======================================================\n")

    for category, query_str in EVAL_QUERIES:
        request = SearchRequest(query=query_str, top_k=5)
        response = service.search(request)

        print(f'Query: "{query_str}" [{category}]')
        print(f"  Parsed Filters      : {response.meta.parsed_filters}")
        print(f"  Used Fallback       : {response.meta.used_fallback}")
        print(f"  Warnings            : {response.meta.warnings}")
        print(f"  Excluded by Filters : {response.meta.excluded_by_filters}")
        print(f"  Latency             : {response.meta.latency_ms:.2f} ms")

        if not response.results:
            print(
                "  (No results returned / all candidates excluded by filters or below threshold)\n"
            )
            continue

        header = (
            f"  {'#':<2} | {'Score':<7} | {'Sim':<6} | {'Price':<7} | "
            f"{'Slot':<10} | {'Gender':<7} | {'Age':<6} | {'Title'}"
        )
        print(header)
        print("  " + "-" * 105)
        for i, res in enumerate(response.results, start=1):
            price_str = f"${res.price:.2f}" if res.price is not None else "N/A"
            title_display = res.title[:45] + ("..." if len(res.title) > 45 else "")
            print(
                f"  {i:<2} | {res.score:<7.4f} | {res.similarity:<6.4f} | {price_str:<7} | "
                f"{res.slot:<10} | {res.gender:<7} | {res.age_group:<6} | {title_display}"
            )
        print()


def main() -> None:
    """Run evaluation suite across FakeLLM, Forced Fallback, and Real LLM (if configured)."""
    parser = argparse.ArgumentParser(description="Try queries across parsing modes.")
    parser.add_argument(
        "--real-llm",
        action="store_true",
        help="Run only Real LLM Mode (requires configured API key).",
    )
    args = parser.parse_args()

    print("Initializing Catalog and Hybrid Index...")
    repo = CatalogRepository(settings.db_path)
    embedder = SentenceTransformerEmbedder(settings.embedding_model_name)
    hybrid_index = HybridIndex(
        catalog_repo=repo,
        embedder=embedder,
        cache_dir=settings.data_dir,
    )
    hybrid_index.build_from_catalog()

    if args.real_llm:
        if settings.llm_api_key and settings.llm_model:
            print("\n[Real LLM Mode] Initializing Gemini client...")
            real_client = GeminiClient(api_key=settings.llm_api_key, model=settings.llm_model)
            real_service = SearchService(
                catalog_repo=repo,
                hybrid_index=hybrid_index,
                parser=QueryParser(llm_client=real_client),
            )
            run_query_suite(real_service, mode_name="Real LLM Mode (Gemini Live API)")
        else:
            print(
                "\nError: --real-llm specified, but LLM_API_KEY / LLM_MODEL "
                "are not configured in .env."
            )
            sys.exit(1)
        return

    # 1. Run with FakeLLMClient (Structured Parse Simulation)
    fake_client = FakeLLMClient(responses=FAKE_LLM_RESPONSES)
    fake_service = SearchService(
        catalog_repo=repo,
        hybrid_index=hybrid_index,
        parser=QueryParser(llm_client=fake_client),
    )
    run_query_suite(fake_service, mode_name="FakeLLM Mode (Simulated Structured LLM Output)")

    # 2. Run with Forced Fallback Mode (Zero LLM Client)
    fallback_service = SearchService(
        catalog_repo=repo,
        hybrid_index=hybrid_index,
        parser=QueryParser(llm_client=None),
    )
    run_query_suite(fallback_service, mode_name="Forced Fallback Mode (Rule-based parsing only)")

    # 3. Real LLM Mode if configured
    if settings.llm_api_key and settings.llm_model:
        try:
            real_client = GeminiClient(api_key=settings.llm_api_key, model=settings.llm_model)
            real_service = SearchService(
                catalog_repo=repo,
                hybrid_index=hybrid_index,
                parser=QueryParser(llm_client=real_client),
            )
            run_query_suite(real_service, mode_name="Real LLM Mode (Gemini Live API)")
        except Exception as e:
            print(f"\n[Real LLM Mode] Failed to initialize live LLM client: {e}")
    else:
        print("\n=======================================================")
        print("Real LLM Mode: NOT EXERCISED (LLM_API_KEY / LLM_MODEL not configured in .env)")
        print("=======================================================\n")


if __name__ == "__main__":
    main()
