# Apple | AiDP — Multi-Tenant Inference Reliability Gateway

An advanced reliability-engineering capstone modeled on Apple's AiDP (AI and Data Platform) Reliability Engineering role, where the product is a shared internal ML/GenAI inference platform several teams route traffic through at once — and the reliability problem that dominates everything is that a shared worker pool serves EVERYONE until something explicitly stops it. A tenant with no quota can consume every worker's capacity and starve a tenant that did nothing wrong; a global health number can hide one tenant's real regression inside nine tenants' healthy average. You build a gateway that enforces a token-bucket quota per tenant BEFORE a request reaches a shared worker, so isolation is enforced instead of assumed, and you prove it live — a well-behaved tenant's own request overloads the moment a co-tenant's ungated flood has already saturated the worker it lands on. You ingest per-tenant per-worker telemetry as append-only samples, score each tenant's health against ITS OWN learned baseline instead of a fleet average, turn a sustained breach into a per-tenant SLO burn-rate with a fast and a slow window, and the moment burn crosses the page threshold you open an incident naming the exact tenant, the error type, and the BLAST RADIUS — which worker, and which other tenants share it. You then trigger a declarative, Argo-CD-shaped GitOps redeploy that replaces only the implicated worker, gated so every other worker's version is provably untouched, and work an end-to-end incident — inject a real fault, watch detection open the incident on its own, redeploy the fix, and PROVE it held by re-measuring the tenant's latency and confirming every tenant in the blast radius stayed healthy the whole time. The reference implementation is plain Python (FastAPI) + SQLite + a small multi-tenant worker simulator, so the reliability reasoning — not a Kubernetes install — stays front and center; the GitOps redeploy is simulated locally, following the same established pattern as this catalog's other SRE capstones.

Built step-by-step with [KhwajaLabs Build](https://khwajalabs.com).

## Stack
- Python
- FastAPI
- SQLite
- token-bucket rate limiting
- multi-tenant isolation
- per-tenant SLO burn-rate
- GitOps-style declarative redeploy (simulated)
- reliability-control-plane design
