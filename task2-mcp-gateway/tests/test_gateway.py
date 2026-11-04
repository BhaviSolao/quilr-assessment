import httpx
import pytest
from fastapi.testclient import TestClient

import gateway
import mock_downstream

ADMIN = {"Authorization": "Bearer admin-token-123"}
VIEWER = {"Authorization": "Bearer viewer-token-456"}


@pytest.fixture
def client(monkeypatch):
    # use the mock server instead of a real one
    mock_downstream.received.clear()
    monkeypatch.setattr(
        gateway, "make_client",
        lambda: httpx.AsyncClient(transport=httpx.ASGITransport(app=mock_downstream.app)),
    )
    return TestClient(gateway.app)


def tool_call(name, request_id=1):
    return {"jsonrpc": "2.0", "id": request_id, "method": "tools/call", "params": {"name": name}}


def test_tools_list_is_forwarded(client):
    r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, headers=VIEWER)
    assert len(r.json()["result"]["tools"]) == 2
    assert len(mock_downstream.received) == 1


def test_viewer_can_call_normal_tool(client):
    r = client.post("/mcp", json=tool_call("get_weather"), headers=VIEWER)
    assert r.json()["result"]["content"][0]["text"] == "ran get_weather"


def test_admin_can_call_admin_tool(client):
    r = client.post("/mcp", json=tool_call("admin_reset_key"), headers=ADMIN)
    assert r.json()["result"]["content"][0]["text"] == "ran admin_reset_key"


def test_viewer_blocked_from_admin_tool(client):
    r = client.post("/mcp", json=tool_call("admin_reset_key", request_id=7), headers=VIEWER)
    assert r.json() == {"jsonrpc": "2.0", "id": 7, "error": {"code": -32001, "message": "Unauthorized Tool Call"}}
    assert mock_downstream.received == []


@pytest.mark.parametrize("name", ["Admin_reset_key", "ADMIN_RESET_KEY", " admin_reset_key"])
def test_case_tricks_blocked(client, name):
    r = client.post("/mcp", json=tool_call(name), headers=VIEWER)
    assert r.json()["error"]["code"] == -32001


def test_batch_rejected(client):
    r = client.post("/mcp", json=[tool_call("admin_reset_key")], headers=VIEWER)
    assert r.json()["error"]["code"] == -32600
    assert mock_downstream.received == []


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer wrong"}, {"Authorization": "Basic abc"}])
def test_bad_token_rejected(client, headers):
    r = client.post("/mcp", json=tool_call("get_weather"), headers=headers)
    assert r.status_code == 401
    assert mock_downstream.received == []


def test_bad_json(client):
    r = client.post("/mcp", content=b"{not json", headers={**VIEWER, "content-type": "application/json"})
    assert r.json()["error"]["code"] == -32700


def test_downstream_down(monkeypatch):
    monkeypatch.setattr(gateway, "DOWNSTREAM_URL", "http://127.0.0.1:1/mcp")
    r = TestClient(gateway.app).post("/mcp", json=tool_call("get_weather"), headers=VIEWER)
    assert r.status_code == 502
    assert r.json()["error"]["message"] == "Downstream MCP server unavailable"
