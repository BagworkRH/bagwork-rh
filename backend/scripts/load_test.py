"""Concurrency smoke / load test — Spec 05 Phase 8 (load testing).

A small stdlib + `requests` harness that hammers two endpoints concurrently
from one machine and reports status counts and latency percentiles. It is a
*sanity* load test: use `k6`, Locust, or a managed load-testing service for
real capacity planning.

Usage:
  python scripts/load_test.py                       # defaults below
  python scripts/load_test.py --url http://localhost:8000 \
      --workers 20 --requests 500
"""
import argparse
import concurrent.futures
import statistics
import time

import requests

ENDPOINTS = [
    "/api/health/",
    "/api/v1/campaigns/",
]
# Anything at or above this is treated as a server-side failure.
ERROR_STATUS_CODE = 500


def _make_request(base_url, path, results):
    started = time.perf_counter()
    try:
        resp = requests.get(f"{base_url}{path}", timeout=10)
        ok = resp.status_code < ERROR_STATUS_CODE
    except requests.RequestException:
        ok = False
    elapsed_ms = (time.perf_counter() - started) * 1000
    results.append((path, ok, elapsed_ms))


def main():
    parser = argparse.ArgumentParser(description="Concurrency smoke test.")
    parser.add_argument("--url", default="http://localhost:8000", help="Base URL")
    parser.add_argument("--workers", type=int, default=20, help="Concurrent workers")
    parser.add_argument("--requests", type=int, default=400, help="Total requests")
    args = parser.parse_args()

    results = []
    total, started = 0, time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [
            pool.submit(_make_request, args.url, path, results)
            for _ in range(args.requests)
            for path in ENDPOINTS
        ]
        for future in concurrent.futures.as_completed(futures):
            future.result()  # raise any unexpected exceptions
            total += 1

    elapsed = time.perf_counter() - started
    latencies = sorted(r[2] for r in results)
    ok_count = sum(1 for r in results if r[1])

    print(f"requests={total}  ok={ok_count}  failed={total - ok_count}")
    print(f"total_time={elapsed:.1f}s  req/s={total / elapsed:.1f}")
    if latencies:
        p50 = statistics.median(latencies)
        p95 = latencies[min(int(len(latencies) * 0.95), len(latencies) - 1)]
        print(f"latency_ms  p50={p50:.0f}  p95={p95:.0f}  max={latencies[-1]:.0f}")

    failed = total - ok_count
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()