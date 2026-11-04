import json
import subprocess
import sys
from pathlib import Path

import pytest

SERVER = Path(__file__).parent.parent / "server.py"


@pytest.fixture
def server():
    proc = subprocess.Popen(
        [sys.executable, str(SERVER)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    send(proc, {"jsonrpc": "2.0", "id": 0, "method": "initialize",
                "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                           "clientInfo": {"name": "test", "version": "1"}}})
    read(proc)
    send(proc, {"jsonrpc": "2.0", "method": "notifications/initialized"})
    yield proc
    proc.kill()


def send(proc, message):
    proc.stdin.write(json.dumps(message) + "\n")
    proc.stdin.flush()


def read(proc):
    line = proc.stdout.readline()
    return json.loads(line)


def call(proc, tool, arguments):
    send(proc, {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                "params": {"name": tool, "arguments": arguments}})
    return read(proc)


def test_lists_two_tools(server):
    send(server, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    names = [t["name"] for t in read(server)["result"]["tools"]]
    assert names == ["get_customer_record", "trigger_refund"]


def test_get_customer_ok(server):
    reply = call(server, "get_customer_record", {"customer_id": "CUST-12345"})
    assert "Rahul Mehta" in reply["result"]["content"][0]["text"]


def test_refund_ok(server):
    reply = call(server, "trigger_refund", {"customer_id": "CUST-00001", "amount": 20.5, "reason": "item was damaged"})
    assert "refund queued" in reply["result"]["content"][0]["text"]


def test_customer_not_found_is_tool_error(server):
    reply = call(server, "get_customer_record", {"customer_id": "CUST-99999"})
    assert reply["result"]["isError"] is True


@pytest.mark.parametrize("bad_id", ["CUST-123", "cust-12345", "CUST-1234A", "", 12345, None])
def test_bad_customer_id(server, bad_id):
    reply = call(server, "get_customer_record", {"customer_id": bad_id})
    assert reply["error"]["code"] == -32602


@pytest.mark.parametrize("field, value", [
    ("amount", 0), ("amount", -5), ("amount", "10"),
    ("reason", "too short"), ("reason", 12345678901),
])
def test_bad_refund_input(server, field, value):
    args = {"customer_id": "CUST-00001", "amount": 10.0, "reason": "late delivery!!"}
    args[field] = value
    reply = call(server, "trigger_refund", args)
    assert reply["error"]["code"] == -32602


def test_missing_and_extra_fields(server):
    assert call(server, "trigger_refund", {"customer_id": "CUST-00001"})["error"]["code"] == -32602
    assert call(server, "get_customer_record", {"customer_id": "CUST-12345", "x": 1})["error"]["code"] == -32602


def test_unknown_tool(server):
    assert call(server, "delete_everything", {})["error"]["code"] == -32602


def test_logs_go_to_stderr_not_stdout(server):
    call(server, "trigger_refund", {"customer_id": "CUST-00001", "amount": 5.0, "reason": "wrong size sent"})
    server.stdin.close()
    stderr = server.stderr.read()
    assert "refund of 5.00" in stderr
    assert "print(" not in SERVER.read_text()
