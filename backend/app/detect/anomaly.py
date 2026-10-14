"""Anomaly detector. Ties health + burn together and, the moment a tenant's
burn crosses the page threshold, computes the BLAST RADIUS — which worker is
implicated, and which OTHER tenants share that worker and are therefore at
risk — and opens an incident naming all three before a human looks at
anything. Detecting on burn (trajectory) rather than a single health snapshot
means we only open an incident for a regression that's actually underway."""
from __future__ import annotations

from dataclasses import dataclass

from app.health import burn as burn_mod
from app.health import evaluate as health_mod
from app.repositories.incidents import IncidentRepo
from app.repositories.telemetry import TelemetryRepo

tele_repo = TelemetryRepo()
incident_repo = IncidentRepo()

# How many of a worker's OTHER recent tenants count as "sharing" it for the
# blast radius — recent enough to plausibly be affected right now.
BLAST_RADIUS_WINDOW = 20


@dataclass
class Detection:
    tenant_id: str
    opened: bool
    incident_id: int | None
    error_type: str
    blast_workers: list[str]
    blast_tenants: list[str]


def _blast_radius(worker_id: str | None, exclude_tenant: str) -> list[str]:
    """Every OTHER tenant with a recent sample on the implicated worker — the
    set of tenants who could be dragged down by the same faulty worker."""
    if not worker_id:
        return []
    samples = tele_repo.recent_for_worker(worker_id, limit=BLAST_RADIUS_WINDOW)
    others = {s["tenant_id"] for s in samples if s["tenant_id"] != exclude_tenant}
    return sorted(others)


def detect(tenant_id: str) -> Detection:
    health = health_mod.evaluate(tenant_id)
    b = burn_mod.evaluate(tenant_id)

    if not b.page:
        return Detection(tenant_id, False, None, "none", [], [])

    blast_workers = [health.worst_worker] if health.worst_worker else []
    blast_tenants = _blast_radius(health.worst_worker, exclude_tenant=tenant_id)

    incident_id = incident_repo.open(
        tenant_id=tenant_id,
        error_type=b.error_type,
        blast_workers=blast_workers,
        blast_tenants=blast_tenants,
        evidence={
            "fast_burn": b.fast_burn,
            "slow_burn": b.slow_burn,
            "p99_ms": health.p99_ms,
            "verdict": health.verdict,
        },
    )
    return Detection(tenant_id, True, incident_id, b.error_type,
                      blast_workers, blast_tenants)
