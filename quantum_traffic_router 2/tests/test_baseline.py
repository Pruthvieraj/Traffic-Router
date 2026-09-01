import numpy as np
import pytest

from baseline import (
    brute_force_optimal,
    nearest_neighbor_2opt,
    nearest_neighbor_2opt_open_path,
    nearest_neighbor_2opt_open_path_with_precedence_repair,
)
from qubo_tsp import open_path_length, satisfies_precedence


def _random_matrix(n, seed):
    rng = np.random.default_rng(seed)
    pts = rng.uniform(0, 100, size=(n, 2))
    return np.linalg.norm(pts[:, None, :] - pts[None, :, :], axis=-1)


@pytest.mark.parametrize("seed", range(5))
def test_nn_2opt_produces_valid_tour(seed):
    W = _random_matrix(7, seed)
    result = nearest_neighbor_2opt(W)
    assert sorted(result["tour"]) == list(range(7))
    assert result["cost"] > 0


@pytest.mark.parametrize("seed", range(8))
def test_open_path_baseline_is_a_valid_permutation(seed):
    n = 6
    W = _random_matrix(n, seed)
    result = nearest_neighbor_2opt_open_path(W, start_idx=0, end_idx=n - 1)
    assert result["path"][0] == 0
    assert result["path"][-1] == n - 1
    assert sorted(result["path"]) == list(range(n))
    assert result["cost"] == pytest.approx(open_path_length(result["path"], W))


@pytest.mark.parametrize("seed", range(8))
def test_open_path_precedence_repair_produces_a_valid_permutation_that_satisfies_it(seed):
    n = 6
    W = _random_matrix(n, seed)
    precedence = [(2, 4)]
    result = nearest_neighbor_2opt_open_path_with_precedence_repair(W, 0, n - 1, precedence)
    assert result["path"][0] == 0
    assert result["path"][-1] == n - 1
    assert sorted(result["path"]) == list(range(n))
    assert satisfies_precedence(result["path"], precedence)
    assert result["still_violates_precedence"] is False


def test_brute_force_finds_a_valid_tour():
    W = np.array([
        [0, 2, 9, 10],
        [1, 0, 6, 4],
        [15, 7, 0, 8],
        [6, 3, 12, 0],
    ], dtype=float)
    result = brute_force_optimal(W)
    assert sorted(result["tour"]) == [0, 1, 2, 3]
    assert result["tour"][0] == 0
