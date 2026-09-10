"""Tests for src/benchmark.py's Experiment 6 (fleet-mode cluster-first/
route-second split vs. a real joint capacitated VRP solver). Like
Experiment 4 and 5, this measures a real, honestly-scoped property against
real data rather than asserting one — see run_experiment_6_cvrp_baseline's
own docstring and src/ortools_vrp_baseline.py's module docstring for the
full "why this is a genuinely harder comparison than Experiment 1's
single-vehicle OR-Tools baseline" story this experiment exists to measure.

The OR-Tools-specific assertions are skipped (not failed) when ortools
isn't installed, mirroring the optional-dependency pattern used throughout
this project (see tests/test_ortools_vrp_baseline.py) — the experiment
function itself must still run and return fleet-mode-only rows either way,
since that degrade-gracefully behavior is part of its contract.

Every call below passes a short `ortools_time_limit_seconds` (OR-Tools'
guided local search runs for the FULL time budget it's given, regardless
of how tiny the instance is, so this is what keeps this file from being
the slowest thing in the suite — see run_experiment_6_cvrp_baseline's own
docstring for why that knob exists). The production default (3.0s, used
by main.py and __main__) is left untouched."""

import pytest

from benchmark import run_experiment_6_cvrp_baseline

try:
    import ortools  # noqa: F401
    ORTOOLS_INSTALLED = True
except ImportError:
    ORTOOLS_INSTALLED = False

FAST = dict(ortools_time_limit_seconds=1.0)


def test_experiment_6_runs_and_returns_expected_shape():
    rows = run_experiment_6_cvrp_baseline(n_trials=6, seed=99, **FAST)
    assert rows
    expected_keys = {
        "experiment", "trial", "n_waypoints", "n_vehicles_offered", "vehicle_capacity",
        "ours_total_cost_min", "ours_n_vehicles_used", "ours_capacity_ok",
    }
    for r in rows:
        assert expected_keys <= set(r.keys())


def test_our_fleet_split_always_respects_the_vehicle_capacity():
    """Baseline sanity check independent of OR-Tools: solve_multi_vehicle's
    own capacity constraint must actually hold on every vehicle, in every
    trial — this experiment isolates the capacity-only case specifically
    so a failure here would mean the split itself is broken, not just
    "not as good as a joint solver.\""""
    rows = run_experiment_6_cvrp_baseline(n_trials=10, seed=21, **FAST)
    assert rows
    for r in rows:
        assert r["ours_capacity_ok"], f"trial {r['trial']} violated its own vehicle_capacity"


@pytest.mark.skipif(not ORTOOLS_INSTALLED, reason="ortools not installed")
def test_ortools_joint_solve_never_costs_more_than_our_two_step_split():
    """The core claim this experiment exists to check: a real joint CVRP
    solver, offered the same-or-larger vehicle pool ours ended up using,
    should never report a HIGHER total cost than our cluster-first/route-
    second split — it can always fall back to reproducing the same split
    if nothing better exists. A per-trial invariant, not just an average."""
    rows = run_experiment_6_cvrp_baseline(n_trials=10, seed=21, **FAST)
    assert rows
    compared = [r for r in rows if "ortools_total_cost_min" in r]
    assert compared, "expected OR-Tools comparison rows when ortools is installed"
    for r in compared:
        assert r["ortools_total_cost_min"] <= r["ours_total_cost_min"] + 1e-6, (
            f"trial {r['trial']}: OR-Tools joint solve ({r['ortools_total_cost_min']}) "
            f"cost more than our two-step split ({r['ours_total_cost_min']})"
        )
        assert r["ours_pct_above_ortools"] >= -1e-6


@pytest.mark.skipif(not ORTOOLS_INSTALLED, reason="ortools not installed")
def test_ortools_also_respects_capacity():
    rows = run_experiment_6_cvrp_baseline(n_trials=8, seed=5, **FAST)
    compared = [r for r in rows if "ortools_capacity_ok" in r]
    assert compared
    for r in compared:
        assert r["ortools_capacity_ok"]


def test_is_reproducible_given_the_same_seed():
    rows_a = run_experiment_6_cvrp_baseline(n_trials=6, seed=42, **FAST)
    rows_b = run_experiment_6_cvrp_baseline(n_trials=6, seed=42, **FAST)
    assert rows_a == rows_b
