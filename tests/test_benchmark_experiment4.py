"""Tests for src/benchmark.py's Experiment 4 (multi-objective time-vs-distance
trade-off). Unlike Experiments 1-3, this one is deliberately zero-noise: it
uses baseline.brute_force_optimal (exact search) instead of the QUBO+SA
solver, specifically so the reported divergence between "optimize for time"
and "optimize for distance" reflects the underlying problem, not simulated-
annealing variance. See run_experiment_4_multi_objective's own docstring for
why "objectives_diverge" is a cost-based test rather than a tour-identity
test."""

import pytest

from benchmark import run_experiment_4_multi_objective


def test_experiment_4_runs_and_returns_expected_shape():
    rows = run_experiment_4_multi_objective(n_trials=6, seed=99)
    assert rows
    expected_keys = {
        "experiment", "trial", "n_waypoints", "objectives_diverge",
        "true_fastest_tour_time_min", "true_fastest_tour_distance_km",
        "true_shortest_tour_distance_km", "true_shortest_tour_time_min",
        "extra_distance_pct_if_time_only", "extra_time_pct_if_distance_only",
    }
    for r in rows:
        assert expected_keys <= set(r.keys())


def test_extra_costs_are_never_negative():
    """Optimizing for the wrong objective can never look CHEAPER on the
    other objective than the tour that was actually optimized for it —
    brute force already found the true optimum for each objective
    separately, so the "wrong" tour's cost on that objective can only be
    greater than or equal to the true optimum, never less. A negative value
    here would mean brute_force_optimal missed a better tour."""
    rows = run_experiment_4_multi_objective(n_trials=15, seed=13)
    assert rows
    for r in rows:
        assert r["extra_distance_pct_if_time_only"] >= -1e-6
        assert r["extra_time_pct_if_distance_only"] >= -1e-6


def test_objectives_diverge_flag_matches_the_measured_costs():
    """objectives_diverge must be True exactly when at least one of the two
    extra-cost percentages is (meaningfully) positive — this keeps the flag
    from silently drifting out of sync with the numbers it summarizes."""
    rows = run_experiment_4_multi_objective(n_trials=15, seed=13)
    for r in rows:
        should_diverge = (
            r["extra_distance_pct_if_time_only"] > 1e-6
            or r["extra_time_pct_if_distance_only"] > 1e-6
        )
        assert r["objectives_diverge"] == should_diverge


def test_fastest_tour_is_never_slower_than_shortest_tour_on_time():
    """The true-optimal-for-time tour's own time cost must be <= the
    true-optimal-for-distance tour's time cost (evaluated on the same time
    matrix) — that's what "optimal" means. Sanity check on brute force
    itself, not just the derived percentages."""
    rows = run_experiment_4_multi_objective(n_trials=15, seed=13)
    for r in rows:
        assert r["true_fastest_tour_time_min"] <= r["true_shortest_tour_time_min"] + 1e-6
        assert r["true_shortest_tour_distance_km"] <= r["true_fastest_tour_distance_km"] + 1e-6


def test_is_reproducible_given_the_same_seed():
    rows_a = run_experiment_4_multi_objective(n_trials=8, seed=42)
    rows_b = run_experiment_4_multi_objective(n_trials=8, seed=42)
    assert rows_a == rows_b
