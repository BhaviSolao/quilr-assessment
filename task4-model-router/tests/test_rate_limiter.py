import threading
import time

from rate_limiter import RateLimiter


def test_blocks_after_limit(tmp_path):
    limiter = RateLimiter(str(tmp_path / "rl.db"), limit=50_000)
    assert limiter.try_reserve("key", 30_000) is not None
    assert limiter.try_reserve("key", 20_000) is not None
    assert limiter.try_reserve("key", 1) is None


def test_tenants_are_separate(tmp_path):
    limiter = RateLimiter(str(tmp_path / "rl.db"), limit=100)
    assert limiter.try_reserve("a", 100) is not None
    assert limiter.try_reserve("b", 100) is not None


def test_old_usage_expires(tmp_path, monkeypatch):
    limiter = RateLimiter(str(tmp_path / "rl.db"), limit=100)
    limiter.try_reserve("key", 100)
    future = time.time() + 61
    monkeypatch.setattr(time, "time", lambda: future)
    assert limiter.try_reserve("key", 100) is not None


def test_real_tokens_and_cancel(tmp_path):
    limiter = RateLimiter(str(tmp_path / "rl.db"), limit=1000)
    row = limiter.try_reserve("key", 500)
    limiter.set_actual_tokens(row, 40)
    assert limiter.used("key") == 40
    limiter.cancel(row)
    assert limiter.used("key") == 0


def test_saved_on_disk(tmp_path):
    path = str(tmp_path / "rl.db")
    RateLimiter(path, limit=100).try_reserve("key", 90)
    assert RateLimiter(path, limit=100).try_reserve("key", 20) is None


def test_parallel_requests_never_go_over_limit(tmp_path):
    # 50 threads x 2000 tokens, only 25 should fit
    limiter = RateLimiter(str(tmp_path / "rl.db"), limit=50_000)
    results = []
    start = threading.Barrier(50)

    def worker():
        start.wait()
        results.append(limiter.try_reserve("key", 2_000) is not None)

    threads = [threading.Thread(target=worker) for _ in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert results.count(True) == 25
    assert limiter.used("key") == 50_000
