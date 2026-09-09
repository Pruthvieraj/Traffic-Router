"""
ortools_baseline.py
====================
Google OR-Tools' actual production vehicle-routing solver, used as a
credibility comparison point for the QUBO/simulated-annealing solver.

Why this exists on top of baseline.py's nearest_neighbor_2opt: that
baseline is a bespoke, hand-rolled heuristic — a fair stand-in for "what a
typical student project would ship," but not a serious industrial solver.
Beating it alone doesn't prove the QUBO approach is competitive with what
real logistics companies actually run. OR-Tools' routing library (the same
optimizer family used inside Google Maps route optimization and countless
production dispatch systems) is a genuinely strong, widely-deployed
solver, so comparing against it is a much higher bar — and, reported
honestly either way, a much more convincing data point for a judge.

This is an OPTIONAL dependency on purpose (a large native wheel with a
real install cost, unlike the rest of this project's requirements) — it is
deliberately NOT listed in requirements.txt. Everything here degrades
cleanly when it's missing: ORTOOLS_AVAILABLE is False, solve_with_ortools
raises a clear RuntimeError with the install command rather than an import
crash, and tests/benchmark.py both skip this comparison rather than
failing when it's absent. Install it with:

    pip install ortools

Honest scope: this wraps OR-Tools for the plain closed-loop TSP case only
— matching qubo_tsp.solve_quantum_inspired / baseline.nearest_neighbor_2opt
exactly, so the comparison in benchmark.py is apples-to-apples. OR-Tools
itself supports far more (fixed start/end paths, multiple vehicles with
capacity, precedence via pickup-delivery pairs, time windows — it's a full
CP-SAT-backed VRP solver) — wiring in every one of those variants here
would just re-implement half this project against a different backend
purely for benchmarking purposes, with no benefit to the actual app. The
closed-loop case is enough to honestly answer "how close is the
quantum-inspired solver to a real industrial solver on the case they both
handle."
"""

import time

import numpy as np

from qubo_tsp import tour_length

try:
    from ortools.constraint_solver import pywrapcp, routing_enums_pb2
    ORTOOLS_AVAILABLE = True
except ImportError:
    ORTOOLS_AVAILABLE = False


def solve_with_ortools(W: np.ndarray, start: int = 0, time_limit_seconds: float = 2.0) -> dict:
    """Solve the same closed-loop TSP (depot = `start`, visit every other
    row/column index exactly once, return to `start`) with Google OR-Tools'
    routing solver: PATH_CHEAPEST_ARC builds a first solution, then guided
    local search polishes it for up to `time_limit_seconds`. Returns the
    same {"tour", "cost", "wall_seconds"} shape as nearest_neighbor_2opt
    and solve_quantum_inspired, so it drops straight into benchmark.py
    alongside them.

    Raises RuntimeError with an install hint if ortools isn't available —
    see the module docstring for why it's an optional dependency.
    """
    if not ORTOOLS_AVAILABLE:
        raise RuntimeError(
            "ortools is not installed. It's an optional dependency used only for "
            "this benchmark comparison (not needed to run the app itself). "
            "Install with: pip install ortools"
        )

    t0 = time.perf_counter()
    n = W.shape[0]

    if n <= 2:
        tour = list(range(n))
        return {"tour": tour, "cost": tour_length(tour, W), "wall_seconds": time.perf_counter() - t0}

    # OR-Tools' routing solver wants integer arc costs; our matrix is float
    # minutes/seconds, so scale up and round rather than truncating away
    # real precision that would otherwise make close-cost routes look tied.
    scale = 1000
    W_int = np.rint(W * scale).astype(np.int64)

    manager = pywrapcp.RoutingIndexManager(n, 1, start)
    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return int(W_int[from_node, to_node])

    transit_callback_index = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )
    search_parameters.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )
    search_parameters.time_limit.FromSeconds(int(max(1, round(time_limit_seconds))))

    solution = routing.SolveWithParameters(search_parameters)
    wall_seconds = time.perf_counter() - t0

    if solution is None:
        # Shouldn't happen on a complete graph (every pair is reachable),
        # but fail loudly rather than silently returning a bogus tour.
        raise RuntimeError("OR-Tools returned no solution for this matrix.")

    tour = []
    index = routing.Start(0)
    while not routing.IsEnd(index):
        tour.append(manager.IndexToNode(index))
        index = solution.Value(routing.NextVar(index))

    return {"tour": tour, "cost": tour_length(tour, W), "wall_seconds": wall_seconds}


if __name__ == "__main__":
    from city_graph import build_demo_graph
    from congestion import apply_congestion
    from distance_matrix import build_travel_time_matrix

    if not ORTOOLS_AVAILABLE:
        print("ortools not installed — run: pip install ortools")
    else:
        G = build_demo_graph()
        Gc = apply_congestion(G, hour=18.5)
        waypoints = ["Majestic", "Indiranagar", "Koramangala", "HSR Layout", "Silk Board", "Jayanagar"]
        W, _ = build_travel_time_matrix(Gc, waypoints)

        result = solve_with_ortools(W, time_limit_seconds=2.0)
        print(f"OR-Tools: {result['cost']:.1f} min in {result['wall_seconds']*1000:.1f} ms")
