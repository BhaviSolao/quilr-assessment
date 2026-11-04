# LLM router with token rate limiting and fallback to a backup model

import asyncio
import logging
import os

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from rate_limiter import RateLimiter

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("router")

PRIMARY_URL = os.environ.get("PRIMARY_URL", "http://127.0.0.1:9101/v1/chat/completions")
BACKUP_URL = os.environ.get("BACKUP_URL", "http://127.0.0.1:9102/v1/chat/completions")
PRIMARY_TIMEOUT = 3.0   # seconds
BACKUP_TIMEOUT = 10.0

limiter = RateLimiter(os.environ.get("RATE_LIMIT_DB", "ratelimit.db"), limit=50_000)
app = FastAPI()


def make_client():
    return httpx.AsyncClient()


def error(status, error_type, message):
    return JSONResponse({"error": {"type": error_type, "message": message}}, status_code=status)


def estimate_tokens(body):
    # rough guess: ~4 chars per token + max answer length
    text = "".join(str(m.get("content", "")) for m in body.get("messages", []))
    return len(text) // 4 + body.get("max_tokens", 500)


async def call_model(url, body, timeout):
    try:
        async with make_client() as client:
            # timeout covers the whole call, late answers get cancelled
            response = await asyncio.wait_for(client.post(url, json=body), timeout=timeout)
    except asyncio.TimeoutError:
        log.warning("%s timed out after %ss", url, timeout)
        return None
    except httpx.HTTPError:
        log.warning("%s could not be reached", url)
        return None

    if response.status_code != 200:
        log.warning("%s returned HTTP %s", url, response.status_code)  # 429, 500, ...
        return None

    try:
        return response.json()
    except ValueError:
        return None


@app.post("/v1/chat/completions")
async def chat(request: Request):
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer ") or not auth[7:].strip():
        return error(401, "authentication_error", "Missing API key")
    api_key = auth[7:].strip()

    try:
        body = await request.json()
    except ValueError:
        return error(400, "invalid_request", "Body must be JSON")
    if not isinstance(body, dict) or not isinstance(body.get("messages"), list):
        return error(400, "invalid_request", "'messages' must be a list")

    tokens = estimate_tokens(body)
    row_id = limiter.try_reserve(api_key, tokens)
    if row_id is None:
        return error(429, "rate_limit_exceeded", "Token limit of 50,000 per minute reached. Try again soon.")

    answer = await call_model(PRIMARY_URL, body, PRIMARY_TIMEOUT)
    route = "primary"
    if answer is None:
        answer = await call_model(BACKUP_URL, body, BACKUP_TIMEOUT)
        route = "backup"

    if answer is None:
        limiter.cancel(row_id)  # don't charge for failed requests
        return error(503, "upstream_unavailable", "All models are unavailable. Please try again later.")

    real_tokens = answer.get("usage", {}).get("total_tokens")
    if isinstance(real_tokens, int):
        limiter.set_actual_tokens(row_id, real_tokens)

    return JSONResponse(answer, headers={"x-served-by": route})
