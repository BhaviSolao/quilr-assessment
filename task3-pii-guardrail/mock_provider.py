# fake LLM that streams a reply with PII split across chunks

import asyncio
import json
import os

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

CHUNKS = [
    "you can email john at john.do",
    "e@example.com, his SSN is 123-",
    "45-6789 and his card is 4111 1111 ",
    "1111 1111. Order #20240611 shipped.",
]

app = FastAPI()
app.state.chunks = CHUNKS
app.state.delay = float(os.environ.get("MOCK_DELAY", "0"))


def event(content=None, finish=None):
    delta = {"content": content} if content is not None else {}
    chunk = {"object": "chat.completion.chunk", "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
    return f"data: {json.dumps(chunk)}\n\n"


@app.post("/v1/chat/completions")
async def completions(request: Request):
    body = await request.json()
    chunks = app.state.chunks

    if not body.get("stream"):
        return {"choices": [{"index": 0, "message": {"role": "assistant", "content": "".join(chunks)}}]}

    async def generate():
        for text in chunks:
            await asyncio.sleep(app.state.delay)
            yield event(content=text)
        yield event(finish="stop")
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
