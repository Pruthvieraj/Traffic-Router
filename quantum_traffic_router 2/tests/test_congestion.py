import numpy as np
import pytest

from congestion import apply_congestion_to_matrix, rush_hour_multiplier


def test_rush_hour_multiplier_peaks_higher_than_offpeak():
    assert rush_hour_multiplier(18.5) > rush_hour_multiplier(3.0)
    assert rush_hour_multiplier(9.0) > rush_hour_multiplier(3.0)
    assert rush_hour_multiplier(3.0) >= 1.0  # never claims traffic is literally free-er than free-flow


def test_apply_congestion_to_matrix_is_reproducible():
    W = np.array([[0, 10, 20], [10, 0, 15], [20, 15, 0]], dtype=float)
    a = apply_congestion_to_matrix(W, hour=18.5, seed=42)
    b = apply_congestion_to_matrix(W, hour=18.5, seed=42)
    assert np.allclose(a, b)


def test_apply_congestion_to_matrix_differs_by_hour():
    W = np.array([[0, 10, 20], [10, 0, 15], [20, 15, 0]], dtype=float)
    quiet = apply_congestion_to_matrix(W, hour=3.0, seed=1)
    rush = apply_congestion_to_matrix(W, hour=18.5, seed=1)
    # rush hour should be noticeably worse on average than 3am, even with
    # per-pair noise applied
    assert rush[np.triu_indices(3, k=1)].mean() > quiet[np.triu_indices(3, k=1)].mean()


def test_apply_congestion_to_matrix_never_touches_diagonal():
    W = np.zeros((4, 4))
    Wc = apply_congestion_to_matrix(W, hour=9.0)
    assert np.all(np.diag(Wc) == 0)
