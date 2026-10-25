import anthropic
from fastapi import FastAPI

from app.models import ChatRequest, ChatResponse

MODEL = "claude-haiku-5-5"
SYSTEM_PROMPT = "You are a concise, helpful assistant."

app = FastAPI(title="Chat Service")
client = anthropic.Anthropic()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/chat")
def chat(request: ChatRequest) -> ChatResponse:
    response = client.messages.create(
        model=MODEL,
        max_tokens=request.max_tokens,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": request.message}],
    )
    reply = "".join(block.text for block in response.content if block.type == "text")
    return ChatResponse(
        reply=reply,
        model=response.model,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
    )
