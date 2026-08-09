import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core.resilience import backoff_delay, extract_status, CircuitBreaker, UpstreamRateLimited, call_with_retry

def test_backoff_bounds():
    for attempt in range(5):
        d = backoff_delay(attempt)
        assert 0 <= d <= 8.5

def test_backoff_honors_retry_after():
    d = backoff_delay(0, retry_after=5)
    assert 5 <= d <= 5.5

def test_extract_status_attr():
    class E(Exception): status_code = 429
    assert extract_status(E("x")) == 429

def test_extract_status_text():
    assert extract_status(Exception("Error code: 429 too many requests")) == 429
    assert extract_status(Exception("connection timed out")) == 504

def test_breaker_opens():
    b = CircuitBreaker(threshold=2, cooldown=30)
    b.record_429(); b.record_429()
    assert b.remaining_block() > 0

def test_breaker_success_resets():
    b = CircuitBreaker(threshold=2, cooldown=30)
    b.record_429(); b.record_success(); b.record_429()
    assert b.remaining_block() == 0

def test_call_with_retry_succeeds_after_fail():
    calls = {"n": 0}
    def fn():
        calls["n"] += 1
        if calls["n"] == 1:
            e = Exception("429 rate limited")
            raise e
        return "ok"
    assert call_with_retry(fn, max_attempts=3, label="t") == "ok"

def test_call_with_retry_non_retryable_raises():
    def fn(): raise ValueError("bad")
    try:
        call_with_retry(fn, max_attempts=3, label="t")
        assert False
    except ValueError:
        pass
