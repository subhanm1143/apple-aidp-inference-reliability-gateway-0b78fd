"""Applies a gated GitOps redeploy: only the WORKER named in the manifest
changes state, and every other worker is untouched — the gate that keeps a
fix for one incident from becoming a second incident. Every apply is
recorded as an append-only event, the same audit trail a real Argo CD
Application's sync history leaves behind."""
from __future__ import annotations

from dataclasses import dataclass

from app.gitops.manifest import build_manifest, parse_manifest
from app.repositories.redeploy import RedeployRepo
from app.repositories.tenants import WorkerRepo

worker_repo = WorkerRepo()
redeploy_repo = RedeployRepo()


@dataclass
class ApplyResult:
    ok: bool
    worker_id: str
    from_version: str
    to_version: str
    untouched_workers: list[str]
    redeploy_event_id: int | None
    reason: str = ""


def redeploy_worker(*, worker_id: str, to_version: str,
                     incident_id: int | None = None) -> ApplyResult:
    """The GATE: fetch current state, refuse if the worker doesn't exist,
    apply ONLY that worker's manifest, and prove every OTHER worker's version
    is unchanged before returning — that proof is what "blast radius stayed
    contained" means at the redeploy layer."""
    all_workers = worker_repo.all()
    current = next((w for w in all_workers if w["id"] == worker_id), None)
    if current is None:
        return ApplyResult(False, worker_id, "", to_version, [], None,
                            reason=f"unknown worker {worker_id!r}")

    others_before = {w["id"]: w["version"] for w in all_workers if w["id"] != worker_id}

    manifest_yaml = build_manifest(worker_id=worker_id, to_version=to_version, healthy=True)
    desired = parse_manifest(manifest_yaml)
    worker_repo.set_version(desired["worker_id"], desired["to_version"], desired["healthy"])

    others_after = {w["id"]: w["version"] for w in worker_repo.all() if w["id"] != worker_id}
    untouched = [wid for wid, v in others_before.items() if others_after.get(wid) == v]
    assert untouched == list(others_before.keys()), (
        "gate violated: a redeploy touched a worker outside its manifest")

    event_id = redeploy_repo.append(
        worker_id=worker_id, incident_id=incident_id,
        from_version=current["version"], to_version=to_version,
        manifest_yaml=manifest_yaml,
    )
    return ApplyResult(True, worker_id, current["version"], to_version,
                        untouched, event_id)
