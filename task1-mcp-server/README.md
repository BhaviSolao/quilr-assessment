# Task 1 - MCP Server

MCP server with two tools, `get_customer_record` and `trigger_refund`. Runs over stdio.

```
pip install -r requirements.txt
python server.py
python -m pytest -q tests
```

Notes:
- Inputs are checked with Pydantic in strict mode, extra fields are rejected
- Bad input returns JSON-RPC error -32602 with the list of wrong fields
- Used the low level `Server` from the SDK so I could return a real -32602 (the decorator version returns errors as normal text results)
- Unknown customer id returns a normal result with `isError: true` since the input itself is valid
- All logging goes to stderr, nothing is printed to stdout
