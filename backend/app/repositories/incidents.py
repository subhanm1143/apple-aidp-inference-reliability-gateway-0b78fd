from __future__ import annotations

import json

from app.db.sqlite import conn


class IncidentRepo:
    def open(self, *, tenant_id: str, error_type: str, blast_workers: list[str],
             blast_tenants: list[str], evidence: dict) -> int:
        """Append-only. Opening an incident is a NEW immutable row, never an
        update — the incident's evidence at the moment it was opened must
        survive even if things get better a minute later."""
        with conn() as c:
            cur = c.execute(
                """
                INSERT INTO incidents
                  (tenant_id, error_type, blast_workers, blast_tenants, evidence_json)
                VALUES (?,?,?,?,?)
                """,
                (tenant_id, error_type, json.dumps(blast_workers),
                 json.dumps(blast_tenants), json.dumps(evidence)),
            )
            return int(cur.lastrowid)

    def all(self, limit: int = 100) -> list[dict]:
        with conn() as c:
            rows = c.execute(
                "SELECT * FROM incidents ORDER BY opened_at DESC, id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["blast_workers"] = json.loads(d["blast_workers"])
            d["blast_tenants"] = json.loads(d["blast_tenants"])
            d["evidence_json"] = json.loads(d["evidence_json"])
            out.append(d)
        return out

    def for_tenant(self, tenant_id: str, limit: int = 20) -> list[dict]:
        with conn() as c:
            rows = c.execute(
                """SELECT * FROM incidents WHERE tenant_id=?
                   ORDER BY opened_at DESC, id DESC LIMIT ?""",
                (tenant_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]
