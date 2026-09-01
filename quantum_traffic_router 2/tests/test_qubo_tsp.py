"""Enforces, in CI, the correctness claims the README makes in prose —
in particular "the open-path QUBO solver was verified against
brute-force-optimal on 20 random trials." That check now runs automatically
on every change instead of having been true once and never re-checked."""

import itertools

import numpy as np
import pytest

from qubo_tsp import (
    open_path_length,
    satisfies_precedence,
    solve_open_path_quantum_inspired,
    solve_quantum_inspired,
)


def _random_matrix(n, seed):
    rng = np.random.default_rng(seed)
    pts = rng.uniform(0, 100, size=(n, 2))
    return np.linalg.norm(pts[:, None, :] - pts[None, :, :], axis=-1)


def _brute_force_open_path_cost(W, start, end):
    n = W.shape[0]
    middle = [v for v in range(n) if v not in (start, end)]
    return min(
        open_path_length([start, *perm, end], W)
        for perm in itertools.permutations(middle)
    )


@pytest.mark.parametrize("seed", range(10))
def test_open_path_solver_matches_brute_force(seed):
    n = 6
    W = _random_matrix(n, seed)
    result = solve_open_path_quantum_inspired(W, start_idx=0, end_idx=n - 1, num_reads=300, seed=seed)

    assert result["path"][0] == 0
    assert result["path"][-1] == n - 1
    assert sorted(result["path"]) == list(range(n))

    best_cost = _brute_force_open_path_cost(W, 0, n - 1)
    assert result["cost"] == pytest.approx(best_cost, abs=1e-6)


def test_open_path_length_matches_manual_sum():
    W = np.array([[0, 1, 4], [1, 0, 2], [4, 2, 0]], dtype=float)
    assert open_path_length([0, 1, 2], W) == pytest.approx(3.0)


def test_solve_open_path_trivial_two_points():
    W = np.array([[0, 5], [5, 0]], dtype=float)
    result = solve_open_path_quantum_inspired(W, 0, 1)
    assert result["path"] == [0, 1]
    assert result["cost"] == pytest.approx(5.0)


# ---------- precedence ("u before v") constraints, open-path case ----------
# The live click-anywhere app only ever solves the fixed-start/fixed-end
# (open-path) formulation, so this is the one that actually needs to honor
# a real "visit X before Y" business rule — see app.py's /api/solve and
# README.md "Where the QUBO framing actually earns its keep."

def _brute_force_open_path_cost_with_precedence(W, start, end, precedence):
    n = W.shape[0]
    middle = [v for v in range(n) if v not in (start, end)]
    best = float("inf")
    for perm in itertools.permutations(middle):
        path = [start, *perm, end]
        if not satisfies_precedence(path, precedence):
            continue
        best = min(best, open_path_length(path, W))
    return best


@pytest.mark.parametrize("seed", range(6))
def test_open_path_solver_with_precedence_matches_constrained_brute_force(seed):
    """The solved path must both (a) actually satisfy the precedence rule
    and (b) match the true optimum AMONG orderings that satisfy it — not
    just be some arbitrary feasible-but-suboptimal route that happens to
    obey the constraint."""
    n = 6
    W = _random_matrix(n, seed)
    # 2 and 4 are both interior stops (0 is start, 5 is end) — "2 before 4".
    precedence = [(2, 4)]
    result = solve_open_path_quantum_inspired(
        W, start_idx=0, end_idx=n - 1, num_reads=300, seed=seed, precedence=precedence,
    )

    assert sorted(result["path"]) == list(range(n))
    assert satisfies_precedence(result["path"], precedence)

    best_cost = _brute_force_open_path_cost_with_precedence(W, 0, n - 1, precedence)
    assert result["cost"] == pytest.approx(best_cost, abs=1e-6)


def test_precedence_naming_start_or_end_as_the_earlier_point_is_a_harmless_noop():
    """(start_idx, v) and (u, end_idx) are always true by construction —
    the solver should just work normally rather than error or waste effort
    on a constraint that can't ever be violated."""
    n = 5
    W = _random_matrix(n, seed=0)
    result = solve_open_path_quantum_inspired(
        W, start_idx=0, end_idx=n - 1, num_reads=200, seed=0,
        precedence=[(0, 2), (3, n - 1)],
    )
    assert sorted(result["path"]) == list(range(n))


@pytest.mark.parametrize("seed", range(3))
def test_closed_loop_solver_produces_valid_tour(seed):
    n = 5
    W = _random_matrix(n, seed)
    result = solve_quantum_inspired(W, num_reads=200, seed=seed)
    assert sorted(result["tour"]) == list(range(n))
    assert result["cost"] > 0
