# Apple AiDP — Multi-Tenant Inference Reliability Gateway — Architecture

## What this is
This service is the **seam** between two things that don't speak the same
language on a shared internal ML platform:

- **per-tenant traffic** (several separate teams, each sending inference
  requests through the same pool of workers, each expecting the others'
  bad day to never touch them)
- **a redeploy decision** (which worker in the shared pool needs to be
  replaced RIGHT NOW, and whether replacing it is safe to do without
  touching anyone else's traffic)

The gateway's whole job is to turn the first into the second SAFELY — enforce
a quota per tenant so nobody can starve anyone else, watch each tenant's own
latency and error rate against ITS OWN learned baseline instead of one global
number, open an incident that names the exact tenant, error type, and blast
radius the moment a real regression is underway, trigger a declarative
GitOps-style redeploy of just the broken worker, and then **prove the fix
held** — the next failure gets caught and fixed without spreading.

## Why multi-tenant reliability is a BLAST-RADIUS problem
A single-tenant API only has to ask "am I healthy." A platform serving several
tenants off a shared worker pool has to ask a second question every time
something breaks: "healthy for WHOM, and did it spread." The whole design
follows from three facts:

1. **A shared worker serves everyone until it's told not to.** Nothing about
   HTTP routing stops one tenant's traffic from landing on a worker that is
   already struggling because of a DIFFERENT tenant's load. Isolation has to
   be built, not assumed.
2. **A quota is a promise, not a suggestion.** If tenant A can send unlimited
   requests, tenant A can consume every worker's capacity and tenant B's
   requests queue behind A's, even though B did nothing wrong. Enforcing a
   quota BEFORE a request reaches a worker is the only way to keep that
   promise.
3. **A global health number hides exactly the failure that matters.** If nine
   tenants are fine and one tenant's error rate has gone to 40%, the platform
   average barely moves. Reliability here means per-tenant visibility, not a
   fleet-wide rollup.

## The loop (this is the spine)
1. **Quota** — a token-bucket rate limiter gates every request against that
   tenant's own bucket BEFORE it reaches a shared worker, so one tenant's
   burst cannot consume capacity another tenant is entitled to.
2. **Route** — an allowed request is forwarded to a worker from the shared
   pool; the worker serves it (or, if the worker is faulty, fails it).
3. **Telemetry** — every served or failed request is appended as a per-tenant
   per-worker sample: latency, whether it errored, which worker took it.
4. **Health** — roll a window of a tenant's samples into a verdict, comparing
   it against THAT TENANT's own learned baseline, requiring a sustained
   breach so one slow request doesn't trigger anything.
5. **Burn** — turn a tenant's sustained breach into an SLO burn-rate with a
   fast and a slow window, so we page on trajectory, per tenant.
6. **Detect & open an incident** — when burn crosses the page threshold, open
   an incident record naming the tenant, the error type, and the blast
   radius (which workers, which tenants are actually affected) BEFORE a human
   looks at a dashboard.
7. **GitOps redeploy** — apply a declarative manifest that replaces only the
   implicated worker(s), recorded as an append-only redeploy event — the
   same shape as a real Argo CD sync, simulated locally so the project runs
   on a laptop with no cluster.
8. **Prove it held** — after the redeploy, re-measure the tenant's latency and
   error rate through the next injected failure and confirm the incident
   stayed inside its blast radius; that comparison is the evidence the fix
   actually worked.

## Why this project SIMULATES Kubernetes and Argo CD instead of running them
The reliability reasoning above — quota enforcement, per-tenant health, burn
math, blast-radius detection, a gated redeploy, proving the fix held — is
identical whether the "worker" is a real Kubernetes pod behind a real Argo CD
sync or a row in a local table. A real cluster would add hours of cloud setup
that teaches nothing about THIS problem. So the reference build models a
worker as a plain Python object with a `version` and a `healthy` flag, and the
"GitOps redeploy" is a declarative YAML-shaped manifest applied by a Python
function that changes that state and appends an audit event — the exact
contract `kubectl apply -f` and Argo CD's reconcile loop expose, minus the
cluster. Following the catalog's established pattern (see
`fireworks-ai-inference-reliability-platform`,
`baseten-inference-autoscale-sre-platform`,
`cloudflare-netpilot-reliability-control-plane`), every SRE-track capstone in
this catalog simulates its infrastructure the same way, for the same reason.

## The contract the operator console renders
- `POST /tenants`                    — register a tenant with a quota and a learned baseline
- `POST /gateway/request`            — send one inference request through quota + routing
- `GET  /tenants/{id}/health`        — the tenant's current health verdict vs its own baseline
- `GET  /tenants/{id}/burn`          — the tenant's SLO burn-rate, fast and slow window
- `POST /incidents/detect`           — run detection now; opens an incident if burn pages
- `GET  /incidents`                  — every incident, its tenant, error type, and blast radius
- `POST /gitops/redeploy`            — apply a gated manifest that replaces the implicated worker(s)
- `GET  /gitops/events`              — the append-only redeploy history
- `GET  /metrics/summary`            — the header: tenants by health, workers by state, quota rejections

The simulator underneath can change (more tenants, a different fault) without
the console changing. The contract is the stable thing.
