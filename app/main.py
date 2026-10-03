"""FastAPI application factory, lifespan management, routes, and exception handlers."""

import logging
import secrets
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.catalog import CatalogRepository
from app.config import settings
from app.embedder import Embedder, SentenceTransformerEmbedder
from app.exceptions import CatalogError, FashionSearchError, IndexingError, ProductNotFoundError
from app.index import HybridIndex
from app.llm.gemini import GeminiClient
from app.parser import QueryParser
from app.pipeline import transform_raw_record, validate_raw_record
from app.schemas import (
    HealthResponse,
    Product,
    ProductBatchItemResult,
    ProductBatchRequest,
    ProductBatchResponse,
    ProductDeleteResponse,
    SearchRequest,
    SearchResponse,
)
from app.service import SearchService

LOG_FORMAT = (
    '{"timestamp": "%(asctime)s", "level": "%(levelname)s", '
    '"logger": "%(name)s", "message": "%(message)s"}'
)
logging.basicConfig(
    level=logging.INFO if not settings.debug else logging.DEBUG,
    format=LOG_FORMAT,
)
logger = logging.getLogger("fashion_search")

# Global state containers initialized during app lifespan
catalog_repo_instance: CatalogRepository | None = None
embedder_instance: Embedder | None = None
hybrid_index_instance: HybridIndex | None = None
query_parser_instance: QueryParser | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage startup and shutdown lifecycle for dependencies, indexes, and LLM parser."""
    global catalog_repo_instance, embedder_instance, hybrid_index_instance, query_parser_instance

    if catalog_repo_instance is None:
        logger.info("Initializing catalog repository...")
        catalog_repo_instance = CatalogRepository(settings.db_path)

    if embedder_instance is None:
        logger.info("Loading sentence-transformers embedder...")
        embedder_instance = SentenceTransformerEmbedder(settings.embedding_model_name)

    if hybrid_index_instance is None:
        logger.info("Building hybrid index from catalog...")
        hybrid_index_instance = HybridIndex(
            catalog_repo=catalog_repo_instance,
            embedder=embedder_instance,
            cache_dir=settings.data_dir,
        )
        hybrid_index_instance.build_from_catalog()
        logger.info("Hybrid index ready with %d active products.", hybrid_index_instance.size())

    if query_parser_instance is None:
        if settings.llm_api_key and settings.llm_model:
            logger.info("Initializing Gemini LLM parser with model %s...", settings.llm_model)
            client = GeminiClient(api_key=settings.llm_api_key, model=settings.llm_model)
            query_parser_instance = QueryParser(client)
        else:
            logger.info("No LLM configured; using deterministic rule-based query parser.")
            query_parser_instance = QueryParser(None)

    yield

    logger.info("Shutting down application...")


def get_catalog_repo() -> CatalogRepository:
    """Dependency provider for CatalogRepository."""
    if catalog_repo_instance is None:
        raise CatalogError("Catalog repository is not initialized.")
    return catalog_repo_instance


def get_hybrid_index() -> HybridIndex:
    """Dependency provider for HybridIndex."""
    if hybrid_index_instance is None:
        raise IndexingError("Hybrid index is not initialized.")
    return hybrid_index_instance


def get_query_parser() -> QueryParser:
    """Dependency provider for QueryParser."""
    global query_parser_instance
    if query_parser_instance is None:
        query_parser_instance = QueryParser(None)
    return query_parser_instance


def get_search_service(
    repo: Annotated[CatalogRepository, Depends(get_catalog_repo)],
    index: Annotated[HybridIndex, Depends(get_hybrid_index)],
    parser: Annotated[QueryParser, Depends(get_query_parser)],
) -> SearchService:
    """Dependency provider for SearchService."""
    return SearchService(catalog_repo=repo, hybrid_index=index, parser=parser)


def verify_admin_key(
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> None:
    """Verify admin API key using constant-time comparison."""
    if not settings.admin_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="admin_disabled",
        )
    if not x_api_key or not secrets.compare_digest(x_api_key, settings.admin_api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_api_key",
        )


def create_app() -> FastAPI:
    """Create and configure FastAPI microservice instance."""
    app = FastAPI(
        title="Semantic Fashion Recommendation Microservice",
        description="Multilingual natural-language search microservice for fashion products",
        version="0.4.0",
        lifespan=lifespan,
    )

    # Custom Exception Handlers
    @app.exception_handler(ProductNotFoundError)
    async def product_not_found_handler(
        request: Request, exc: ProductNotFoundError
    ) -> JSONResponse:
        logger.warning("Product not found: %s", exc.message)
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"error": "not_found", "message": exc.message},
        )

    @app.exception_handler(FashionSearchError)
    async def domain_exception_handler(request: Request, exc: FashionSearchError) -> JSONResponse:
        logger.error("Domain error (%s): %s", exc.__class__.__name__, exc.message)
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.__class__.__name__, "message": exc.message},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        logger.warning("Request validation failed: %s", exc.errors())
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"error": "validation_error", "details": exc.errors()},
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled server exception: %s", str(exc))
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": "internal_server_error", "message": "An unexpected error occurred."},
        )

    # Health Endpoint
    @app.get("/health", response_model=HealthResponse, tags=["Monitoring"])
    async def health_check(
        repo: Annotated[CatalogRepository, Depends(get_catalog_repo)],
        index: Annotated[HybridIndex, Depends(get_hybrid_index)],
        service: Annotated[SearchService, Depends(get_search_service)],
    ) -> HealthResponse:
        """Health check verifying index state, database connectivity, and LLM configuration."""
        catalog_count = repo.count_active()
        index_size = index.size()
        return HealthResponse(
            status="healthy",
            index_loaded=index_size > 0,
            catalog_reachable=True,
            llm_status=service.llm_status,
            index_size=index_size,
            catalog_size=catalog_count,
        )

    # Search Endpoint
    @app.post("/search", response_model=SearchResponse, tags=["Search"])
    async def search_endpoint(
        request: SearchRequest,
        service: Annotated[SearchService, Depends(get_search_service)],
    ) -> SearchResponse:
        """Execute natural-language semantic and keyword hybrid product search."""
        return service.search(request)

    # Product Batch Ingestion Endpoint
    @app.post(
        "/products",
        response_model=ProductBatchResponse,
        dependencies=[Depends(verify_admin_key)],
        tags=["Catalog Administration"],
    )
    async def batch_ingest_products(
        batch_req: ProductBatchRequest,
        repo: Annotated[CatalogRepository, Depends(get_catalog_repo)],
        index: Annotated[HybridIndex, Depends(get_hybrid_index)],
    ) -> ProductBatchResponse:
        """Ingest raw Amazon metadata records in batch with atomic persistence."""
        item_results: list[ProductBatchItemResult | None] = [None] * len(batch_req.products)
        valid_records: list[tuple[int, Product]] = []
        seen_in_batch: set[str] = set()
        global_mean = repo.compute_global_mean_rating()

        for idx, raw_record in enumerate(batch_req.products):
            asin = raw_record.get("parent_asin") or raw_record.get("asin")
            if not asin:
                item_results[idx] = ProductBatchItemResult(
                    parent_asin="unknown",
                    status="rejected",
                    reason="no_parent_asin",
                )
                continue

            asin_str = str(asin).strip()
            if asin_str in seen_in_batch:
                item_results[idx] = ProductBatchItemResult(
                    parent_asin=asin_str,
                    status="rejected",
                    reason="duplicate_in_batch",
                )
                continue
            seen_in_batch.add(asin_str)

            is_valid, reason = validate_raw_record(
                raw_record,
                require_price=not settings.include_unknown_price,
                min_title_length=settings.min_title_length,
            )
            if not is_valid:
                item_results[idx] = ProductBatchItemResult(
                    parent_asin=asin_str,
                    status="rejected",
                    reason=reason or "validation_failed",
                )
                continue

            product = transform_raw_record(
                raw_record,
                global_mean_rating=global_mean,
                bayesian_m=settings.bayesian_m,
            )
            valid_records.append((idx, product))

        # Atomically persist valid products and update indexes
        valid_products = [p for _, p in valid_records]
        persisted = index.upsert_batch_atomic(valid_products)
        persisted_map = {p.parent_asin: p for p in persisted}

        # Populate accepted items in exact input order
        for idx, product in valid_records:
            persisted_p = persisted_map[product.parent_asin]
            item_status: Literal["created", "updated"] = (
                "created" if persisted_p.version == 1 else "updated"
            )
            item_results[idx] = ProductBatchItemResult(
                parent_asin=product.parent_asin,
                status=item_status,
                version=persisted_p.version,
            )

        final_items = [item for item in item_results if item is not None]
        accepted_cnt = len(persisted)
        rejected_cnt = len(final_items) - accepted_cnt

        return ProductBatchResponse(
            accepted_count=accepted_cnt,
            rejected_count=rejected_cnt,
            index_version=index.index_version,
            items=final_items,
        )

    # Product Soft-Delete Endpoint
    @app.delete(
        "/products/{id}",
        response_model=ProductDeleteResponse,
        dependencies=[Depends(verify_admin_key)],
        tags=["Catalog Administration"],
    )
    async def delete_product_endpoint(
        id: str,
        index: Annotated[HybridIndex, Depends(get_hybrid_index)],
    ) -> ProductDeleteResponse:
        """Soft-delete product by ID and immediately remove from search indexes."""
        exists, already_deleted = index.delete_product(id)
        if not exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product '{id}' not found in catalog.",
            )

        del_status: Literal["deleted", "already_deleted"] = (
            "already_deleted" if already_deleted else "deleted"
        )
        return ProductDeleteResponse(
            product_id=id,
            status=del_status,
            index_version=index.index_version,
        )

    return app


app = create_app()
