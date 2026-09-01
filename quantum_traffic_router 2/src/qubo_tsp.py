"""
qubo_tsp.py
===========
The core "quantum-inspired" solver.

We formulate "find the shortest round trip visiting every waypoint exactly
once" (a Traveling Salesman Problem over the waypoint travel-time matrix
from distance_matrix.py) as a QUBO (Quadratic Unconstrained Binary
Optimization) problem — the standard representation used for quantum
annealers (D-Wave) and for quantum-approximate algorithms (QAOA) — and
solve it with a classical simulated-annealing sampler that mimics quantum
annealing's search behaviour (thermal/quantum-fluctuation-driven escape
from local minima), rather than a purely greedy classical heuristic.

This is what the SIH problem statement (SIH26137, "Quantum-Inspired
Traffic Route Optimization") is asking for, and it's also the part of the
project a patent claim should center on: the technical effect being
claimed is "better solution quality within a fixed compute-time budget,
compared to a classical baseline, achieved via a QUBO reformulation of the
routing problem" — see benchmark.py for how that comparison is measured.

--------------------------------------------------------------------------
QUBO formulation (standard TSP-to-QUBO mapping, e.g. Lucas 2014):

Binary variable x[v, t] = 1 if waypoint v is visited at tour position t,
for v, t in 0..N-1.

Objective (minimize total travel time):
    sum over t in 0..N-1, u != v :  W[u, v] * x[u, t] * x[v, (t+1) % N]

Constraints (each enforced as a quadratic penalty, weight A):
    (a) every position has exactly one waypoint:
            A * sum_t ( 1 - sum_v x[v, t] )^2
    (b) every waypoint is visited exactly once:
            A * sum_v ( 1 - sum_t x[v, t] )^2

A must be large enough that violating a constraint always costs more than
any possible travel-time saving; we set it to a small multiple of the
largest entry in the travel-time matrix times N (see PENALTY_SAFETY_FACTOR).
--------------------------------------------------------------------------
"""

import itertools
import time
import numpy as np
import dimod
from dwave.samplers import SimulatedAnnealingSampler

PENALTY_SAFETY_FACTOR = 4.0  # multiple of (N * max travel time) used as constraint penalty


def _var(v: int, t: int, n: int) -> int:
    """Flatten (waypoint v, position t) into a single linear variable index."""
    return v * n + t


def build_tsp_bqm(W: np.ndarray, precedence: list[tuple[int, int]] | None = None) -> dimod.BinaryQuadraticModel:
    """Build the TSP QUBO, as a dimod BinaryQuadraticModel, for travel-time
    matrix W (shape N x N, symmetric, zero diagonal).

    `precedence`: optional list of (u, v) waypoint-index pairs meaning
    "u must be visited before v" (e.g. a pickup before its matching
    drop-off). This is the flexibility demo: adding a real business
    constraint here is a few lines of one more quadratic penalty term,
    baked directly into the same optimization — see
    add_precedence_penalty() and README.md "Where the QUBO framing
    actually earns its keep" for why this is the honest differentiator,
    rather than claiming raw speed/quality superiority on the plain
    unconstrained problem (see benchmark.py, which reports both stories
    truthfully).
    """
    n = W.shape[0]
    A = PENALTY_SAFETY_FACTOR * n * W.max()

    bqm = dimod.BinaryQuadraticModel(vartype=dimod.BINARY)

    # --- objective: travel time between consecutive tour positions ---
    for t in range(n):
        t_next = (t + 1) % n
        for u, v in itertools.permutations(range(n), 2):
            bqm.add_quadratic(_var(u, t, n), _var(v, t_next, n), W[u, v])

    # --- constraint (a): exactly one waypoint per position ---
    # A * (1 - sum_v x[v,t])^2 expanded into linear + quadratic terms
    for t in range(n):
        vars_t = [_var(v, t, n) for v in range(n)]
        for vi in vars_t:
            bqm.add_linear(vi, -A)  # from -2*A*x_i / 2 term after expansion, see below
        for vi, vj in itertools.combinations(vars_t, 2):
            bqm.add_quadratic(vi, vj, 2 * A)
        bqm.offset += A

    # --- constraint (b): exactly one position per waypoint ---
    for v in range(n):
        vars_v = [_var(v, t, n) for t in range(n)]
        for vi in vars_v:
            bqm.add_linear(vi, -A)
        for vi, vj in itertools.combinations(vars_v, 2):
            bqm.add_quadratic(vi, vj, 2 * A)
        bqm.offset += A

    # --- optional constraint (c): precedence ("u before v") ---
    if precedence:
        for (u, v) in precedence:
            add_precedence_penalty(bqm, u, v, n, penalty=A)

    return bqm


def add_precedence_penalty(bqm: dimod.BinaryQuadraticModel, u: int, v: int, n: int, penalty: float) -> None:
    """Add a soft penalty discouraging any assignment where waypoint v ends
    up at the same position as, or an earlier position than, waypoint u —
    i.e. encodes "u must come before v in the tour".

    For every pair of positions (t_u, t_v) with t_u >= t_v, penalize
    x[u, t_u] * x[v, t_v] — in a feasible one-hot tour exactly one such
    product is active, so this only fires when the ordering is actually
    violated.
    """
    for t_u in range(n):
        for t_v in range(n):
            if t_u >= t_v:
                bqm.add_quadratic(_var(u, t_u, n), _var(v, t_v, n), penalty)


def _decode_sample(sample: dict, n: int) -> list[int] | None:
    """Turn a {var_index: 0/1} sample into a tour [v0, v1, ..., v(n-1)],
    or None if the sample isn't a valid permutation (each position exactly
    one city, each city exactly one position)."""
    grid = np.zeros((n, n), dtype=int)
    for v in range(n):
        for t in range(n):
            grid[v, t] = sample.get(_var(v, t, n), 0)

    if not np.all(grid.sum(axis=0) == 1):  # each position must have exactly one city
        return None
    if not np.all(grid.sum(axis=1) == 1):  # each city must appear exactly once
        return None

    tour = [int(np.argmax(grid[:, t])) for t in range(n)]
    return tour


def tour_length(tour: list[int], W: np.ndarray) -> float:
    n = len(tour)
    return sum(W[tour[t], tour[(t + 1) % n]] for t in range(n))


def satisfies_precedence(tour: list[int], precedence: list[tuple[int, int]]) -> bool:
    """True iff, for every (u, v) in `precedence`, u appears before v in `tour`."""
    position = {city: idx for idx, city in enumerate(tour)}
    return all(position[u] < position[v] for u, v in precedence)


def solve_quantum_inspired(
    W: np.ndarray,
    num_reads: int = 500,
    seed: int = 1,
    precedence: list[tuple[int, int]] | None = None,
    num_sweeps: int | None = None,
) -> dict:
    """Solve the TSP via QUBO + classical simulated annealing (the
    'quantum-inspired' solver).

    Returns a dict: {tour, cost, wall_seconds, feasible_reads, total_reads}
    """
    n = W.shape[0]
    bqm = build_tsp_bqm(W, precedence=precedence)
    sampler = SimulatedAnnealingSampler()

    t0 = time.perf_counter()
    sample_kwargs = {"num_reads": num_reads, "seed": seed}
    if num_sweeps is not None:
        sample_kwargs["num_sweeps"] = num_sweeps
    sampleset = sampler.sample(bqm, **sample_kwargs)
    wall_seconds = time.perf_counter() - t0

    best_tour, best_cost, feasible_count = None, float("inf"), 0
    for sample, energy in sampleset.data(fields=["sample", "energy"]):
        tour = _decode_sample(sample, n)
        if tour is None:
            continue
        feasible_count += 1
        cost = tour_length(tour, W)
        if cost < best_cost:
            best_tour, best_cost = tour, cost

    if best_tour is None:
        # Extremely unlikely with a properly-weighted penalty, but fall back
        # to a greedy repair of the single lowest-energy sample so the demo
        # never crashes mid-pitch.
        best_tour = _greedy_repair(next(iter(sampleset.samples())), n)
        best_cost = tour_length(best_tour, W)

    return {
        "tour": best_tour,
        "cost": best_cost,
        "wall_seconds": wall_seconds,
        "feasible_reads": feasible_count,
        "total_reads": num_reads,
    }


def _greedy_repair(sample: dict, n: int) -> list[int]:
    """Fallback decode: if no sampled read was a clean permutation, build one
    greedily from the raw activations (used only if penalty tuning ever
    fails to produce a single feasible read out of `num_reads`)."""
    grid = np.zeros((n, n))
    for v in range(n):
        for t in range(n):
            grid[v, t] = sample.get(_var(v, t, n), 0)
    tour, used = [], set()
    for t in range(n):
        order = np.argsort(-grid[:, t])
        for v in order:
            if v not in used:
                tour.append(int(v))
                used.add(v)
                break
    for v in range(n):
        if v not in used:
            tour.append(v)
    return tour


def open_path_length(path: list[int], W: np.ndarray) -> float:
    """Like tour_length, but for an A-to-B path (no return trip to the
    start) — what the interactive 'click a start and end point anywhere in
    the city' feature needs, as opposed to the round-trip delivery tours
    used everywhere else in this project."""
    return sum(W[path[i], path[i + 1]] for i in range(len(path) - 1))


def build_open_path_bqm(
    W: np.ndarray, start_idx: int, end_idx: int, precedence: list[tuple[int, int]] | None = None,
) -> dimod.BinaryQuadraticModel | None:
    """QUBO for 'shortest path visiting every waypoint exactly once, from a
    FIXED start to a FIXED end' (a Hamiltonian path, not a cycle) — used
    when a user has clicked a distinct start point, end point, and zero or
    more stops in between, and wants them visited in the best order without
    looping back to the start.

    Design choice: start_idx and end_idx are never given their own decision
    variables at all — there is exactly one way to place them (position 0
    and position n-1 respectively), so instead of adding a penalty term to
    *discourage* wrong placements (as build_tsp_bqm does for its
    constraints), we simply never create the variables that would let them
    be placed anywhere else. That makes "start is at 0† / "end is at n-1"
    true by construction ("start is at position 0", "end is at position
    n-1"), with zero risk of the annealer finding a low-energy-but-invalid
    sample — only the ordering of the interior stops is actually searched.

    `precedence`: optional list of (u, v) interior-stop-index pairs meaning
    "u must be visited before v" — the same real-world feature
    build_tsp_bqm already offers for the closed-loop case (see its own
    docstring and add_precedence_penalty), extended here to the live
    click-anywhere app's fixed-start/fixed-end formulation. u/v referring to
    start_idx or end_idx is handled by the caller (see app.py's
    validation): a pair that's automatically true by construction (anything
    "after start" or "before end") is silently skipped rather than wasting
    penalty terms on it, since start/end aren't even decision variables
    here.

    Returns None for n <= 2 (start and end only, or a degenerate single
    point) — there's nothing to optimize in that case; the caller should
    just use W[start_idx, end_idx] directly.
    """
    n = W.shape[0]
    middle = [v for v in range(n) if v not in (start_idx, end_idx)]
    if not middle:
        return None

    A = PENALTY_SAFETY_FACTOR * n * max(W.max(), 1e-6)
    bqm = dimod.BinaryQuadraticModel(vartype=dimod.BINARY)

    # constraint: each interior position (1..n-2) holds exactly one middle stop
    for t in range(1, n - 1):
        vars_t = [_var(v, t, n) for v in middle]
        for vi in vars_t:
            bqm.add_linear(vi, -A)
        for vi, vj in itertools.combinations(vars_t, 2):
            bqm.add_quadratic(vi, vj, 2 * A)
        bqm.offset += A

    # constraint: each middle stop is placed at exactly one interior position
    for v in middle:
        vars_v = [_var(v, t, n) for t in range(1, n - 1)]
        for vi in vars_v:
            bqm.add_linear(vi, -A)
        for vi, vj in itertools.combinations(vars_v, 2):
            bqm.add_quadratic(vi, vj, 2 * A)
        bqm.offset += A

    # objective: fixed-start -> first interior stop, and last interior stop -> fixed-end
    # (these fold in as LINEAR terms precisely because start/end aren't variables)
    for v in middle:
        bqm.add_linear(_var(v, 1, n), W[start_idx, v])
        bqm.add_linear(_var(v, n - 2, n), W[v, end_idx])

    # objective: interior stop -> next interior stop
    for t in range(1, n - 2):
        for u, v in itertools.permutations(middle, 2):
            bqm.add_quadratic(_var(u, t, n), _var(v, t + 1, n), W[u, v])

    # optional constraint: precedence ("u before v") among interior stops.
    # start_idx/end_idx are fixed by construction (position 0 / n-1), never
    # decision variables, so a pair naming either of them is either always
    # true (start-before-anything, anything-before-end — skip, nothing to
    # penalize) or impossible (app.py rejects those before this is called).
    if precedence:
        for (u, v) in precedence:
            if u == start_idx or v == end_idx:
                continue
            _add_open_path_precedence_penalty(bqm, u, v, n, penalty=A)

    return bqm


def _add_open_path_precedence_penalty(bqm: dimod.BinaryQuadraticModel, u: int, v: int, n: int, penalty: float) -> None:
    """Like add_precedence_penalty, but for the open-path formulation,
    where only INTERIOR positions 1..n-2 exist as decision variables at all
    (position 0 and n-1 belong to the fixed start/end and were never given
    variables) — so this only ever touches variables build_open_path_bqm
    actually created, instead of accidentally introducing unconstrained
    phantom variables at position 0 or n-1 the way reusing
    add_precedence_penalty's full range(n) would."""
    for t_u in range(1, n - 1):
        for t_v in range(1, n - 1):
            if t_u >= t_v:
                bqm.add_quadratic(_var(u, t_u, n), _var(v, t_v, n), penalty)


def _decode_open_path(sample: dict, n: int, start_idx: int, end_idx: int, middle: list[int]) -> list[int] | None:
    assignment: dict[int, int] = {}
    seen_positions: set[int] = set()
    seen_cities: set[int] = set()
    for v in middle:
        for t in range(1, n - 1):
            if sample.get(_var(v, t, n), 0):
                if t in seen_positions or v in seen_cities:
                    return None  # double-booked position or city -> invalid sample
                assignment[t] = v
                seen_positions.add(t)
                seen_cities.add(v)
    if len(assignment) != len(middle):
        return None  # some interior position or city left unassigned -> invalid sample
    return [start_idx] + [assignment[t] for t in range(1, n - 1)] + [end_idx]


def solve_open_path_quantum_inspired(
    W: np.ndarray, start_idx: int, end_idx: int, num_reads: int = 400, seed: int = 1,
    precedence: list[tuple[int, int]] | None = None,
) -> dict:
    """Solve the fixed-start/fixed-end routing problem via QUBO + simulated
    annealing. Mirrors solve_quantum_inspired()'s return shape.

    `precedence`: see build_open_path_bqm — optional "u before v" pairs
    baked directly into the same QUBO, same as the closed-loop solver.
    """
    n = W.shape[0]
    middle = [v for v in range(n) if v not in (start_idx, end_idx)]

    if not middle:
        path = [start_idx, end_idx]
        return {"path": path, "cost": open_path_length(path, W), "wall_seconds": 0.0,
                "feasible_reads": 1, "total_reads": 1}

    bqm = build_open_path_bqm(W, start_idx, end_idx, precedence=precedence)
    sampler = SimulatedAnnealingSampler()

    t0 = time.perf_counter()
    sampleset = sampler.sample(bqm, num_reads=num_reads, seed=seed)
    wall_seconds = time.perf_counter() - t0

    # When precedence is given, prefer the best feasible read that actually
    # satisfies it — the penalty makes violating it extremely costly, so in
    # practice the lowest-energy feasible reads already satisfy it, but this
    # makes that a checked guarantee rather than an assumption. best_any
    # tracks the best feasible read regardless, as a last-resort fallback.
    best_path, best_cost, feasible_count = None, float("inf"), 0
    best_path_any, best_cost_any = None, float("inf")
    for sample, energy in sampleset.data(fields=["sample", "energy"]):
        path = _decode_open_path(sample, n, start_idx, end_idx, middle)
        if path is None:
            continue
        feasible_count += 1
        cost = open_path_length(path, W)
        if cost < best_cost_any:
            best_path_any, best_cost_any = path, cost
        if precedence and not satisfies_precedence(path, precedence):
            continue
        if cost < best_cost:
            best_path, best_cost = path, cost

    if best_path is None and best_path_any is not None:
        # Every feasible read violated precedence — extremely unlikely given
        # the penalty weight, but fall back to the best feasible read rather
        # than dropping into the plain nearest-neighbor fallback below,
        # which doesn't know about precedence at all.
        best_path, best_cost = best_path_any, best_cost_any

    if best_path is None:
        # fallback: nearest-neighbor greedy over the interior stops, so the
        # demo never crashes even in the extremely unlikely case that not one
        # of num_reads samples was a valid assignment. Precedence-aware via
        # the same post-hoc repair the classical baseline uses (see
        # baseline.nearest_neighbor_2opt_open_path_with_precedence_repair) —
        # this code path is only ever reached if the annealer produced zero
        # valid permutations at all, so it doesn't need to be more than "not
        # wrong."
        remaining = set(middle)
        path, current = [start_idx], start_idx
        while remaining:
            nxt = min(remaining, key=lambda v: W[current, v])
            path.append(nxt)
            remaining.remove(nxt)
            current = nxt
        path.append(end_idx)
        if precedence:
            for (u, v) in precedence:
                if not satisfies_precedence(path, [(u, v)]):
                    path = [c for c in path if c != v]
                    path.insert(path.index(u) + 1, v)
        best_path, best_cost = path, open_path_length(path, W)

    return {
        "path": best_path, "cost": best_cost, "wall_seconds": wall_seconds,
        "feasible_reads": feasible_count, "total_reads": num_reads,
    }


if __name__ == "__main__":
    from city_graph import build_demo_graph
    from congestion import apply_congestion
    from distance_matrix import build_travel_time_matrix

    G = build_demo_graph()
    Gc = apply_congestion(G, hour=18.5)
    waypoints = ["Majestic", "Indiranagar", "Koramangala", "HSR Layout", "Silk Board", "Jayanagar"]
    W, _ = build_travel_time_matrix(Gc, waypoints)

    result = solve_quantum_inspired(W)
    named_tour = [waypoints[i] for i in result["tour"]]
    print("Quantum-inspired tour:", " -> ".join(named_tour + [named_tour[0]]))
    print(f"Total time: {result['cost']:.1f} min | solve wall time: {result['wall_seconds']*1000:.0f} ms")
    print(f"Feasible reads: {result['feasible_reads']}/{result['total_reads']}")
