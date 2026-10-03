"""Session-scoped pytest fixtures and catalog database guard."""

import hashlib
import sqlite3
from collections.abc import Generator
from pathlib import Path

import pytest

from app.config import settings


@pytest.fixture(scope="session", autouse=True)
def guard_catalog_db() -> Generator[None, None, None]:
    """Guard session to ensure data/catalog.db is never mutated by test suites."""
    db_path = Path(settings.db_path)
    if not db_path.is_file():
        yield
        return

    initial_sha = hashlib.sha256(db_path.read_bytes()).hexdigest()
    with sqlite3.connect(db_path) as conn:
        initial_count = conn.cursor().execute("SELECT COUNT(*) FROM products").fetchone()[0]

    yield

    final_sha = hashlib.sha256(db_path.read_bytes()).hexdigest()
    with sqlite3.connect(db_path) as conn:
        final_count = conn.cursor().execute("SELECT COUNT(*) FROM products").fetchone()[0]

    assert initial_sha == final_sha, (
        f"data/catalog.db SHA256 mutated during test run! (before={initial_sha}, after={final_sha})"
    )
    assert initial_count == final_count, (
        f"data/catalog.db row count mutated during test run! "
        f"(before={initial_count}, after={final_count})"
    )
