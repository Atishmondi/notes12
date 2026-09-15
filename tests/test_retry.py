"""Deterministic retry tests: scripted fake clients, recorded sleeps, no network."""

import json

import pytest
from google.genai import errors as genai_errors

from notes12.extractor import GeminiExtractionError, extract_notes


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
            }
        ],
        "relationships": [],
    }


class FakeResponse:
    def __init__(self, text):
        self.text = text


class ScriptedModels:
    def __init__(self, script):
        self._script = list(script)
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self._script.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class ScriptedClient:
    def __init__(self, script):
        self.models = ScriptedModels(script)


def server_error(code):
    return genai_errors.ServerError(
        code, {"error": {"code": code, "message": "temporary outage", "status": "X"}}
    )


def client_error(code):
    return genai_errors.ClientError(
        code, {"error": {"code": code, "message": "client problem", "status": "Y"}}
    )


class SleepRecorder:
    def __init__(self):
        self.delays = []

    def __call__(self, seconds):
        self.delays.append(seconds)


def extract(**kwargs):
    kwargs.setdefault("api_key", "test-key")
    return extract_notes("some text", **kwargs)


def assert_wire_clean(call):
    config = call["config"]
    assert config["response_mime_type"] == "application/json"
    assert set(config["response_schema"]["properties"]) == {
        "title",
        "summary",
        "map_type",
        "nodes",
        "relationships",
    }


def test_transient_503_retried_then_succeeds():
    sleep = SleepRecorder()
    client = ScriptedClient([server_error(503), FakeResponse(json.dumps(make_valid_payload()))])
    doc = extract(client=client, max_retries=2, retry_base_delay=0.5, sleep=sleep)
    assert doc.title == "Photosynthesis"
    assert len(client.models.calls) == 2
    assert sleep.delays == [0.5]
    assert_wire_clean(client.models.calls[0])


def test_transient_429_retried_despite_client_error_class():
    sleep = SleepRecorder()
    client = ScriptedClient([client_error(429), FakeResponse(json.dumps(make_valid_payload()))])
    extract(client=client, max_retries=2, retry_base_delay=0.5, sleep=sleep)
    assert len(client.models.calls) == 2
    assert sleep.delays == [0.5]


def test_retries_exhausted_raises_with_attempt_count():
    sleep = SleepRecorder()
    client = ScriptedClient([server_error(503)] * 3)
    with pytest.raises(GeminiExtractionError, match="3 attempts"):
        extract(client=client, max_retries=2, retry_base_delay=0.5, sleep=sleep)
    assert len(client.models.calls) == 3
    assert sleep.delays == [0.5, 1.0]


@pytest.mark.parametrize("code", [400, 401, 403, 404])
def test_non_transient_client_errors_not_retried(code):
    sleep = SleepRecorder()
    client = ScriptedClient([client_error(code)])
    with pytest.raises(GeminiExtractionError):
        extract(client=client, max_retries=2, retry_base_delay=0.5, sleep=sleep)
    assert len(client.models.calls) == 1
    assert sleep.delays == []


def test_generic_error_not_retried():
    sleep = SleepRecorder()
    client = ScriptedClient([ValueError("boom")])
    with pytest.raises(GeminiExtractionError, match="boom"):
        extract(client=client, max_retries=2, retry_base_delay=0.5, sleep=sleep)
    assert len(client.models.calls) == 1
    assert sleep.delays == []


def test_success_makes_exactly_one_attempt():
    sleep = SleepRecorder()
    client = ScriptedClient([FakeResponse(json.dumps(make_valid_payload()))])
    extract(client=client, sleep=sleep)
    assert len(client.models.calls) == 1
    assert sleep.delays == []


def test_model_override_still_works_with_retry():
    sleep = SleepRecorder()
    client = ScriptedClient([server_error(502), FakeResponse(json.dumps(make_valid_payload()))])
    extract(client=client, model="custom-model-xyz", sleep=sleep)
    assert len(client.models.calls) == 2
    assert client.models.calls[0]["model"] == "custom-model-xyz"
    assert_wire_clean(client.models.calls[0])
