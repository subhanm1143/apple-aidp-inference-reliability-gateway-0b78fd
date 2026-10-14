from __future__ import annotations

from app.db.sqlite import conn


class TelemetryRepo:
    def insert(self, *, tenant_id: str, worker_id: str | None, ts: str,
               latency_ms: float, errored: bool, quota_reject: bool = False) -> None:
        """Append one per-tenant per-worker sample. Never updates — telemetry is
        history, and health/burn are computed over a WINDOW of it, per tenant."""
        with conn() as c:
            c.execute(
                """
                INSERT INTO samples (tenant_id, worker_id, ts, latency_ms, errored, quota_reject)
                VALUES (?,?,?,?,?,?)
                """,
                (tenant_id, worker_id, ts, latency_ms, 1 if errored else 0,
                 1 if quota_reject else 0),
            )

    def recent(self, tenant_id: str, limit: int = 60) -> list[dict]:
        """The most recent `limit` samples for a tenant, newest first. Health and
        burn read this window, not a single sample."""
        with conn() as c:
            rows = c.execute(
                """
                SELECT * FROM samples WHERE tenant_id=?
                ORDER BY ts DESC, id DESC LIMIT ?
                """,
                (tenant_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def recent_for_worker(self, worker_id: str, limit: int = 60) -> list[dict]:
        """Every tenant's recent samples that landed on one worker — this is how
        a blast radius is computed: who else shares the worker that's failing."""
        with conn() as c:
            rows = c.execute(
                """
                SELECT * FROM samples WHERE worker_id=?
                ORDER BY ts DESC, id DESC LIMIT ?
                """,
                (worker_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]
