"""Tests for src/benchmark.py's Experiment 5 (time-window position-pruning
effectiveness). Like Experiment 4, this measures a real, honestly-scoped
property against real data rather than asserting one — see
run_experiment_5_time_windows's own docstring and src/time_windows.py's
module docstring for the full "pruning helps but doesn't guarantee"
story this experiment exists to measure."""

import pytest

from benchmark import run_experiment_5_time_windows


def test_experiment_5_runs_and_returns_expected_shape():
    rows = run_experiment_5_time_windows(n_trials=6, seed=99)
    assert rows
    expected_keys = {
        "experiment", "trial", "n_waypoints", "target_waypoint",
        "baseline_arrival_min", "window", "without_pruning_satisfied",
        "with_pruning_satisfied",
    }
    for r in rows:
        assert expected_keys <= set(r.keys())


def test_with_pruning_never_does_worse_than_without_pruning():
    """The core claim this experiment exists to check: enforcing the
    provably-safe position range can only ever help or tie, never make
    satisfaction less likely than not constraining the solve at all — a
    per-trial invariant, checked directly rather than only in aggregate."""
    rows = run_experiment_5_time_windows(n_trials=15, seed=7)
    assert rows
    for r in rows:
        if r["without_pruning_satisfied"]:
            assert r["with_pruning_satisfied"], (
                "pruning should never turn an already-satisfied window into a violated one"
            )


def test_windows_are_constructed_as_a_genuine_ask_not_trivially_true():
    """Sanity check on the experiment's own methodology: since each window
    is deliberately shifted earlier than where the waypoint naturally
    landed, the unconstrained (without-pruning) baseline should satisfy it
    rarely, not by default — otherwise the comparison would be vacuous."""
    rows = run_experiment_5_time_windows(n_trials=15, seed=7)
    assert rows
    without_ok = sum(1 for r in rows if r["without_pruning_satisfied"])
    assert without_ok / len(rows) < 0.3


def test_is_reproducible_given_the_same_seed():
    rows_a = run_experiment_5_time_windows(n_trials=8, seed=42)
    rows_b = run_experiment_5_time_windows(n_trials=8, seed=42)
    assert rows_a == rows_b
