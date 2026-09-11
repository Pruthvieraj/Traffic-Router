"""Tests for src/explain.py — route explainability / constraint
attribution. This module interprets already-solved routes (or asks the
existing solver to solve the same instance twice for a before/after
comparison); it adds no new solver logic, so these tests check the
interpretation is correct against hand-computable or independently
recomputed values, not against a black box."""

import numpy as np
import pytest

from explain import explain_fleet, explain_open_path_precedence_impact, explain_path, explain_precedence_impact
from qubo_tsp import open_path_length, solve_open_path_quantum_inspired, solve_quantum_inspired, tour_length
from clustering import solve_multi_vehicle
from baseline import nearest_neighbor_2opt_open_path, nearest_neighbor_2opt_open_path_with_precedence_repair


def _random_matrix(n, seed):
    rng = np.random.default_rng(seed)
    pts = rng.uniform(0, 100, size=(n, 2))
    return np.linalg.norm(pts[:, None, :] - pts[None, :, :], axis=-1)


# ---------- explain_path ----------

def test_explain_path_total_matches_independently_computed_cost():
    W = _random_matrix(6, seed=1)
    path = [0, 2, 4, 1, 3, 5, 0]
    result = explain_path(path, W)
    expected = sum(W[path[i], path[i + 1]] for i in range(len(path) - 1))
    assert result["total_cost"] == pytest.approx(expected, abs=0.01)


def test_explain_path_legs_sum_to_total_and_percentages_sum_to_100():
    W = _random_matrix(6, seed=2)
    path = [0, 1, 2, 3, 4, 5, 0]
    result = explain_path(path, W)
    assert sum(leg["cost"] for leg in result["legs"]) == pytest.approx(result["total_cost"], abs=0.05)
    assert sum(leg["pct_of_total"] for leg in result["legs"]) == pytest.approx(100.0, abs=0.5)


def test_explain_path_bottleneck_is_the_actual_max_cost_leg():
    W = _random_matrix(7, seed=3)
    path = [0, 1, 2, 3, 4, 5, 6, 0]
    result = explain_path(path, W)
    assert result["bottleneck_leg"]["cost"] == max(leg["cost"] for leg in result["legs"])


def test_explain_path_uses_waypoint_names_when_given():
    W = _random_matrix(4, seed=4)
    names = ["A", "B", "C", "D"]
    result = explain_path([0, 1, 2, 3, 0], W, waypoint_names=names)
    assert result["legs"][0]["from"] == "A"
    assert result["legs"][0]["to"] == "B"


def test_explain_path_precedence_check_reports_satisfied_and_positions():
    W = _random_matrix(5, seed=5)
    path = [0, 1, 2, 3, 4]  # open path, 0 before 4 by position
    result = explain_path(path, W, precedence=[(0, 4), (4, 0)])
    checks = {c["rule"]: c for c in result["precedence_checks"]}
    ok = [c for c in result["precedence_checks"] if c["u_index"] == 0 and c["v_index"] == 4][0]
    bad = [c for c in result["precedence_checks"] if c["u_index"] == 4 and c["v_index"] == 0][0]
    assert ok["satisfied"] is True
    assert ok["u_position"] == 0 and ok["v_position"] == 4
    assert bad["satisfied"] is False


def test_explain_path_rejects_a_path_with_fewer_than_two_stops():
    W = _random_matrix(3, seed=6)
    with pytest.raises(ValueError):
        explain_path([0], W)


# ---------- explain_precedence_impact ----------

def test_explain_precedence_impact_matches_solver_costs_exactly():
    W = _random_matrix(7, seed=11)
    precedence = [(1, 5)]
    impact = explain_precedence_impact(W, precedence, num_reads=300, seed=2)

    without = solve_quantum_inspired(W, num_reads=300, seed=2)
    with_c = solve_quantum_inspired(W, num_reads=300, seed=2, precedence=precedence)

    assert impact["cost_without_constraint"] == pytest.approx(without["cost"], abs=0.01)
    assert impact["cost_with_constraint"] == pytest.approx(with_c["cost"], abs=0.01)
    assert impact["extra_cost"] == pytest.approx(with_c["cost"] - without["cost"], abs=0.01)


def test_explain_precedence_impact_extra_cost_is_never_negative():
    """The unconstrained solve is a superset of tours the constrained solve
    can pick from, so (barring solver noise beyond a small tolerance) the
    constrained cost should not be meaningfully cheaper than the
    unconstrained one."""
    W = _random_matrix(6, seed=21)
    impact = explain_precedence_impact(W, [(2, 4)], num_reads=500, seed=3)
    assert impact["extra_cost"] >= -1.0  # small solver-noise tolerance


def test_explain_precedence_impact_rejects_empty_precedence():
    W = _random_matrix(5, seed=1)
    with pytest.raises(ValueError):
        explain_precedence_impact(W, [])


# ---------- explain_open_path_precedence_impact (fixed-start/fixed-end —
# what the click-router UI's /api/solve actually solves, unlike
# explain_precedence_impact above which is closed-loop-only) ----------

def test_explain_open_path_precedence_impact_matches_solver_costs_exactly_quantum():
    W = _random_matrix(8, seed=31)
    start_idx, end_idx = 0, 7
    precedence = [(2, 5)]
    impact = explain_open_path_precedence_impact(W, start_idx, end_idx, precedence, method="quantum", num_reads=300, seed=2)

    without = solve_open_path_quantum_inspired(W, start_idx, end_idx, num_reads=300, seed=2)
    with_c = solve_open_path_quantum_inspired(W, start_idx, end_idx, num_reads=300, seed=2, precedence=precedence)

    assert impact["cost_without_constraint"] == pytest.approx(without["cost"], abs=0.01)
    assert impact["cost_with_constraint"] == pytest.approx(with_c["cost"], abs=0.01)
    assert impact["extra_cost"] == pytest.approx(with_c["cost"] - without["cost"], abs=0.01)
    assert impact["path_with_constraint"][0] == start_idx
    assert impact["path_with_constraint"][-1] == end_idx


def test_explain_open_path_precedence_impact_matches_solver_costs_exactly_classical():
    W = _random_matrix(7, seed=32)
    start_idx, end_idx = 0, 6
    precedence = [(1, 4)]
    impact = explain_open_path_precedence_impact(W, start_idx, end_idx, precedence, method="classical")

    without = nearest_neighbor_2opt_open_path(W, start_idx, end_idx)
    with_c = nearest_neighbor_2opt_open_path_with_precedence_repair(W, start_idx, end_idx, precedence)

    assert impact["cost_without_constraint"] == pytest.approx(without["cost"], abs=0.01)
    assert impact["cost_with_constraint"] == pytest.approx(with_c["cost"], abs=0.01)


def test_explain_open_path_precedence_impact_extra_cost_is_never_meaningfully_negative():
    W = _random_matrix(7, seed=33)
    impact = explain_open_path_precedence_impact(W, 0, 6, [(2, 4)], method="quantum", num_reads=500, seed=3)
    assert impact["extra_cost"] >= -1.0  # small solver-noise tolerance, same bound as the closed-loop test above


def test_explain_open_path_precedence_impact_rejects_empty_precedence():
    W = _random_matrix(5, seed=1)
    with pytest.raises(ValueError):
        explain_open_path_precedence_impact(W, 0, 4, [])


# ---------- explain_fleet ----------

def test_explain_fleet_per_vehicle_costs_sum_to_result_total():
    W = _random_matrix(9, seed=31)
    depot_idx = 0
    stop_indices = list(range(1, 9))
    result = solve_multi_vehicle(W, depot_idx, stop_indices, 3, method="classical")
    explanation = explain_fleet(result, W)
    summed = sum(v["total_cost"] for v in explanation["vehicles"])
    assert summed == pytest.approx(explanation["total_cost"], abs=0.1)


def test_explain_fleet_reports_capacity_margin_when_demands_given():
    W = _random_matrix(8, seed=41)
    depot_idx = 0
    stop_indices = list(range(1, 8))
    demands = {i: 10.0 for i in stop_indices}
    vehicle_capacity = 30.0
    result = solve_multi_vehicle(
        W, depot_idx, stop_indices, 3, method="classical",
        demands=demands, vehicle_capacity=vehicle_capacity,
    )
    explanation = explain_fleet(result, W, demands=demands, vehicle_capacity=vehicle_capacity)
    for v in explanation["vehicles"]:
        assert v["capacity_margin"] is not None
        assert v["capacity_margin"] == pytest.approx(vehicle_capacity - v["demand"], abs=0.01)
        assert v["capacity_margin"] >= -1e-6  # solve_multi_vehicle already guarantees this


def test_explain_fleet_precedence_checks_only_appear_on_owning_vehicle():
    W = _random_matrix(9, seed=51)
    depot_idx = 0
    stop_indices = list(range(1, 9))
    precedence = None
    # Find a precedence pair that lands on the same vehicle, same pattern
    # used by benchmark.py's Experiment 3.
    result = None
    for u in stop_indices:
        for v in stop_indices:
            if u == v:
                continue
            try:
                result = solve_multi_vehicle(
                    W, depot_idx, stop_indices, 3, method="classical", precedence=[(u, v)],
                )
                precedence = [(u, v)]
                break
            except ValueError:
                continue
        if precedence:
            break
    assert precedence is not None, "expected at least one applicable precedence pair"

    explanation = explain_fleet(result, W, precedence=precedence)
    owning_vehicles = [v for v in explanation["vehicles"] if v["precedence_checks"]]
    assert len(owning_vehicles) == 1
    assert owning_vehicles[0]["precedence_checks"][0]["satisfied"] is True
