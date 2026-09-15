import json

import pytest

from notes12.extractor import (
    DEFAULT_MODEL,
    GeminiExtractionError,
    build_extraction_prompt,
    extract_notes,
    response_schema,
)
from notes12.schema import Notes12Document


def make_valid_payload():
    return {
        "title": "Photosynthesis",
        "summary": "How plants convert light into energy.",
        "map_type": "hierarchy",
        "nodes": [
            {
                "id": "photosynthesis",
                "label": "Photosynthesis",
                "type": "process",
                "description": "Converts light energy into chemical energy.",
            },
            {
                "id": "chlorophyll",
                "label": "Chlorophyll",
                "type": "pigment",
                "description": "Absorbs light for photosynthesis.",
            },
        ],
        "relationships": [
            {
                "source": "chlorophyll",
                "target": "photosynthesis",
                "type": "enables",
                "directed": True,
            }
        ],
    }


class FakeResponse:
    def __init__(self, text):
        self.text = text


class FakeModels:
    def __init__(self, response=None, error=None):
        self._response = response
        self._error = error
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return self._response


class FakeClient:
    def __init__(self, response=None, error=None):
        self.models = FakeModels(response=response, error=error)


def test_success_mocked_response_becomes_valid_document():
    client = FakeClient(FakeResponse(json.dumps(make_valid_payload())))
    doc = extract_notes("plants use chlorophyll", api_key="test-key", client=client)
    assert doc.title == "Photosynthesis"
    assert doc.map_type == "hierarchy"
    assert [n.id for n in doc.nodes] == ["photosynthesis", "chlorophyll"]
    assert doc.relationships[0].directed is True


def test_default_model_is_current_flash():
    assert DEFAULT_MODEL == "gemini-3.6-flash"


def test_adapter_requests_structured_json_output():
    client = FakeClient(FakeResponse(json.dumps(make_valid_payload())))
    extract_notes("raw input text", api_key="test-key", client=client)
    assert len(client.models.calls) == 1
    call = client.models.calls[0]
    assert call["model"] == "gemini-3.6-flash"
    assert "raw input text" in call["contents"]
    config = call["config"]
    assert config["response_mime_type"] == "application/json"
    schema = config["response_schema"]
    assert set(schema["properties"]) == {"title", "summary", "map_type", "nodes", "relationships"}
    assert _find_keys(schema, {"additionalProperties", "additional_properties"}) == []


def test_explicit_model_override_still_works():
    client = FakeClient(FakeResponse(json.dumps(make_valid_payload())))
    extract_notes("raw input text", api_key="test-key", model="custom-model-xyz", client=client)
    assert client.models.calls[0]["model"] == "custom-model-xyz"


def _find_keys(node, names):
    found = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key in names:
                found.append(key)
            found.extend(_find_keys(value, names))
    elif isinstance(node, list):
        for item in node:
            found.extend(_find_keys(item, names))
    return found


def test_response_schema_drops_keywords_gemini_rejects():
    # Regression test: the Developer API rejects additionalProperties with
    # INVALID_ARGUMENT, so the sent schema must not contain it anywhere,
    # while preserving the full locked contract shape.
    schema = response_schema()
    assert _find_keys(schema, {"additionalProperties", "additional_properties"}) == []
    assert set(schema["properties"]) == {"title", "summary", "map_type", "nodes", "relationships"}
    assert set(schema["required"]) == {"title", "summary", "map_type", "nodes", "relationships"}
    assert schema["properties"]["map_type"]["enum"] == [
        "hierarchy",
        "timeline",
        "cause_effect",
        "comparison",
        "graph",
    ]
    # Everything except the dropped keywords matches the locked Pydantic schema.
    raw = Notes12Document.model_json_schema()
    assert _find_keys(raw, {"additionalProperties"}) != []


@pytest.mark.parametrize(
    "bad_text",
    [
        "{not valid json",
        json.dumps({"title": "incomplete"}),
        json.dumps({**make_valid_payload(), "map_type": "mindmap"}),
    ],
)
def test_malformed_output_rejected(bad_text):
    client = FakeClient(FakeResponse(bad_text))
    with pytest.raises(GeminiExtractionError):
        extract_notes("some text", api_key="test-key", client=client)


def test_invalid_reference_output_rejected():
    payload = make_valid_payload()
    payload["relationships"] = [
        {"source": "ghost", "target": "photosynthesis", "type": "x", "directed": True}
    ]
    client = FakeClient(FakeResponse(json.dumps(payload)))
    with pytest.raises(GeminiExtractionError):
        extract_notes("some text", api_key="test-key", client=client)


def test_api_errors_surfaced_cleanly():
    client = FakeClient(error=RuntimeError("boom"))
    with pytest.raises(GeminiExtractionError, match="boom"):
        extract_notes("some text", api_key="test-key", client=client)


@pytest.mark.parametrize("bad_input", ["", "   ", None, 123])
def test_empty_or_invalid_input_rejected(bad_input):
    client = FakeClient(FakeResponse(json.dumps(make_valid_payload())))
    with pytest.raises(GeminiExtractionError):
        extract_notes(bad_input, api_key="test-key", client=client)
    assert client.models.calls == []


def test_missing_api_key_produces_clear_error(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    client = FakeClient(FakeResponse(json.dumps(make_valid_payload())))
    with pytest.raises(GeminiExtractionError, match="GEMINI_API_KEY"):
        extract_notes("some text", client=client)
    assert client.models.calls == []


def test_prompt_contains_text_and_contract_terms():
    prompt = build_extraction_prompt("hello world")
    assert "hello world" in prompt
    for term in ("title", "summary", "nodes", "relationships", "map_type"):
        assert term in prompt
