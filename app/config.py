"""Configuration settings for the Fashion Search microservice."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and defaults."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Server settings
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    # LLM settings
    llm_api_key: str = ""
    llm_model: str = ""  # Leave blank to require explicit configuration
    llm_timeout_seconds: float = 3.0

    # Model & Embedder settings
    embedding_model_name: str = "paraphrase-multilingual-MiniLM-L12-v2"
    embedding_batch_size: int = 64

    # Storage paths
    data_dir: Path = Path("data")
    db_path: Path = Path("data/catalog.db")
    faiss_index_path: Path = Path("data/faiss.index")
    bm25_index_path: Path = Path("data/bm25.pkl")
    id_map_path: Path = Path("data/id_map.json")
    held_out_path: Path = Path("data/held_out_products.jsonl")
    raw_meta_path: Path = Path("meta_Amazon_Fashion.jsonl/meta_Amazon_Fashion.jsonl")
    raw_reviews_path: Path = Path("data/Amazon_Fashion.jsonl")

    # Ingestion & catalog policies
    include_unknown_price: bool = False
    min_title_length: int = 15
    sample_size: int = 30000
    held_out_fraction: float = 0.2
    random_seed: int = 42
    max_batch_size: int = 500
    admin_api_key: str = ""

    # Data Cleaning & Quality Control policies
    qc_min_title_length: int = 10
    qc_min_quality_score: float = 0.35
    qc_min_classification_confidence: str = "medium"
    qc_price_min: float = 0.20
    qc_price_max: float = 10000.0
    qc_min_search_text_tokens: int = 3
    quarantine_db_path: Path = Path("data/quarantine.db")
    quarantine_jsonl_path: Path = Path("data/quarantine.jsonl")
    cleaning_report_path: Path = Path("data/cleaning_report.json")

    # Retrieval & Ranking tunables
    rrf_k: int = 60
    retrieval_top_k: int = 50
    default_top_k: int = 10
    max_top_k: int = 50
    max_query_length: int = 500
    min_similarity_threshold: float = 0.0
    low_confidence_similarity: float = 0.6191
    progressive_pool_sizes: list[int] = [50, 200, 1000]
    gender_include_unknown: bool = False

    # Reranker & Metadata Filtering Tunables (Phases 2, 4, 5, 6)
    reranker_enabled: bool = True
    reranker_candidate_k: int = 50
    reranker_use_cross_encoder: bool = False
    reranker_cross_encoder_model: str = "cross-encoder/ms-marco-TinyBERT-L-2-v2"
    reranker_cross_encoder_top_n: int = 20
    reranker_cross_encoder_blend: float = 0.35
    reranker_cache_size: int = 1000

    # Configurable Reranker Feature Weights
    reranker_weight_semantic: float = 0.28
    reranker_weight_lexical: float = 0.12
    reranker_weight_exact_phrase: float = 0.15
    reranker_weight_slot: float = 0.20
    reranker_weight_color: float = 0.10
    reranker_weight_demographic: float = 0.08
    reranker_weight_occasion: float = 0.05
    reranker_weight_quality: float = 0.05
    reranker_weight_price: float = 0.05
    reranker_costume_penalty: float = 0.35

    # Soft boosts
    boost_weight_season: float = 0.05
    boost_weight_occasion: float = 0.05
    boost_weight_color: float = 0.03
    boost_weight_brand: float = 0.05
    quality_weight: float = 0.05
    quality_boost_weight: float = 0.05
    bayesian_m: float = 10.0
    global_mean_rating: float = 4.2

    # Phase 5 Policies and Caches
    innerwear_policy: str = "exclude_unless_requested"
    innerwear_keywords: list[str] = [
        "underwear",
        "bra",
        "panties",
        "panty",
        "briefs",
        "boxers",
        "lingerie",
        "bralette",
        "boxer briefs",
        "shapewear",
        "thong",
        "jock",
    ]
    outfit_similarity_floor: float = 0.35
    outfit_min_item_price: float = 2.00
    outfit_compatibility_weight: float = 0.15
    outfit_candidate_depths: list[int] = [50, 100, 200, 400]
    llm_breaker_failures: int = 3
    llm_breaker_cooldown_seconds: float = 60.0
    non_english_fallback_policy: str = "warn"
    log_queries: bool = False
    metrics_window_size: int = 1000
    parse_cache_ttl_seconds: int = 3600
    parse_cache_size: int = 1000
    query_cache_size: int = 1000

    # Guardrails & Noise Filtering
    lru_cache_size: int = 1000
    multilingual_stopwords: set[str] = {
        "de",
        "la",
        "le",
        "les",
        "pour",
        "des",
        "el",
        "para",
        "und",
        "der",
        "die",
        "das",
        "per",
        "con",
        "del",
        "della",
        "gli",
        "delle",
        "por",
        "sobre",
        "avec",
        "dans",
        "sur",
        "en",
        "un",
        "une",
        "los",
        "las",
        "unos",
        "unas",
    }
    suggested_queries: list[str] = [
        "summer beach outfit",
        "women's running shoes",
        "men's casual cotton shirt",
    ]


settings = Settings()
