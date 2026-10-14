"""Per-tenant health. A single slow or failed request breaching a tenant's own
baseline is not 'unhealthy' — a sustained breach across the window is. This
debounce is what stops the gateway from opening an incident over one slow
request and then flapping between healthy and unhealthy on noise."""
from __future__ import annotations

from dataclasses import dataclass

from app.repositories.tenants import TenantRepo
from app.repositories.telemetry import TelemetryRepo

tenant_repo = TenantRepo()
tele_repo = TelemetryRepo()

# A signal must breach in at least this fraction of the window to count as a
# sustained breach. 0.6 = "most of the recent window", not one unlucky sample.
SUSTAINED_FRACTION = 0.6
# How many recent samples define "now" for one tenant.
WINDOW = 30
# A tenant breaches latency when its p99 exceeds its OWN baseline by this
# multiplier — comparing to a learned baseline, not a fixed global number.
LATENCY_MULTIPLIER = 2.0
# A tenant breaches error rate when it exceeds its own baseline by this many
# ADDITIONAL percentage points.
ERROR_MARGIN_PCT = 5.0


@dataclass
class Health:
    tenant_id: str
    verdict: str            # 'healthy' | 'degraded' | 'unhealthy'
    breached_signals: list[str]
    p99_ms: float
    samples_seen: int
    worst_worker: str | None


def _fraction_breaching(values: list[float], threshold: float) -> float:
    if not values:
        return 0.0
    breaching = sum(1 for v in values if v > threshold)
    return breaching / len(values)


def _p99(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = max(0, int(round(0.99 * (len(ordered) - 1))))
    return ordered[idx]


def evaluate(tenant_id: str) -> Health:
    tenant = tenant_repo.get(tenant_id)
    if tenant is None:
        raise KeyError(tenant_id)
    window = tele_repo.recent(tenant_id, limit=WINDOW)
    if not window:
        # No telemetry is itself a problem, but not a latency/error breach.
        return Health(tenant_id, "degraded", ["no_telemetry"], 0.0, 0, None)

    served = [s for s in window if not s["quota_reject"]]
    lat = [s["latency_ms"] for s in served]
    err_pct = (100.0 * sum(1 for s in served if s["errored"]) / len(served)
               if served else 0.0)

    breached: list[str] = []
    lat_threshold = tenant["baseline_p99_ms"] * LATENCY_MULTIPLIER
    if lat and _fraction_breaching(lat, lat_threshold) >= SUSTAINED_FRACTION:
        breached.append("p99_ms")
    err_threshold = tenant["baseline_err_pct"] + ERROR_MARGIN_PCT
    if err_pct > err_threshold:
        breached.append("err_pct")

    if not breached:
        verdict = "healthy"
    elif len(breached) == 1:
        verdict = "degraded"
    else:
        verdict = "unhealthy"

    # The worker most represented among this tenant's WORST samples — the
    # first clue for the blast-radius calculation two steps from now.
    worst_worker = None
    if lat:
        p99_val = _p99(lat)
        worst = [s for s in served if s["latency_ms"] >= p99_val and s["worker_id"]]
        if worst:
            worst_worker = worst[0]["worker_id"]

    return Health(tenant_id, verdict, breached, round(_p99(lat), 1),
                  len(window), worst_worker)
