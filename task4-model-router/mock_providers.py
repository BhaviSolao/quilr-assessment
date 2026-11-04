# fake model providers (modes: ok, 429, 500, slow)

import asyncio
import os

from fastapi import FastAPI
from fastapi.responses import JSONResponse, PlainTextResponse


def make_provider(name, mode="ok"):
    app = FastAPI()
    app.state.mode = mode
    app.state.calls = 0

    @app.post("/v1/chat/completions")
    async def completions():
        app.state.calls += 1
        if app.state.mode == "429":
            return JSONResponse({"error": "quota exceeded for org-secret-123"}, status_code=429)
        if app.state.mode == "500":
            return PlainTextResponse("Traceback: KeyError at /srv/model/app.py", status_code=500)
        if app.state.mode == "slow":
            await asyncio.sleep(5)
        return {
            "choices": [{"message": {"role": "assistant", "content": f"hello from {name}"}}],
            "usage": {"total_tokens": 42},
        }

    return app


app = make_provider(os.environ.get("MOCK_NAME", "mock"), os.environ.get("MOCK_MODE", "ok"))
