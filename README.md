# Chat Service

A small FastAPI service that puts Claude behind a clean HTTP API: single questions, streamed answers, and multi-turn conversations with memory. Inputs are validated with Pydantic, Claude API failures are mapped to meaningful HTTP status codes, and the whole API is covered by tests that run in under a second without calling the real API.

Built with Python 3.12, FastAPI, Pydantic, and the Anthropic Python SDK (model: Claude Haiku 5.5).

## Endpoints

| Method | Path | What it does |
| --- | --- | --- |
| `GET` | `/health` | Liveness check. Returns `{"status": "ok"}`. |
| `POST` | `/chat` | Ask one question, get the full answer plus token usage. |
| `POST` | `/chat/stream` | Ask one question, receive the answer as it is generated (server-sent events). |
| `POST` | `/conversations` | Start a conversation. Returns `201` and a `conversation_id`. |
| `POST` | `/conversations/{conversation_id}/messages` | Send a message in a conversation. Claude sees the full history. |
| `GET` | `/conversations/{conversation_id}` | Read a conversation's full history. |

Interactive docs are generated automatically at `/docs` while the server is running.

### Request body (`/chat`, `/chat/stream`, `/conversations/{id}/messages`)

```json
{"message": "What is RAG?", "max_tokens": 500}
```

| Field | Rules |
| --- | --- |
| `message` | Required, 1 to 4000 characters |
| `max_tokens` | Optional, 1 to 4096, default 1024 |

Invalid input is rejected with `422` before Claude is called, so a bad request never costs an API call.

### Response (`/chat`, `/conversations/{id}/messages`)

```json
{
  "reply": "RAG retrieves relevant documents first, then answers using them.",
  "model": "claude-haiku-5-5",
  "input_tokens": 35,
  "output_tokens": 18
}
```

### Streaming format (`/chat/stream`)

Each piece of text arrives as a server-sent event, followed by a final `[DONE]`:

```
data: {"text": "RAG retrieves"}

data: {"text": " relevant documents first..."}

data: [DONE]

```

## Error handling

| Situation | Status | Notes |
| --- | --- | --- |
| Invalid request body | `422` | Pydantic's field-level error messages |
| Unknown `conversation_id` | `404` | |
| Claude rate limit | `503` | Temporary; the client should retry |
| Claude unreachable | `502` | |
| Invalid API key | `500` | The caller sees a generic message; the real cause is logged server-side |
| Other Claude API errors | `502` | |

The Anthropic SDK already retries transient failures twice before the service sees an error.

On `/chat/stream`, the `200` status has already been sent when generation starts, so a failure is reported as a final `data: {"error": "..."}` event instead, with no `[DONE]` after it.

If Claude fails during a conversation, the user's message is removed again, so the stored history never contains an unanswered message.

## Running locally

Requirements: Python 3.12+, [uv](https://docs.astral.sh/uv/), and an Anthropic API key.

```bash
git clone https://github.com/Vsaraf334/chat-service.git
cd chat-service
uv sync
echo "ANTHROPIC_API_KEY=your-key-here" > .env
uv run --env-file .env fastapi dev app/main.py
```

Then open http://127.0.0.1:8000/docs, or try it from the command line:

```bash
# one question
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What is FastAPI in one sentence?"}'

# a streamed answer (-N prints events as they arrive)
curl -N -X POST http://127.0.0.1:8000/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "Explain Python generators in 3 sentences"}'
```

`.env` is git-ignored. Never commit an API key.

### With Docker

```bash
docker build -t chat-service .
docker run --env-file .env -p 8000:8000 chat-service
```

The image installs only production dependencies, runs as a non-root user, and never contains the API key: `.dockerignore` keeps `.env` out of the build, and the key is passed in at run time with `--env-file`.

## Tests and checks

```bash
uv run pytest          # 17 tests
uv run ruff check .    # lint
uv run ruff format .   # format
uv run pyright app     # type check
```

The tests replace the Claude client with a mock (`unittest.mock.MagicMock` via `monkeypatch`), so they need no API key or network, run in under a second, and cost nothing. They cover:

- the response shape and the exact arguments sent to Claude;
- validation boundaries (`max_tokens` of 0, 1, 4096 and 4097; empty messages), including that Claude is never called for invalid input;
- only `text` content blocks being returned to the caller;
- the exact server-sent event format, and error events on a failed stream;
- error mapping (`503` for rate limits, `502` for connection errors);
- conversations keeping both sides in order, `404` for unknown IDs, and a failed message not being kept in the history.

## Design decisions

- **The server chooses the model.** Callers can't pick a model, which keeps cost under the service's control. `message` length and `max_tokens` are capped for the same reason.
- **One place builds Claude requests.** `claude_args()` is shared by every endpoint, so the model, system prompt, and limits can't drift apart between endpoints.
- **Conversations are stored in memory.** It's simple and fast, but conversations are lost on restart and can't be shared between several server processes. A production version would store them in a database such as Postgres or Redis.
- **The full history is sent on every turn.** The Claude API is stateless, so input tokens grow with each turn of a conversation. Long conversations would need summarisation or prompt caching to control cost.

## Next steps

- Persistent conversation storage
- Tracing and cost tracking per request
