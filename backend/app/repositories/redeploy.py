from __future__ import annotations

from app.db.sqlite import conn


class RedeployRepo:
    def append(self, *, worker_id: str, incident_id: int | None,
               from_version: str, to_version: str, manifest_yaml: str) -> int:
        """Append-only. A redeploy is a NEW immutable event — the same audit
        shape a real Argo CD Application's sync history leaves behind."""
        with conn() as c:
            cur = c.execute(
                """
                INSERT INTO redeploy_events
                  (worker_id, incident_id, from_version, to_version, manifest_yaml)
                VALUES (?,?,?,?,?)
                """,
                (worker_id, incident_id, from_version, to_version, manifest_yaml),
            )
            return int(cur.lastrowid)

    def history(self, worker_id: str | None = None, limit: int = 100) -> list[dict]:
        with conn() as c:
            if worker_id:
                rows = c.execute(
                    """SELECT * FROM redeploy_events WHERE worker_id=?
                       ORDER BY created_at DESC, id DESC LIMIT ?""",
                    (worker_id, limit),
                ).fetchall()
            else:
                rows = c.execute(
                    "SELECT * FROM redeploy_events ORDER BY created_at DESC, id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [dict(r) for r in rows]
