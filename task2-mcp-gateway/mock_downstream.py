# fake MCP server for testing

from fastapi import FastAPI, Request

app = FastAPI()
received = []

TOOLS = [
    {"name": "get_weather", "inputSchema": {"type": "object"}},
    {"name": "admin_reset_key", "inputSchema": {"type": "object"}},
]


@app.post("/mcp")
async def mcp(request: Request):
    message = await request.json()
    received.append(message)

    if message["method"] == "tools/list":
        result = {"tools": TOOLS}
    elif message["method"] == "tools/call":
        result = {"content": [{"type": "text", "text": "ran " + message["params"]["name"]}]}
    else:
        result = {}

    return {"jsonrpc": "2.0", "id": message.get("id"), "result": result}
