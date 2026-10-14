from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.db.sqlite import conn


@dataclass
class Tenant:
    id: str
    rate_per_sec: float
    burst: int
    baseline_p99_ms: float
    baseline_err_pct: float


class TenantRepo:
    def upsert(self, t: Tenant) -> None:
        with conn() as c:
            c.execute(
                """
                INSERT INTO tenants (id, rate_per_sec, burst, baseline_p99_ms, baseline_err_pct)
                VALUES (?,?,?,?,?)
                ON CONFLICT (id) DO UPDATE SET
                  rate_per_sec=excluded.rate_per_sec, burst=excluded.burst,
                  baseline_p99_ms=excluded.baseline_p99_ms,
                  baseline_err_pct=excluded.baseline_err_pct
                """,
                (t.id, t.rate_per_sec, t.burst, t.baseline_p99_ms, t.baseline_err_pct),
            )

    def get(self, tenant_id: str) -> Optional[dict]:
        with conn() as c:
            row = c.execute("SELECT * FROM tenants WHERE id=?", (tenant_id,)).fetchone()
        return dict(row) if row else None

    def all(self) -> list[dict]:
        with conn() as c:
            rows = c.execute("SELECT * FROM tenants ORDER BY id").fetchall()
        return [dict(r) for r in rows]


class WorkerRepo:
    def upsert(self, worker_id: str, version: str, healthy: bool = True) -> None:
        with conn() as c:
            c.execute(
                """
                INSERT INTO workers (id, version, healthy) VALUES (?,?,?)
                ON CONFLICT (id) DO UPDATE SET version=excluded.version, healthy=excluded.healthy
                """,
                (worker_id, version, 1 if healthy else 0),
            )

    def all(self) -> list[dict]:
        with conn() as c:
            rows = c.execute("SELECT * FROM workers ORDER BY id").fetchall()
        return [dict(r) for r in rows]

    def healthy_ids(self) -> list[str]:
        with conn() as c:
            rows = c.execute("SELECT id FROM workers WHERE healthy=1 ORDER BY id").fetchall()
        return [r["id"] for r in rows]

    def set_health(self, worker_id: str, healthy: bool) -> None:
        with conn() as c:
            c.execute("UPDATE workers SET healthy=? WHERE id=?", (1 if healthy else 0, worker_id))

    def set_version(self, worker_id: str, version: str, healthy: bool) -> None:
        with conn() as c:
            c.execute(
                "UPDATE workers SET version=?, healthy=? WHERE id=?",
                (version, 1 if healthy else 0, worker_id),
            )
