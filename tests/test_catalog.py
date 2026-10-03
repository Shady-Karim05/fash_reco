"""Unit tests for SQLite catalog repository, versioning, and soft deletion."""

from pathlib import Path

import pytest

from app.catalog import CatalogRepository
from app.exceptions import ProductNotFoundError
from app.schemas import Product


@pytest.fixture
def temp_repo(tmp_path: Path) -> CatalogRepository:
    """Fixture providing an isolated catalog repository instance."""
    db_file = tmp_path / "test_catalog.db"
    return CatalogRepository(db_file)


@pytest.fixture
def sample_product() -> Product:
    """Fixture providing a baseline Product instance."""
    return Product(
        parent_asin="B0811M2JG9",
        title="Mento Streamtail Thong Sandal",
        store="Mento",
        price=29.81,
        average_rating=4.5,
        rating_number=50,
        quality_score=4.45,
        image_url="https://example.com/sandal.jpg",
        gender="unisex",
        age_group="adult",
        slot="footwear",
        colors=["black"],
        seasons=["summer"],
        occasions=["beach"],
        features=["Leather strap", "Cushioned footbed"],
        description="Comfortable beach sandals.",
        search_text="Mento Streamtail Thong Sandal. Brand: Mento. Type: footwear.",
    )


class TestCatalogRepository:
    """Tests for SQLite catalog operations."""

    def test_upsert_and_retrieve_product(
        self, temp_repo: CatalogRepository, sample_product: Product
    ) -> None:
        """New product is inserted with version=1 and correct attributes."""
        saved = temp_repo.upsert_product(sample_product)
        assert saved.version == 1
        assert saved.is_deleted is False
        assert saved.created_at != ""
        assert saved.updated_at != ""

        retrieved = temp_repo.get_by_id(sample_product.parent_asin)
        assert retrieved is not None
        assert retrieved.parent_asin == sample_product.parent_asin
        assert retrieved.title == sample_product.title
        assert retrieved.price == sample_product.price
        assert retrieved.version == 1

    def test_version_increments_on_repost(
        self, temp_repo: CatalogRepository, sample_product: Product
    ) -> None:
        """Upserting the same product increments version and updates timestamp."""
        p1 = temp_repo.upsert_product(sample_product)
        assert p1.version == 1
        initial_created = p1.created_at

        # Update title and repost
        updated_input = sample_product.model_copy(update={"title": "Updated Mento Sandal"})
        p2 = temp_repo.upsert_product(updated_input)
        assert p2.version == 2
        assert p2.created_at == initial_created
        assert p2.title == "Updated Mento Sandal"

        # Repost third time
        p3 = temp_repo.upsert_product(p2)
        assert p3.version == 3

    def test_soft_delete_and_visibility(
        self, temp_repo: CatalogRepository, sample_product: Product
    ) -> None:
        """Soft-deleted products are hidden from standard queries."""
        temp_repo.upsert_product(sample_product)
        assert temp_repo.count_active() == 1

        # Perform soft delete
        deleted = temp_repo.soft_delete(sample_product.parent_asin)
        assert deleted is True
        assert temp_repo.count_active() == 0

        # Normal get returns None
        assert temp_repo.get_by_id(sample_product.parent_asin) is None

        # get with include_deleted=True returns the product marked deleted
        with_deleted = temp_repo.get_by_id(sample_product.parent_asin, include_deleted=True)
        assert with_deleted is not None
        assert with_deleted.is_deleted is True

    def test_soft_delete_missing_raises_error(self, temp_repo: CatalogRepository) -> None:
        """Soft deleting a nonexistent ID raises ProductNotFoundError."""
        with pytest.raises(ProductNotFoundError):
            temp_repo.soft_delete("NONEXISTENT_ID")

    def test_batch_upsert_and_get_by_ids(self, temp_repo: CatalogRepository) -> None:
        """Batch upsert persists multiple items in a single transaction."""
        products = [
            Product(
                parent_asin=f"PROD_{i}",
                title=f"Fashion Item {i}",
                slot="top",
                quality_score=4.2,
                search_text=f"Item {i}",
            )
            for i in range(5)
        ]
        saved = temp_repo.upsert_products_batch(products)
        assert len(saved) == 5
        assert temp_repo.count_active() == 5

        ids = ["PROD_0", "PROD_2", "PROD_4"]
        results = temp_repo.get_by_ids(ids)
        assert len(results) == 3
        assert set(results.keys()) == set(ids)

    def test_compute_global_mean_rating(
        self, temp_repo: CatalogRepository, sample_product: Product
    ) -> None:
        """Computes average rating across active products."""
        temp_repo.upsert_product(sample_product)  # rating 4.5
        p2 = sample_product.model_copy(
            update={"parent_asin": "PROD_2", "average_rating": 3.5, "rating_number": 10}
        )
        temp_repo.upsert_product(p2)

        mean = temp_repo.compute_global_mean_rating()
        assert round(mean, 2) == 4.0
