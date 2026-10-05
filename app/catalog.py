"""SQLite catalog repository for product persistence, versioning, and soft deletion."""

import json
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from app.attributes import derive_slot
from app.exceptions import CatalogError, ProductNotFoundError
from app.schemas import Product


class CatalogRepository:
    """SQLite-backed product catalog repository ensuring ACID persistence."""

    def __init__(self, db_path: Path | str) -> None:
        """Initialize catalog repository.

        Args:
            db_path: Path to SQLite database file.
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    @contextmanager
    def _get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager providing configured SQLite database connection.

        Yields:
            sqlite3.Connection with row_factory set to sqlite3.Row.
        """
        try:
            conn = sqlite3.connect(str(self.db_path), timeout=30.0)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            yield conn
            conn.commit()
        except sqlite3.Error as e:
            if "conn" in locals():
                conn.rollback()
            raise CatalogError(f"Database error: {e}") from e
        finally:
            if "conn" in locals():
                conn.close()

    def init_db(self) -> None:
        """Create tables and indexes if they do not exist."""
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS products (
                    parent_asin TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    store TEXT,
                    price REAL,
                    average_rating REAL,
                    rating_number INTEGER,
                    quality_score REAL NOT NULL,
                    image_url TEXT,
                    gender TEXT NOT NULL,
                    age_group TEXT NOT NULL,
                    slot TEXT NOT NULL,
                    accessory_type TEXT,
                    colors TEXT NOT NULL,
                    seasons TEXT NOT NULL,
                    occasions TEXT NOT NULL,
                    features TEXT NOT NULL,
                    description TEXT,
                    review_snippets TEXT NOT NULL DEFAULT '[]',
                    search_text TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    is_deleted INTEGER NOT NULL DEFAULT 0
                );
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_products_slot ON products(slot);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_products_gender ON products(gender);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_products_age ON products(age_group);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_products_price ON products(price);")

            # Embeddings persistence table (A5)
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS embeddings (
                    parent_asin TEXT PRIMARY KEY,
                    text_hash TEXT NOT NULL,
                    model_name TEXT NOT NULL,
                    vector BLOB NOT NULL
                );
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_embeddings_model ON embeddings(model_name);"
            )

            # Metadata table for monotonic index_version
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )
            conn.execute("INSERT OR IGNORE INTO meta (key, value) VALUES ('index_version', '1');")

            # Migration: ensure review_snippets and accessory_type exist on existing databases
            cursor = conn.execute("PRAGMA table_info(products)")
            cols = [r["name"] for r in cursor.fetchall()]
            if "review_snippets" not in cols:
                conn.execute(
                    "ALTER TABLE products ADD COLUMN review_snippets TEXT NOT NULL DEFAULT '[]'"
                )
            if "accessory_type" not in cols:
                conn.execute("ALTER TABLE products ADD COLUMN accessory_type TEXT")

    def get_index_version(self) -> int:
        """Get the current persisted monotonic index version."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT value FROM meta WHERE key = 'index_version'").fetchone()
            if row:
                return int(row["value"])
            return 1

    def increment_index_version(self) -> int:
        """Increment and return the persisted monotonic index version."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT value FROM meta WHERE key = 'index_version'").fetchone()
            current_ver = int(row["value"]) if row else 1
            new_ver = current_ver + 1
            conn.execute(
                "INSERT OR REPLACE INTO meta (key, value) VALUES ('index_version', ?)",
                (str(new_ver),),
            )
            return new_ver

    def _row_to_product(self, row: sqlite3.Row) -> Product:
        """Convert SQLite row to Product Pydantic model."""
        data = dict(row)
        slot = data["slot"]
        # Phase 7: Contextual phrase-level correction
        derived = derive_slot(data["title"])
        if derived == "top" and slot == "bottom":
            slot = "top"

        return Product(
            parent_asin=data["parent_asin"],
            title=data["title"],
            store=data["store"],
            price=data["price"],
            average_rating=data["average_rating"],
            rating_number=data["rating_number"],
            quality_score=data["quality_score"],
            image_url=data["image_url"],
            gender=data["gender"],
            age_group=data["age_group"],
            slot=slot,
            accessory_type=data.get("accessory_type"),
            colors=json.loads(data["colors"]),
            seasons=json.loads(data["seasons"]),
            occasions=json.loads(data["occasions"]),
            features=json.loads(data["features"]),
            description=data["description"],
            review_snippets=json.loads(data["review_snippets"])
            if data.get("review_snippets")
            else [],
            search_text=data["search_text"],
            version=data["version"],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            is_deleted=bool(data["is_deleted"]),
        )

    def upsert_product(self, product: Product) -> Product:
        """Upsert a single product with version incrementing and timestamp handling.

        Args:
            product: Product model to upsert.

        Returns:
            The persisted Product with updated version and timestamps.
        """
        results = self.upsert_products_batch([product])
        return results[0]

    def upsert_products_batch(self, products: list[Product]) -> list[Product]:
        """Batch upsert products inside a single atomic transaction.

        Args:
            products: List of products to persist.

        Returns:
            List of persisted Product instances.
        """
        if not products:
            return []

        now_str = datetime.now(UTC).isoformat()
        persisted: list[Product] = []

        with self._get_connection() as conn:
            for p in products:
                # Check if product already exists
                cur = conn.execute(
                    "SELECT version, created_at FROM products WHERE parent_asin = ?",
                    (p.parent_asin,),
                )
                existing = cur.fetchone()

                if existing:
                    new_version = existing["version"] + 1
                    created_at = existing["created_at"]
                else:
                    new_version = 1
                    created_at = p.created_at or now_str

                updated_at = now_str

                conn.execute(
                    """
                    INSERT INTO products (
                        parent_asin, title, store, price, average_rating, rating_number,
                        quality_score, image_url, gender, age_group, slot, accessory_type, colors,
                        seasons, occasions, features, description, review_snippets, search_text,
                        version, created_at, updated_at, is_deleted
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(parent_asin) DO UPDATE SET
                        title = excluded.title,
                        store = excluded.store,
                        price = excluded.price,
                        average_rating = excluded.average_rating,
                        rating_number = excluded.rating_number,
                        quality_score = excluded.quality_score,
                        image_url = excluded.image_url,
                        gender = excluded.gender,
                        age_group = excluded.age_group,
                        slot = excluded.slot,
                        accessory_type = excluded.accessory_type,
                        colors = excluded.colors,
                        seasons = excluded.seasons,
                        occasions = excluded.occasions,
                        features = excluded.features,
                        description = excluded.description,
                        review_snippets = excluded.review_snippets,
                        search_text = excluded.search_text,
                        version = excluded.version,
                        updated_at = excluded.updated_at,
                        is_deleted = 0;
                    """,
                    (
                        p.parent_asin,
                        p.title,
                        p.store,
                        p.price,
                        p.average_rating,
                        p.rating_number,
                        p.quality_score,
                        p.image_url,
                        p.gender,
                        p.age_group,
                        p.slot,
                        p.accessory_type,
                        json.dumps(p.colors),
                        json.dumps(p.seasons),
                        json.dumps(p.occasions),
                        json.dumps(p.features),
                        p.description,
                        json.dumps(p.review_snippets),
                        p.search_text,
                        new_version,
                        created_at,
                        updated_at,
                        0,
                    ),
                )

                updated_p = p.model_copy(
                    update={
                        "version": new_version,
                        "created_at": created_at,
                        "updated_at": updated_at,
                        "is_deleted": False,
                    }
                )
                persisted.append(updated_p)

        return persisted

    def upsert_products_and_embeddings_batch(
        self,
        products: list[Product],
        embeddings_data: list[tuple[str, str, str, bytes]],
    ) -> list[Product]:
        """Batch upsert products and their embedding vectors in the same atomic transaction (A5).

        Args:
            products: List of Product domain objects.
            embeddings_data: List of (parent_asin, text_hash, model_name, vector_blob) tuples.

        Returns:
            List of persisted Product instances.
        """
        if not products:
            return []

        now_str = datetime.now(UTC).isoformat()
        persisted: list[Product] = []

        with self._get_connection() as conn:
            for p in products:
                cur = conn.execute(
                    "SELECT version, created_at FROM products WHERE parent_asin = ?",
                    (p.parent_asin,),
                )
                existing = cur.fetchone()

                if existing:
                    new_version = existing["version"] + 1
                    created_at = existing["created_at"]
                else:
                    new_version = 1
                    created_at = p.created_at or now_str

                updated_at = now_str

                conn.execute(
                    """
                    INSERT INTO products (
                        parent_asin, title, store, price, average_rating, rating_number,
                        quality_score, image_url, gender, age_group, slot, accessory_type, colors,
                        seasons, occasions, features, description, review_snippets, search_text,
                        version, created_at, updated_at, is_deleted
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(parent_asin) DO UPDATE SET
                        title = excluded.title,
                        store = excluded.store,
                        price = excluded.price,
                        average_rating = excluded.average_rating,
                        rating_number = excluded.rating_number,
                        quality_score = excluded.quality_score,
                        image_url = excluded.image_url,
                        gender = excluded.gender,
                        age_group = excluded.age_group,
                        slot = excluded.slot,
                        accessory_type = excluded.accessory_type,
                        colors = excluded.colors,
                        seasons = excluded.seasons,
                        occasions = excluded.occasions,
                        features = excluded.features,
                        description = excluded.description,
                        review_snippets = excluded.review_snippets,
                        search_text = excluded.search_text,
                        version = excluded.version,
                        updated_at = excluded.updated_at,
                        is_deleted = 0;
                    """,
                    (
                        p.parent_asin,
                        p.title,
                        p.store,
                        p.price,
                        p.average_rating,
                        p.rating_number,
                        p.quality_score,
                        p.image_url,
                        p.gender,
                        p.age_group,
                        p.slot,
                        p.accessory_type,
                        json.dumps(p.colors),
                        json.dumps(p.seasons),
                        json.dumps(p.occasions),
                        json.dumps(p.features),
                        p.description,
                        json.dumps(p.review_snippets),
                        p.search_text,
                        new_version,
                        created_at,
                        updated_at,
                        0,
                    ),
                )

                updated_p = p.model_copy(
                    update={
                        "version": new_version,
                        "created_at": created_at,
                        "updated_at": updated_at,
                        "is_deleted": False,
                    }
                )
                persisted.append(updated_p)

            # Insert/update embeddings in same transaction
            for asin, thash, mname, vblob in embeddings_data:
                conn.execute(
                    """
                    INSERT INTO embeddings (parent_asin, text_hash, model_name, vector)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(parent_asin) DO UPDATE SET
                        text_hash = excluded.text_hash,
                        model_name = excluded.model_name,
                        vector = excluded.vector;
                    """,
                    (asin, thash, mname, vblob),
                )

        return persisted

    def get_all_embeddings(self, model_name: str) -> dict[str, tuple[str, bytes]]:
        """Retrieve all stored embeddings matching the given model_name.

        Args:
            model_name: Target embedding model identifier.

        Returns:
            Dictionary mapping parent_asin to (text_hash, vector_bytes).
        """
        results: dict[str, tuple[str, bytes]] = {}
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT parent_asin, text_hash, vector FROM embeddings WHERE model_name = ?",
                (model_name,),
            ).fetchall()
            for r in rows:
                results[r["parent_asin"]] = (r["text_hash"], r["vector"])
        return results

    def upsert_embeddings_batch(self, embeddings_data: list[tuple[str, str, str, bytes]]) -> None:
        """Batch upsert embedding vectors into embeddings table.

        Args:
            embeddings_data: List of (parent_asin, text_hash, model_name, vector_blob) tuples.
        """
        if not embeddings_data:
            return
        with self._get_connection() as conn:
            conn.executemany(
                """
                INSERT INTO embeddings (parent_asin, text_hash, model_name, vector)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(parent_asin) DO UPDATE SET
                    text_hash = excluded.text_hash,
                    model_name = excluded.model_name,
                    vector = excluded.vector;
                """,
                embeddings_data,
            )

    def get_quality_score_bounds(self) -> tuple[float, float]:
        """Get min and max Bayesian quality scores from active products.

        Returns:
            Tuple of (min_quality, max_quality). Defaults to (0.0, 5.0) if empty.
        """
        with self._get_connection() as conn:
            row = conn.execute(
                """
                SELECT MIN(quality_score) as min_q, MAX(quality_score) as max_q
                FROM products
                WHERE is_deleted = 0
                """
            ).fetchone()
            if row and row["min_q"] is not None and row["max_q"] is not None:
                min_q = float(row["min_q"])
                max_q = float(row["max_q"])
                if min_q == max_q:
                    return min_q, min_q + 1.0
            return 0.0, 5.0

    def soft_delete_product(self, parent_asin: str) -> tuple[bool, bool]:
        """Soft delete a product by ID.

        Args:
            parent_asin: Product unique identifier.

        Returns:
            Tuple of (exists: bool, was_already_deleted: bool).
        """
        now_str = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            check = conn.execute(
                "SELECT is_deleted FROM products WHERE parent_asin = ?",
                (parent_asin,),
            ).fetchone()
            if not check:
                return False, False
            if bool(check["is_deleted"]):
                return True, True

            conn.execute(
                """
                UPDATE products
                SET is_deleted = 1, updated_at = ?
                WHERE parent_asin = ?
                """,
                (now_str, parent_asin),
            )
            return True, False

    def soft_delete(self, parent_asin: str) -> bool:
        """Mark a product as deleted (soft delete).

        Args:
            parent_asin: Unique product identifier.

        Returns:
            True if product was found and soft-deleted, False otherwise.
        """
        exists, was_already = self.soft_delete_product(parent_asin)
        if not exists:
            raise ProductNotFoundError(parent_asin)
        return not was_already

    def get_by_id(self, parent_asin: str, include_deleted: bool = False) -> Product | None:
        """Retrieve single product by parent_asin.

        Args:
            parent_asin: Unique identifier.
            include_deleted: Whether to return soft-deleted product.

        Returns:
            Product instance if found, else None.
        """
        query = "SELECT * FROM products WHERE parent_asin = ?"
        if not include_deleted:
            query += " AND is_deleted = 0"

        with self._get_connection() as conn:
            row = conn.execute(query, (parent_asin,)).fetchone()
            if row:
                return self._row_to_product(row)
        return None

    def get_by_ids(
        self, parent_asins: list[str], include_deleted: bool = False
    ) -> dict[str, Product]:
        """Retrieve multiple products by their identifiers.

        Args:
            parent_asins: List of product IDs.
            include_deleted: Whether to include soft-deleted products.

        Returns:
            Dictionary mapping parent_asin to Product.
        """
        if not parent_asins:
            return {}

        placeholders = ",".join("?" for _ in parent_asins)
        query = f"SELECT * FROM products WHERE parent_asin IN ({placeholders})"
        if not include_deleted:
            query += " AND is_deleted = 0"

        results: dict[str, Product] = {}
        with self._get_connection() as conn:
            for row in conn.execute(query, parent_asins):
                prod = self._row_to_product(row)
                results[prod.parent_asin] = prod

        return results

    def get_all_active(self) -> list[Product]:
        """Retrieve all active (non-deleted) products from catalog.

        Returns:
            List of active Product instances.
        """
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM products WHERE is_deleted = 0").fetchall()
            return [self._row_to_product(r) for r in rows]

    def count_active(self) -> int:
        """Count active (non-deleted) products in catalog.

        Returns:
            Count of active products.
        """
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM products WHERE is_deleted = 0"
            ).fetchone()
            return int(row["cnt"]) if row else 0

    def compute_global_mean_rating(self) -> float:
        """Compute the average rating across all products with valid ratings.

        Returns:
            Global mean rating float (defaults to 4.2 if no data).
        """
        with self._get_connection() as conn:
            row = conn.execute(
                """
                SELECT AVG(average_rating) AS mean_rating
                FROM products
                WHERE is_deleted = 0 AND average_rating IS NOT NULL AND average_rating > 0
                """
            ).fetchone()
            if row and row["mean_rating"] is not None:
                return float(row["mean_rating"])
            return 4.2
