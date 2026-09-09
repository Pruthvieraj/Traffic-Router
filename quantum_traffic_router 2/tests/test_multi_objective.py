"""Tests for multi-objective routing support:
- qubo_tsp.combine_objectives, and the `objectives=` parameter on
  solve_quantum_inspired / solve_open_path_quantum_inspired.
- distance_matrix.build_distance_matrix — the real second objective (road
  distance, a fuel/emissions proxy) that makes this a genuine trade-off
  rather than two names for the same number.

Backward compatibility is the load-bearing property here: every existing
caller passes W positionally and nothing else, so W must keep working
exactly as before, and `objectives=[(W, 1.0)]` must be provably identical
to `W=W` (not just "close"), since that equivalence is the whole reason no
change was needed to build_tsp_bqm/build_open_path_bqm themselves."""

import numpy as np
import pytest

from qubo_tsp import (
    combine_objectives,
    open_path_length,
    solve_open_path_quantum_inspired,
    solve_quantum_inspired,
    tour_length,
)
from city_graph import build_city_graph
from congestion import apply_congestion
from distance_matrix import build_distance_matrix, build_travel_time_matrix


def _random_matrix(n, seed):
    rng = np.random.default_rng(seed)
    pts = rng.uniform(0, 100, size=(n, 2))
    return np.linalg.norm(pts[:, None, :] - pts[None, :, :], axis=-1)


# ---------- combine_objectives ----------

def test_combine_objectives_single_matrix_full_weight_is_identity():
    W = _random_matrix(5, seed=1)
    combined = combine_objectives([(W, 1.0)])
    assert np.array_equal(combined, W)


def test_combine_objectives_weighted_sum():
    A = np.array([[0, 1], [1, 0]], dtype=float)
    B = np.array([[0, 3], [3, 0]], dtype=float)
    combined = combine_objectives([(A, 0.25), (B, 0.75)])
    assert np.allclose(combined, 0.25 * A + 0.75 * B)


def test_combine_objectives_rejects_empty_list():
    with pytest.raises(ValueError):
        combine_objectives([])


# ---------- solve_quantum_inspired multi-objective ----------

def test_solve_quantum_inspired_rejects_both_w_and_objectives():
    W = _random_matrix(5, seed=1)
    with pytest.raises(ValueError):
        solve_quantum_inspired(W=W, objectives=[(W, 1.0)])


def test_solve_quantum_inspired_rejects_neither_w_nor_objectives():
    with pytest.raises(ValueError):
        solve_quantum_inspired()


def test_solve_quantum_inspired_single_objective_is_exactly_equivalent_to_plain_w():
    """objectives=[(W, 1.0)] must be provably identical to W=W, not just
    approximately close — same BQM, same seed, same tour, same cost. This
    is the backward-compatibility guarantee the whole design rests on."""
    W = _random_matrix(6, seed=3)
    plain = solve_quantum_inspired(W=W, num_reads=200, seed=5)
    multi = solve_quantum_inspired(objectives=[(W, 1.0)], num_reads=200, seed=5)
    assert plain["tour"] == multi["tour"]
    assert plain["cost"] == multi["cost"]


def test_solve_quantum_inspired_objective_breakdown_matches_real_tour_length():
    n = 6
    W1 = _random_matrix(n, seed=1)
    W2 = _random_matrix(n, seed=2)
    result = solve_quantum_inspired(objectives=[(W1, 0.5), (W2, 0.5)], num_reads=300, seed=7)
    assert "objective_breakdown" in result
    assert len(result["objective_breakdown"]) == 2
    assert result["objective_breakdown"][0] == pytest.approx(tour_length(result["tour"], W1))
    assert result["objective_breakdown"][1] == pytest.approx(tour_length(result["tour"], W2))


def test_solve_quantum_inspired_extreme_weight_recovers_single_objective_exactly():
    """Weighting one objective at 1.0 and the other at 0.0 must recover
    EXACTLY that single objective's own solve — the clearest possible
    demonstration this is a genuine trade-off knob, not a cosmetic second
    number bolted onto one real objective."""
    n = 6
    W1 = _random_matrix(n, seed=11)
    W2 = _random_matrix(n, seed=12)
    only_w1 = solve_quantum_inspired(W=W1, num_reads=400, seed=1)

    favor_w1 = solve_quantum_inspired(objectives=[(W1, 1.0), (W2, 0.0)], num_reads=400, seed=1)

    assert favor_w1["tour"] == only_w1["tour"]
    assert favor_w1["objective_breakdown"][0] == pytest.approx(only_w1["cost"])


# ---------- solve_open_path_quantum_inspired multi-objective ----------

def test_open_path_solver_multi_objective_breakdown():
    n = 6
    W1 = _random_matrix(n, seed=21)
    W2 = _random_matrix(n, seed=22)
    result = solve_open_path_quantum_inspired(
        start_idx=0, end_idx=n - 1, objectives=[(W1, 0.6), (W2, 0.4)], num_reads=300, seed=9,
    )
    assert result["path"][0] == 0
    assert result["path"][-1] == n - 1
    assert result["objective_breakdown"][0] == pytest.approx(open_path_length(result["path"], W1))
    assert result["objective_breakdown"][1] == pytest.approx(open_path_length(result["path"], W2))


def test_open_path_solver_rejects_both_and_neither():
    W = _random_matrix(5, seed=1)
    with pytest.raises(ValueError):
        solve_open_path_quantum_inspired(W=W, start_idx=0, end_idx=4, objectives=[(W, 1.0)])
    with pytest.raises(ValueError):
        solve_open_path_quantum_inspired(start_idx=0, end_idx=4)


# ---------- distance_matrix.build_distance_matrix (the real second objective) ----------

def test_build_distance_matrix_shape_symmetry_and_nonnegativity():
    G = build_city_graph("Bengaluru")
    Gc = apply_congestion(G, hour=18.5, seed=42)
    waypoints = ["Majestic", "Indiranagar", "Koramangala", "HSR Layout"]
    W_time, _ = build_travel_time_matrix(Gc, waypoints)
    W_dist = build_distance_matrix(Gc, waypoints)
    assert W_dist.shape == W_time.shape
    assert np.allclose(W_dist, W_dist.T)
    assert np.all(np.diag(W_dist) == 0)
    assert np.all(W_dist >= 0)


def test_build_distance_matrix_is_a_genuinely_different_objective_from_time():
    """The whole point of this second matrix: it must not be a scaled copy
    of the time matrix (a constant ratio everywhere), or "multi-objective"
    would be two names for the same number, not a real trade-off."""
    G = build_city_graph("Bengaluru")
    Gc = apply_congestion(G, hour=18.5, seed=42)
    waypoints = ["Majestic", "Indiranagar", "Koramangala", "HSR Layout", "Silk Board", "Jayanagar"]
    W_time, _ = build_travel_time_matrix(Gc, waypoints)
    W_dist = build_distance_matrix(Gc, waypoints)
    iu = np.triu_indices(len(waypoints), k=1)
    ratios = W_dist[iu] / W_time[iu]
    assert ratios.std() > 1e-3  # not a constant multiple


def test_build_distance_matrix_rejects_unknown_waypoint():
    G = build_city_graph("Bengaluru")
    Gc = apply_congestion(G, hour=18.5, seed=42)
    with pytest.raises(ValueError):
        build_distance_matrix(Gc, ["Majestic", "Not A Real Place"])
