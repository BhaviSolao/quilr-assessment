# LLM gateway that redacts PII from streamed responses

import json
import logging
import os

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from redactor import StreamRedactor, redact

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("llm-gateway")

PROVIDER_URL = os.environ.get("PROVIDER_URL", "http://127.0.0.1:9002/v1/chat/completions")

app = FastAPI()


def sse_event(data):
    return f"data: {data}\n\n"


def content_event(text):
    chunk = {"object": "chat.completion.chunk", "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}]}
    return sse_event(json.dumps(chunk))


async def redacted_stream(body):
    redactor = StreamRedactor()

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            async with client.stream("POST", PROVIDER_URL, json=body) as response:
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[len("data:"):].strip()

                    # end of stream, send what's left
                    if data == "[DONE]":
                        leftover = redactor.flush()
                        if leftover:
                            yield content_event(leftover)
                        yield sse_event("[DONE]")
                        return

                    chunk = json.loads(data)
                    choice = chunk["choices"][0]
                    text = choice.get("delta", {}).get("content")

                    if text:
                        safe_text = redactor.feed(text)
                        if safe_text:
                            yield content_event(safe_text)

                    # flush before the finish chunk
                    if choice.get("finish_reason"):
                        leftover = redactor.flush()
                        if leftover:
                            yield content_event(leftover)
                        yield sse_event(json.dumps(chunk | {"choices": [{**choice, "delta": {}}]}))

    except httpx.HTTPError:
        log.error("provider stream failed")
        yield sse_event(json.dumps({"error": {"message": "The model provider is unavailable"}}))


@app.post("/v1/chat/completions")
async def chat(request: Request):
    body = await request.json()

    if body.get("stream"):
        return StreamingResponse(redacted_stream(body), media_type="text/event-stream")

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(PROVIDER_URL, json=body)
    except httpx.HTTPError:
        return JSONResponse({"error": {"message": "The model provider is unavailable"}}, status_code=502)

    data = response.json()
    for choice in data.get("choices", []):
        choice["message"]["content"] = redact(choice["message"]["content"])
    return data
