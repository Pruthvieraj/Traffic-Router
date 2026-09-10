"""Tests for the optional OR-Tools capacitated-VRP comparison baseline
(src/ortools_vrp_baseline.py). Same optional-dependency skip pattern as
tests/test_ortools_baseline.py — this whole file skips cleanly, not a
failure, when ortools isn't installed."""

import numpy as np
import pytest

ortools_vrp_baseline = pytest.importorskip("ortools_vrp_baseline", reason="ortools not installed")

from clustering import solve_multi_vehicle

pytestmark = pytest.mark.skipif(
    not ortools_vrp_baseline.ORTOOLS_AVAILABLE,
    reason="ortools import succeeded but native solver unavailable",
)


def _random_matrix(n, seed):
    rng = np.random.default_rng(seed)
    pts = rng.uniform(0, 100, size=(n, 2))
    return np.linalg.norm(pts[:, None, :] - pts[None, :, :], axis=-1)


def _route_cost(path, W):
    return sum(W[path[i], path[i + 1]] for i in range(len(path) - 1))


@pytest.mark.parametrize("seed", range(5))
def test_every_stop_visited_exactly_once_across_the_fleet(seed):
    n = 9  # depot (0) + 8 stops
    W = _random_matrix(n, seed)
    stop_indices = list(range(1, n))
    demands = {i: 10.0 for i in stop_indices}
    result = ortools_vrp_baseline.solve_cvrp_with_ortools(
        W, depot_idx=0, stop_indices=stop_indices, n_vehicles=4,
        demands=demands, vehicle_capacity=30.0, time_limit_seconds=2,
    )
    all_stops_visited = sorted(s for v in result["vehicles"] for s in v["stops"])
    assert all_stops_visited == stop_indices


@pytest.mark.parametrize("seed", range(5))
def test_capacity_is_actually_respected_on_every_vehicle(seed):
    n = 10
    W = _random_matrix(n, seed)
    stop_indices = list(range(1, n))
    rng = np.random.default_rng(seed)
    demands = {i: float(rng.integers(5, 15)) for i in stop_indices}
    capacity = 25.0
    result = ortools_vrp_baseline.solve_cvrp_with_ortools(
        W, depot_idx=0, stop_indices=stop_indices, n_vehicles=6,
        demands=demands, vehicle_capacity=capacity, time_limit_seconds=2,
    )
    for v in result["vehicles"]:
        assert v["demand"] <= capacity + 1e-6


def test_every_vehicle_path_starts_and_ends_at_the_depot():
    n = 8
    W = _random_matrix(n, seed=2)
    stop_indices = list(range(1, n))
    demands = {i: 10.0 for i in stop_indices}
    result = ortools_vrp_baseline.solve_cvrp_with_ortools(
        W, depot_idx=0, stop_indices=stop_indices, n_vehicles=3,
        demands=demands, vehicle_capacity=30.0, time_limit_seconds=2,
    )
    for v in result["vehicles"]:
        assert v["path"][0] == 0
        assert v["path"][-1] == 0


def test_reported_cost_matches_the_actual_path_cost():
    n = 8
    W = _random_matrix(n, seed=4)
    stop_indices = list(range(1, n))
    demands = {i: 10.0 for i in stop_indices}
    result = ortools_vrp_baseline.solve_cvrp_with_ortools(
        W, depot_idx=0, stop_indices=stop_indices, n_vehicles=3,
        demands=demands, vehicle_capacity=30.0, time_limit_seconds=2,
    )
    for v in result["vehicles"]:
        assert v["cost"] == pytest.approx(_route_cost(v["path"], W))
    assert result["total_cost"] == pytest.approx(sum(v["cost"] for v in result["vehicles"]))


def test_joint_ortools_solve_never_costs_more_than_this_projects_cluster_first_split():
    """The real, specific claim this module exists to check: OR-Tools
    solves the split and the routing JOINTLY, while solve_multi_vehicle
    does cluster-first/route-second — so on the same instance, a genuine
    joint solver should never do WORSE than the two-step heuristic (it can
    always fall back to reproducing the same split if nothing better
    exists). Not asserting it does BETTER on every seed — sometimes the
    two-step split is already good enough that there's no room to improve
    within OR-Tools' time budget — just that it's never a worse total."""
    n = 9
    W = _random_matrix(n, seed=7)
    stop_indices = list(range(1, n))
    demands = {i: 10.0 for i in stop_indices}
    capacity = 30.0
    n_vehicles = 4

    ours = solve_multi_vehicle(
        W, depot_idx=0, stop_indices=stop_indices, n_vehicles=n_vehicles,
        method="classical", demands=demands, vehicle_capacity=capacity,
    )
    theirs = ortools_vrp_baseline.solve_cvrp_with_ortools(
        W, depot_idx=0, stop_indices=stop_indices, n_vehicles=max(n_vehicles, ours["n_vehicles"]),
        demands=demands, vehicle_capacity=capacity, time_limit_seconds=3,
    )
    assert theirs["total_cost"] <= ours["total_cost"] + 1e-6


def test_raises_clear_error_when_capacity_cant_be_satisfied_by_the_offered_fleet():
    W = _random_matrix(5, seed=1)
    stop_indices = [1, 2, 3, 4]
    demands = {i: 20.0 for i in stop_indices}
    with pytest.raises(ValueError, match="raise n_vehicles"):
        ortools_vrp_baseline.solve_cvrp_with_ortools(
            W, depot_idx=0, stop_indices=stop_indices, n_vehicles=1,
            demands=demands, vehicle_capacity=25.0,
        )


def test_raises_clear_error_when_a_single_stop_exceeds_capacity():
    W = _random_matrix(4, seed=1)
    stop_indices = [1, 2, 3]
    demands = {1: 10.0, 2: 999.0, 3: 10.0}
    with pytest.raises(ValueError, match=r"Stop\(s\) \[2\] have demand greater than vehicle_capacity"):
        ortools_vrp_baseline.solve_cvrp_with_ortools(
            W, depot_idx=0, stop_indices=stop_indices, n_vehicles=3,
            demands=demands, vehicle_capacity=25.0,
        )


def test_missing_ortools_raises_a_clear_runtime_error(monkeypatch):
    monkeypatch.setattr(ortools_vrp_baseline, "ORTOOLS_AVAILABLE", False)
    with pytest.raises(RuntimeError, match="pip install ortools"):
        ortools_vrp_baseline.solve_cvrp_with_ortools(
            np.zeros((3, 3)), depot_idx=0, stop_indices=[1, 2], n_vehicles=1,
            demands={1: 1.0, 2: 1.0}, vehicle_capacity=10.0,
        )
