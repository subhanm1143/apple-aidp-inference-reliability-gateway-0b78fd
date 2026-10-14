"""The failure injector. Drops one worker into a faulty state on demand — the
schedule that lets this project test its own detection path deterministically
instead of hoping a real failure happens during a demo. Toggled through the
same `workers` table the redeploy layer writes to, so injecting a fault and
fixing it with a GitOps redeploy are symmetric operations on one row."""
from __future__ import annotations

from app.repositories.tenants import WorkerRepo

worker_repo = WorkerRepo()


def inject(worker_id: str) -> None:
    """Mark a worker faulty. The gateway simulator (Step 4) reads worker
    health from this same table, so the very next tick routes traffic into
    the fault exactly as it would in a real cluster losing a pod's health
    check."""
    worker_repo.set_health(worker_id, healthy=False)


def clear(worker_id: str) -> None:
    """Mark a worker healthy again WITHOUT changing its version — this is
    what a human flipping a flag or restarting a pod looks like, distinct
    from a GitOps redeploy that also changes the deployed version."""
    worker_repo.set_health(worker_id, healthy=True)


def faulty_ids() -> set[str]:
    return {w["id"] for w in worker_repo.all() if not w["healthy"]}
