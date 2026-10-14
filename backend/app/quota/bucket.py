"""Per-tenant token-bucket rate limiter. This is the ONE piece of code that
enforces the entire promise this project makes: no tenant can consume another
tenant's capacity. It runs BEFORE a request ever reaches a worker."""
from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class Bucket:
    capacity: float       # max tokens the bucket can hold (the burst)
    tokens: float          # tokens available right now
    rate_per_sec: float    # tokens added back per second
    last_refill: float     # monotonic time of the last refill


class TokenBucketQuota:
    """One bucket per tenant, held in memory for the life of the process. A
    request costs exactly one token. If the tenant has no tokens left, the
    request is rejected BEFORE it can touch a shared worker — that ordering
    is the whole isolation guarantee."""

    def __init__(self) -> None:
        self._buckets: dict[str, Bucket] = {}

    def register(self, tenant_id: str, rate_per_sec: float, burst: int,
                 now: float | None = None) -> None:
        now = now if now is not None else time.monotonic()
        self._buckets[tenant_id] = Bucket(
            capacity=float(burst), tokens=float(burst),
            rate_per_sec=rate_per_sec, last_refill=now,
        )

    def _refill(self, b: Bucket, now: float) -> None:
        elapsed = max(0.0, now - b.last_refill)
        b.tokens = min(b.capacity, b.tokens + elapsed * b.rate_per_sec)
        b.last_refill = now

    def allow(self, tenant_id: str, now: float | None = None) -> bool:
        """Refill for elapsed time, then take one token if available. Returns
        False (never raises) so a rejected request is a normal, telemetered
        outcome, not an exception path."""
        b = self._buckets.get(tenant_id)
        if b is None:
            return False
        now = now if now is not None else time.monotonic()
        self._refill(b, now)
        if b.tokens >= 1.0:
            b.tokens -= 1.0
            return True
        return False

    def tokens_available(self, tenant_id: str, now: float | None = None) -> float:
        b = self._buckets.get(tenant_id)
        if b is None:
            return 0.0
        now = now if now is not None else time.monotonic()
        self._refill(b, now)
        return round(b.tokens, 3)


if __name__ == "__main__":
    q = TokenBucketQuota()
    t = 0.0
    q.register("tenant-a", rate_per_sec=5.0, burst=10, now=t)
    # Burst of 10 allowed immediately, the 11th is rejected with no refill yet.
    allowed = [q.allow("tenant-a", now=t) for _ in range(11)]
    assert allowed[:10] == [True] * 10, allowed
    assert allowed[10] is False, allowed
    # After 1 second at 5/sec, 5 more tokens exist.
    t += 1.0
    allowed_after_refill = [q.allow("tenant-a", now=t) for _ in range(6)]
    assert allowed_after_refill[:5] == [True] * 5, allowed_after_refill
    assert allowed_after_refill[5] is False, allowed_after_refill
    # A second tenant's bucket is untouched by the first tenant's burst.
    q.register("tenant-b", rate_per_sec=5.0, burst=10, now=t)
    assert q.tokens_available("tenant-b", now=t) == 10.0
    print("ok: burst caps at capacity, refill is time-based, tenants are isolated")
