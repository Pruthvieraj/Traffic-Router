"""Tests for the optional OR-Tools comparison baseline. ortools is a large
native dependency that's deliberately not in requirements.txt (see
src/ortools_baseline.py's docstring), so this whole file skips cleanly —
not a failure — when it isn't installed, exactly like tests/test_layout.py
does for Playwright and tests/test_openapi_spec.py does for pyyaml."""

import numpy as np
import pytest

ortools_baseline = pytest.importorskip("ortools_baseline", reason="ortools not installed")

from baseline import brute_force_optimal
from qubo_tsp import tour_length

pytestmark = pytest.mark.skipif(
    not ortools_baseline.ORTOOLS_AVAILABLE,
    reason="ortools import succeeded but native solver unavailable",
)


def _random_matrix(n, seed):
    rng = np.random.default_rng(seed)
    pts = rng.uniform(0, 100, size=(n, 2))
    return np.linalg.norm(pts[:, None, :] - pts[None, :, :], axis=-1)


@pytest.mark.parametrize("seed", range(5))
def test_ortools_produces_a_valid_tour_starting_at_the_depot(seed):
    n = 7
    W = _random_matrix(n, seed)
    result = ortools_baseline.solve_with_ortools(W, start=0, time_limit_seconds=1)
    assert sorted(result["tour"]) == list(range(n))
    assert result["tour"][0] == 0
    assert result["cost"] == pytest.approx(tour_length(result["tour"], W))


@pytest.mark.parametrize("seed", range(5))
def test_ortools_matches_true_optimal_on_small_instances(seed):
    """OR-Tools is a serious solver — on instances small enough that brute
    force is still tractable, it should find the actual optimum, not just
    something plausible."""
    n = 8
    W = _random_matrix(n, seed)
    opt = brute_force_optimal(W)
    result = ortools_baseline.solve_with_ortools(W, start=0, time_limit_seconds=2)
    assert result["cost"] == pytest.approx(opt["cost"], rel=1e-6)


def test_ortools_never_beats_the_true_optimum(seed=3):
    """Sanity bound: whatever OR-Tools finds can't cost less than the exact
    brute-force optimum — if this ever fails it means the two solvers are
    scoring the tour inconsistently (e.g. a units/scaling bug), not that
    OR-Tools 'won'."""
    n = 7
    W = _random_matrix(n, seed)
    opt = brute_force_optimal(W)
    result = ortools_baseline.solve_with_ortools(W, start=0, time_limit_seconds=1)
    assert result["cost"] >= opt["cost"] - 1e-6


def test_ortools_handles_the_degenerate_two_city_case():
    W = np.array([[0, 5], [5, 0]], dtype=float)
    result = ortools_baseline.solve_with_ortools(W, start=0)
    assert sorted(result["tour"]) == [0, 1]
    assert result["cost"] == pytest.approx(10.0)


def test_ortools_respects_a_nondefault_start_index():
    n = 6
    W = _random_matrix(n, seed=1)
    result = ortools_baseline.solve_with_ortools(W, start=3, time_limit_seconds=1)
    assert result["tour"][0] == 3
    assert sorted(result["tour"]) == list(range(n))


def test_missing_ortools_raises_a_clear_runtime_error(monkeypatch):
    """Simulates the 'not installed' path directly, since ortools actually
    being importable in this test environment doesn't let us exercise the
    real ImportError branch otherwise."""
    monkeypatch.setattr(ortools_baseline, "ORTOOLS_AVAILABLE", False)
    with pytest.raises(RuntimeError, match="pip install ortools"):
        ortools_baseline.solve_with_ortools(np.zeros((3, 3)))
