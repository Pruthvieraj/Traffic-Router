"""
qpu_solver.py
=============
A real D-Wave quantum annealer as a first-class solver `method` —
`method="qpu"` alongside this project's existing `"quantum"` (classical
simulated annealing standing in for a quantum annealer) and `"classical"`
(nearest-neighbor + 2-opt) methods, wired into the SAME public solve
functions those already go through (`clustering.solve_open_path_scalable`,
`clustering.solve_multi_vehicle`) and the SAME live app (`app.py`) — not a
one-off demo script kept off to the side. `run_on_real_quantum_hardware.py`
now calls into this module too, instead of duplicating the QPU submission
logic it originally had inline.

Every `"qpu"` call builds the IDENTICAL BQM this project already builds for
`"quantum"` (`qubo_tsp.build_tsp_bqm` / `build_open_path_bqm` — same
objective, same constraint penalties, same precedence/position-window
support) and submits it to a real chip via
`dwave.system.EmbeddingComposite(dwave.system.DWaveSampler())`, instead of
classically simulating one.

WHAT THIS NEEDS THAT NOTHING ELSE IN THIS PROJECT DOES: your own D-Wave
Leap API token from a plan that actually includes API access — see
README.md's "Real quantum hardware validation" section for the full setup
and the honest correction that free self-serve Leap signup does NOT get
you a usable token (only a paid plan or an accepted Leap Quantum LaunchPad
application does). Once you have a real token: `pip install dwave-system`,
then `export DWAVE_API_TOKEN=...` or `dwave setup`. This is NOT needed to
run main.py, app.py, or any test in this project: every solve function here
accepts an optional `sampler=` override used ONLY by
`tests/test_qpu_solver.py` to inject a lightweight stand-in with the same
`.sample(bqm, num_reads=...)` interface real D-Wave samplers expose — so
the WIRING (decoding, best-feasible-read selection, precedence/position-
window filtering, error handling) is verified without needing real
hardware access, the same way a payment integration's request-building
logic gets tested without an actual real charge. Selecting `method="qpu"`
without a configured token fails with a clear, caught error explaining
what's missing (this sandbox's own lack of a token demonstrates that exact
failure — see QPU_AVAILABLE / the ValueError text below) — it never
crashes the caller.

SIZE. A real QPU chip has a fixed, finite qubit count and a sparse
physical connectivity graph — nothing like a classical simulator's
"as many variables as fit in RAM." This project's BQM couples every
waypoint pair (a fully-connected structure), which real hardware has to
EMBED onto its sparser graph using extra physical qubits per logical
variable — embeddability isn't something this module can verify without
actual hardware access, so it enforces a conservative
`MAX_QPU_INTERIOR_STOPS` cap and raises a clear, specific error above it
rather than submitting a job likely to fail embedding (or silently burning
through a scarce, real QPU-second allotment).
"""

import os
import time

import numpy as np

from qubo_tsp import (
    _decode_open_path,
    _decode_sample,
    build_open_path_bqm,
    build_tsp_bqm,
    open_path_length,
    satisfies_position_windows,
    satisfies_precedence,
    tour_length,
)

try:
    from dwave.system import DWaveSampler, EmbeddingComposite
    QPU_AVAILABLE = True
except ImportError:
    QPU_AVAILABLE = False

# Conservative, deliberately small — see this module's own "SIZE" note
# above. Real embeddability depends on the specific chip's topology at
# solve time, which this project has no way to check without hardware
# access, so this cap is a documented, honest guess at "small enough to be
# worth trying," not a verified guarantee.
MAX_QPU_INTERIOR_STOPS = 8


def _build_sampler():
    """Connect to a real D-Wave QPU via the Leap cloud service. Raises
    ImportError if dwave-system isn't installed, or whatever dwave-system
    itself raises (typically ValueError("API token not defined")) if no
    API token is configured — both are real, honest failures this
    function does NOT swallow, so callers can show the user exactly what's
    missing rather than a generic "something went wrong."
    """
    if not QPU_AVAILABLE:
        raise ImportError(
            "dwave-system isn't installed — run `pip install dwave-system` to enable method=\"qpu\". "
            "See README.md's \"Real quantum hardware validation\" section for full one-time setup."
        )
    qpu = DWaveSampler()
    return EmbeddingComposite(qpu)


def _sample(sampler, bqm, num_reads: int, label: str):
    """Submit `bqm` to `sampler`, tolerating stand-in samplers used by
    tests that don't accept the real D-Wave cloud client's `label=`
    kwarg (a Leap-dashboard-only readability nicety, not part of the
    core sample() contract every dimod-compatible sampler shares)."""
    try:
        return sampler.sample(bqm, num_reads=num_reads, label=label)
    except TypeError:
        return sampler.sample(bqm, num_reads=num_reads)


def _chip_info(sampleset) -> dict:
    """Best-effort extraction of real-hardware diagnostics from a
    sampleset's .info — present when `sampler` is a genuine QPU chain,
    absent (and reported as None, not a fake placeholder) for the
    lightweight test stand-ins that have no such thing to report."""
    info = getattr(sampleset, "info", {}) or {}
    qpu_access_us = info.get("timing", {}).get("qpu_access_time") if isinstance(info.get("timing"), dict) else None
    embedding = info.get("embedding_context", {}).get("embedding") if isinstance(info.get("embedding_context"), dict) else None
    return {
        "qpu_access_time_us": qpu_access_us,
        "num_physical_qubits_used": sum(len(chain) for chain in embedding.values()) if embedding else None,
    }


def solve_tsp_on_qpu(
    W: np.ndarray, precedence: list[tuple[int, int]] | None = None,
    position_windows: dict[int, tuple[int, int]] | None = None,
    num_reads: int = 100, label: str = "QubitRoute closed-tour solve", sampler=None,
) -> dict:
    """Closed-tour ("visit every waypoint and return to the start") QUBO,
    solved on a real D-Wave QPU. Mirrors qubo_tsp.solve_quantum_inspired's
    return shape (tour/cost/wall_seconds/feasible_reads/total_reads), plus
    "chip_id" and the diagnostics from _chip_info — None for both on a
    non-hardware sampler (e.g. a test stand-in), never fabricated.

    `sampler`: internal override for tests only — a stand-in object
    exposing the same `.sample(bqm, num_reads=...)` interface real D-Wave
    samplers do. Leave unset in real use; it connects to your configured
    Leap account via _build_sampler().
    """
    n = W.shape[0]
    if n - 1 > MAX_QPU_INTERIOR_STOPS + 1:  # -1 waypoints, but closed-tour has no fixed start/end to exclude
        raise ValueError(
            f"solve_tsp_on_qpu is capped at {MAX_QPU_INTERIOR_STOPS + 1} waypoints for real hardware "
            f"(got {n}) — see this module's own \"SIZE\" docstring note for why. Use method=\"quantum\" "
            "(classical simulated annealing) instead for larger instances."
        )

    connected = sampler is None
    sampler = sampler or _build_sampler()
    chip_id = sampler.child.properties.get("chip_id") if connected and hasattr(sampler, "child") else None

    bqm = build_tsp_bqm(W, precedence=precedence, position_windows=position_windows)

    t0 = time.perf_counter()
    sampleset = _sample(sampler, bqm, num_reads, label)
    wall_seconds = time.perf_counter() - t0

    best_tour, best_cost, feasible_count = None, float("inf"), 0
    best_tour_any, best_cost_any = None, float("inf")
    for sample, _energy in sampleset.data(fields=["sample", "energy"]):
        tour = _decode_sample(sample, n)
        if tour is None:
            continue
        feasible_count += 1
        cost = tour_length(tour, W)
        if cost < best_cost_any:
            best_tour_any, best_cost_any = tour, cost
        if precedence and not satisfies_precedence(tour, precedence):
            continue
        if position_windows and not satisfies_position_windows(tour, position_windows):
            continue
        if cost < best_cost:
            best_tour, best_cost = tour, cost

    if best_tour is None:
        best_tour, best_cost = best_tour_any, best_cost_any

    result = {
        "tour": best_tour,
        "cost": best_cost,
        "wall_seconds": wall_seconds,
        "feasible_reads": feasible_count,
        "total_reads": num_reads,
        "chip_id": chip_id,
        "method": "qpu",
    }
    result.update(_chip_info(sampleset))
    return result


def solve_open_path_on_qpu(
    W: np.ndarray, start_idx: int, end_idx: int, precedence: list[tuple[int, int]] | None = None,
    position_windows: dict[int, tuple[int, int]] | None = None,
    num_reads: int = 100, label: str = "QubitRoute open-path solve", sampler=None,
) -> dict:
    """Fixed-start/fixed-end QUBO, solved on a real D-Wave QPU. Mirrors
    qubo_tsp.solve_open_path_quantum_inspired's return shape. See
    solve_tsp_on_qpu's docstring for the `sampler=` test-injection note —
    identical contract here.
    """
    n = W.shape[0]
    middle = [v for v in range(n) if v not in (start_idx, end_idx)]
    if len(middle) > MAX_QPU_INTERIOR_STOPS:
        raise ValueError(
            f"solve_open_path_on_qpu is capped at {MAX_QPU_INTERIOR_STOPS} interior stops for real "
            f"hardware (got {len(middle)}) — see this module's own \"SIZE\" docstring note for why. "
            "Use method=\"quantum\" (classical simulated annealing) instead for larger instances."
        )

    if not middle:
        path = [start_idx, end_idx]
        return {
            "path": path, "cost": open_path_length(path, W), "wall_seconds": 0.0,
            "feasible_reads": 1, "total_reads": 1, "chip_id": None, "method": "qpu",
            "qpu_access_time_us": None, "num_physical_qubits_used": None,
        }

    connected = sampler is None
    sampler = sampler or _build_sampler()
    chip_id = sampler.child.properties.get("chip_id") if connected and hasattr(sampler, "child") else None

    bqm = build_open_path_bqm(W, start_idx, end_idx, precedence=precedence, position_windows=position_windows)

    t0 = time.perf_counter()
    sampleset = _sample(sampler, bqm, num_reads, label)
    wall_seconds = time.perf_counter() - t0

    best_path, best_cost, feasible_count = None, float("inf"), 0
    best_path_any, best_cost_any = None, float("inf")
    for sample, _energy in sampleset.data(fields=["sample", "energy"]):
        path = _decode_open_path(sample, n, start_idx, end_idx, middle)
        if path is None:
            continue
        feasible_count += 1
        cost = open_path_length(path, W)
        if cost < best_cost_any:
            best_path_any, best_cost_any = path, cost
        if precedence and not satisfies_precedence(path, precedence):
            continue
        if position_windows and not satisfies_position_windows(path, position_windows):
            continue
        if cost < best_cost:
            best_path, best_cost = path, cost

    if best_path is None:
        best_path, best_cost = best_path_any, best_cost_any

    result = {
        "path": best_path,
        "cost": best_cost,
        "wall_seconds": wall_seconds,
        "feasible_reads": feasible_count,
        "total_reads": num_reads,
        "chip_id": chip_id,
        "method": "qpu",
    }
    result.update(_chip_info(sampleset))
    return result
