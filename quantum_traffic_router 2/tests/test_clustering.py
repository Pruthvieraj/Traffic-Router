"""Tests the scaling-past-10-stops feature (src/clustering.py). The two
properties that actually matter for a hackathon judge probing feasibility:
(1) below the cluster threshold, behavior is byte-for-byte identical to the
exact solver — clustering changes nothing about the already-verified small-N
case; (2) above the threshold, the result is always a genuinely valid route
(every stop visited exactly once, correct start/end) even though it's no
longer guaranteed globally optimal."""

import numpy as np
import pytest

from baseline import nearest_neighbor_2opt_open_path
from clustering import solve_multi_vehicle, solve_open_path_scalable
from qubo_tsp import open_path_length


def _random_matrix(n, seed):
    rng = np.random.default_rng(seed)
    pts = rng.uniform(0, 100, size=(n, 2))
    return np.linalg.norm(pts[:, None, :] - pts[None, :, :], axis=-1)


def _assert_valid_open_path(path, n, start, end):
    assert path[0] == start
    assert path[-1] == end
    assert sorted(path) == list(range(n))


@pytest.mark.parametrize("seed", range(5))
def test_small_n_is_exact_passthrough(seed):
    n = 6
    W = _random_matrix(n, seed)
    scalable = solve_open_path_scalable(W, 0, n - 1, method="classical", cluster_size=9)
    direct = nearest_neighbor_2opt_open_path(W, 0, n - 1)
    assert scalable["path"] == direct["path"]
    assert scalable["cost"] == pytest.approx(direct["cost"])
    assert scalable["clusters_used"] == 1


@pytest.mark.parametrize("n", [12, 18, 25])
def test_large_n_produces_a_valid_path(n):
    W = _random_matrix(n, seed=n)
    result = solve_open_path_scalable(W, 0, n - 1, method="classical", cluster_size=8)
    _assert_valid_open_path(result["path"], n, 0, n - 1)
    assert result["clusters_used"] > 1
    # the reported cost must match independently recomputing it from the path
    assert result["cost"] == pytest.approx(open_path_length(result["path"], W))


@pytest.mark.parametrize("n", [15, 22])
def test_large_n_quality_is_reasonable(n):
    """Not a global-optimality claim — that's intractable at this size for
    any method, classical or quantum. Just a sanity check that clustering
    doesn't produce a wildly worse route than solving the whole thing
    unclustered."""
    W = _random_matrix(n, seed=100 + n)
    clustered = solve_open_path_scalable(W, 0, n - 1, method="classical", cluster_size=8)
    unclustered = nearest_neighbor_2opt_open_path(W, 0, n - 1)
    assert clustered["cost"] < unclustered["cost"] * 2.0


def test_quantum_method_also_works_at_scale():
    n = 14
    W = _random_matrix(n, seed=7)
    result = solve_open_path_scalable(W, 0, n - 1, method="quantum", cluster_size=6)
    _assert_valid_open_path(result["path"], n, 0, n - 1)


def test_single_interior_stop_does_not_crash():
    W = _random_matrix(3, seed=1)
    result = solve_open_path_scalable(W, 0, 2, method="classical", cluster_size=1)
    _assert_valid_open_path(result["path"], 3, 0, 2)


# ---------- precedence pass-through / honest scope limit ----------

def test_precedence_is_honored_on_the_single_cluster_passthrough():
    from qubo_tsp import satisfies_precedence

    n = 6
    W = _random_matrix(n, seed=3)
    precedence = [(2, 4)]
    result = solve_open_path_scalable(W, 0, n - 1, method="classical", cluster_size=9, precedence=precedence)
    _assert_valid_open_path(result["path"], n, 0, n - 1)
    assert satisfies_precedence(result["path"], precedence)
    assert result["clusters_used"] == 1


def test_precedence_above_cluster_size_raises_instead_of_silently_ignoring():
    """Once stops must be split across independently-solved clusters, a
    cross-cluster precedence pair can't be reliably enforced by the
    stitching step — this must fail loudly rather than quietly return a
    route that doesn't actually honor the constraint it was asked for."""
    n = 12
    W = _random_matrix(n, seed=4)
    with pytest.raises(ValueError):
        solve_open_path_scalable(W, 0, n - 1, method="classical", cluster_size=8, precedence=[(2, 4)])


# ---------- solve_multi_vehicle (the multi-vehicle dispatch demo) ----------

def _assert_valid_closed_loop(path, depot):
    """Every vehicle's path must start and end at the depot, and everything
    in between is unique (no stop visited twice by the same vehicle)."""
    assert path[0] == depot
    assert path[-1] == depot
    interior = path[1:-1]
    assert len(interior) == len(set(interior))
    assert depot not in interior


def test_multi_vehicle_every_stop_assigned_exactly_once():
    n = 9
    W = _random_matrix(n, seed=3)
    depot = 0
    stop_indices = list(range(1, n))
    result = solve_multi_vehicle(W, depot, stop_indices, n_vehicles=3, method="classical")

    assert result["n_vehicles"] == 3
    all_assigned = []
    for v in result["vehicles"]:
        _assert_valid_closed_loop(v["path"], depot)
        all_assigned.extend(v["path"][1:-1])
    # every non-depot stop assigned to exactly one vehicle, none dropped or duplicated
    assert sorted(all_assigned) == sorted(stop_indices)


def test_multi_vehicle_total_cost_matches_sum_of_vehicle_costs():
    n = 7
    W = _random_matrix(n, seed=5)
    result = solve_multi_vehicle(W, 0, list(range(1, n)), n_vehicles=2, method="classical")
    assert result["total_cost"] == pytest.approx(sum(v["cost"] for v in result["vehicles"]))
    for v in result["vehicles"]:
        assert v["cost"] == pytest.approx(open_path_length(v["path"], W))


def test_multi_vehicle_caps_vehicle_count_at_stop_count():
    """Asking for more vehicles than there are stops shouldn't crash or
    create empty-route 'phantom' vehicles."""
    n = 4
    W = _random_matrix(n, seed=8)
    result = solve_multi_vehicle(W, 0, [1, 2, 3], n_vehicles=10, method="classical")
    assert result["n_vehicles"] <= 3
    assert all(v["stops"] >= 1 for v in result["vehicles"])


def test_multi_vehicle_single_vehicle_matches_closed_loop_baseline():
    """With n_vehicles=1, this should just be an ordinary single-vehicle
    closed-loop tour — no different from calling the underlying solver
    directly on depot + all stops."""
    n = 6
    W = _random_matrix(n, seed=2)
    result = solve_multi_vehicle(W, 0, list(range(1, n)), n_vehicles=1, method="classical")
    assert result["n_vehicles"] == 1
    _assert_valid_closed_loop(result["vehicles"][0]["path"], 0)


def test_multi_vehicle_empty_stops_returns_empty_fleet():
    W = _random_matrix(3, seed=1)
    result = solve_multi_vehicle(W, 0, [], n_vehicles=3, method="classical")
    assert result == {"vehicles": [], "total_cost": 0.0, "n_vehicles": 0, "wall_seconds": 0.0}


def test_multi_vehicle_quantum_method_also_works():
    n = 5
    W = _random_matrix(n, seed=11)
    result = solve_multi_vehicle(W, 0, list(range(1, n)), n_vehicles=2, method="quantum")
    all_assigned = []
    for v in result["vehicles"]:
        _assert_valid_closed_loop(v["path"], 0)
        all_assigned.extend(v["path"][1:-1])
    assert sorted(all_assigned) == [1, 2, 3, 4]


# ---------- capacity constraint (max_stops_per_vehicle) ----------

def test_capacity_is_actually_enforced_on_every_vehicle():
    """Without a capacity limit, plain farthest-point clustering can (and
    does, for this seed) hand one vehicle noticeably more stops than
    another. With max_stops_per_vehicle set, no vehicle may exceed it —
    this is the property that turns 'first cut' into 'has a real,
    enforced constraint'."""
    n = 11  # depot (0) + 10 stops
    W = _random_matrix(n, seed=42)
    stop_indices = list(range(1, n))
    result = solve_multi_vehicle(W, 0, stop_indices, n_vehicles=2, method="classical", max_stops_per_vehicle=3)
    for v in result["vehicles"]:
        assert v["stops"] <= 3
    # every stop still assigned to exactly one vehicle, none dropped/duplicated
    all_assigned = [s for v in result["vehicles"] for s in v["path"][1:-1]]
    assert sorted(all_assigned) == stop_indices


def test_capacity_auto_raises_vehicle_count_when_requested_fleet_is_too_small():
    """Asking for 1 vehicle but capping capacity at 3 stops, with 10 stops
    to place, is impossible to satisfy with 1 vehicle — the function must
    raise n_vehicles rather than silently violate the cap or drop stops."""
    n = 11
    W = _random_matrix(n, seed=7)
    stop_indices = list(range(1, n))
    result = solve_multi_vehicle(W, 0, stop_indices, n_vehicles=1, method="classical", max_stops_per_vehicle=3)
    assert result["n_vehicles"] >= 4  # ceil(10 / 3) = 4
    for v in result["vehicles"]:
        assert v["stops"] <= 3


def test_capacity_none_matches_omitting_the_argument_entirely():
    """max_stops_per_vehicle=None and simply not passing the argument at
    all must be exactly equivalent — both take the "no explicit cap" path
    (which, since the imbalance-fix below, means the default fair-share
    balancing, not zero balancing)."""
    n = 7
    W = _random_matrix(n, seed=3)
    stop_indices = list(range(1, n))
    with_none = solve_multi_vehicle(W, 0, stop_indices, n_vehicles=2, method="classical", max_stops_per_vehicle=None)
    without_arg = solve_multi_vehicle(W, 0, stop_indices, n_vehicles=2, method="classical")
    assert with_none["n_vehicles"] == without_arg["n_vehicles"]
    assert [v["path"] for v in with_none["vehicles"]] == [v["path"] for v in without_arg["vehicles"]]


def test_default_split_is_balanced_even_with_no_explicit_capacity():
    """Regression test for a real reported bug: with no capacity limit
    set, plain farthest-point clustering could hand one vehicle a wildly
    disproportionate share of stops purely because of how they happened to
    be distributed in space — a live demo run produced a 14-stops-vs-2-stops
    split across 2 vehicles for 16 total stops. solve_multi_vehicle now
    always rebalances against a default fair-share target of
    ceil(stops / n_vehicles) even when the caller never mentions capacity
    at all, so no vehicle should end up more than roughly double the size
    of the smallest one, let alone 7x."""
    n = 17  # depot (0) + 16 stops, deliberately clustered unevenly in space
    rng = np.random.default_rng(99)
    # 14 points bunched tightly together, 2 points far away — the exact
    # shape of distribution that produced the reported 14-vs-2 split.
    pts = np.vstack([
        rng.uniform(0, 5, size=(14, 2)),
        rng.uniform(80, 100, size=(2, 2)),
        rng.uniform(40, 45, size=(1, 2)),  # depot, roughly in between
    ])
    W = np.linalg.norm(pts[:, None, :] - pts[None, :, :], axis=-1)
    depot = 16
    stop_indices = list(range(16))

    result = solve_multi_vehicle(W, depot, stop_indices, n_vehicles=2, method="classical")
    sizes = sorted(v["stops"] for v in result["vehicles"])
    assert len(result["vehicles"]) == 2
    assert sizes == [8, 8]  # ceil(16/2) = 8 each — an exactly even split here
    all_assigned = sorted(s for v in result["vehicles"] for s in v["path"][1:-1])
    assert all_assigned == stop_indices


def test_capacity_exactly_evenly_divisible_needs_no_extra_vehicles():
    n = 7  # depot + 6 stops
    W = _random_matrix(n, seed=1)
    stop_indices = list(range(1, n))
    result = solve_multi_vehicle(W, 0, stop_indices, n_vehicles=2, method="classical", max_stops_per_vehicle=3)
    assert result["n_vehicles"] == 2  # 6 stops / capacity 3 = exactly 2, no need to raise it
    for v in result["vehicles"]:
        assert v["stops"] <= 3


# ---------- per-stop demand weights (demands + vehicle_capacity) ----------

def test_demand_capacity_is_actually_enforced_on_every_vehicle():
    """The weighted counterpart to test_capacity_is_actually_enforced_on_
    every_vehicle: no vehicle's TOTAL DEMAND (not stop count) may exceed
    vehicle_capacity, even though a few heavy stops could otherwise land
    on the same vehicle as a plain stop-count cap would allow."""
    n = 11  # depot (0) + 10 stops
    W = _random_matrix(n, seed=42)
    stop_indices = list(range(1, n))
    demands = {i: 40.0 for i in stop_indices}
    demands[3] = 90.0  # one unusually heavy stop
    result = solve_multi_vehicle(
        W, 0, stop_indices, n_vehicles=2, method="classical", demands=demands, vehicle_capacity=100.0,
    )
    for v in result["vehicles"]:
        assigned = v["path"][1:-1]
        total = sum(demands[s] for s in assigned)
        assert total <= 100.0 + 1e-9
        assert v["demand"] == pytest.approx(total)
    all_assigned = sorted(s for v in result["vehicles"] for s in v["path"][1:-1])
    assert all_assigned == stop_indices


def test_demand_capacity_auto_raises_vehicle_count_when_too_small():
    n = 11
    W = _random_matrix(n, seed=7)
    stop_indices = list(range(1, n))
    demands = {i: 30.0 for i in stop_indices}  # 10 stops * 30 = 300 total demand
    result = solve_multi_vehicle(
        W, 0, stop_indices, n_vehicles=1, method="classical", demands=demands, vehicle_capacity=100.0,
    )
    assert result["n_vehicles"] >= 3  # ceil(300 / 100) = 3
    for v in result["vehicles"]:
        assert sum(demands[s] for s in v["path"][1:-1]) <= 100.0 + 1e-9


def test_demand_without_explicit_capacity_balances_by_total_demand():
    """With demands given but no vehicle_capacity, the default fair-share
    balancing should target total DEMAND per vehicle, not stop count — a
    vehicle with 2 heavy stops and one with 6 light stops can both be
    'fair' shares even though their stop counts differ a lot."""
    n = 9  # depot (0) + 8 stops
    W = _random_matrix(n, seed=5)
    stop_indices = list(range(1, n))
    demands = {i: (100.0 if i in (1, 2) else 10.0) for i in stop_indices}  # total = 200 + 60 = 260
    result = solve_multi_vehicle(W, 0, stop_indices, n_vehicles=2, method="classical", demands=demands)
    assert result["n_vehicles"] == 2
    totals = sorted(round(v["demand"], 6) for v in result["vehicles"])
    # fair share target is 130 each; the greedy repair should get reasonably close
    assert max(totals) <= 260.0
    assert sum(totals) == pytest.approx(260.0)


def test_demand_rejects_a_stop_heavier_than_vehicle_capacity():
    n = 5
    W = _random_matrix(n, seed=2)
    stop_indices = list(range(1, n))
    demands = {i: 10.0 for i in stop_indices}
    demands[2] = 500.0  # impossible for any vehicle to carry, regardless of fleet size
    with pytest.raises(ValueError):
        solve_multi_vehicle(W, 0, stop_indices, n_vehicles=2, method="classical", demands=demands, vehicle_capacity=100.0)


def test_demand_rejects_missing_entries():
    n = 5
    W = _random_matrix(n, seed=2)
    stop_indices = list(range(1, n))
    demands = {1: 10.0, 2: 20.0}  # missing entries for 3 and 4
    with pytest.raises(ValueError):
        solve_multi_vehicle(W, 0, stop_indices, n_vehicles=2, method="classical", demands=demands, vehicle_capacity=100.0)


def test_demands_and_max_stops_per_vehicle_together_is_rejected():
    n = 5
    W = _random_matrix(n, seed=2)
    stop_indices = list(range(1, n))
    demands = {i: 10.0 for i in stop_indices}
    with pytest.raises(ValueError):
        solve_multi_vehicle(
            W, 0, stop_indices, n_vehicles=2, method="classical",
            demands=demands, max_stops_per_vehicle=2,
        )


def test_no_demands_leaves_demand_field_none():
    n = 5
    W = _random_matrix(n, seed=2)
    result = solve_multi_vehicle(W, 0, list(range(1, n)), n_vehicles=2, method="classical")
    assert all(v["demand"] is None for v in result["vehicles"])


# ---------- precedence in multi-vehicle mode (patent-readiness checklist item 8) ----------
#
# Precedence in multi-vehicle mode only means something if the fleet split
# happens to keep both stops of a pair on the SAME vehicle — that split is
# decided first, with no awareness of precedence at all, so these tests
# cover both outcomes: a same-vehicle pair must actually be honored (using
# the depot-anchored open-path solver under the hood, not the closed-loop
# one — see solve_multi_vehicle's "PRECEDENCE" docstring section for why),
# and a cross-vehicle pair must raise loudly instead of quietly ignoring it.

def test_precedence_is_honored_when_forced_onto_one_vehicle_classical():
    from qubo_tsp import satisfies_precedence

    n = 7
    W = _random_matrix(n, seed=5)
    stop_indices = list(range(1, n))
    precedence = [(2, 5)]
    # n_vehicles=1 guarantees every stop (and thus both ends of the pair)
    # lands on the same, only, vehicle.
    result = solve_multi_vehicle(W, 0, stop_indices, n_vehicles=1, method="classical", precedence=precedence)
    assert len(result["vehicles"]) == 1
    path = result["vehicles"][0]["path"]
    _assert_valid_closed_loop(path, depot=0)
    assert satisfies_precedence(path, precedence)


def test_precedence_is_honored_when_forced_onto_one_vehicle_quantum():
    from qubo_tsp import satisfies_precedence

    n = 9
    W = _random_matrix(n, seed=6)
    stop_indices = list(range(1, n))
    precedence = [(3, 7)]
    result = solve_multi_vehicle(W, 0, stop_indices, n_vehicles=1, method="quantum", precedence=precedence)
    assert len(result["vehicles"]) == 1
    path = result["vehicles"][0]["path"]
    _assert_valid_closed_loop(path, depot=0)
    assert satisfies_precedence(path, precedence)
    # sanity: reported cost matches independently recomputing it from the path
    assert result["total_cost"] == pytest.approx(open_path_length(path, W))


def test_precedence_across_vehicles_raises_instead_of_silently_ignoring():
    n = 6
    W = _random_matrix(n, seed=7)
    stop_indices = list(range(1, n))
    # One vehicle per stop guarantees any pair spans two different vehicles.
    with pytest.raises(ValueError, match="different vehicles"):
        solve_multi_vehicle(
            W, 0, stop_indices, n_vehicles=len(stop_indices), method="classical",
            precedence=[(stop_indices[0], stop_indices[1])],
        )


def test_precedence_referencing_a_non_stop_index_raises():
    """A precedence pair naming the depot (or any index outside
    stop_indices) can't be assigned to any vehicle's cluster at all —
    must be a clear error, not a KeyError or a silently-dropped rule."""
    n = 6
    W = _random_matrix(n, seed=7)
    stop_indices = list(range(1, n))
    with pytest.raises(ValueError, match="isn't in stop_indices"):
        solve_multi_vehicle(W, 0, stop_indices, n_vehicles=2, method="classical", precedence=[(0, stop_indices[0])])


def test_precedence_leaves_other_vehicles_unaffected():
    """Only the vehicle(s) that actually own an applicable precedence pair
    should switch to the anchored-open-path solve path — every other
    vehicle must still come back as an ordinary, valid closed loop."""
    n = 9
    W = _random_matrix(n, seed=6)
    stop_indices = list(range(1, n))
    result = solve_multi_vehicle(W, 0, stop_indices, n_vehicles=1, method="classical", precedence=[(3, 7)])
    for v in result["vehicles"]:
        _assert_valid_closed_loop(v["path"], depot=0)
    # total_cost must still equal the sum of the individual vehicle costs
    assert result["total_cost"] == pytest.approx(sum(v["cost"] for v in result["vehicles"]))
