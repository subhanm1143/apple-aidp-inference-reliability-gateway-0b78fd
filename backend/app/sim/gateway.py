"""Multi-tenant inference-worker simulator. Each healthy worker can serve up
to WORKER_CAPACITY requests per tick cleanly. Requests are handed to workers
round-robin in the order they arrive here — so if a tenant's burst is not
gated by a quota BEFORE this stage, that tenant's requests grab worker slots
first and a completely well-behaved tenant's request can still overload,
just because it landed after the flood. That is the noisy-neighbor bug the
token bucket (Step 3) exists to prevent, by rejecting the burst before it
ever reaches this function. A request routed to a FAULTY worker separately
pays a fault penalty on latency and error rate — this is the fault the
incident-detection pipeline (Steps 5-7) has to catch."""
from __future__ import annotations

WORKER_CAPACITY = 5        # requests per tick one healthy worker serves cleanly
BASE_LATENCY_MS = 40.0
OVERLOAD_LATENCY_MS = 250.0
FAULT_LATENCY_MS = 2000.0
FAULT_ERROR_RATE = 0.6      # fraction of requests to a faulty worker that error


def serve_tick(offered: list[tuple[str, str]], workers: list[str],
               faulty: set[str]) -> list[dict]:
    """`offered` is an ordered list of (tenant_id, request_id) pairs already
    admitted past the quota gate. Requests are handed round-robin to workers
    in `offered` order; a worker past its per-tick capacity serves the
    request late (an overload penalty) instead of cleanly."""
    served_count = {w: 0 for w in workers}
    samples = []
    for i, (tenant_id, _req_id) in enumerate(offered):
        worker_id = workers[i % len(workers)]
        served_count[worker_id] += 1
        overloaded = served_count[worker_id] > WORKER_CAPACITY
        if worker_id in faulty:
            latency = FAULT_LATENCY_MS
            errored = (hash((tenant_id, worker_id, i)) % 100) < int(FAULT_ERROR_RATE * 100)
        elif overloaded:
            latency = OVERLOAD_LATENCY_MS
            errored = False
        else:
            latency = BASE_LATENCY_MS
            errored = False
        samples.append({
            "tenant_id": tenant_id,
            "worker_id": worker_id,
            "latency_ms": latency,
            "errored": errored,
        })
    return samples


if __name__ == "__main__":
    workers = ["w-1", "w-2", "w-3"]

    # A light, well-behaved tenant lands on clean base latency, no faults.
    clean = serve_tick([("tenant-a", f"r{i}") for i in range(6)], workers, faulty=set())
    assert all(s["latency_ms"] == BASE_LATENCY_MS for s in clean), clean

    # tenant-a alone floods 15 requests: exactly WORKER_CAPACITY (5) land on
    # each of the 3 workers, so tenant-a itself sees no overload yet.
    flood = serve_tick([("tenant-a", f"r{i}") for i in range(15)], workers, faulty=set())
    assert all(s["latency_ms"] == BASE_LATENCY_MS for s in flood), flood

    # tenant-b's ONE well-behaved request, offered right after tenant-a's
    # flood already saturated every worker to capacity, still overloads —
    # tenant-b did nothing wrong; it just shared a worker with a flood that
    # was never gated by a quota.
    mixed = serve_tick(
        [("tenant-a", f"r{i}") for i in range(15)] + [("tenant-b", "r0")],
        workers, faulty=set(),
    )
    b_sample = mixed[-1]
    assert b_sample["tenant_id"] == "tenant-b"
    assert b_sample["latency_ms"] == OVERLOAD_LATENCY_MS, b_sample

    # A faulty worker drags down whichever tenant happens to land on it.
    faulty_run = serve_tick(
        [("tenant-c", "r0"), ("tenant-c", "r1"), ("tenant-c", "r2")],
        workers, faulty={"w-1"},
    )
    assert faulty_run[0]["latency_ms"] == FAULT_LATENCY_MS

    print("ok: clean load holds base latency, an ungated flood overloads a "
          "well-behaved tenant sharing its worker, a faulty worker drags "
          "down whoever lands on it")
