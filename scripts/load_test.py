"""Load test for the FastAPI wrapper (S9-T1).

Fires concurrent requests at POST /v1/query and reports latency percentiles
and error breakdown. Also doubles as a live check that the Sprint 6
per-tenant rate limiter (30 req/min) actually trips under real concurrent
load, not just in the mocked unit test.

Usage:
    uv run uvicorn src.api.main:app --port 8080 &
    uv run python scripts/load_test.py --url http://localhost:8080 \
        --api-key <tenant-key> --requests 50 --concurrency 10
"""
import argparse
import asyncio
import time
from collections import Counter

import httpx

QUERIES = [
    "What is the carry-on baggage weight limit?",
    "What happens if my flight is cancelled under DGCA rules?",
    "How do I redeem loyalty points?",
    "What is the refund policy for a cancelled ticket?",
    "Can I carry a power bank in cabin baggage?",
]


async def _fire_one(client: httpx.AsyncClient, url: str, api_key: str, query: str) -> tuple[int, float]:
    t0 = time.monotonic()
    try:
        resp = await client.post(
            f"{url}/v1/query", json={"query": query}, headers={"X-API-Key": api_key}, timeout=30.0,
        )
        status = resp.status_code
    except httpx.RequestError:
        status = -1
    return status, time.monotonic() - t0


async def run_load_test(url: str, api_key: str, n_requests: int, concurrency: int) -> None:
    sem = asyncio.Semaphore(concurrency)
    results: list[tuple[int, float]] = []

    async def _bounded(i: int):
        async with sem:
            async with httpx.AsyncClient() as client:
                r = await _fire_one(client, url, api_key, QUERIES[i % len(QUERIES)])
                results.append(r)

    t0 = time.monotonic()
    await asyncio.gather(*[_bounded(i) for i in range(n_requests)])
    wall_time = time.monotonic() - t0

    statuses = Counter(s for s, _ in results)
    latencies = sorted(t for s, t in results if s == 200)

    print(f"\n{'='*50}")
    print(f"LOAD TEST: {n_requests} requests, concurrency={concurrency}")
    print(f"{'='*50}")
    print(f"Wall time        : {wall_time:.2f}s")
    print(f"Status breakdown : {dict(statuses)}")
    if latencies:
        p50 = latencies[len(latencies) // 2]
        p95 = latencies[int(len(latencies) * 0.95)] if len(latencies) > 1 else latencies[0]
        print(f"200 OK latency   : p50={p50:.2f}s  p95={p95:.2f}s  max={max(latencies):.2f}s")
    n_429 = statuses.get(429, 0)
    print(f"Rate-limited (429): {n_429} — {'rate limiter engaged' if n_429 else 'no throttling observed'}")
    print("=" * 50)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:8080")
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--requests", type=int, default=50)
    parser.add_argument("--concurrency", type=int, default=10)
    args = parser.parse_args()

    asyncio.run(run_load_test(args.url, args.api_key, args.requests, args.concurrency))


if __name__ == "__main__":
    main()
