"""Tests for src/qpu_solver.py — real D-Wave QPU as a first-class solver
`method`, alongside "quantum" (simulated annealing) and "classical".

None of these tests need a D-Wave Leap account or API token — see
qpu_solver.py's own module docstring for why: the WIRING (decoding,
best-feasible-read selection, precedence/position-window filtering, error
handling, the size cap) is verified either against this sandbox's real
"no token configured" failure (a genuine, unmocked failure — there really
is no token here) or with a lightweight injected stand-in sampler
(dwave-samplers' own SimulatedAnnealingSampler, which already speaks the
same dimod .sample()/SampleSet interface a real QPU chain does) standing
in for actual hardware access."""

import numpy as np
import pytest
from dwave.samplers import SimulatedAnnealingSampler

from qpu_solver import (
    MAX_QPU_INTERIOR_STOPS,
    QPU_AVAILABLE,
    _build_sampler,
    solve_open_path_on_qpu,
    solve_tsp_on_qpu,
)
from qubo_tsp import (
    open_path_length,
    satisfies_position_windows,
    satisfies_precedence,
    tour_length,
)


def _random_matrix(n, seed):
    rng = np.random.default_rng(seed)
    pts = rng.uniform(0, 100, size=(n, 2))
    return np.linalg.norm(pts[:, None, :] - pts[None, :, :], axis=-1)


# ---------- honest, real (unmocked) no-credentials behavior ----------

def test_dwave_system_sdk_is_actually_installed_in_this_environment():
    """qpu_solver.py's whole design rests on QPU_AVAILABLE correctly
    reflecting whether dwave-system is importable — this environment
    happens to have it installed (a dependency of other project scripts),
    so this locks in that the detection is right, not just plausible."""
    assert QPU_AVAILABLE is True


def test_build_sampler_fails_clearly_with_no_configured_token():
    """This sandbox genuinely has no D-Wave Leap API token configured —
    _build_sampler() must fail with a clear, real error (not silently
    return something broken), and it does, unmocked: this is the actual
    failure a live app deployment without credentials would hit too."""
    with pytest.raises(Exception) as exc_info:
        _build_sampler()
    # dwave-system's own real message for "no token" — checked loosely
    # (substring) since the exact wording is the SDK's, not this project's.
    assert "token" in str(exc_info.value).lower() or "auth" in str(exc_info.value).lower()


# ---------- wiring correctness, via an injected stand-in sampler ----------

@pytest.fixture
def fake_sampler():
    """A real dimod-compatible sampler (classical, instant, needs no
    hardware or network) standing in for `EmbeddingComposite(DWaveSampler())`
    — it returns a genuine dimod SampleSet with the same .data(fields=...)
    interface qpu_solver.py's decode loop relies on, so this tests the
    REAL decode/selection logic, not a hand-rolled fake."""
    return SimulatedAnnealingSampler()


def test_solve_tsp_on_qpu_returns_a_valid_tour_and_expected_fields(fake_sampler):
    n = 6
    W = _random_matrix(n, seed=1)
    result = solve_tsp_on_qpu(W, num_reads=200, sampler=fake_sampler)
    assert sorted(result["tour"]) == list(range(n))
    assert result["cost"] == pytest.approx(tour_length(result["tour"], W), abs=0.01)
    assert result["method"] == "qpu"
    # no real hardware chain was used, so hardware-only diagnostics are
    # honestly None, never fabricated
    assert result["chip_id"] is None
    assert result["qpu_access_time_us"] is None


def test_solve_open_path_on_qpu_returns_a_valid_path_and_expected_fields(fake_sampler):
    n = 6
    W = _random_matrix(n, seed=2)
    result = solve_open_path_on_qpu(W, start_idx=0, end_idx=n - 1, num_reads=200, sampler=fake_sampler)
    assert result["path"][0] == 0
    assert result["path"][-1] == n - 1
    assert sorted(result["path"]) == list(range(n))
    assert result["cost"] == pytest.approx(open_path_length(result["path"], W), abs=0.01)


def test_solve_tsp_on_qpu_respects_precedence(fake_sampler):
    n = 6
    W = _random_matrix(n, seed=3)
    precedence = [(1, 4)]
    result = solve_tsp_on_qpu(W, precedence=precedence, num_reads=400, sampler=fake_sampler)
    assert satisfies_precedence(result["tour"], precedence)


def test_solve_tsp_on_qpu_respects_position_windows(fake_sampler):
    n = 6
    W = _random_matrix(n, seed=4)
    position_windows = {2: (0, 1)}
    result = solve_tsp_on_qpu(W, position_windows=position_windows, num_reads=400, sampler=fake_sampler)
    assert satisfies_position_windows(result["tour"], position_windows)


def test_solve_open_path_on_qpu_respects_precedence(fake_sampler):
    n = 6
    W = _random_matrix(n, seed=5)
    precedence = [(2, 4)]
    result = solve_open_path_on_qpu(
        W, start_idx=0, end_idx=n - 1, precedence=precedence, num_reads=400, sampler=fake_sampler,
    )
    assert satisfies_precedence(result["path"], precedence)


def test_solve_open_path_on_qpu_handles_no_interior_stops(fake_sampler):
    """start and end only — nothing to submit to hardware at all, must
    short-circuit rather than build a degenerate empty BQM."""
    W = _random_matrix(2, seed=6)
    result = solve_open_path_on_qpu(W, start_idx=0, end_idx=1, sampler=fake_sampler)
    assert result["path"] == [0, 1]
    assert result["feasible_reads"] == 1


# ---------- the size cap ----------

def test_solve_tsp_on_qpu_rejects_instances_above_the_size_cap(fake_sampler):
    n = MAX_QPU_INTERIOR_STOPS + 5
    W = _random_matrix(n, seed=7)
    with pytest.raises(ValueError, match="capped at"):
        solve_tsp_on_qpu(W, sampler=fake_sampler)


def test_solve_open_path_on_qpu_rejects_instances_above_the_size_cap(fake_sampler):
    n = MAX_QPU_INTERIOR_STOPS + 5
    W = _random_matrix(n, seed=8)
    with pytest.raises(ValueError, match="capped at"):
        solve_open_path_on_qpu(W, start_idx=0, end_idx=n - 1, sampler=fake_sampler)


def test_solve_tsp_on_qpu_accepts_instances_at_exactly_the_size_cap(fake_sampler):
    n = MAX_QPU_INTERIOR_STOPS + 1  # closed tour: n waypoints, no fixed start/end to exclude
    W = _random_matrix(n, seed=9)
    result = solve_tsp_on_qpu(W, num_reads=200, sampler=fake_sampler)
    assert sorted(result["tour"]) == list(range(n))
