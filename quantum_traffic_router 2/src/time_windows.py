"""
time_windows.py
================
Time-window constraints — "waypoint X must be reached between 9:00 and
11:00" — on top of the existing QUBO solver, WITHOUT reformulating it.

THE HONEST FORMULATION PROBLEM, stated plainly: qubo_tsp.py's QUBO encodes
a tour as x[v, t] = 1 iff waypoint v is at tour POSITION t (0-indexed visit
order). Real time windows are about WALL-CLOCK arrival time, which is the
CUMULATIVE SUM of travel times along whichever specific edges the solved
tour actually uses up to that point — a quantity that depends on the
solution itself, not just its position. A position-based QUBO has no direct
way to penalize "arrive after 11:00," because "arrival time at position t"
isn't a fixed function of t alone; it varies tour by tour. Encoding TRUE
wall-clock windows exactly needs a different formulation family entirely
(arc-based decision variables x[u,v] plus continuous or discretized time
variables per node, e.g. an MTZ-style time-propagation constraint) — a
bigger rewrite than this project's other constraint additions (precedence,
capacity, position windows), which is exactly why this was flagged as the
highest-formulation-risk item on the roadmap. This module does NOT do that
rewrite. It does something smaller and fully honest instead:

1. RIGOROUS PRUNING, not a guarantee: derive_position_window() converts a
   real clock-time window into a TOUR-POSITION range [t_min, t_max] that is
   PROVABLY SAFE to enforce — every position outside that range is
   mathematically impossible to satisfy the window from, for ANY tour, not
   just the one eventually found (see its own docstring for the proof).
   Enforcing [t_min, t_max] via qubo_tsp.add_position_window_penalty can
   therefore never discard a solution that could have satisfied the
   window — but positions INSIDE the range aren't guaranteed to satisfy it
   either, just not provably ruled out.
2. HONEST VERIFICATION, always: compute_arrival_schedule() computes the
   REAL cumulative arrival time at every stop of whatever tour the solver
   actually returned, and check_time_windows() reports, per waypoint,
   whether its window is genuinely satisfied — a checked fact about the
   specific solution, never assumed from the position-window pruning alone.
3. solve_with_time_windows() ties both together: derive safe position
   bounds for every requested window, solve with them enforced, then
   VERIFY the result and report exactly which windows (if any) are still
   violated — because pruning reduces the odds of a violation without
   eliminating it. This is the same "measure it, don't just assert it"
   standard the rest of this project holds itself to (see benchmark.py's
   Experiments 2-4).
"""

import itertools

import numpy as np

from qubo_tsp import (
    open_path_length,
    solve_open_path_quantum_inspired,
    solve_quantum_inspired,
    tour_length,
)


def _sorted_edges(W: np.ndarray) -> list[float]:
    """Every distinct (unordered) edge weight in W, ascending — used as the
    raw material for the rigorous lower/upper cumulative-time bounds
    below. W is assumed symmetric with a zero diagonal (this project's
    convention throughout), so each unordered pair is counted once."""
    n = W.shape[0]
    return sorted(float(W[i, j]) for i, j in itertools.combinations(range(n), 2))


def derive_position_window(
    W: np.ndarray, window: tuple[float, float], start_offset: float = 0.0,
) -> tuple[int, int]:
    """Convert a real clock-time window (earliest, latest) into an
    inclusive tour-POSITION range [t_min, t_max] (0-indexed: position 0 is
    the first-visited waypoint) that is provably safe to enforce as a hard
    QUBO constraint — i.e. every position this function excludes is
    mathematically guaranteed to violate the window, for ANY tour over W,
    not just whichever one the solver happens to find.

    THE PROOF: reaching tour position t requires traveling exactly t
    distinct edges (position 0 needs none, since it's the first stop).
    Whatever those t specific edges are, their sum can never be smaller
    than the sum of the t globally SMALLEST edge weights in W (summing any
    t distinct numbers is always >= summing the t smallest available
    numbers), and can never be larger than the sum of the t globally
    LARGEST. So:
        min_cumulative(t) = start_offset + sum(t smallest edges in W)
        max_cumulative(t) = start_offset + sum(t largest edges in W)
    are, respectively, a valid LOWER and UPPER bound on the true arrival
    time at position t for every possible tour. A position t is therefore
    PROVABLY infeasible for window (earliest, latest) if
    min_cumulative(t) > latest (even in the best case, you arrive too
    late) or max_cumulative(t) < earliest (even in the worst case, you
    arrive too early). Both min_cumulative and max_cumulative are
    non-decreasing in t (adding one more edge never decreases a sum of
    non-negative weights), so the infeasible-too-late positions form a
    contiguous suffix and the infeasible-too-early positions form a
    contiguous prefix — the feasible set in between is therefore always
    one contiguous [t_min, t_max] range (never a "gap" of feasible
    positions with an infeasible one in the middle), which is what makes
    a single (t_min, t_max) pair a complete, correct description of it.

    Raises ValueError if no position is even possibly feasible (the window
    can provably never be satisfied by any tour over this W) — reported
    plainly rather than silently clamped to something misleading.
    """
    earliest, latest = window
    if earliest > latest:
        raise ValueError(f"window earliest ({earliest}) must be <= latest ({latest}).")

    n = W.shape[0]
    edges = _sorted_edges(W)  # ascending; len == n*(n-1)/2
    min_cumulative = [start_offset + sum(edges[:t]) for t in range(n)]
    max_cumulative = [start_offset + sum(sorted(edges, reverse=True)[:t]) for t in range(n)]

    feasible = [
        t for t in range(n)
        if min_cumulative[t] <= latest and max_cumulative[t] >= earliest
    ]
    if not feasible:
        raise ValueError(
            f"Window ({earliest}, {latest}) is provably infeasible for this instance — even in the "
            f"best/worst case, no tour position could land inside it (checked against every possible "
            f"prefix-edge-sum bound, not just one candidate tour)."
        )
    return min(feasible), max(feasible)


def compute_arrival_schedule(
    tour_or_path: list[int], W: np.ndarray, start_offset: float = 0.0,
) -> list[dict]:
    """The REAL cumulative arrival time at every stop of an already-solved
    route (open path OR closed tour — both are just a sequence here, no
    wraparound leg included, matching how a delivery run's own clock
    doesn't "arrive back at the start" as a new event). Position 0's
    arrival time is `start_offset` itself (no travel needed to be at the
    first stop). Independent of solve_quantum_inspired/qubo_tsp entirely —
    this is a standalone, checkable computation over `tour_or_path` + `W`.
    """
    schedule = []
    t = start_offset
    for pos, waypoint in enumerate(tour_or_path):
        if pos > 0:
            t += float(W[tour_or_path[pos - 1], waypoint])
        schedule.append({"position": pos, "waypoint_index": waypoint, "arrival_time": round(t, 2)})
    return schedule


def check_time_windows(schedule: list[dict], time_windows: dict[int, tuple[float, float]]) -> list[dict]:
    """Check a computed arrival schedule (from compute_arrival_schedule)
    against real clock-time windows and report, per requested waypoint,
    whether it's actually satisfied — the ground truth this whole module
    exists to check, as opposed to the provably-safe-but-not-sufficient
    position pruning in derive_position_window."""
    arrival_by_waypoint = {entry["waypoint_index"]: entry["arrival_time"] for entry in schedule}
    results = []
    for waypoint, (earliest, latest) in time_windows.items():
        arrival = arrival_by_waypoint.get(waypoint)
        satisfied = arrival is not None and earliest <= arrival <= latest
        slack = None
        if arrival is not None:
            slack = round(min(arrival - earliest, latest - arrival), 2)
        results.append({
            "waypoint_index": waypoint,
            "window": (earliest, latest),
            "arrival_time": arrival,
            "satisfied": satisfied,
            "slack_minutes": slack,
        })
    return results


def solve_with_time_windows(
    W: np.ndarray, time_windows: dict[int, tuple[float, float]], start_offset: float = 0.0,
    cyclic: bool = True, start_idx: int = 0, end_idx: int = 0, num_reads: int = 500, seed: int = 1,
) -> dict:
    """Solve a routing instance with real clock-time windows requested on
    one or more waypoints — the honest, end-to-end version of this
    module's whole story:

    1. For each requested window, derive a provably-safe position range
       (derive_position_window) and pass all of them to the existing
       solver as `position_windows` — pruning positions that could never
       satisfy the window, enforced exactly like precedence.
    2. Solve (solve_quantum_inspired for `cyclic=True` closed tours,
       solve_open_path_quantum_inspired for a fixed start/end path).
    3. Compute the REAL arrival schedule of whatever tour was actually
       found, and check every requested window against it.

    Returns the solver's own result dict plus "schedule" (the real
    arrival times) and "time_window_checks" (per-waypoint satisfied/
    violated, from step 3) — so a caller always sees the checked outcome,
    never just the (weaker) pruning guarantee from step 1.
    """
    if not time_windows:
        raise ValueError("time_windows must be a non-empty {waypoint_index: (earliest, latest)} map.")

    position_windows = {
        waypoint: derive_position_window(W, window, start_offset=start_offset)
        for waypoint, window in time_windows.items()
    }

    if cyclic:
        result = solve_quantum_inspired(
            W, num_reads=num_reads, seed=seed, position_windows=position_windows,
        )
        route = result["tour"]
    else:
        result = solve_open_path_quantum_inspired(
            W, start_idx=start_idx, end_idx=end_idx, num_reads=num_reads, seed=seed,
            position_windows=position_windows,
        )
        route = result["path"]

    schedule = compute_arrival_schedule(route, W, start_offset=start_offset)
    checks = check_time_windows(schedule, time_windows)

    result["schedule"] = schedule
    result["time_window_checks"] = checks
    result["all_time_windows_satisfied"] = all(c["satisfied"] for c in checks)
    return result
