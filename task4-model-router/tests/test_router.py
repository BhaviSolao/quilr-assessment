import time

import httpx
import pytest
from fastapi.testclient import TestClient

import router
from mock_providers import make_provider
from rate_limiter import RateLimiter

BODY = {"messages": [{"role": "user", "content": "hi"}], "max_tokens": 100}
AUTH = {"Authorization": "Bearer tenant-1"}


@pytest.fixture
def setup(tmp_path, monkeypatch):
    def build(primary_mode="ok", backup_mode="ok", limit=50_000):
        primary = make_provider("primary", primary_mode)
        backup = make_provider("backup", backup_mode)
        mounts = {
            "http://primary": httpx.ASGITransport(app=primary),
            "http://backup": httpx.ASGITransport(app=backup),
        }
        monkeypatch.setattr(router, "make_client", lambda: httpx.AsyncClient(mounts=mounts))
        monkeypatch.setattr(router, "PRIMARY_URL", "http://primary/v1/chat/completions")
        monkeypatch.setattr(router, "BACKUP_URL", "http://backup/v1/chat/completions")
        monkeypatch.setattr(router, "limiter", RateLimiter(str(tmp_path / "rl.db"), limit=limit))
        return TestClient(router.app), primary, backup

    return build


def check_safe_error(response, status, error_type):
    assert response.status_code == status
    assert response.json()["error"]["type"] == error_type
    for secret in ["Traceback", "app.py", "org-secret", "http://"]:
        assert secret not in response.text


def test_primary_works(setup):
    client, primary, backup = setup()
    r = client.post("/v1/chat/completions", json=BODY, headers=AUTH)
    assert r.json()["choices"][0]["message"]["content"] == "hello from primary"
    assert backup.state.calls == 0


def test_fallback_on_429(setup):
    client, _, _ = setup(primary_mode="429")
    r = client.post("/v1/chat/completions", json=BODY, headers=AUTH)
    assert r.headers["x-served-by"] == "backup"


def test_fallback_on_500(setup):
    client, _, _ = setup(primary_mode="500")
    r = client.post("/v1/chat/completions", json=BODY, headers=AUTH)
    assert r.headers["x-served-by"] == "backup"


def test_fallback_after_3_seconds(setup):
    client, _, _ = setup(primary_mode="slow")
    start = time.time()
    r = client.post("/v1/chat/completions", json=BODY, headers=AUTH)
    elapsed = time.time() - start
    assert r.headers["x-served-by"] == "backup"
    assert 3.0 <= elapsed < 3.5


def test_both_down_gives_safe_error_and_refund(setup):
    client, _, _ = setup(primary_mode="500", backup_mode="429")
    r = client.post("/v1/chat/completions", json=BODY, headers=AUTH)
    check_safe_error(r, 503, "upstream_unavailable")
    assert router.limiter.used("tenant-1") == 0


def test_rate_limit(setup):
    client, _, _ = setup(limit=700)
    big = {**BODY, "max_tokens": 600}
    assert client.post("/v1/chat/completions", json=big, headers=AUTH).status_code == 200
    # mock only uses 42 tokens so the 2nd one still fits
    assert client.post("/v1/chat/completions", json=big, headers=AUTH).status_code == 200
    r = client.post("/v1/chat/completions", json={**BODY, "max_tokens": 650}, headers=AUTH)
    check_safe_error(r, 429, "rate_limit_exceeded")


def test_missing_api_key(setup):
    client, _, _ = setup()
    check_safe_error(client.post("/v1/chat/completions", json=BODY), 401, "authentication_error")


def test_bad_body(setup):
    client, _, _ = setup()
    r = client.post("/v1/chat/completions", json={"messages": "hi"}, headers=AUTH)
    check_safe_error(r, 400, "invalid_request")
