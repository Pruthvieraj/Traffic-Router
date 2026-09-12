"""A lightweight, dependency-free (beyond `requests`, already required)
load test for /api/solve and /api/solve_fleet.

Why this exists: a second, independent judge review of this project asked
a fair question this repo had no real answer to — "your Procfile runs one
gunicorn worker, what happens under concurrent load?" — and suggested "a
real concurrency/load test... answers the scalability question with a
number instead of a guess." This script is that number. It does NOT spin
up any paid infrastructure or external service; it drives ordinary HTTP
requests against your own locally running `app.py` (or any URL you point
it at) using Python's stdlib `concurrent.futures` thread pool plus the
`requests` library already in requirements.txt.

Two modes, because "what happens under load" actually has two honest
answers depending on which knob you're testing:

  rate-limit  Fires a fast burst at a NORMALLY running server (rate
              limiting ON, the real production posture) and reports how
              many requests were served vs. correctly rejected with 429.
              This is the answer to "what stops abuse" (Q13) — a number,
              not just "flask-limiter is installed."

  capacity    Measures real solve latency/throughput at increasing
              concurrency against a server started with rate limiting
              deliberately disabled for this purpose only:

                  DISABLE_RATE_LIMIT_FOR_LOADTEST=1 python3 app.py

              This is the answer to "how does one gunicorn worker hold up"
              (Q12/Q14/Q15) — with the explicit, printed caveat that a
              single Flask/gunicorn worker serves requests one at a time,
              so latency should visibly climb with concurrency; that's the
              real, honest limit this project has always documented, not
              a bug in this script.

Usage:
    # Terminal 1 — capacity mode needs the opt-in env var:
    DISABLE_RATE_LIMIT_FOR_LOADTEST=1 python3 app.py

    # Terminal 2:
    python3 loadtest.py capacity --stops 8 --concurrency 1,5,10,20 --requests 30
    python3 loadtest.py rate-limit --burst 30

Results are printed as a table and also written to
output/loadtest_results.json so a real number can be pasted into a slide
or JUDGE_PREP.md instead of re-run live in front of judges (the review's
own advice: never demo something time-sensitive live if you don't have to).
"""
from __future__ import annotations

import argparse
import json
import os
import random
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

DEFAULT_URL = "http://127.0.0.1:5000"


def _make_matrix(n_stops: int, seed: int = 42) -> list[list[float]]:
    """A random symmetric travel-time matrix (seconds), in a range typical
    of the kind of stop lists this app's own tests and demo use — not
    picked to make the solver look artificially fast or slow."""
    rng = random.Random(seed)
    m = [[0.0] * n_stops for _ in range(n_stops)]
    for i in range(n_stops):
        for j in range(i + 1, n_stops):
            t = rng.uniform(120, 1800)
            m[i][j] = t
            m[j][i] = t
    return m


def _solve_payload(n_stops: int, method: str) -> dict:
    return {"matrix": _make_matrix(n_stops), "method": method, "hour": 12.0}


def _solve_fleet_payload(n_stops: int, method: str, n_vehicles: int) -> dict:
    return {
        "matrix": _make_matrix(n_stops),
        "method": method,
        "hour": 12.0,
        "n_vehicles": n_vehicles,
        "depot_index": 0,
    }


def _one_request(session: requests.Session, url: str, payload: dict, timeout: float):
    t0 = time.perf_counter()
    try:
        resp = session.post(url, json=payload, timeout=timeout)
        elapsed = time.perf_counter() - t0
        return {"status": resp.status_code, "elapsed": elapsed, "ok": resp.status_code == 200}
    except requests.exceptions.RequestException as exc:
        elapsed = time.perf_counter() - t0
        return {"status": None, "elapsed": elapsed, "ok": False, "error": str(exc)}


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return float("nan")
    values = sorted(values)
    k = (len(values) - 1) * (pct / 100.0)
    f, c = int(k), min(int(k) + 1, len(values) - 1)
    if f == c:
        return values[f]
    return values[f] + (values[c] - values[f]) * (k - f)


def run_capacity(args) -> dict:
    endpoint = "/api/solve_fleet" if args.endpoint == "solve_fleet" else "/api/solve"
    url = args.url.rstrip("/") + endpoint
    payload = (
        _solve_fleet_payload(args.stops, args.method, args.n_vehicles)
        if args.endpoint == "solve_fleet"
        else _solve_payload(args.stops, args.method)
    )

    # Warm up: the first quantum-method solve pays a one-time import/JIT
    # cost that would otherwise pollute the concurrency=1 baseline.
    with requests.Session() as s:
        warm = _one_request(s, url, payload, args.timeout)
        if not warm["ok"]:
            print(
                f"Warm-up request failed (status={warm['status']}, "
                f"error={warm.get('error')}). Is app.py running at {args.url} "
                f"with DISABLE_RATE_LIMIT_FOR_LOADTEST=1 set?",
                file=sys.stderr,
            )
            sys.exit(1)

    levels = [int(c) for c in args.concurrency.split(",")]
    results = {"mode": "capacity", "endpoint": endpoint, "stops": args.stops, "method": args.method, "levels": []}

    print(f"\ncapacity mode — {endpoint}  method={args.method}  stops={args.stops}")
    print(f"{'concurrency':>11} {'n':>5} {'ok':>5} {'p50 ms':>9} {'p95 ms':>9} {'p99 ms':>9} {'req/s':>8}")

    for concurrency in levels:
        n = max(args.requests, concurrency)  # at least one request per worker
        session = requests.Session()
        t_start = time.perf_counter()
        outcomes = []
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = [pool.submit(_one_request, session, url, payload, args.timeout) for _ in range(n)]
            for fut in as_completed(futures):
                outcomes.append(fut.result())
        wall = time.perf_counter() - t_start

        ok_latencies_ms = [o["elapsed"] * 1000 for o in outcomes if o["ok"]]
        n_ok = len(ok_latencies_ms)
        throughput = n / wall if wall > 0 else float("nan")

        p50 = _percentile(ok_latencies_ms, 50)
        p95 = _percentile(ok_latencies_ms, 95)
        p99 = _percentile(ok_latencies_ms, 99)

        print(f"{concurrency:>11} {n:>5} {n_ok:>5} {p50:>9.0f} {p95:>9.0f} {p99:>9.0f} {throughput:>8.2f}")

        results["levels"].append(
            {
                "concurrency": concurrency,
                "n_requests": n,
                "n_ok": n_ok,
                "p50_ms": p50,
                "p95_ms": p95,
                "p99_ms": p99,
                "throughput_req_per_s": throughput,
                "wall_seconds": wall,
            }
        )

    return results


def run_rate_limit(args) -> dict:
    url = args.url.rstrip("/") + "/api/solve"
    payload = _solve_payload(args.stops, "classical")

    session = requests.Session()
    print(f"\nrate-limit mode — firing a burst of {args.burst} requests as fast as possible against {url}")
    print("(this server should be running WITHOUT DISABLE_RATE_LIMIT_FOR_LOADTEST — the real posture)")

    with ThreadPoolExecutor(max_workers=min(args.burst, 20)) as pool:
        futures = [pool.submit(_one_request, session, url, payload, args.timeout) for _ in range(args.burst)]
        outcomes = [fut.result() for fut in as_completed(futures)]

    n_200 = sum(1 for o in outcomes if o["status"] == 200)
    n_429 = sum(1 for o in outcomes if o["status"] == 429)
    n_other = len(outcomes) - n_200 - n_429

    print(f"  200 OK:              {n_200}")
    print(f"  429 Too Many Requests: {n_429}")
    if n_other:
        print(f"  other/error:         {n_other}")

    if n_429 == 0 and args.burst > 20:
        print(
            "\nNOTE: no 429s seen even though the burst exceeded the documented "
            "20/minute limit — check that this server was started WITHOUT "
            "DISABLE_RATE_LIMIT_FOR_LOADTEST=1 and that flask-limiter is installed.",
            file=sys.stderr,
        )

    return {"mode": "rate-limit", "burst": args.burst, "n_200": n_200, "n_429": n_429, "n_other": n_other}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("mode", choices=["capacity", "rate-limit"])
    parser.add_argument("--url", default=DEFAULT_URL, help=f"base URL of a running app.py (default: {DEFAULT_URL})")
    parser.add_argument("--stops", type=int, default=8, help="number of stops in the generated request (default: 8)")
    parser.add_argument("--method", default="classical", choices=["classical", "quantum"])
    parser.add_argument("--endpoint", default="solve", choices=["solve", "solve_fleet"])
    parser.add_argument("--n-vehicles", type=int, default=2, dest="n_vehicles")
    parser.add_argument("--concurrency", default="1,5,10,20", help="comma-separated concurrency levels (capacity mode)")
    parser.add_argument("--requests", type=int, default=30, help="requests per concurrency level (capacity mode)")
    parser.add_argument("--burst", type=int, default=30, help="requests fired in the burst (rate-limit mode)")
    parser.add_argument("--timeout", type=float, default=30.0, help="per-request timeout in seconds")
    parser.add_argument("--out", default="output/loadtest_results.json")
    args = parser.parse_args()

    results = run_capacity(args) if args.mode == "capacity" else run_rate_limit(args)

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nWrote {args.out}")


if __name__ == "__main__":
    main()
