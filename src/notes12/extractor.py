"""Gemini structured extraction (V0).

Narrow scope: raw text -> Gemini -> structured Notes12 JSON -> Notes12Document.
Bounded retries for transient errors only. No Discord, frontend, database, or image input.
"""

import os
import time
from collections.abc import Callable
from typing import Any

from pydantic import ValidationError

from notes12.schema import Notes12Document

DEFAULT_MODEL = "gemini-3.6-flash"

EXTRACTION_INSTRUCTIONS = """Transform the supplied text into a Notes12 knowledge map.

Return ONLY a single JSON object with exactly these fields:
- title: string
- summary: string
- map_type: one of hierarchy, timeline, cause_effect, comparison, graph (rendering hint)
- nodes: array of {id, label, type, description}
- relationships: array of {source, target, type, directed}

Rules:
- relationships are the source of truth; map_type is only a rendering hint
- node type is AI-chosen free-form; relationship type is AI-chosen free-form
- node ids are unique slugs; relationship source/target must reference node ids
- node descriptions are short (1-2 sentences)
- no extra fields, no markdown, no explanation
"""


class GeminiExtractionError(Exception):
    """Clean error for extraction failures (config, API, or validation)."""


def build_extraction_prompt(text: str) -> str:
    """Combine fixed instructions with the raw text. Pure function (no I/O)."""
    return f"{EXTRACTION_INSTRUCTIONS}\nText:\n{text.strip()}"


def _strip_unsupported_schema_keywords(schema: Any) -> Any:
    """Recursively drop schema keywords the Gemini Developer API rejects.

    Our models emit `additionalProperties: false` via `extra="forbid"`, but the
    Developer API's response_schema does not accept that keyword (it fails with
    INVALID_ARGUMENT). Application-side validation still forbids extra fields.
    """
    if isinstance(schema, dict):
        return {
            key: _strip_unsupported_schema_keywords(value)
            for key, value in schema.items()
            if key not in ("additionalProperties", "additional_properties")
        }
    if isinstance(schema, list):
        return [_strip_unsupported_schema_keywords(item) for item in schema]
    return schema


def response_schema() -> dict[str, Any]:
    """JSON Schema derived from the locked model, sanitized for the Gemini API."""
    return _strip_unsupported_schema_keywords(Notes12Document.model_json_schema())


def _resolve_api_key(explicit_key: str | None) -> str:
    key = (explicit_key or os.getenv("GEMINI_API_KEY") or "").strip()
    if not key:
        raise GeminiExtractionError(
            "GEMINI_API_KEY is not set. Export it or pass api_key explicitly."
        )
    return key


def _create_client(api_key: str) -> Any:
    from google import genai

    return genai.Client(api_key=api_key)


# HTTP statuses worth one more attempt. Mirrors the SDK's APIError.code surface:
# 429 arrives as ClientError and 5xx as ServerError, so match on code, not class.
_TRANSIENT_HTTP_CODES = frozenset({429, 500, 502, 503, 504})


def _is_transient_error(exc: Exception) -> bool:
    """True only for retryable server/rate-limit failures (never auth/config)."""
    code = getattr(exc, "code", getattr(exc, "status_code", None))
    return isinstance(code, int) and not isinstance(code, bool) and code in _TRANSIENT_HTTP_CODES


def extract_notes(
    text: str,
    *,
    api_key: str | None = None,
    model: str = DEFAULT_MODEL,
    client: Any | None = None,
    max_retries: int = 2,
    retry_base_delay: float = 1.0,
    sleep: Callable[[float], None] | None = None,
) -> Notes12Document:
    """Extract a validated Notes12Document from raw text via Gemini.

    Retries transient failures (HTTP 429/500/502/503/504) up to `max_retries`
    times with exponential backoff (`retry_base_delay * 2**n` seconds).
    `sleep` is injectable so tests stay deterministic (defaults to time.sleep).
    """
    if not isinstance(text, str) or not text.strip():
        raise GeminiExtractionError("input text must be a non-empty string")

    resolved_key = _resolve_api_key(api_key)
    active_client = client if client is not None else _create_client(resolved_key)
    prompt = build_extraction_prompt(text)
    config = {
        "response_mime_type": "application/json",
        "response_schema": response_schema(),
    }
    sleep_fn = sleep if sleep is not None else time.sleep

    attempts = 0
    while True:
        attempts += 1
        try:
            response = active_client.models.generate_content(
                model=model, contents=prompt, config=config
            )
            break
        except GeminiExtractionError:
            raise
        except Exception as exc:
            if attempts > max_retries or not _is_transient_error(exc):
                if attempts == 1:
                    raise GeminiExtractionError(f"Gemini request failed: {exc}") from exc
                raise GeminiExtractionError(
                    f"Gemini request failed after {attempts} attempts: {exc}"
                ) from exc
            sleep_fn(retry_base_delay * (2 ** (attempts - 1)))

    raw = getattr(response, "text", None)
    if not isinstance(raw, str) or not raw.strip():
        raise GeminiExtractionError("Gemini returned an empty response")

    try:
        return Notes12Document.model_validate_json(raw)
    except ValidationError as exc:
        raise GeminiExtractionError(f"Gemini output failed validation: {exc}") from exc
