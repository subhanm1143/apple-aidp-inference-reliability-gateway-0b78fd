"""Builds the declarative manifest a GitOps redeploy applies. This is the
same CONTRACT `kubectl apply -f` and an Argo CD Application sync expose — a
YAML document naming the desired state — simulated locally so the project
runs with no cluster. Committing this string is the moment a real setup
would push to git and let Argo CD reconcile; here `apply.py` reconciles it
directly, which is the only thing a local simulation skips."""
from __future__ import annotations


def build_manifest(*, worker_id: str, to_version: str, healthy: bool = True) -> str:
    """A minimal, deterministic YAML-shaped manifest for ONE worker. Real
    Argo CD manifests carry a Deployment + Service; this carries exactly the
    two fields this project's workers table tracks, because that's the whole
    surface the reliability loop steers."""
    return (
        "apiVersion: gateway.khwajalabs/v1\n"
        "kind: Worker\n"
        "metadata:\n"
        f"  name: {worker_id}\n"
        "spec:\n"
        f"  version: {to_version}\n"
        f"  healthy: {str(healthy).lower()}\n"
    )


def parse_manifest(manifest_yaml: str) -> dict:
    """A tiny, dependency-free parser for the exact shape `build_manifest`
    produces — good enough to prove the round trip, not a general YAML
    parser. Real Argo CD hands this job to a full YAML/JSON engine."""
    fields: dict[str, str] = {}
    for line in manifest_yaml.splitlines():
        stripped = line.strip()
        if stripped.startswith("name:"):
            fields["worker_id"] = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("version:"):
            fields["to_version"] = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("healthy:"):
            fields["healthy"] = stripped.split(":", 1)[1].strip() == "true"
    return fields


if __name__ == "__main__":
    m = build_manifest(worker_id="w-1", to_version="v2", healthy=True)
    parsed = parse_manifest(m)
    assert parsed == {"worker_id": "w-1", "to_version": "v2", "healthy": True}, parsed
    print("ok: build_manifest -> parse_manifest round-trips the desired state")
