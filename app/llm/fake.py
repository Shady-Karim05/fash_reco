"""Fake LLM client for deterministic testing without external API calls."""

import json
import re
from typing import Any

from app.exceptions import LLMError


class FakeLLMClient:
    """Configurable Fake LLM Client for fast, zero-network unit and integration testing."""

    def __init__(
        self,
        responses: dict[str, str | dict[str, Any]] | None = None,
        default_response: str | dict[str, Any] | None = None,
        raise_timeout_times: int = 0,
        raise_error_times: int = 0,
        return_invalid_json: bool = False,
    ) -> None:
        """Initialize FakeLLMClient.

        Args:
            responses: Map of query substrings or exact queries to JSON strings or dicts.
            default_response: Fallback JSON string or dict when query not in responses.
            raise_timeout_times: Number of times to raise TimeoutError before succeeding.
            raise_error_times: Number of times to raise LLMError before succeeding.
            return_invalid_json: If True, returns malformed non-JSON text.
        """
        self.responses = responses or {}
        self.default_response = default_response
        self.raise_timeout_times = raise_timeout_times
        self.raise_error_times = raise_error_times
        self.return_invalid_json = return_invalid_json
        self.call_count = 0
        self.last_system: str | None = None
        self.last_user: str | None = None

    def complete_json(self, system: str, user: str, timeout: float = 3.0) -> str:
        """Simulate LLM JSON completion.

        Args:
            system: System instructions.
            user: User content / query.
            timeout: Timeout in seconds.

        Returns:
            JSON string response.

        Raises:
            TimeoutError: If raise_timeout_times > 0.
            LLMError: If raise_error_times > 0.
        """
        self.call_count += 1
        self.last_system = system
        self.last_user = user

        if self.raise_timeout_times > 0:
            self.raise_timeout_times -= 1
            raise TimeoutError(f"Simulated LLM timeout after {timeout}s")

        if self.raise_error_times > 0:
            self.raise_error_times -= 1
            raise LLMError("Simulated LLM service failure")

        if self.return_invalid_json:
            return "This is not valid JSON { missing_bracket: 123"

        # Check matched response
        user_lower = user.lower()
        for pattern, resp in self.responses.items():
            if pattern.lower() in user_lower:
                return resp if isinstance(resp, str) else json.dumps(resp)

        if self.default_response is not None:
            return (
                self.default_response
                if isinstance(self.default_response, str)
                else json.dumps(self.default_response)
            )

        # Dynamic heuristic fake response
        is_kids = bool(
            re.search(r"\b(?:kids?|boys?|girls?|child|baby|toddler|\d+\s*year)\b", user_lower)
        )
        gender: str | None = None
        if "men" in user_lower and "women" not in user_lower:
            gender = "men"
        elif "women" in user_lower:
            gender = "women"

        price_match = re.search(r"(?:under|below|less than|\$)\s*(\d+(?:\.\d+)?)", user_lower)
        max_price = float(price_match.group(1)) if price_match else None

        # Check non-USD currency
        has_rupee = "rupee" in user_lower or "inr" in user_lower or "₹" in user_lower
        has_euro = "euro" in user_lower or "€" in user_lower

        warnings: list[str] = []
        if has_rupee or has_euro:
            warnings.append("price_currency_not_supported")
            max_price = None

        return json.dumps(
            {
                "normalized_query_en": user,
                "language": "en",
                "gender": gender,
                "age_group": "kids" if is_kids else "adult",
                "min_price": None,
                "max_price": max_price,
                "colors": [],
                "slots": [],
                "season": None,
                "occasion": None,
                "warnings": warnings,
            }
        )
