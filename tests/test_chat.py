from types import SimpleNamespace
from unittest.mock import MagicMock

import anthropic
import httpx2
import pytest
from fastapi.testclient import TestClient

from app import main

FAKE_REQUEST = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


def rate_limit_error() -> anthropic.RateLimitError:
    return anthropic.RateLimitError(
        "rate limited", response=httpx2.Response(429, request=FAKE_REQUEST), body=None
    )


def connection_error() -> anthropic.APIConnectionError:
    return anthropic.APIConnectionError(request=FAKE_REQUEST)


@pytest.fixture
def fake_client(monkeypatch):
    """Replace the real Claude client with a fake that returns a fixed reply."""
    fake = MagicMock()
    fake.messages.create.return_value = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="Hello from a fake Claude")],
        model="claude-haiku-5-5",
        usage=SimpleNamespace(input_tokens=10, output_tokens=5),
    )
    monkeypatch.setattr(main, "client", fake)
    return fake


@pytest.fixture
def api():
    return TestClient(main.app)


def test_health(api):
    response = api.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_chat_returns_reply_and_usage(api, fake_client):
    response = api.post("/chat", json={"message": "hi"})
    assert response.status_code == 200
    assert response.json() == {
        "reply": "Hello from a fake Claude",
        "model": "claude-haiku-5-5",
        "input_tokens": 10,
        "output_tokens": 5,
    }


def test_chat_sends_message_to_claude(api, fake_client):
    api.post("/chat", json={"message": "What is RAG?", "max_tokens": 200})
    sent = fake_client.messages.create.call_args.kwargs
    assert sent["max_tokens"] == 200
    assert sent["messages"] == [{"role": "user", "content": "What is RAG?"}]


def test_empty_message_is_rejected(api, fake_client):
    response = api.post("/chat", json={"message": ""})
    assert response.status_code == 422
    fake_client.messages.create.assert_not_called()


@pytest.mark.parametrize(
    ("max_tokens", "expected_status"), [(1, 200), (4096, 200), (0, 422), (4097, 422)]
)
def test_max_tokens_boundaries(api, fake_client, max_tokens, expected_status):
    response = api.post("/chat", json={"message": "hi", "max_tokens": max_tokens})
    assert response.status_code == expected_status
    if expected_status == 200:
        fake_client.messages.create.assert_called_once()
    else:
        fake_client.messages.create.assert_not_called()


def test_only_text_blocks_are_returned(api, fake_client):
    fake_client.messages.create.return_value = SimpleNamespace(
        content=[
            SimpleNamespace(type="text", text="Hello"),
            SimpleNamespace(type="image", url="http://example.com/image.png"),
            SimpleNamespace(type="text", text="World"),
        ],
        model="claude-haiku-5-5",
        usage=SimpleNamespace(input_tokens=10, output_tokens=5),
    )
    response = api.post("/chat", json={"message": "hi"})
    assert response.status_code == 200
    assert response.json()["reply"] == "HelloWorld"


def test_chat_stream_sends_events(api, fake_client):
    fake_stream = fake_client.messages.stream.return_value.__enter__.return_value
    fake_stream.text_stream = ["Hel", "lo"]

    response = api.post("/chat/stream", json={"message": "hi"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    assert (
        response.text
        == 'data: {"text": "Hel"}\n\ndata: {"text": "lo"}\n\ndata: [DONE]\n\n'
    )


def test_chat_stream_rejects_empty_message(api, fake_client):
    response = api.post("/chat/stream", json={"message": ""})
    assert response.status_code == 422
    fake_client.messages.stream.assert_not_called()


def test_chat_rate_limited_returns_503(api, fake_client):
    fake_client.messages.create.side_effect = rate_limit_error()
    response = api.post("/chat", json={"message": "hi"})
    assert response.status_code == 503


def test_chat_connection_error_returns_502(api, fake_client):
    fake_client.messages.create.side_effect = connection_error()
    response = api.post("/chat", json={"message": "hi"})
    assert response.status_code == 502


def test_chat_stream_error_sends_error_event(api, fake_client):
    fake_client.messages.stream.side_effect = rate_limit_error()
    response = api.post("/chat/stream", json={"message": "hi"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert 'data: {"error": "Claude is busy. Try again shortly."}' in response.text
    assert "[DONE]" not in response.text
