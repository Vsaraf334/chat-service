from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app import main


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
