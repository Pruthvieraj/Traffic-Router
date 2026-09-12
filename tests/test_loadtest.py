"""Unit tests for loadtest.py's pure helper functions — matrix generation,
percentile math, and payload shapes. Deliberately does NOT spin up a real
server or make a real HTTP request: loadtest.py's whole point is to be run
by hand against a locally running app.py (see its own module docstring),
not to be part of the automated suite that runs on every push. This file
just makes sure the arithmetic and payload-building it depends on is
correct, the same way calibrate_from_uvh26.py's logic is unit-tested via
src/vehicle_density_calibration.py even though the CLI script itself isn't
run in CI.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import loadtest  # noqa: E402


def test_make_matrix_is_symmetric_with_zero_diagonal():
    m = loadtest._make_matrix(6)
    n = len(m)
    assert n == 6
    for row in m:
        assert len(row) == n
    for i in range(n):
        assert m[i][i] == 0
        for j in range(n):
            assert m[i][j] == m[j][i]


def test_make_matrix_is_deterministic_for_a_given_seed():
    a = loadtest._make_matrix(5, seed=7)
    b = loadtest._make_matrix(5, seed=7)
    assert a == b


def test_make_matrix_differs_for_different_seeds():
    a = loadtest._make_matrix(5, seed=1)
    b = loadtest._make_matrix(5, seed=2)
    assert a != b


def test_make_matrix_off_diagonal_values_are_in_the_documented_range():
    m = loadtest._make_matrix(8)
    n = len(m)
    for i in range(n):
        for j in range(n):
            if i != j:
                assert 120 <= m[i][j] <= 1800


def test_solve_payload_has_the_fields_api_solve_expects():
    payload = loadtest._solve_payload(5, "quantum")
    assert payload["method"] == "quantum"
    assert payload["hour"] == 12.0
    assert len(payload["matrix"]) == 5
    assert all(len(row) == 5 for row in payload["matrix"])


def test_solve_fleet_payload_has_the_extra_fleet_fields():
    payload = loadtest._solve_fleet_payload(6, "classical", n_vehicles=3)
    assert payload["n_vehicles"] == 3
    assert payload["depot_index"] == 0
    assert payload["method"] == "classical"
    assert len(payload["matrix"]) == 6


def test_percentile_matches_known_values_on_a_simple_list():
    values = [10, 20, 30, 40, 50]
    assert loadtest._percentile(values, 0) == 10
    assert loadtest._percentile(values, 50) == 30
    assert loadtest._percentile(values, 100) == 50


def test_percentile_interpolates_between_points():
    values = [0, 100]
    # halfway between the two points
    assert loadtest._percentile(values, 50) == 50


def test_percentile_of_empty_list_is_nan():
    result = loadtest._percentile([], 50)
    assert result != result  # NaN != NaN is the standard float check


def test_percentile_does_not_care_about_input_order():
    assert loadtest._percentile([30, 10, 20], 50) == loadtest._percentile([10, 20, 30], 50)
