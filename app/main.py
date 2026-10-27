import json
import logging

import anthropic
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse

from app.models import ChatRequest, ChatResponse

MODEL = "claude-haiku-5-5"
SYSTEM_PROMPT = "You are a concise, helpful assistant."

app = FastAPI(title="Chat Service")
client = anthropic.Anthropic()
logger = logging.getLogger(__name__)


def claude_args(request: ChatRequest) -> dict:
    """The arguments every Claude call in this service uses."""
    return {
        "model": MODEL,
        "max_tokens": request.max_tokens,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": request.message}],
    }


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/chat")
def chat(request: ChatRequest) -> ChatResponse:
    try:
        response = client.messages.create(**claude_args(request))
    except anthropic.APIError as e:
        raise to_http_error(e) from e
    reply = "".join(block.text for block in response.content if block.type == "text")
    return ChatResponse(
        reply=reply,
        model=response.model,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
    )


def stream_reply(request: ChatRequest):
    try:
        with client.messages.stream(**claude_args(request)) as stream:
            for text in stream.text_stream:
                payload = json.dumps({"text": text})
                yield f"data: {payload}\n\n"
    except anthropic.APIError as e:
        detail = to_http_error(e).detail
        error_detail = json.dumps({"error": detail})
        yield f"data: {error_detail}\n\n"
        return

    yield "data: [DONE]\n\n"


def to_http_error(error: anthropic.APIError) -> HTTPException:
    """Map a Claude SDK error to the HTTP error this service returns."""
    if isinstance(error, anthropic.RateLimitError):
        return HTTPException(
            status_code=503, detail="Claude is busy. Try again shortly."
        )
    if isinstance(error, anthropic.APIConnectionError):
        return HTTPException(status_code=502, detail="API connection timeout.")
    if isinstance(error, anthropic.AuthenticationError):
        logger.error("Claude rejected the API key. Check ANTHROPIC_API_KEY.")
        return HTTPException(status_code=500, detail="Server error")
    return HTTPException(status_code=502, detail="Claude returned an unexpected error")


@app.post("/chat/stream")
def chat_stream(request: ChatRequest) -> StreamingResponse:
    return StreamingResponse(stream_reply(request), media_type="text/event-stream")
