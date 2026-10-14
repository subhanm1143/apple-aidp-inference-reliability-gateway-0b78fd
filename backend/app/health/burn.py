"""Per-tenant SLO burn-rate. Each tenant's budget is the fraction of requests
allowed to breach ITS OWN baseline (latency over 2x baseline, or an error)
before its reliability promise is meaningless. Burn rate is how fast the
tenant is spending that budget: 1x burns it exactly over the window; 14x
burns it in a fraction of the time. We alert per tenant, with a fast and a
slow window, so we catch a fast meltdown early AND a slow leak eventually —
and, crucially, on the RIGHT tenant, not a platform-wide average."""
from __future__ import annotations

from dataclasses import dataclass

from app.repositories.tenants import TenantRepo
from app.repositories.telemetry import TelemetryRepo

tenant_repo = TenantRepo()
tele_repo = TelemetryRepo()

# Multi-window burn-rate alerting (the Google SRE pattern): a FAST window
# catches a sudden meltdown; a SLOW window catches a slow leak. Both must
# burn hot to page.
FAST_WINDOW = 5
SLOW_WINDOW = 30
# Burn-rate thresholds: page only if the fast window is burning >= this AND
# the slow window confirms it >= this. High fast + confirming slow = real.
FAST_BURN_PAGE = 14.4
SLOW_BURN_PAGE = 3.0
# Budget: fraction of requests allowed to breach baseline before the tenant's
# reliability promise is at risk. 0.02 = "2% of traffic may run hot."
BREACH_BUDGET_FRACTION = 0.02


@dataclass
class Burn:
    tenant_id: str
    fast_burn: float
    slow_burn: float
    page: bool
    error_type: str    # 'latency_regression' | 'error_spike' | 'none'


def _breach_fraction(samples: list[dict], baseline_p99_ms: float) -> tuple[float, str]:
    """Observed fraction of served requests that breached baseline, and which
    kind of breach dominates — the error_type an opened incident will carry."""
    served = [s for s in samples if not s["quota_reject"]]
    if not served:
        return 0.0, "none"
    errored = sum(1 for s in served if s["errored"])
    slow = sum(1 for s in served if s["latency_ms"] > baseline_p99_ms * 2.0)
    breaching = sum(1 for s in served
                     if s["errored"] or s["latency_ms"] > baseline_p99_ms * 2.0)
    fraction = breaching / len(served)
    error_type = "error_spike" if errored >= slow else "latency_regression"
    return fraction, error_type if breaching else "none"


def evaluate(tenant_id: str) -> Burn:
    tenant = tenant_repo.get(tenant_id)
    if tenant is None:
        raise KeyError(tenant_id)
    window = tele_repo.recent(tenant_id, limit=SLOW_WINDOW)

    fast_fraction, fast_type = _breach_fraction(window[:FAST_WINDOW], tenant["baseline_p99_ms"])
    slow_fraction, slow_type = _breach_fraction(window[:SLOW_WINDOW], tenant["baseline_p99_ms"])
    fast_burn = fast_fraction / BREACH_BUDGET_FRACTION if BREACH_BUDGET_FRACTION else 0.0
    slow_burn = slow_fraction / BREACH_BUDGET_FRACTION if BREACH_BUDGET_FRACTION else 0.0

    # Page only when BOTH windows agree it's hot: fast catches it early, slow
    # confirms it's not a one-off spike. This is the multi-window discipline.
    page = fast_burn >= FAST_BURN_PAGE and slow_burn >= SLOW_BURN_PAGE
    error_type = fast_type if fast_type != "none" else slow_type
    return Burn(tenant_id, round(fast_burn, 2), round(slow_burn, 2), page, error_type)
