"""Protocol definition for LLM clients."""

from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMClient(Protocol):
    """Protocol for LLM clients that complete prompts and return JSON strings."""

    def complete_json(self, system: str, user: str, timeout: float = 3.0) -> str:
        """Send prompt to LLM and return raw text output (expected to be JSON).

        Args:
            system: System instructions.
            user: User content / query payload.
            timeout: Maximum allowed completion time in seconds.

        Returns:
            Raw response text from the LLM.

        Raises:
            TimeoutError: If the request exceeds timeout.
            LLMError: If communication or generation fails.
            ConfigurationError: If API credentials or model are missing.
        """
        ...
