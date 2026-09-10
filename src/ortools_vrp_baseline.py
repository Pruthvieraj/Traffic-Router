"""
ortools_vrp_baseline.py
========================
Google OR-Tools' actual capacitated Vehicle Routing Problem (CVRP) solver,
used as a credibility comparison point for `clustering.solve_multi_vehicle`
in FLEET mode specifically — the single-vehicle comparison already exists
in `ortools_baseline.py`, but that one only handles plain closed-loop TSP,
not a multi-vehicle capacity constraint.

Why this exists on top of `ortools_baseline.py`: `solve_multi_vehicle`'s
own docstring is upfront that it is NOT a full capacitated VRP solver —
the fleet split (clustering) and each vehicle's own route are optimized
SEPARATELY, not jointly, and there's no cross-vehicle search for a better
overall split once vehicles are assigned. OR-Tools' routing library, when
given a capacity dimension across a shared vehicle pool, genuinely does
solve the split and the routing jointly (it can move a stop from one
vehicle's route to another's mid-search if that lowers total cost). That
makes it a real, honest "how far is a cluster-first/route-second demand
split from what a real joint solver would find" comparison point — a
stronger, more specific claim than the plain-TSP comparison in
`ortools_baseline.py` gives for FLEET mode specifically.

Same optional-dependency pattern as ortools_baseline.py: NOT in
requirements.txt, degrades cleanly (ORTOOLS_AVAILABLE False,
solve_cvrp_with_ortools raises a clear RuntimeError with the install
command) when ortools isn't installed. Install with:

    pip install ortools

Honest scope: this wraps OR-Tools for the DEMAND-CAPACITY case only
(mirrors solve_multi_vehicle's `demands`/`vehicle_capacity` path, not its
`max_stops_per_vehicle` stop-count path) and does NOT attempt precedence
— OR-Tools supports precedence via pickup-delivery pair constraints, but
wiring that in here would mean re-deriving a second, parallel precedence
implementation purely for benchmarking, with no benefit to the live app.
Capacity alone is enough to honestly answer "how close is the
cluster-first/route-second demand split to what a real joint capacitated
VRP solver finds," which is the specific gap Experiment 3 already
measures for THIS project's own capacity-only vs. composed comparison.
"""

import time

import numpy as np

try:
    from ortools.constraint_solver import pywrapcp, routing_enums_pb2
    ORTOOLS_AVAILABLE = True
except ImportError:
    ORTOOLS_AVAILABLE = False


def solve_cvrp_with_ortools(
    W: np.ndarray, depot_idx: int, stop_indices: list[int], n_vehicles: int,
    demands: dict[int, float], vehicle_capacity: float, time_limit_seconds: float = 5.0,
) -> dict:
    """Solve a real capacitated VRP — one shared depot (`depot_idx`), every
    stop in `stop_indices` visited exactly once by exactly one of up to
    `n_vehicles` vehicles, each vehicle's TOTAL demand capped at
    `vehicle_capacity` — with Google OR-Tools' routing solver (capacity
    dimension + guided local search), and the split and per-vehicle routing
    decided JOINTLY, not in two separate steps.

    Returns the SAME shape `clustering.solve_multi_vehicle` does —
    {"vehicles": [{"vehicle", "path", "cost", "stops", "demand"}, ...],
    "total_cost", "n_vehicles", "wall_seconds"} — so the two can be
    compared/reported side by side with no extra glue code.
    "n_vehicles" in the return is how many OR-Tools actually USED (routes
    with at least one stop), which can be fewer than the `n_vehicles` pool
    offered to it if a tighter split was cheaper overall — that's real
    information, not a bug, and is reported as such.

    Raises RuntimeError with an install hint if ortools isn't available,
    and ValueError if demands/vehicle_capacity can't be satisfied by ANY
    number of vehicles up to `n_vehicles` (mirroring solve_multi_vehicle's
    own up-front validation) — same honest-failure philosophy as the rest
    of this project: no silent capacity violation, no silently dropped
    stop.
    """
    if not ORTOOLS_AVAILABLE:
        raise RuntimeError(
            "ortools is not installed. It's an optional dependency used only for "
            "this benchmark comparison (not needed to run the app itself). "
            "Install with: pip install ortools"
        )

    t0 = time.perf_counter()
    stop_indices = list(stop_indices)
    if not stop_indices:
        return {"vehicles": [], "total_cost": 0.0, "n_vehicles": 0, "wall_seconds": time.perf_counter() - t0}

    weights = {int(k): float(v) for k, v in demands.items()}
    missing = [idx for idx in stop_indices if idx not in weights]
    if missing:
        raise ValueError(f"demands is missing an entry for stop index(es): {missing}.")
    too_heavy = [idx for idx in stop_indices if weights[idx] > vehicle_capacity]
    if too_heavy:
        raise ValueError(
            f"Stop(s) {too_heavy} have demand greater than vehicle_capacity on their own — "
            "no single vehicle could ever carry them, regardless of fleet size."
        )
    total_demand = sum(weights[idx] for idx in stop_indices)
    min_vehicles_needed = int(-(-total_demand // vehicle_capacity))  # ceil division
    if min_vehicles_needed > n_vehicles:
        raise ValueError(
            f"vehicle_capacity={vehicle_capacity} needs at least {min_vehicles_needed} vehicles for "
            f"total demand {total_demand}, but n_vehicles={n_vehicles} was offered — raise n_vehicles."
        )

    # Local index space: 0 = depot, 1..k = stop_indices in order. OR-Tools'
    # RoutingIndexManager always wants a dense 0..n-1 node space, and this
    # project's global waypoint indices aren't guaranteed contiguous/0-based.
    local_nodes = [depot_idx] + stop_indices
    n_local = len(local_nodes)
    W_local = W[np.ix_(local_nodes, local_nodes)]

    scale = 1000  # same integer-scaling reasoning as ortools_baseline.py
    W_int = np.rint(W_local * scale).astype(np.int64)
    demand_int = [0] + [int(round(weights[idx])) for idx in stop_indices]
    capacity_int = int(round(vehicle_capacity))

    manager = pywrapcp.RoutingIndexManager(n_local, n_vehicles, 0)
    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_index, to_index):
        return int(W_int[manager.IndexToNode(from_index), manager.IndexToNode(to_index)])

    transit_callback_index = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    def demand_callback(from_index):
        return demand_int[manager.IndexToNode(from_index)]

    demand_callback_index = routing.RegisterUnaryTransitCallback(demand_callback)
    routing.AddDimensionWithVehicleCapacity(
        demand_callback_index, 0, [capacity_int] * n_vehicles, True, "Capacity",
    )

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
        # Capacity was checked feasible above, so a real production solver
        # not finding ANY solution within the time limit on an instance
        # this small would be surprising — fail loudly rather than
        # returning something that looks like a result but isn't one.
        raise RuntimeError(
            "OR-Tools found no feasible CVRP solution within the time limit "
            f"({time_limit_seconds}s) — try a longer time_limit_seconds."
        )

    vehicles = []
    total_cost = 0.0
    for v in range(n_vehicles):
        index = routing.Start(v)
        local_path = [manager.IndexToNode(index)]
        route_cost = 0.0
        while not routing.IsEnd(index):
            next_index = solution.Value(routing.NextVar(index))
            route_cost += W_local[manager.IndexToNode(index), manager.IndexToNode(next_index)]
            index = next_index
            local_path.append(manager.IndexToNode(index))
        if len(local_path) <= 2:
            continue  # this vehicle's route is depot -> depot: never used, not reported
        global_path = [local_nodes[i] for i in local_path]
        stops = global_path[1:-1]
        vehicles.append({
            "vehicle": len(vehicles),
            "path": global_path,
            "cost": route_cost,
            "stops": stops,
            "demand": sum(weights[idx] for idx in stops),
        })
        total_cost += route_cost

    return {
        "vehicles": vehicles, "total_cost": total_cost,
        "n_vehicles": len(vehicles), "wall_seconds": wall_seconds,
    }


if __name__ == "__main__":
    from city_graph import build_demo_graph
    from congestion import apply_congestion
    from distance_matrix import build_travel_time_matrix

    if not ORTOOLS_AVAILABLE:
        print("ortools not installed — run: pip install ortools")
    else:
        G = build_demo_graph()
        Gc = apply_congestion(G, hour=18.5)
        waypoints = [
            "Majestic", "Indiranagar", "Koramangala", "HSR Layout", "Silk Board",
            "Jayanagar", "Whitefield", "Electronic City",
        ]
        W, _ = build_travel_time_matrix(Gc, waypoints)
        demands = {i: 10.0 for i in range(1, len(waypoints))}
        result = solve_cvrp_with_ortools(
            W, depot_idx=0, stop_indices=list(range(1, len(waypoints))),
            n_vehicles=3, demands=demands, vehicle_capacity=30.0, time_limit_seconds=5.0,
        )
        print(f"OR-Tools CVRP: {result['n_vehicles']} vehicles used, "
              f"total cost {result['total_cost']:.1f} min, "
              f"in {result['wall_seconds']*1000:.1f} ms")
