import json
import threading
import time

import httpx
import pytest
import uvicorn

import gateway
import mock_provider


def start_server(app, port):
    server = uvicorn.Server(uvicorn.Config(app, port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.01)
    return server


@pytest.fixture(scope="module")
def gateway_url():
    gateway.PROVIDER_URL = "http://127.0.0.1:9902/v1/chat/completions"
    servers = [start_server(mock_provider.app, 9902), start_server(gateway.app, 9903)]
    yield "http://127.0.0.1:9903/v1/chat/completions"
    for s in servers:
        s.should_exit = True


def read_stream(url):
    text, times = "", []
    start = time.time()
    with httpx.stream("POST", url, json={"stream": True, "messages": []}, timeout=10) as r:
        for line in r.iter_lines():
            if line.startswith("data:") and "[DONE]" not in line:
                chunk = json.loads(line[5:])
                piece = chunk["choices"][0]["delta"].get("content")
                if piece:
                    text += piece
                    times.append(time.time() - start)
    return text, times


def test_stream_is_redacted(gateway_url):
    mock_provider.app.state.delay = 0
    text, _ = read_stream(gateway_url)
    assert "john.do" not in text and "6789" not in text and "4111" not in text
    assert text.count("[REDACTED]") == 3
    assert "Order #20240611 shipped." in text


def test_first_words_arrive_before_stream_ends(gateway_url):
    mock_provider.app.state.delay = 0.3
    _, times = read_stream(gateway_url)
    mock_provider.app.state.delay = 0
    assert times[0] < 0.6
    assert times[-1] > 1.0


def test_non_streaming_is_redacted(gateway_url):
    r = httpx.post(gateway_url, json={"messages": []}, timeout=10)
    assert "[REDACTED]" in r.json()["choices"][0]["message"]["content"]
