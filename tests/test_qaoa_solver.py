"""Tests for the optional QAOA comparison solver. qiskit is a sizeable
dependency deliberately not in requirements.txt (see src/qaoa_solver.py's
docstring for why), so this whole file skips cleanly — not a failure —
when it isn't installed, exactly like tests/test_ortools_baseline.py does
for ortools.

These tests deliberately stay at 1-3 interior stops (4-9 qubits): that's
this module's own honestly-stated ceiling for a classical statevector
simulation (see the module docstring), and it keeps the suite fast — a
QAOA run here is a full optimization loop over many simulated circuit
evaluations, not a single call."""

import itertools

import numpy as np
import pytest

qaoa_solver = pytest.importorskip("qaoa_solver", reason="qiskit not installed")

from qubo_tsp import open_path_length

pytestmark = pytest.mark.skipif(
    not qaoa_solver.QISKIT_AVAILABLE,
    reason="qiskit import succeeded but not actually usable",
)


def _random_matrix(n, seed):
    rng = np.random.default_rng(seed)
    pts = rng.uniform(0, 100, size=(n, 2))
    return np.linalg.norm(pts[:, None, :] - pts[None, :, :], axis=-1)


def _brute_force_open_path(W, start_idx, end_idx):
    n = W.shape[0]
    middle = [v for v in range(n) if v not in (start_idx, end_idx)]
    best_path, best_cost = None, float("inf")
    for perm in itertools.permutations(middle):
        path = [start_idx, *perm, end_idx]
        cost = open_path_length(path, W)
        if cost < best_cost:
            best_path, best_cost = path, cost
    return best_path, best_cost


def test_degenerate_case_with_no_interior_stops_needs_no_qubits():
    """start and end only — nothing to optimize, so this should short-
    circuit before ever touching Qiskit, matching build_open_path_bqm's
    own None-for-n<=2 contract."""
    W = np.array([[0, 5], [5, 0]], dtype=float)
    result = qaoa_solver.solve_open_path_with_qaoa(W, start_idx=0, end_idx=1)
    assert result["num_qubits"] == 0
    assert result["valid"] is True
    assert result["path"] == [0, 1]
    assert result["cost"] == pytest.approx(5.0)


@pytest.mark.parametrize("seed", range(4))
def test_single_interior_stop_is_trivially_correct(seed):
    """Only one possible ordering exists with a single interior stop, so
    this is really testing decode/energy plumbing, not QAOA's search
    quality — a useful sanity floor before the harder 2-3 stop cases."""
    n = 3
    W = _random_matrix(n, seed)
    result = qaoa_solver.solve_open_path_with_qaoa(W, start_idx=0, end_idx=n - 1, reps=1)
    assert result["num_qubits"] == 1
    assert result["valid"] is True
    assert result["cost"] == pytest.approx(open_path_length([0, 1, 2], W))


@pytest.mark.parametrize("seed", range(6))
def test_two_interior_stops_finds_the_true_optimum(seed):
    """4 qubits, 2 possible orderings — small enough that a properly wired
    QAOA circuit (correct Ising coefficients, correct decode) should find
    the true optimum essentially every time, not just 'a valid answer'."""
    n = 4
    W = _random_matrix(n, seed)
    _, true_optimal_cost = _brute_force_open_path(W, 0, n - 1)
    result = qaoa_solver.solve_open_path_with_qaoa(W, start_idx=0, end_idx=n - 1, reps=2, maxiter=150)
    assert result["valid"] is True
    assert result["cost"] == pytest.approx(true_optimal_cost, rel=1e-6)


def test_a_valid_result_never_costs_less_than_the_true_optimum(seed=3):
    """Sanity bound, same spirit as the OR-Tools test of the same name:
    whatever QAOA returns can't beat the exact brute-force optimum — if it
    ever did, that would mean the decode/energy plumbing is inconsistent
    with open_path_length, not that QAOA 'won'."""
    n = 5
    W = _random_matrix(n, seed)
    _, true_optimal_cost = _brute_force_open_path(W, 0, n - 1)
    result = qaoa_solver.solve_open_path_with_qaoa(W, start_idx=0, end_idx=n - 1, reps=2, maxiter=150)
    if result["valid"]:
        assert result["cost"] >= true_optimal_cost - 1e-6


def test_result_shape_has_every_documented_field():
    n = 4
    W = _random_matrix(n, seed=0)
    result = qaoa_solver.solve_open_path_with_qaoa(W, start_idx=0, end_idx=n - 1, reps=1)
    assert set(result.keys()) == {"path", "cost", "valid", "wall_seconds", "num_qubits", "best_energy"}
    assert result["wall_seconds"] > 0
    assert result["num_qubits"] == 4  # (n-2)^2 for n=4


def test_missing_qiskit_raises_a_clear_runtime_error(monkeypatch):
    """Simulates the 'not installed' path directly, since qiskit actually
    being importable in this test environment doesn't let us exercise the
    real ImportError branch otherwise."""
    monkeypatch.setattr(qaoa_solver, "QISKIT_AVAILABLE", False)
    with pytest.raises(RuntimeError, match="pip install qiskit"):
        qaoa_solver.solve_open_path_with_qaoa(np.zeros((4, 4)), start_idx=0, end_idx=3)
