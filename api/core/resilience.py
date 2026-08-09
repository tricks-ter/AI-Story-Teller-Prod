import time
import random
import threading
import logging

logger = logging.getLogger(__name__)

RETRYABLE_STATUSES = {429, 500, 502, 503, 504}

class UpstreamRateLimited(Exception):
    def __init__(self, retry_after=5.0, detail=""):
        super().__init__(detail or "Upstream rate limited")
        self.retry_after = retry_after

class CircuitBreaker:
    """Per-process lightweight breaker: after `threshold` consecutive 429s,
    fail fast for `cooldown` seconds so the upstream can recover."""
    def __init__(self, threshold=5, cooldown=30.0):
        self._lock = threading.Lock()
        self.threshold = threshold
        self.cooldown = cooldown
        self.fail_count = 0
        self.open_until = 0.0

    def record_429(self):
        with self._lock:
            self.fail_count += 1
            if self.fail_count >= self.threshold:
                self.open_until = time.monotonic() + self.cooldown
                self.fail_count = 0
                logger.warning("[resilience] circuit OPEN for %ss after repeated 429s", self.cooldown)

    def record_success(self):
        with self._lock:
            self.fail_count = 0

    def remaining_block(self):
        with self._lock:
            return max(0.0, self.open_until - time.monotonic())

BREAKER = CircuitBreaker()

def extract_status(exc):
    """Defensively probe unknown SDK exception shapes for an HTTP status."""
    for attr in ("status_code", "code", "http_status", "status"):
        v = getattr(exc, attr, None)
        if isinstance(v, int): return v
        if isinstance(v, str) and v.strip().isdigit(): return int(v.strip())
    resp = getattr(exc, "response", None)
    if resp is not None:
        v = getattr(resp, "status_code", None)
        if isinstance(v, int): return v
    text = str(exc).lower()
    if "429" in text or "rate limit" in text or "too many requests" in text or "quota" in text: return 429
    if "timed out" in text or "timeout" in text: return 504
    if "502" in text: return 502
    if "503" in text: return 503
    if "500" in text or "internal server error" in text: return 500
    return None

def extract_retry_after(exc):
    resp = getattr(exc, "response", None)
    headers = getattr(resp, "headers", None) if resp is not None else None
    if headers:
        try:
            ra = headers.get("Retry-After") or headers.get("retry-after")
            if ra: return max(0.5, min(float(ra), 30.0))
        except Exception:
            pass
    return None

def backoff_delay(attempt, retry_after=None, base=0.8, cap=8.0):
    """Exponential backoff with full jitter; honors Retry-After when present."""
    if retry_after:
        return retry_after + random.uniform(0.0, 0.5)
    exp = min(cap, base * (2 ** attempt))
    return exp * (0.5 + random.random())

def call_with_retry(fn, max_attempts=3, label="zai"):
    """Run fn(); retry retryable upstream errors with jittered backoff.
    Raises the last exception (or UpstreamRateLimited) when exhausted."""
    last = None
    for attempt in range(max_attempts):
        blocked = BREAKER.remaining_block()
        if blocked > 0:
            raise UpstreamRateLimited(retry_after=min(blocked, 10.0), detail="circuit open")
        try:
            result = fn()
            BREAKER.record_success()
            return result
        except Exception as e:
            last = e
            status = extract_status(e)
            if status == 429:
                BREAKER.record_429()
            if status not in RETRYABLE_STATUSES or attempt == max_attempts - 1:
                raise
            ra = extract_retry_after(e) if status == 429 else None
            delay = backoff_delay(attempt, ra)
            logger.warning("[%s] upstream %s; retry %d/%d in %.2fs", label, status or "error", attempt + 1, max_attempts - 1, delay)
            time.sleep(delay)
    raise last

def friendly_upstream(status, raw):
    if status == 429:
        return "The AI engine is receiving too many requests (429). We cooled down and retried automatically — please try again in a moment."
    if status in (500, 502, 503):
        return "The AI engine had a temporary server error. We retried automatically — please try again."
    if status == 504:
        return "The AI engine timed out. We retried automatically — please try again."
    return raw
