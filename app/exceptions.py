"""Domain exceptions for the Fashion Search microservice."""


class FashionSearchError(Exception):
    """Base exception for all fashion search errors."""

    def __init__(self, message: str, status_code: int = 500) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class CatalogError(FashionSearchError):
    """Catalog database access or integrity error."""

    def __init__(self, message: str, status_code: int = 500) -> None:
        super().__init__(message, status_code)


class ProductNotFoundError(CatalogError):
    """Product not found in catalog."""

    def __init__(self, product_id: str) -> None:
        super().__init__(f"Product with id '{product_id}' not found.", status_code=404)


class IndexingError(FashionSearchError):
    """Index building, loading, or sync error."""

    def __init__(self, message: str, status_code: int = 500) -> None:
        super().__init__(message, status_code)


class ParserError(FashionSearchError):
    """Query parsing failure."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message, status_code)


class ConfigurationError(FashionSearchError):
    """Missing or invalid system configuration."""

    def __init__(self, message: str, status_code: int = 500) -> None:
        super().__init__(message, status_code)


class LLMError(FashionSearchError):
    """LLM generation or communication error."""

    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message, status_code)
