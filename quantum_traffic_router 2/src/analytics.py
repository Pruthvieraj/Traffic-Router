"""
analytics.py
============
The most basic possible usage counter for the live demo — how many solves
have run, split by endpoint/method, plus average solve time — exposed at
GET /api/analytics so a judge (or you, mid-demo) can point at a live
number instead of a claim.

**Honest scope, stated plainly:**

1. This is an in-process counter (a dict behind a lock), not a database.
   It resets to zero every time the process restarts — including Render's
   free-tier spin-down/spin-up cycle. It is NOT a durable analytics
   pipeline and was never meant to be; it answers "how much traffic has
   this specific running process seen," nothing more.
2. It is per-process. `Procfile` runs `gunicorn app:app` with no `--workers`
   flag, i.e. exactly one worker process, so for this project's actual
   deployment the counters really do reflect every request the app has
   served. If you ever scale this to multiple gunicorn workers, each
   worker gets its OWN counters and /api/analytics only reports whichever
   worker happened to answer that particular request — this module makes
   no attempt to share state across processes (that would need Redis or a
   database, which is real infrastructure this demo doesn't need to carry
   just to show a request count).
3. No per-request/per-user data is stored — only aggregate counts and a
   running sum for the average. There is nothing here to leak: no IPs, no
   request bodies, no timestamps of individual calls.
"""

import threading
import time

_lock = threading.Lock()
_started_at = time.time()
_counts = {
    "solve": 0,
    "solve_fleet": 0,
    "errors": 0,
    "method_quantum": 0,
    "method_classical": 0,
    "incident_applied": 0,
    "precedence_applied": 0,
    "demand_weights_used": 0,
}
_total_solve_ms = 0.0
_solve_ms_count = 0


def record_solve(endpoint: str, method: str, solve_ms: float, incident_applied: bool = False,
                  precedence_applied: bool = False, demand_weights_used: bool = False) -> None:
    """Called once per successful /api/solve or /api/solve_fleet response.
    `endpoint` is "solve" or "solve_fleet"; `method` is "quantum" or
    "classical" (anything else is just not double-counted, not rejected —
    this is a counter, not a validator)."""
    global _total_solve_ms, _solve_ms_count
    with _lock:
        if endpoint in _counts:
            _counts[endpoint] += 1
        method_key = f"method_{method}"
        if method_key in _counts:
            _counts[method_key] += 1
        if incident_applied:
            _counts["incident_applied"] += 1
        if precedence_applied:
            _counts["precedence_applied"] += 1
        if demand_weights_used:
            _counts["demand_weights_used"] += 1
        _total_solve_ms += solve_ms
        _solve_ms_count += 1


def record_error() -> None:
    """Called once per 400/500 response from either solve endpoint —
    deliberately not split by error type/message, since that starts
    edging toward logging request content rather than counting outcomes."""
    with _lock:
        _counts["errors"] += 1


def snapshot() -> dict:
    """A plain-data summary safe to jsonify directly for GET /api/analytics."""
    with _lock:
        total_solves = _counts["solve"] + _counts["solve_fleet"]
        avg_ms = round(_total_solve_ms / _solve_ms_count, 1) if _solve_ms_count else None
        return {
            "since": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(_started_at)),
            "uptime_seconds": round(time.time() - _started_at, 1),
            "total_solves": total_solves,
            "solves_by_endpoint": {
                "solve": _counts["solve"],
                "solve_fleet": _counts["solve_fleet"],
            },
            "solves_by_method": {
                "quantum": _counts["method_quantum"],
                "classical": _counts["method_classical"],
            },
            "avg_solve_ms": avg_ms,
            "errors": _counts["errors"],
            "incident_simulations": _counts["incident_applied"],
            "precedence_requests": _counts["precedence_applied"],
            "demand_weight_requests": _counts["demand_weights_used"],
            "note": (
                "In-process counters only: reset on every restart/redeploy, and "
                "specific to whichever single worker process served this request "
                "(see src/analytics.py's docstring). Not a durable analytics "
                "pipeline — a live number for the current running demo, nothing more."
            ),
        }


def _reset_for_tests() -> None:
    """Test-only helper (tests/test_app.py) — analytics is process-global
    state, so without this, test order would make individual test
    assertions about exact counts flaky."""
    global _total_solve_ms, _solve_ms_count
    with _lock:
        for k in _counts:
            _counts[k] = 0
        _total_solve_ms = 0.0
        _solve_ms_count = 0
