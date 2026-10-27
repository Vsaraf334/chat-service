import json

import anthropic
from fastapi import FastAPI
from fastapi.responses import StreamingResponse

from app.models import ChatRequest, ChatResponse

MODEL = "claude-haiku-5-5"
SYSTEM_PROMPT = "You are a concise, helpful assistant."

app = FastAPI(title="Chat Service")
client = anthropic.Anthropic()


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
    response = client.messages.create(**claude_args(request))
    reply = "".join(block.text for block in response.content if block.type == "text")
    return ChatResponse(
        reply=reply,
        model=response.model,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
    )


def stream_reply(request: ChatRequest):
    with client.messages.stream(**claude_args(request)) as stream:
        for text in stream.text_stream:
            payload = json.dumps({"text": text})
            yield f"data: {payload}\n\n"

    yield "data: [DONE]\n\n"


@app.post("/chat/stream")
def chat_stream(request: ChatRequest) -> StreamingResponse:
    return StreamingResponse(stream_reply(request), media_type="text/event-stream")
