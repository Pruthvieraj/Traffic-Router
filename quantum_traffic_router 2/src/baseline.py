"""
baseline.py
===========
Classical solvers used purely as comparison points for the QUBO/simulated-
annealing solver in qubo_tsp.py — this is what makes the "technical effect"
claim measurable rather than a vibe.

- `nearest_neighbor_2opt`: what a typical classical routing heuristic looks
  like (greedy construction + local-search polish). This is the fair
  real-world baseline — it's fast and it's what most non-quantum-inspired
  student projects would ship.
- `brute_force_optimal`: exact optimum via exhaustive search. Only tractable
  for small N (<= ~10 waypoints) — used in benchmark.py purely to compute
  "% above true optimal" for both other methods, on small problem sizes.
"""

import itertools
import time
import numpy as np

from qubo_tsp import tour_length


def nearest_neighbor_2opt(W: np.ndarray, start: int = 0) -> dict:
    """Classical baseline: greedy nearest-neighbor construction, then
    2-opt local search until no improving swap remains."""
    t0 = time.perf_counter()
    n = W.shape[0]

    # --- construction: nearest neighbor ---
    unvisited = set(range(n)) - {start}
    tour = [start]
    while unvisited:
        last = tour[-1]
        nxt = min(unvisited, key=lambda v: W[last, v])
        tour.append(nxt)
        unvisited.remove(nxt)

    # --- local search: 2-opt ---
    improved = True
    while improved:
        improved = False
        for i in range(n - 1):
            for j in range(i + 2, n):
                if i == 0 and j == n - 1:
                    continue  # would just reverse the whole tour
                a, b, c, d = tour[i], tour[i + 1], tour[j], tour[(j + 1) % n]
                before = W[a, b] + W[c, d]
                after = W[a, c] + W[b, d]
                if after < before - 1e-9:
                    tour[i + 1:j + 1] = reversed(tour[i + 1:j + 1])
                    improved = True

    wall_seconds = time.perf_counter() - t0
    return {"tour": tour, "cost": tour_length(tour, W), "wall_seconds": wall_seconds}


def nearest_neighbor_2opt_with_precedence_repair(W: np.ndarray, precedence: list[tuple[int, int]], start: int = 0) -> dict:
    """This is the honest 'what a team would actually have to bolt on' baseline
    for handling a new business rule (e.g. 'pick up before drop off') with a
    classical local-search heuristic that was never designed to know about
    such constraints.

    Runs plain nearest_neighbor_2opt (which optimizes travel time only, with
    no idea precedence exists), then checks whether the constraint happens to
    hold. If not, applies a simple repair: move the later-required city to
    just after the earlier-required one and re-run 2-opt. This is exactly
    the kind of one-off, constraint-specific patch code you'd have to keep
    writing by hand for every new rule — contrast with qubo_tsp.py, where
    the same rule is one function call (add_precedence_penalty) that composes
    with every other constraint automatically.
    """
    from qubo_tsp import satisfies_precedence

    result = nearest_neighbor_2opt(W, start=start)
    tour = result["tour"]
    repaired = False

    for (u, v) in precedence:
        if not satisfies_precedence(tour, [(u, v)]):
            repaired = True
            tour = [c for c in tour if c != v]
            insert_at = tour.index(u) + 1
            tour.insert(insert_at, v)

    result["tour"] = tour
    result["cost"] = tour_length(tour, W)
    result["repaired"] = repaired
    result["still_violates_precedence"] = not satisfies_precedence(tour, precedence)
    return result


def brute_force_optimal(W: np.ndarray) -> dict:
    """Exact optimum by trying every permutation. Only use for small N
    (cost grows as (N-1)!/2) — this is a benchmarking tool, not a production
    solver."""
    t0 = time.perf_counter()
    n = W.shape[0]
    best_tour, best_cost = None, float("inf")
    rest = list(range(1, n))  # fix city 0 as the start to cut redundant rotations
    for perm in itertools.permutations(rest):
        tour = [0] + list(perm)
        cost = tour_length(tour, W)
        if cost < best_cost:
            best_tour, best_cost = tour, cost
    wall_seconds = time.perf_counter() - t0
    return {"tour": best_tour, "cost": best_cost, "wall_seconds": wall_seconds}


def nearest_neighbor_2opt_open_path(W: np.ndarray, start_idx: int, end_idx: int) -> dict:
    """Classical comparison baseline for the fixed-start/fixed-end case
    (see qubo_tsp.solve_open_path_quantum_inspired): greedy nearest-neighbor
    construction from the start through the interior stops, then 2-opt —
    but restricted to interior swaps only, since the start and end are
    fixed requirements here, not something a generic classical heuristic
    would even know to respect without this restriction hard-coded in."""
    from qubo_tsp import open_path_length

    t0 = time.perf_counter()
    n = W.shape[0]
    middle = [v for v in range(n) if v not in (start_idx, end_idx)]

    if not middle:
        path = [start_idx, end_idx]
        return {"path": path, "cost": open_path_length(path, W), "wall_seconds": time.perf_counter() - t0}

    # construction: nearest-neighbor from start through the interior stops
    unvisited = set(middle)
    path = [start_idx]
    while unvisited:
        last = path[-1]
        nxt = min(unvisited, key=lambda v: W[last, v])
        path.append(nxt)
        unvisited.remove(nxt)
    path.append(end_idx)

    # 2-opt, restricted to the interior segment (positions 1..n-2) so the
    # fixed start/end never move
    improved = True
    while improved:
        improved = False
        for i in range(1, n - 2):
            for j in range(i + 1, n - 1):
                a, b, c, d = path[i - 1], path[i], path[j], path[(j + 1) if j + 1 < n else j]
                before = W[a, b] + W[c, d]
                after = W[a, c] + W[b, d]
                if after < before - 1e-9:
                    path[i:j + 1] = reversed(path[i:j + 1])
                    improved = True

    return {"path": path, "cost": open_path_length(path, W), "wall_seconds": time.perf_counter() - t0}


if __name__ == "__main__":
    from city_graph import build_demo_graph
    from congestion import apply_congestion
    from distance_matrix import build_travel_time_matrix

    G = build_demo_graph()
    Gc = apply_congestion(G, hour=18.5)
    waypoints = ["Majestic", "Indiranagar", "Koramangala", "HSR Layout", "Silk Board", "Jayanagar"]
    W, _ = build_travel_time_matrix(Gc, waypoints)

    nn = nearest_neighbor_2opt(W)
    opt = brute_force_optimal(W)
    print(f"Nearest-neighbor+2-opt: {nn['cost']:.1f} min in {nn['wall_seconds']*1000:.1f} ms")
    print(f"Brute-force optimal:    {opt['cost']:.1f} min in {opt['wall_seconds']*1000:.1f} ms")
