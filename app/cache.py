"""Thread-safe LRU Query Cache and TTL Parse Cache for search performance (B6)."""

import threading
import time
from collections import OrderedDict
from typing import Any

from app.parser import ParsedQuery
from app.schemas import OutfitResponse, SearchResponse


class QueryCache:
    """Thread-safe LRU cache for search and outfit responses.

    Keyed by: (normalized_query_en, filter_tuple, brand, top_k, mode, index_version).
    Naturally invalidated by index_version changes.
    """

    def __init__(self, max_size: int = 1000) -> None:
        """Initialize query cache.

        Args:
            max_size: Maximum entries before evicting least recently used.
        """
        self.max_size = max_size
        self._cache: OrderedDict[tuple[Any, ...], SearchResponse | OutfitResponse] = OrderedDict()
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def make_key(
        self,
        normalized_query_en: str,
        filters: dict[str, Any],
        brand: str | None,
        top_k: int,
        mode: str,
        index_version: int,
    ) -> tuple[Any, ...]:
        """Create deterministic immutable tuple key for cache lookup.

        Args:
            normalized_query_en: English normalized query string.
            filters: Filter dictionary.
            brand: Brand filter string if any.
            top_k: Top k requested.
            mode: Search mode ('product' or 'outfit').
            index_version: Monotonic index version.

        Returns:
            Immutable tuple key.
        """
        filter_tuple = tuple(
            sorted((k, tuple(v) if isinstance(v, list) else v) for k, v in filters.items())
        )
        return (
            normalized_query_en.strip().lower(),
            filter_tuple,
            brand.lower() if brand else None,
            top_k,
            mode,
            index_version,
        )

    def get(self, key: tuple[Any, ...]) -> SearchResponse | OutfitResponse | None:
        """Retrieve cached response if present.

        Args:
            key: Cache key tuple.

        Returns:
            Cached response or None.
        """
        with self._lock:
            if key in self._cache:
                self.hits += 1
                self._cache.move_to_end(key)
                return self._cache[key]
            self.misses += 1
            return None

    def put(self, key: tuple[Any, ...], response: SearchResponse | OutfitResponse) -> None:
        """Store response in cache.

        Args:
            key: Cache key tuple.
            response: Response object to cache.
        """
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                self._cache[key] = response
            else:
                if len(self._cache) >= self.max_size:
                    self._cache.popitem(last=False)
                self._cache[key] = response

    def clear(self) -> None:
        """Clear all entries in cache."""
        with self._lock:
            self._cache.clear()
            self.hits = 0
            self.misses = 0

    @property
    def hit_rate(self) -> float:
        """Compute current cache hit rate as a percentage."""
        with self._lock:
            total = self.hits + self.misses
            return round((self.hits / total * 100.0), 2) if total > 0 else 0.0


class ParseCache:
    """Thread-safe TTL cache for LLM query parses.

    Never caches fallback parses. Entries expire after `ttl_seconds`.
    """

    def __init__(self, max_size: int = 1000, ttl_seconds: float = 3600.0) -> None:
        """Initialize parse cache.

        Args:
            max_size: Maximum entries in cache.
            ttl_seconds: Time-to-live per cache entry in seconds.
        """
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._cache: OrderedDict[str, tuple[ParsedQuery, float]] = OrderedDict()
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, raw_query: str) -> ParsedQuery | None:
        """Retrieve valid cached parsed query if not expired.

        Args:
            raw_query: Raw search query text.

        Returns:
            ParsedQuery if valid and present, else None.
        """
        key = raw_query.strip().lower()
        now = time.time()
        with self._lock:
            if key in self._cache:
                parsed, timestamp = self._cache[key]
                if now - timestamp <= self.ttl_seconds:
                    self.hits += 1
                    self._cache.move_to_end(key)
                    return parsed
                # Expired
                del self._cache[key]
            self.misses += 1
            return None

    def put(self, raw_query: str, parsed: ParsedQuery, used_fallback: bool) -> None:
        """Cache successful LLM parse. Never cache fallback parses.

        Args:
            raw_query: Raw search query text.
            parsed: Resulting ParsedQuery.
            used_fallback: True if parsed via fallback rule-engine.
        """
        if used_fallback:
            return  # Rule B6: never cache fallback parses

        key = raw_query.strip().lower()
        now = time.time()
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                self._cache[key] = (parsed, now)
            else:
                if len(self._cache) >= self.max_size:
                    self._cache.popitem(last=False)
                self._cache[key] = (parsed, now)

    def clear(self) -> None:
        """Clear all entries in parse cache."""
        with self._lock:
            self._cache.clear()
            self.hits = 0
            self.misses = 0

    @property
    def hit_rate(self) -> float:
        """Compute current parse cache hit rate as a percentage."""
        with self._lock:
            total = self.hits + self.misses
            return round((self.hits / total * 100.0), 2) if total > 0 else 0.0
