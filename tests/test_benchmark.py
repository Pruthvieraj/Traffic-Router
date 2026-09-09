"""Smoke test for src/benchmark.py's Experiment 3 (composed-constraint
benchmark). Experiments 1/2 aren't unit-tested elsewhere in this project
either — they're randomized empirical studies meant to be read, not
asserted on exactly — but Experiment 3's core claim ("COMPOSED always
satisfies both constraints; solving in isolation doesn't") is exactly the
kind of invariant worth locking in as a real regression test, since it's
the specific finding the patent-readiness report leans on."""

import pytest

from benchmark import run_experiment_3_composed


def test_experiment_3_runs_and_returns_expected_shape():
    rows = run_experiment_3_composed(n_trials=6, seed=99)
    assert rows  # at least one applicable trial found
    expected_keys = {
        "experiment", "trial", "n_waypoints", "n_vehicles", "vehicle_capacity",
        "precedence_rule", "composed_precedence_ok", "composed_capacity_ok",
        "capacity_only_precedence_ok_by_luck",
        "precedence_only_pair_separated_by_demand_blind_split",
        "precedence_only_capacity_ok_by_luck",
        "precedence_only_worst_vehicle_over_capacity_pct",
    }
    for r in rows:
        assert expected_keys <= set(r.keys())


def test_composed_always_satisfies_both_constraints():
    """The core invariant this experiment exists to demonstrate: solving
    precedence and demand-weighted capacity TOGETHER in one
    solve_multi_vehicle call must never violate either — this is a
    guarantee of the existing, already-tested solve_multi_vehicle
    validation/construction, not a probabilistic claim, so every trial
    must satisfy it, not just most."""
    rows = run_experiment_3_composed(n_trials=15, seed=13)
    assert rows
    for r in rows:
        assert r["composed_precedence_ok"] is True
        assert r["composed_capacity_ok"] is True


def test_precedence_only_worst_over_pct_is_none_exactly_when_pair_separated():
    """The worst-overload percentage is only meaningful when the
    demand-blind split kept the pair together — make sure the two fields
    stay consistent with each other rather than silently defaulting."""
    rows = run_experiment_3_composed(n_trials=15, seed=13)
    for r in rows:
        if r["precedence_only_pair_separated_by_demand_blind_split"]:
            assert r["precedence_only_capacity_ok_by_luck"] is None
            assert r["precedence_only_worst_vehicle_over_capacity_pct"] is None
        else:
            assert r["precedence_only_capacity_ok_by_luck"] in (True, False)
            assert r["precedence_only_worst_vehicle_over_capacity_pct"] is not None


def test_is_reproducible_given_the_same_seed():
    rows_a = run_experiment_3_composed(n_trials=8, seed=42)
    rows_b = run_experiment_3_composed(n_trials=8, seed=42)
    assert rows_a == rows_b
