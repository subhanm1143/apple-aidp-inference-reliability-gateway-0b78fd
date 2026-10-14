"""FastAPI control-plane API. Wires the whole loop from ARCHITECTURE.md into
the contract the operator console renders: register a tenant, send traffic
through the quota-gated gateway, read a tenant's health and burn, detect and
open an incident, apply a gated GitOps redeploy, and read the append-only
history. Every endpoint is a thin call into the module that already owns the
logic — this file has no reliability reasoning of its own."""
from __future__ import annotations

import time
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.db.sqlite import init_schema
from app.detect import anomaly
from app.gitops.apply import redeploy_worker
from app.health import burn as burn_mod
from app.health import evaluate as health_mod
from app.injector import fault
from app.quota.bucket import TokenBucketQuota
from app.repositories.incidents import IncidentRepo
from app.repositories.redeploy import RedeployRepo
from app.repositories.tenants import Tenant, TenantRepo, WorkerRepo
from app.repositories.telemetry import TelemetryRepo
from app.sim.gateway import serve_tick

app = FastAPI(title="Apple AiDP Multi-Tenant Inference Reliability Gateway")

tenant_repo = TenantRepo()
worker_repo = WorkerRepo()
tele_repo = TelemetryRepo()
incident_repo = IncidentRepo()
redeploy_repo = RedeployRepo()
quota = TokenBucketQuota()

WORKERS = ["w-1", "w-2", "w-3"]


@app.on_event("startup")
def _startup() -> None:
    init_schema()
    for w in WORKERS:
        worker_repo.upsert(w, version="v1", healthy=True)


class TenantIn(BaseModel):
    id: str
    rate_per_sec: float
    burst: int
    baseline_p99_ms: float
    baseline_err_pct: float


class RequestIn(BaseModel):
    tenant_id: str
    count: int = 1


class RedeployIn(BaseModel):
    worker_id: str
    to_version: str
    incident_id: int | None = None


@app.post("/tenants")
def register_tenant(body: TenantIn) -> dict:
    tenant_repo.upsert(Tenant(body.id, body.rate_per_sec, body.burst,
                               body.baseline_p99_ms, body.baseline_err_pct))
    quota.register(body.id, body.rate_per_sec, body.burst)
    return {"registered": body.id}


@app.post("/gateway/request")
def gateway_request(body: RequestIn) -> dict:
    """Send `count` requests for one tenant through the quota gate, then the
    shared worker pool. Rejected requests are telemetered too, at zero
    latency — a rejection is a normal outcome, not a served request."""
    tenant = tenant_repo.get(body.tenant_id)
    if tenant is None:
        raise HTTPException(404, f"unknown tenant {body.tenant_id!r}")

    now = time.monotonic()
    admitted: list[tuple[str, str]] = []
    rejected = 0
    for i in range(body.count):
        if quota.allow(body.tenant_id, now=now):
            admitted.append((body.tenant_id, f"req-{i}"))
        else:
            rejected += 1

    ts = datetime.now(timezone.utc).isoformat()
    for _ in range(rejected):
        tele_repo.insert(tenant_id=body.tenant_id, worker_id=None, ts=ts,
                          latency_ms=0.0, errored=False, quota_reject=True)

    served = serve_tick(admitted, WORKERS, fault.faulty_ids())
    for s in served:
        tele_repo.insert(tenant_id=s["tenant_id"], worker_id=s["worker_id"], ts=ts,
                          latency_ms=s["latency_ms"], errored=s["errored"])

    return {"admitted": len(admitted), "rejected": rejected, "served": served}


@app.get("/tenants/{tenant_id}/health")
def get_health(tenant_id: str) -> dict:
    h = health_mod.evaluate(tenant_id)
    return h.__dict__


@app.get("/tenants/{tenant_id}/burn")
def get_burn(tenant_id: str) -> dict:
    b = burn_mod.evaluate(tenant_id)
    return b.__dict__


@app.post("/incidents/detect")
def detect_incident(tenant_id: str) -> dict:
    d = anomaly.detect(tenant_id)
    return d.__dict__


@app.get("/incidents")
def list_incidents() -> list[dict]:
    return incident_repo.all()


@app.post("/gitops/redeploy")
def gitops_redeploy(body: RedeployIn) -> dict:
    result = redeploy_worker(worker_id=body.worker_id, to_version=body.to_version,
                              incident_id=body.incident_id)
    if not result.ok:
        raise HTTPException(400, result.reason)
    # A redeploy fixes the fault too — the worker comes back healthy.
    fault.clear(body.worker_id)
    return result.__dict__


@app.get("/gitops/events")
def gitops_events(worker_id: str | None = None) -> list[dict]:
    return redeploy_repo.history(worker_id)


@app.get("/metrics/summary")
def metrics_summary() -> dict:
    tenants = tenant_repo.all()
    workers = worker_repo.all()
    by_health = {"healthy": 0, "degraded": 0, "unhealthy": 0}
    for t in tenants:
        by_health[health_mod.evaluate(t["id"]).verdict] += 1
    return {
        "tenants_by_health": by_health,
        "workers_healthy": sum(1 for w in workers if w["healthy"]),
        "workers_total": len(workers),
        "open_incidents": len(incident_repo.all()),
    }
