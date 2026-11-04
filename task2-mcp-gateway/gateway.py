# MCP gateway - blocks admin_ tools for non-admin users

import logging
import os

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("mcp-gateway")

DOWNSTREAM_URL = os.environ.get("DOWNSTREAM_URL", "http://127.0.0.1:9001/mcp")

# demo tokens, would be JWTs in a real setup
TOKENS = {
    "admin-token-123": "admin",
    "viewer-token-456": "viewer",
}

app = FastAPI()


def make_client():
    return httpx.AsyncClient(timeout=30)


def jsonrpc_error(request_id, code, message, status=200):
    body = {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}
    return JSONResponse(body, status_code=status)


def get_role(auth_header):
    if not auth_header or not auth_header.startswith("Bearer "):
        return None
    token = auth_header[len("Bearer "):].strip()
    return TOKENS.get(token)


@app.post("/mcp")
async def mcp_proxy(request: Request):
    role = get_role(request.headers.get("authorization"))
    if role is None:
        return jsonrpc_error(None, -32000, "Unauthorized: missing or invalid token", status=401)

    try:
        message = await request.json()
    except ValueError:
        return jsonrpc_error(None, -32700, "Parse error")

    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        # also blocks batches so admin calls can't hide in a list
        return jsonrpc_error(None, -32600, "Invalid Request")

    request_id = message.get("id")
    method = message.get("method")

    if method == "tools/call":
        params = message.get("params") or {}
        tool_name = params.get("name") if isinstance(params, dict) else None

        if not isinstance(tool_name, str):
            return jsonrpc_error(request_id, -32602, "Invalid params: tool name is required")

        # lower() so Admin_reset_key is caught too
        is_admin_tool = tool_name.strip().lower().startswith("admin_")
        if is_admin_tool and role != "admin":
            log.warning("BLOCKED %s for role=%s", tool_name, role)
            return jsonrpc_error(request_id, -32001, "Unauthorized Tool Call")

    # forward it (without the client's token)
    try:
        async with make_client() as client:
            response = await client.post(DOWNSTREAM_URL, json=message)
    except httpx.HTTPError:
        log.error("downstream server is unreachable")
        return jsonrpc_error(request_id, -32603, "Downstream MCP server unavailable", status=502)

    return JSONResponse(response.json(), status_code=response.status_code)
