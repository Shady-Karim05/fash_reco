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

    # Soft boosts
    boost_weight_season: float = 0.05
    boost_weight_occasion: float = 0.05
    boost_weight_color: float = 0.03
    quality_boost_weight: float = 0.05
    bayesian_m: float = 10.0
    global_mean_rating: float = 4.2

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
