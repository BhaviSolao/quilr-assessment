# Task 2 - MCP Gateway

Proxy that sits between the agent and the MCP server and checks the role from the Bearer token.

```
pip install -r requirements.txt
python -m pytest -q tests
```

To try it manually:

```
uvicorn mock_downstream:app --port 9001
uvicorn gateway:app --port 8080
curl -s localhost:8080/mcp -H "Authorization: Bearer viewer-token-456" -H "content-type: application/json" -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"admin_reset_key"}}'
```

Test tokens: `admin-token-123` and `viewer-token-456`

Notes:
- `tools/list` and other methods are forwarded as they are
- `tools/call` for any `admin_` tool is blocked with -32001 unless the role is admin, and it never reaches the MCP server
- Tool name is lowercased before checking so `Admin_reset_key` doesn't get through
- Batch requests are rejected so an admin call can't be hidden in a list
- Client token is not forwarded to the MCP server
- Tokens are hardcoded for the demo, would use JWTs in a real setup
