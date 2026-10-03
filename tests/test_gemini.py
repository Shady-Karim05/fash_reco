"""Unit tests for Gemini LLM client with mocked SDK."""

from unittest.mock import MagicMock, patch

import pytest

from app.exceptions import ConfigurationError, LLMError
from app.llm.gemini import GeminiClient


class TestGeminiClient:
    """Tests for GeminiClient error handling, configuration, and completion."""

    def test_missing_api_key_raises_configuration_error(self) -> None:
        """Missing API key raises ConfigurationError on call."""
        client = GeminiClient(api_key="", model="gemini-2.5-flash")
        with pytest.raises(ConfigurationError, match="LLM_API_KEY and LLM_MODEL"):
            client.complete_json(system="sys", user="user")

    def test_missing_model_raises_configuration_error(self) -> None:
        """Missing model raises ConfigurationError on call."""
        client = GeminiClient(api_key="fake-key", model="")
        with pytest.raises(ConfigurationError, match="LLM_API_KEY and LLM_MODEL"):
            client.complete_json(system="sys", user="user")

    def test_successful_json_completion(self) -> None:
        """Successful API call returns clean response text."""
        client = GeminiClient(api_key="fake-key", model="gemini-2.5-flash")
        mock_genai_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = '{"is_fashion_query": true, "normalized_query_en": "beach dress"}'
        mock_genai_client.models.generate_content.return_value = mock_response

        client._client = mock_genai_client

        result = client.complete_json(system="sys", user="beach dress")
        assert '{"is_fashion_query": true' in result
        mock_genai_client.models.generate_content.assert_called_once()

    def test_empty_response_raises_llm_error(self) -> None:
        """Empty response text from API raises LLMError."""
        client = GeminiClient(api_key="fake-key", model="gemini-2.5-flash")
        mock_genai_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = ""
        mock_genai_client.models.generate_content.return_value = mock_response

        client._client = mock_genai_client

        with pytest.raises(LLMError, match="empty response"):
            client.complete_json(system="sys", user="user")

    def test_timeout_raises_timeout_error(self) -> None:
        """Timeout or deadline exceeded raises TimeoutError."""
        client = GeminiClient(api_key="fake-key", model="gemini-2.5-flash")
        mock_genai_client = MagicMock()
        mock_genai_client.models.generate_content.side_effect = Exception(
            "Deadline exceeded: 504 Gateway Timeout"
        )

        client._client = mock_genai_client

        with pytest.raises(TimeoutError, match="timed out"):
            client.complete_json(system="sys", user="user")

    def test_generic_exception_raises_llm_error(self) -> None:
        """Non-timeout API errors raise LLMError."""
        client = GeminiClient(api_key="fake-key", model="gemini-2.5-flash")
        mock_genai_client = MagicMock()
        mock_genai_client.models.generate_content.side_effect = Exception("Internal API Error 500")

        client._client = mock_genai_client

        with pytest.raises(LLMError, match="Gemini API error"):
            client.complete_json(system="sys", user="user")

    def test_lazy_initialization_failure_raises_configuration_error(self) -> None:
        """Failure to import or initialize google.genai raises ConfigurationError."""
        client = GeminiClient(api_key="fake-key", model="gemini-2.5-flash")
        with (
            patch("google.genai.Client", side_effect=Exception("SDK load failure")),
            pytest.raises(ConfigurationError, match="Failed to initialize"),
        ):
            client._get_client()
