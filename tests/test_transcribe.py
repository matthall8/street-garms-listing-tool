"""What transcribe.py sends, and what it reports back, captured offline.

The HTTP client the Anthropic provider builds is swapped for one with a fake
transport, so a real agent sends a real request body that never leaves the
process. The key is a dummy: nothing here needs a real one.
"""

import json
from io import BytesIO

import httpx
import pytest
from PIL import Image
from pydantic_ai.exceptions import ModelHTTPError, UnexpectedModelBehavior

from labels import transcribe
from labels.transcribe import (
    ART_MODEL,
    ART_PROMPT,
    ART_USER_MESSAGE,
    CLIENT_RETRIES,
    NOT_SENT,
    OUTPUT_RETRIES,
    SETTINGS_RECORD,
)

VALID = {"art_number_raw": None, "art_legible": "not_visible", "ambiguous_characters": []}
INVALID = {"art_number_raw": None, "art_legible": "not a legibility"}
REPORTED = "reported-model-name"


def message(body: dict, tool_input: dict) -> httpx.Response:
    """A Messages API response calling the output tool with `tool_input`."""
    return httpx.Response(200, json={
        "id": "msg_test", "type": "message", "role": "assistant", "model": REPORTED,
        "content": [{"type": "tool_use", "id": "toolu_test",
                     "name": body["tools"][0]["name"], "input": tool_input}],
        "stop_reason": "tool_use", "stop_sequence": None,
        "usage": {"input_tokens": 10, "output_tokens": 5},
    })


def server_error() -> httpx.Response:
    # retry-after-ms keeps the SDK's backoff to a millisecond.
    return httpx.Response(500, headers={"retry-after-ms": "1"},
                          json={"type": "error", "error": {"type": "api_error",
                                                           "message": "test"}})


@pytest.fixture
def api(monkeypatch):
    """The requests a real agent sends. Set `api.replies` to a list of
    callables taking the body; the last one repeats."""
    import pydantic_ai.providers.anthropic as provider_module

    class Api:
        def __init__(self):
            self.requests: list[httpx.Request] = []
            self.replies = [lambda body: message(body, VALID)]

        @property
        def bodies(self) -> list[dict]:
            return [json.loads(r.content) for r in self.requests]

    fake = Api()

    def handler(request: httpx.Request) -> httpx.Response:
        fake.requests.append(request)
        reply = fake.replies[min(len(fake.requests), len(fake.replies)) - 1]
        return reply(json.loads(request.content))

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    monkeypatch.setattr(provider_module, "create_async_http_client",
                        lambda *a, **k: httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    transcribe.get_art_agent.cache_clear()
    yield fake
    transcribe.get_art_agent.cache_clear()


def png() -> bytes:
    out = BytesIO()
    Image.new("RGB", (8, 8), (255, 255, 255)).save(out, format="PNG")
    return out.getvalue()


def read(**kwargs) -> transcribe.ArtRead:
    return transcribe.read_art(png(), "image/png", **kwargs)


class TestRequestBody:
    """Setting the model settings explicitly changed nothing sent: the body
    is what the agent sent when every setting was left to the libraries,
    apart from the timeout, which was already set."""

    def test_the_body_has_these_fields_and_no_others(self, api):
        read()
        [body] = api.bodies
        # No thinking and no output_config: the model's defaults apply.
        assert sorted(body) == ["max_tokens", "messages", "model", "stream", "system",
                                "tool_choice", "tools"]

    def test_the_settings_are_the_values_sent_before(self, api):
        read()
        [body] = api.bodies
        assert {k: body[k] for k in ("model", "max_tokens", "stream", "tool_choice")} == {
            "model": ART_MODEL.removeprefix("anthropic:"), "max_tokens": 4096,
            "stream": False, "tool_choice": {"type": "any"}}

    def test_the_prompt_user_message_and_photo_are_sent(self, api):
        read()
        [body] = api.bodies
        assert body["system"] == ART_PROMPT
        [turn] = body["messages"]
        text, image = turn["content"]
        assert (turn["role"], text["text"]) == ("user", ART_USER_MESSAGE)
        assert (image["type"], image["source"]["media_type"]) == ("image", "image/png")

    def test_the_timeout_is_sent_as_the_clients(self, api):
        read()
        [request] = api.requests
        assert request.headers["x-stainless-timeout"] == "60"

    def test_the_record_matches_what_is_sent(self, api):
        """The header's `model_settings` can't claim a setting the body lacks."""
        read()
        [request] = api.requests
        body = json.loads(request.content)
        assert SETTINGS_RECORD["max_tokens"] == body["max_tokens"]
        assert SETTINGS_RECORD["thinking"] == NOT_SENT and "thinking" not in body
        assert SETTINGS_RECORD["effort"] == NOT_SENT and "output_config" not in body
        assert str(SETTINGS_RECORD["timeout"]) == request.headers["x-stainless-timeout"]


class TestRetries:
    """The values set are the ones used. Today's equal the libraries'
    defaults, so each is also run at a value no default has: a setting
    that stopped reaching the client or the agent fails here."""

    @pytest.mark.parametrize("retries", [CLIENT_RETRIES, 0, 3])
    def test_a_server_error_is_retried_by_the_client(self, api, monkeypatch, retries):
        monkeypatch.setattr(transcribe, "CLIENT_RETRIES", retries)
        api.replies = [lambda body: server_error()]
        with pytest.raises(ModelHTTPError):
            read()
        assert len(api.requests) == retries + 1

    @pytest.mark.parametrize("retries", [OUTPUT_RETRIES, 0, 2])
    def test_invalid_output_is_retried_by_the_agent(self, api, monkeypatch, retries):
        monkeypatch.setattr(transcribe, "OUTPUT_RETRIES", retries)
        api.replies = [lambda body: message(body, INVALID)]
        with pytest.raises(UnexpectedModelBehavior):
            read()
        assert len(api.requests) == retries + 1


class TestReadArt:
    def test_it_reports_the_model_name_from_the_response(self, api):
        assert read().model_name == REPORTED

    def test_it_reports_the_runs_usage(self, api):
        usage = read().usage
        assert (usage.requests, usage.input_tokens, usage.output_tokens) == (1, 10, 5)

    def test_an_output_retry_counts_as_a_request(self, api):
        api.replies = [lambda body: message(body, INVALID), lambda body: message(body, VALID)]
        assert read().usage.requests == 2

    def test_an_http_retry_does_not(self, api):
        """It happens inside one request, so `requests` can't show it."""
        api.replies = [lambda body: server_error(), lambda body: message(body, VALID)]
        assert read().usage.requests == 1
        assert len(api.requests) == 2

    def test_transcribe_art_returns_the_reading_alone(self, api):
        assert transcribe.transcribe_art(png(), "image/png") == read().reading


class TestTestModel:
    """`--model test` builds no Anthropic client, so it needs no key."""

    def test_it_runs_with_no_key(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        transcribe.get_art_agent.cache_clear()
        try:
            result = read(model="test")
        finally:
            transcribe.get_art_agent.cache_clear()
        assert result.model_name == "test" and result.usage.requests == 1

    def test_only_anthropic_models_are_built(self):
        assert transcribe.build_model("test") == "test"
