"""
explain.py
==========
Route explainability / constraint attribution — turning a solved route from
"here's a list of stops" into "here's why it looks like this": which leg
costs the most, whether each business rule is actually satisfied and where,
and what enforcing a precedence constraint really cost versus not having it
at all.

Deliberately built on top of the existing, already-tested solvers and result
shapes (qubo_tsp.solve_quantum_inspired, clustering.solve_multi_vehicle) —
this module adds NO new solver code and changes NOTHING about how a route is
computed. It only interprets a path that's already been solved (or asks the
existing solver to solve the SAME instance twice, with and without a
constraint, to measure its real cost) — the same "additive, not a rewrite"
pattern used by benchmark.py's Experiment 3 and Experiment 4.
"""

import numpy as np


def explain_path(
    path: list[int], W: np.ndarray, waypoint_names: list[str] | None = None,
    precedence: list[tuple[int, int]] | None = None,
) -> dict:
    """Break down one already-solved path (open path OR a vehicle's closed
    loop [depot, ...stops..., depot] — both are just a sequence of legs,
    no wraparound assumed since a closed loop already repeats its first
    index at the end) into:

    - "legs": per-leg cost and share of the total, in visiting order.
    - "total_cost": sum of every leg (matches qubo_tsp.tour_length /
      open_path_length on this same path+matrix — recomputed independently
      here rather than trusted from the solver, so this function is a
      standalone check, not just a pretty-printer of a number it was handed).
    - "bottleneck_leg": the single most expensive leg — the direct answer
      to "why is this route so long," since one bad leg is often most of
      the story.
    - "precedence_checks": for each (u, v) rule, whether u actually comes
      before v in `path` and at which positions — makes "the rule is
      satisfied" a checkable fact about this specific route, not a claim
      about the solver in general.

    `waypoint_names` (optional) are used purely for display ("from"/"to"
    strings); the numeric "from_index"/"to_index" are always included so
    this works with or without names.
    """
    if len(path) < 2:
        raise ValueError("path must have at least 2 stops to have any legs.")

    def _name(idx):
        return waypoint_names[idx] if waypoint_names is not None else idx

    edges = list(zip(path[:-1], path[1:]))
    costs = [float(W[a, b]) for a, b in edges]
    total_cost = sum(costs)

    legs = []
    for (a, b), cost in zip(edges, costs):
        legs.append({
            "from_index": a,
            "to_index": b,
            "from": _name(a),
            "to": _name(b),
            "cost": round(cost, 2),
            "pct_of_total": round(cost / total_cost * 100, 1) if total_cost > 0 else 0.0,
        })

    bottleneck_leg = max(legs, key=lambda leg: leg["cost"]) if legs else None

    precedence_checks = []
    if precedence:
        position = {city: idx for idx, city in enumerate(path)}
        for u, v in precedence:
            pos_u, pos_v = position.get(u), position.get(v)
            satisfied = pos_u is not None and pos_v is not None and pos_u < pos_v
            precedence_checks.append({
                "rule": f"{_name(u)} before {_name(v)}",
                "u_index": u,
                "v_index": v,
                "satisfied": satisfied,
                "u_position": pos_u,
                "v_position": pos_v,
            })

    return {
        "legs": legs,
        "total_cost": round(total_cost, 2),
        "bottleneck_leg": bottleneck_leg,
        "precedence_checks": precedence_checks,
    }


def explain_precedence_impact(
    W: np.ndarray, precedence: list[tuple[int, int]], num_reads: int = 400, seed: int = 1,
) -> dict:
    """Solve the SAME closed-loop instance twice — once with no
    constraints, once with `precedence` enforced — and report the real cost
    of that specific rule on this specific instance. This is the
    per-instance, on-demand version of what benchmark.py's Experiment 2
    measures in aggregate across many random trials: here it answers "what
    did THIS rule cost ME," not "what does a rule like this cost on
    average."

    Both solves use qubo_tsp.solve_quantum_inspired unchanged — this
    function adds no solver logic of its own, only the before/after
    comparison and the resulting percentage.
    """
    from qubo_tsp import solve_quantum_inspired

    if not precedence:
        raise ValueError("precedence must be a non-empty list of (u, v) pairs.")

    without = solve_quantum_inspired(W, num_reads=num_reads, seed=seed)
    with_constraint = solve_quantum_inspired(W, num_reads=num_reads, seed=seed, precedence=precedence)

    extra_cost = with_constraint["cost"] - without["cost"]
    extra_pct = (extra_cost / without["cost"] * 100) if without["cost"] > 0 else 0.0

    return {
        "precedence": list(precedence),
        "tour_without_constraint": without["tour"],
        "cost_without_constraint": round(without["cost"], 2),
        "tour_with_constraint": with_constraint["tour"],
        "cost_with_constraint": round(with_constraint["cost"], 2),
        "extra_cost": round(extra_cost, 2),
        "extra_cost_pct": round(extra_pct, 1),
    }


def explain_open_path_precedence_impact(
    W: np.ndarray, start_idx: int, end_idx: int, precedence: list[tuple[int, int]],
    method: str = "quantum", num_reads: int = 400, seed: int = 1,
) -> dict:
    """The open-path analogue of explain_precedence_impact (above), for the
    fixed-start/fixed-end routes /api/solve actually solves — the click-
    router UI's precedence panel — rather than the closed-loop TSP
    explain_precedence_impact was originally written for. Solves the SAME
    open-path instance twice — once with no precedence at all, once with
    `precedence` enforced — and reports the real extra cost THIS specific
    rule adds to THIS specific route, on THIS specific matrix.

    `method="classical"` uses the same nearest-neighbor + 2-opt (-with-
    repair) baseline /api/solve itself would use for that method; anything
    else uses the quantum-inspired QUBO solver — same method contract as
    clustering.solve_open_path_scalable. Like explain_precedence_impact,
    this adds no solver logic of its own, only the before/after comparison.
    """
    from qubo_tsp import solve_open_path_quantum_inspired
    from baseline import nearest_neighbor_2opt_open_path, nearest_neighbor_2opt_open_path_with_precedence_repair

    if not precedence:
        raise ValueError("precedence must be a non-empty list of (u, v) pairs.")

    if method == "classical":
        without = nearest_neighbor_2opt_open_path(W, start_idx, end_idx)
        with_constraint = nearest_neighbor_2opt_open_path_with_precedence_repair(W, start_idx, end_idx, precedence)
    else:
        without = solve_open_path_quantum_inspired(W, start_idx, end_idx, num_reads=num_reads, seed=seed)
        with_constraint = solve_open_path_quantum_inspired(
            W, start_idx, end_idx, num_reads=num_reads, seed=seed, precedence=precedence,
        )

    extra_cost = with_constraint["cost"] - without["cost"]
    extra_pct = (extra_cost / without["cost"] * 100) if without["cost"] > 0 else 0.0

    return {
        "precedence": list(precedence),
        "path_without_constraint": without["path"],
        "cost_without_constraint": round(without["cost"], 2),
        "path_with_constraint": with_constraint["path"],
        "cost_with_constraint": round(with_constraint["cost"], 2),
        "extra_cost": round(extra_cost, 2),
        "extra_cost_pct": round(extra_pct, 1),
    }


def explain_fleet(
    result: dict, W: np.ndarray, waypoint_names: list[str] | None = None,
    demands: dict[int, float] | None = None, vehicle_capacity: float | None = None,
    precedence: list[tuple[int, int]] | None = None,
) -> dict:
    """Per-vehicle explanation of a clustering.solve_multi_vehicle() result:
    each vehicle's own explain_path() breakdown, plus (when `demands` +
    `vehicle_capacity` were used for the solve) how much capacity headroom
    that vehicle has left, and (when `precedence` was used) which vehicle
    owns the rule and whether it's satisfied on that vehicle's own route.

    Takes the already-computed `result` (as returned by solve_multi_vehicle)
    rather than re-solving — this is pure interpretation of an existing
    result, same as explain_path.
    """
    vehicles_out = []
    for veh in result["vehicles"]:
        path = veh["path"]
        explanation = explain_path(path, W, waypoint_names=waypoint_names, precedence=None)

        capacity_margin = None
        capacity_margin_pct = None
        if demands is not None and vehicle_capacity is not None and veh.get("demand") is not None:
            capacity_margin = round(vehicle_capacity - veh["demand"], 2)
            capacity_margin_pct = round(capacity_margin / vehicle_capacity * 100, 1) if vehicle_capacity > 0 else None

        applicable_precedence = []
        if precedence:
            stops_on_vehicle = set(path)
            for u, v in precedence:
                if u in stops_on_vehicle and v in stops_on_vehicle:
                    position = {city: idx for idx, city in enumerate(path)}
                    applicable_precedence.append({
                        "rule": f"{waypoint_names[u] if waypoint_names else u} before "
                                f"{waypoint_names[v] if waypoint_names else v}",
                        "u_index": u, "v_index": v,
                        "satisfied": position[u] < position[v],
                        "u_position": position[u], "v_position": position[v],
                    })

        vehicles_out.append({
            "vehicle": veh["vehicle"],
            "path": path,
            "legs": explanation["legs"],
            "total_cost": explanation["total_cost"],
            "bottleneck_leg": explanation["bottleneck_leg"],
            "demand": veh.get("demand"),
            "capacity_margin": capacity_margin,
            "capacity_margin_pct": capacity_margin_pct,
            "precedence_checks": applicable_precedence,
        })

    return {
        "vehicles": vehicles_out,
        "total_cost": round(result["total_cost"], 2),
        "n_vehicles": result["n_vehicles"],
    }
