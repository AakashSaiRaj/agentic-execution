#!/usr/bin/env python3
"""Basic load test for the AI Agent Execution Platform.

Fires N executions concurrently against a running API, waits for each to reach a
terminal state, and reports throughput and latency. Dependency-free (stdlib).

Usage:
  python scripts/loadtest.py --base http://localhost:8000 --count 30 --concurrency 10
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed


def _headers(api_key, extra=None):
    headers = dict(extra or {})
    if api_key:
        headers["X-API-Key"] = api_key
    return headers


def _post(base, i, api_key):
    payload = json.dumps(
        {"user_request": f"Load test #{i}: research topic {i} and compute {i} * 7"}
    ).encode()
    req = urllib.request.Request(
        base + "/api/executions",
        data=payload,
        headers=_headers(api_key, {"Content-Type": "application/json"}),
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)["id"]


def _get(base, execution_id, api_key):
    req = urllib.request.Request(
        base + f"/api/executions/{execution_id}", headers=_headers(api_key)
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def run_one(base, i, api_key, timeout):
    started = time.time()
    execution_id = _post(base, i, api_key)
    while time.time() - started < timeout:
        data = _get(base, execution_id, api_key)
        if data["status"] in ("COMPLETED", "FAILED"):
            return {
                "status": data["status"],
                "latency": time.time() - started,
                "server_ms": data.get("duration_ms"),
                "tokens": data.get("total_tokens") or 0,
            }
        time.sleep(0.25)
    return {"status": "TIMEOUT", "latency": time.time() - started, "server_ms": None, "tokens": 0}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:8000")
    parser.add_argument("--count", type=int, default=30)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("--api-key", default="")
    args = parser.parse_args()

    print(
        f"Load test: {args.count} executions, concurrency {args.concurrency}, "
        f"target {args.base}"
    )
    start = time.time()
    results = []
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = [
            pool.submit(run_one, args.base, i, args.api_key, args.timeout)
            for i in range(args.count)
        ]
        for future in as_completed(futures):
            results.append(future.result())
    wall = time.time() - start

    completed = [r for r in results if r["status"] == "COMPLETED"]
    failed = [r for r in results if r["status"] == "FAILED"]
    timeouts = [r for r in results if r["status"] == "TIMEOUT"]
    latencies = sorted(r["latency"] for r in results)

    def pct(p):
        if not latencies:
            return 0.0
        return latencies[min(len(latencies) - 1, int(len(latencies) * p))]

    print("\n=== Results ===")
    print(f"total wall time:     {wall:.2f}s")
    print(f"completed:           {len(completed)}/{args.count}")
    print(f"failed:              {len(failed)}")
    print(f"timeouts:            {len(timeouts)}")
    print(f"throughput:          {len(completed) / wall:.1f} executions/s")
    print(f"latency p50/p95/max: {pct(0.5):.2f}s / {pct(0.95):.2f}s / {max(latencies, default=0):.2f}s")
    print(f"tokens (completed):  {sum(r['tokens'] for r in completed)}")

    if failed or timeouts:
        sys.exit(1)


if __name__ == "__main__":
    main()
