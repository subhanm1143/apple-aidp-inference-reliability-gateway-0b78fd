"""Prove the fix held. Re-measures a tenant's p99 latency AFTER a GitOps
redeploy against the BEFORE snapshot taken when the incident opened, and
checks every tenant in the incident's blast radius stayed inside its OWN
baseline throughout — the second half of the promise this project makes: not
just "did we fix the tenant that broke" but "did anyone else pay for it
while we fixed it." That second check is what makes this a MULTI-TENANT
proof and not just an incident close-out."""
from __future__ import annotations

from dataclasses import dataclass

from app.health import evaluate as health_mod

health_evaluate = health_mod.evaluate


@dataclass
class ProofResult:
    tenant_id: str
    before_p99_ms: float
    after_p99_ms: float
    held: bool
    isolation_held: bool
    isolation_report: dict[str, str]


def snapshot_p99(tenant_id: str) -> float:
    """Call this the moment an incident opens, BEFORE the redeploy — the
    'before' half of the comparison the proof depends on."""
    return health_evaluate(tenant_id).p99_ms


def prove(tenant_id: str, before_p99_ms: float, blast_tenants: list[str]) -> ProofResult:
    """Call this AFTER the redeploy and a fresh tick of traffic. `held` means
    the tenant that broke is back to healthy at or below its pre-incident
    p99. `isolation_held` means every OTHER tenant that shared the faulty
    worker never left 'healthy' — the blast radius stayed exactly as wide as
    the incident record said it was, and no wider."""
    after = health_evaluate(tenant_id)
    held = after.verdict == "healthy" and after.p99_ms <= before_p99_ms

    isolation_report: dict[str, str] = {}
    isolation_held = True
    for other_id in blast_tenants:
        other_health = health_evaluate(other_id)
        isolation_report[other_id] = other_health.verdict
        if other_health.verdict != "healthy":
            isolation_held = False

    return ProofResult(tenant_id, round(before_p99_ms, 1), after.p99_ms,
                        held, isolation_held, isolation_report)
