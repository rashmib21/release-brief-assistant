"""LLM access. Gemini for real use, a deterministic mock for tests and offline demos."""
import logging
import time
from typing import Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from ..config import get_settings

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)

# Problems that usually go away on their own: worth a quick retry before telling the person.
RETRYABLE = {"rate_limit", "timeout", "unavailable"}


class LLMError(Exception):
    """kind: rate_limit | timeout | unavailable | invalid_output | provider_error | not_configured"""

    def __init__(self, kind: str, message: str):
        self.kind = kind
        super().__init__(message)


class LLMClient(Protocol):
    model_name: str

    def generate(self, step: str, system: str, user: str, schema: type[T], context: dict) -> T: ...


class GeminiClient:
    def __init__(self, api_key: str, model: str, timeout_seconds: int, max_retries: int = 2):
        if not api_key:
            raise LLMError("not_configured", "GEMINI_API_KEY is not set on the server.")
        from google import genai  # imported lazily so mock mode needs no network libs

        self._genai = genai
        self._client = genai.Client(api_key=api_key)
        self.model_name = model
        self._timeout_ms = timeout_seconds * 1000
        self._max_retries = max_retries

    def _config(self, system: str, schema: type[T]):
        from google.genai import types

        kwargs = dict(
            system_instruction=system,
            response_mime_type="application/json",
            response_schema=schema,
            temperature=0.2,
            max_output_tokens=8192,
            http_options=types.HttpOptions(timeout=self._timeout_ms),
        )
        # Gemini 2.5 Flash "thinks" before answering, which is slow and can eat the output budget. This task does not need it.
        if "2.5" in self.model_name and "flash" in self.model_name:
            kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
        return types.GenerateContentConfig(**kwargs)

    def _call_once(self, system: str, user: str, schema: type[T]) -> T:
        from google.genai import errors

        try:
            response = self._client.models.generate_content(model=self.model_name, contents=user, config=self._config(system, schema))
        except errors.APIError as exc:
            code = getattr(exc, "code", None)
            if code == 429:
                raise LLMError("rate_limit", "The AI provider rate limit was hit. Wait a minute and retry.") from exc
            if code in (408, 504):
                raise LLMError("timeout", "The AI provider timed out. Retry.") from exc
            if code in (500, 502, 503):
                raise LLMError("unavailable", "The AI provider is overloaded right now. Retry in a moment.") from exc
            if code in (401, 403):
                raise LLMError("not_configured", "The AI provider rejected the API key. Check GEMINI_API_KEY on the server.") from exc
            if code == 404:
                raise LLMError("not_configured", f"The AI model '{self.model_name}' was not found. Check GEMINI_MODEL on the server.") from exc
            raise LLMError("provider_error", f"AI provider error ({code}).") from exc
        except Exception as exc:  # network errors, client timeouts
            if "timeout" in str(exc).lower() or "timed out" in str(exc).lower():
                raise LLMError("timeout", "The AI provider timed out. Retry.") from exc
            raise LLMError("provider_error", "Could not reach the AI provider.") from exc

        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, schema):
            return parsed
        text = (response.text or "").strip()
        if not text:
            raise LLMError("invalid_output", "The AI returned an empty answer (it may have been blocked or cut off).")
        # Some models wrap JSON in a Markdown fence even when asked not to.
        if text.startswith("```"):
            text = text.strip("`")
            text = text[4:] if text.lower().startswith("json") else text
        try:
            return schema.model_validate_json(text.strip())
        except ValidationError as exc:
            raise LLMError("invalid_output", f"AI returned JSON in the wrong shape: {exc.error_count()} errors") from exc

    def generate(self, step: str, system: str, user: str, schema: type[T], context: dict) -> T:
        delay = 2.0
        for attempt in range(self._max_retries + 1):
            try:
                return self._call_once(system, user, schema)
            except LLMError as exc:
                if exc.kind not in RETRYABLE or attempt == self._max_retries:
                    raise
                logger.warning("llm temporary error (%s) on step %s, retrying in %.0fs", exc.kind, step, delay)
                time.sleep(delay)
                delay *= 2
        raise LLMError("provider_error", "Unreachable")  # pragma: no cover


def get_llm_client() -> LLMClient:
    settings = get_settings()
    if settings.llm_provider == "mock":
        from .mock import MockLLM

        return MockLLM()
    return GeminiClient(settings.gemini_api_key, settings.gemini_model, settings.llm_timeout_seconds, settings.llm_max_retries)
