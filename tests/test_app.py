"""Flask endpoint tests for app.py — these exercise exactly the request
shapes the browser sends in templates/click_router.html, without needing a
running server or any network access (OSRM calls happen client-side, so
/api/solve itself is pure, network-free optimization)."""

import pytest

import analytics
import app as app_module


@pytest.fixture
def client():
    app_module.app.testing = True
    analytics._reset_for_tests()
    return app_module.app.test_client()


def test_live_app_loads(client):
    """The interactive click-router UI now lives at /app (Major #4: landing
    page moved to / and the live app moved down a level — see test_landing_*
    below for the new root route)."""
    resp = client.get("/app")
    assert resp.status_code == 200
    assert b"Click-Anywhere Route Optimizer" in resp.data


def test_live_app_includes_the_product_audit_ui_additions(client):
    """Cheap smoke check that the new UI pieces actually rendered into the
    page (not a behavior test — tests/test_layout.py covers that) — this
    just catches a template typo/removed id before a browser test would."""
    html = client.get("/app").data.decode()
    for element_id in (
        "statsStripBtn", "exampleRouteBtn", "qpuOption", "insightsPanel", "insightsCharts",
        "optionsBtn", "optionsDrawer", "historyBtn", "historyPanel", "historyList",
        "drawerInsightsBtn",
    ):
        assert f'id="{element_id}"' in html, f"missing #{element_id} in the rendered page"


def test_landing_page_loads_at_root(client):
    """/ now serves the unified landing page (Major #4 from the product
    audit) rather than the live app directly — it links out to /app and
    /demo instead of embedding the map."""
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"QubitRoute" in resp.data
    assert b'href="/app"' in resp.data
    assert b'href="/demo"' in resp.data
    # The landing page is a lightweight marketing/onboarding page, not the
    # map UI itself — it should NOT contain the live app's markup.
    assert b"Click-Anywhere Route Optimizer" not in resp.data


def test_demo_route_serves_the_static_flagship_map(client):
    """/demo serves the prebuilt multi-city static demo (output/multi_city_map.html,
    falling back to the repo-root index.html) — either way it should be the
    same self-contained file the audit's "instant demo" card links to."""
    resp = client.get("/demo")
    assert resp.status_code == 200
    assert b"Quantum-Inspired Route Optimizer" in resp.data


def test_solve_valid_classical(client):
    matrix = [[0, 300, 600], [300, 0, 400], [600, 400, 0]]
    resp = client.post("/api/solve", json={"matrix": matrix, "method": "classical", "hour": 18.5})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["order"][0] == 0
    assert data["order"][-1] == 2
    assert sorted(data["order"]) == [0, 1, 2]
    # traffic-awareness fields must be present and sane
    assert data["cost_minutes"] > 0
    assert data["free_flow_minutes"] > 0
    assert data["naive_order_minutes"] > 0
    assert -1e-6 <= data["savings_vs_naive_pct"] <= 100
    assert data["hour_simulated"] == pytest.approx(18.5)


def test_solve_defaults_hour_when_not_sent(client):
    matrix = [[0, 300, 600], [300, 0, 400], [600, 400, 0]]
    resp = client.post("/api/solve", json={"matrix": matrix, "method": "classical"})
    assert resp.status_code == 200
    assert resp.get_json()["hour_simulated"] == pytest.approx(12.0)


def test_solve_valid_quantum(client):
    matrix = [[0, 300, 600], [300, 0, 400], [600, 400, 0]]
    resp = client.post("/api/solve", json={"matrix": matrix, "method": "quantum"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert sorted(data["order"]) == [0, 1, 2]


def test_solve_time_window_satisfied_is_reported_and_reflects_the_real_schedule(client):
    matrix = [
        [0, 300, 400, 500, 600],
        [300, 0, 200, 350, 450],
        [400, 200, 0, 300, 400],
        [500, 350, 300, 0, 250],
        [600, 450, 400, 250, 0],
    ]
    resp = client.post(
        "/api/solve",
        json={"matrix": matrix, "method": "quantum", "time_windows": {"2": [5, 15]}},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["time_windows_applied"] is True
    assert len(data["time_window_checks"]) == 1
    check = data["time_window_checks"][0]
    assert check["waypoint_index"] == 2
    assert check["satisfied"] is True
    assert data["all_time_windows_satisfied"] is True
    # the reported arrival time must match independently recomputing it
    # from the real solved order + the SAME congested matrix the server
    # actually solved on (hour defaults to noon, so congestion.py's model
    # still applies a real multiplier — this isn't just the free-flow
    # matrix), not just be trusted/echoed back.
    import numpy as np
    from congestion import apply_congestion_to_matrix
    from time_windows import compute_arrival_schedule
    W_free_flow = np.array(matrix, dtype=float) / 60.0
    W_congested = apply_congestion_to_matrix(W_free_flow, hour=12.0)
    schedule = compute_arrival_schedule(data["order"], W_congested)
    expected_arrival = next(s["arrival_time"] for s in schedule if s["waypoint_index"] == 2)
    assert check["arrival_time"] == pytest.approx(expected_arrival, abs=0.05)


def test_solve_omitting_time_windows_behaves_exactly_as_before(client):
    matrix = [[0, 300, 600], [300, 0, 400], [600, 400, 0]]
    resp = client.post("/api/solve", json={"matrix": matrix, "method": "quantum"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["time_windows_applied"] is False
    assert data["time_window_checks"] == []
    assert data["all_time_windows_satisfied"] is True


def test_solve_time_window_on_start_or_end_point_is_rejected(client):
    matrix = [[0, 300, 600], [300, 0, 400], [600, 400, 0]]
    resp = client.post(
        "/api/solve", json={"matrix": matrix, "method": "quantum", "time_windows": {"0": [1, 5]}},
    )
    assert resp.status_code == 400
    assert "Start or End" in resp.get_json()["error"]


def test_solve_time_window_with_classical_method_is_rejected(client):
    matrix = [[0, 300, 600], [300, 0, 400], [600, 400, 0]]
    resp = client.post(
        "/api/solve", json={"matrix": matrix, "method": "classical", "time_windows": {"1": [1, 5]}},
    )
    assert resp.status_code == 400
    assert "classical" in resp.get_json()["error"]


def test_solve_time_window_malformed_value_is_rejected(client):
    matrix = [[0, 300, 600], [300, 0, 400], [600, 400, 0]]
    resp = client.post(
        "/api/solve", json={"matrix": matrix, "method": "quantum", "time_windows": {"1": [5]}},
    )
    assert resp.status_code == 400


def test_solve_provably_infeasible_time_window_returns_a_clear_400_not_a_500(client):
    matrix = [[0, 300, 600], [300, 0, 400], [600, 400, 0]]
    resp = client.post(
        "/api/solve", json={"matrix": matrix, "method": "quantum", "time_windows": {"1": [10000, 10001]}},
    )
    assert resp.status_code == 400
    assert "point 1" in resp.get_json()["error"]


def test_solve_time_windows_above_cluster_size_is_rejected(client):
    n = 14
    matrix = [[0.0 if i == j else 300.0 + abs(i - j) * 10 for j in range(n)] for i in range(n)]
    resp = client.post(
        "/api/solve", json={"matrix": matrix, "method": "quantum", "time_windows": {"3": [1, 5]}},
    )
    assert resp.status_code == 400
    assert "interior" in resp.get_json()["error"]


def test_solve_accepts_optional_points_field_without_changing_result(client):
    """`points` (real [lat, lon] coordinates matching the matrix's rows) is
    an optional field that only the live-traffic provider needs — see
    src/traffic_provider.py's GoogleRoutesTrafficProvider. Under the
    default TRAFFIC_PROVIDER=simulated it must be accepted but ignored, so
    a client that starts sending it doesn't change any existing behavior."""
    matrix = [[0, 300, 600], [300, 0, 400], [600, 400, 0]]
    points = [[12.9767, 77.5713], [12.9352, 77.6245], [12.9116, 77.6389]]
    resp_with = client.post(
        "/api/solve", json={"matrix": matrix, "method": "classical", "hour": 18.5, "points": points}
    )
    resp_without = client.post(
        "/api/solve", json={"matrix": matrix, "method": "classical", "hour": 18.5}
    )
    assert resp_with.status_code == 200
    assert resp_with.get_json()["cost_minutes"] == pytest.approx(resp_without.get_json()["cost_minutes"])


def test_solve_rejects_malformed_points_field(client):
    matrix = [[0, 300, 600], [300, 0, 400], [600, 400, 0]]
    resp = client.post(
        "/api/solve",
        json={"matrix": matrix, "method": "classical", "points": [[12.9, 77.5], [12.8, 77.6]]},  # wrong length
    )
    assert resp.status_code == 400
    assert "points" in resp.get_json()["error"]


def test_solve_scales_past_old_ten_stop_limit(client):
    """This exact request would have been REJECTED before the clustering
    feature (old MAX_STOPS was 10) — confirms the scaling upgrade actually
    took effect end-to-end through the live endpoint, not just in isolated
    unit tests of clustering.py."""
    n = 20
    matrix = [[abs(i - j) * 37.0 for j in range(n)] for i in range(n)]
    resp = client.post("/api/solve", json={"matrix": matrix, "method": "classical"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert sorted(data["order"]) == list(range(n))
    assert data["clusters_used"] > 1


def test_solve_rejects_non_square(client):
    resp = client.post("/api/solve", json={"matrix": [[0, 1], [1, 0, 2]], "method": "classical"})
    assert resp.status_code == 400


def test_solve_rejects_too_few_points(client):
    resp = client.post("/api/solve", json={"matrix": [[0]], "method": "classical"})
    assert resp.status_code == 400


def test_solve_rejects_beyond_max_stops(client):
    n = app_module.MAX_STOPS + 5
    matrix = [[abs(i - j) * 10.0 for j in range(n)] for i in range(n)]
    resp = client.post("/api/solve", json={"matrix": matrix, "method": "classical"})
    assert resp.status_code == 400


# ---------- incident simulation (re-optimize around a spiked leg) ----------

def test_solve_with_incident_pairs_flags_it_in_the_response(client):
    matrix = [[0, 300, 600, 900], [300, 0, 400, 700], [600, 400, 0, 500], [900, 700, 500, 0]]
    resp = client.post("/api/solve", json={
        "matrix": matrix, "method": "classical", "hour": 13, "incident_pairs": [[0, 1]],
    })
    assert resp.status_code == 200
    assert resp.get_json()["incident_applied"] is True


def test_solve_without_incident_pairs_flags_it_false(client):
    matrix = [[0, 300, 600, 900], [300, 0, 400, 700], [600, 400, 0, 500], [900, 700, 500, 0]]
    resp = client.post("/api/solve", json={"matrix": matrix, "method": "classical"})
    assert resp.status_code == 200
    assert resp.get_json()["incident_applied"] is False


def test_solve_incident_pairs_can_change_the_chosen_order(client):
    """A big enough spike on the leg the un-spiked solve chose should make
    the optimizer route around it, given an alternative exists."""
    matrix = [[0, 300, 600, 900], [300, 0, 400, 700], [600, 400, 0, 500], [900, 700, 500, 0]]
    baseline = client.post("/api/solve", json={"matrix": matrix, "method": "classical", "hour": 13}).get_json()
    spiked = client.post("/api/solve", json={
        "matrix": matrix, "method": "classical", "hour": 13, "incident_pairs": [[0, 1]],
    }).get_json()
    assert spiked["order"] != baseline["order"]


def test_solve_rejects_malformed_incident_pairs(client):
    matrix = [[0, 300], [300, 0]]
    resp = client.post("/api/solve", json={"matrix": matrix, "method": "classical", "incident_pairs": [[0]]})
    assert resp.status_code == 400


# ---------- precedence ("visit X before Y") constraints ----------

def _six_point_matrix():
    # 0 = start, 5 = end; 1..4 are interior stops.
    return [[abs(i - j) * 120.0 for j in range(6)] for i in range(6)]


def test_solve_with_precedence_satisfies_it_and_flags_the_response(client):
    matrix = _six_point_matrix()
    resp = client.post("/api/solve", json={
        "matrix": matrix, "method": "quantum", "precedence": [[3, 1]],  # forces a non-default order
    })
    assert resp.status_code == 200
    data = resp.get_json()
    order = data["order"]
    assert order.index(3) < order.index(1)
    assert data["precedence_applied"] is True
    assert data["precedence_satisfied"] is True


def test_solve_without_precedence_flags_it_false_but_satisfied(client):
    matrix = _six_point_matrix()
    resp = client.post("/api/solve", json={"matrix": matrix, "method": "classical"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["precedence_applied"] is False
    assert data["precedence_satisfied"] is True  # vacuously true — nothing to violate


def test_solve_rejects_precedence_pair_requiring_something_after_end(client):
    matrix = _six_point_matrix()
    resp = client.post("/api/solve", json={"matrix": matrix, "method": "classical", "precedence": [[5, 2]]})
    assert resp.status_code == 400
    assert "End" in resp.get_json()["error"]


def test_solve_rejects_precedence_pair_requiring_something_before_start(client):
    matrix = _six_point_matrix()
    resp = client.post("/api/solve", json={"matrix": matrix, "method": "classical", "precedence": [[2, 0]]})
    assert resp.status_code == 400
    assert "Start" in resp.get_json()["error"]


def test_solve_rejects_precedence_pair_with_out_of_range_index(client):
    matrix = _six_point_matrix()
    resp = client.post("/api/solve", json={"matrix": matrix, "method": "classical", "precedence": [[2, 99]]})
    assert resp.status_code == 400


def test_solve_rejects_precedence_above_cluster_size(client):
    n = 20
    matrix = [[abs(i - j) * 37.0 for j in range(n)] for i in range(n)]
    resp = client.post("/api/solve", json={"matrix": matrix, "method": "classical", "precedence": [[2, 4]]})
    assert resp.status_code == 400
    assert "cluster" in resp.get_json()["error"].lower()


def test_solve_precedence_trivially_true_pairs_with_start_and_end_are_allowed(client):
    matrix = _six_point_matrix()
    resp = client.post("/api/solve", json={
        "matrix": matrix, "method": "classical", "precedence": [[0, 3], [2, 5]],
    })
    assert resp.status_code == 200


def test_solve_precedence_and_incident_compose_in_one_request(client):
    """Patent-readiness checklist item 9: precedence and incident-triggered
    re-optimization must actually WORK TOGETHER in a single request, not
    just pass independently in separate tests — this is what a "these
    constraints compose" claim needs to be true, verified end-to-end
    through the live endpoint rather than assumed from each feature's own
    isolated tests."""
    matrix = _six_point_matrix()
    resp = client.post("/api/solve", json={
        "matrix": matrix, "method": "quantum",
        "precedence": [[3, 1]],       # forces a non-default visiting order
        "incident_pairs": [[0, 2]],   # spikes one leg to force re-routing around it
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["incident_applied"] is True
    assert data["precedence_applied"] is True
    assert data["precedence_satisfied"] is True
    order = data["order"]
    assert sorted(order) == [0, 1, 2, 3, 4, 5]
    assert order.index(3) < order.index(1)


# ---------- /api/solve_fleet (multi-vehicle dispatch demo) ----------

def test_solve_fleet_valid_request(client):
    matrix = [
        [0, 300, 400, 500],
        [300, 0, 200, 350],
        [400, 200, 0, 300],
        [500, 350, 300, 0],
    ]
    resp = client.post("/api/solve_fleet", json={"matrix": matrix, "method": "classical", "n_vehicles": 2})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["n_vehicles_used"] == 2
    assert len(data["vehicles"]) == 2
    assigned = []
    for v in data["vehicles"]:
        assert v["order"][0] == 0
        assert v["order"][-1] == 0
        assigned.extend(v["order"][1:-1])
    assert sorted(assigned) == [1, 2, 3]
    assert data["total_cost_minutes"] == pytest.approx(sum(v["cost_minutes"] for v in data["vehicles"]), abs=0.2)


def test_solve_fleet_accepts_optional_points_field_without_changing_result(client):
    matrix = [
        [0, 300, 400, 500],
        [300, 0, 200, 350],
        [400, 200, 0, 300],
        [500, 350, 300, 0],
    ]
    points = [[12.97, 77.57], [12.93, 77.62], [12.91, 77.63], [12.91, 77.61]]
    resp_with = client.post(
        "/api/solve_fleet", json={"matrix": matrix, "method": "classical", "n_vehicles": 2, "points": points}
    )
    resp_without = client.post(
        "/api/solve_fleet", json={"matrix": matrix, "method": "classical", "n_vehicles": 2}
    )
    assert resp_with.status_code == 200
    assert resp_with.get_json()["total_cost_minutes"] == pytest.approx(resp_without.get_json()["total_cost_minutes"])


def test_solve_fleet_rejects_malformed_points_field(client):
    matrix = [
        [0, 300, 400, 500],
        [300, 0, 200, 350],
        [400, 200, 0, 300],
        [500, 350, 300, 0],
    ]
    resp = client.post(
        "/api/solve_fleet",
        json={"matrix": matrix, "method": "classical", "n_vehicles": 2, "points": [[12.9, 77.5]]},
    )
    assert resp.status_code == 400
    assert "points" in resp.get_json()["error"]


def test_solve_fleet_rejects_too_few_points(client):
    resp = client.post("/api/solve_fleet", json={"matrix": [[0, 1], [1, 0]], "method": "classical"})
    assert resp.status_code == 400


def test_solve_fleet_rejects_non_square(client):
    resp = client.post("/api/solve_fleet", json={"matrix": [[0, 1], [1, 0, 2], [1, 2, 0]], "method": "classical"})
    assert resp.status_code == 400


def test_solve_fleet_rejects_bad_depot_index(client):
    matrix = [[0, 1, 2], [1, 0, 3], [2, 3, 0]]
    resp = client.post("/api/solve_fleet", json={"matrix": matrix, "method": "classical", "depot_index": 9})
    assert resp.status_code == 400


def test_solve_fleet_enforces_max_stops_per_vehicle(client):
    n = 6  # depot + 5 stops
    matrix = [[abs(i - j) * 100.0 for j in range(n)] for i in range(n)]
    resp = client.post("/api/solve_fleet", json={
        "matrix": matrix, "method": "classical", "n_vehicles": 2, "max_stops_per_vehicle": 2,
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["max_stops_per_vehicle"] == 2
    assert data["n_vehicles_used"] >= 3  # ceil(5 / 2) = 3, so it must have been auto-raised from 2
    for v in data["vehicles"]:
        assert v["stops"] <= 2


def test_solve_fleet_rejects_invalid_max_stops_per_vehicle(client):
    matrix = [[0, 1, 2, 3], [1, 0, 4, 5], [2, 4, 0, 6], [3, 5, 6, 0]]
    resp = client.post("/api/solve_fleet", json={"matrix": matrix, "method": "classical", "max_stops_per_vehicle": 0})
    assert resp.status_code == 400


# ---------- precedence in fleet mode (patent-readiness checklist item 8) ----------
#
# Precedence only has a coherent meaning in fleet mode when the fleet split
# keeps both stops of a pair on the same vehicle — these tests cover the
# success path (forced onto one vehicle) and the honest failure path (split
# across vehicles must be a clean 400, never a silently-wrong route or a 500).

def _seven_point_fleet_matrix():
    n = 7  # depot (0) + 6 stops
    return [[abs(i - j) * 90.0 for j in range(n)] for i in range(n)]


def test_solve_fleet_with_precedence_on_a_single_vehicle(client):
    matrix = _seven_point_fleet_matrix()
    resp = client.post("/api/solve_fleet", json={
        "matrix": matrix, "method": "classical", "n_vehicles": 1, "precedence": [[5, 3]],
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["precedence_applied"] is True
    assert data["precedence_satisfied"] is True
    order = data["vehicles"][0]["order"]
    assert order.index(5) < order.index(3)


def test_solve_fleet_without_precedence_flags_it_false_but_satisfied(client):
    matrix = _seven_point_fleet_matrix()
    resp = client.post("/api/solve_fleet", json={"matrix": matrix, "method": "classical", "n_vehicles": 2})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["precedence_applied"] is False
    assert data["precedence_satisfied"] is True  # vacuously true — nothing to violate


def test_solve_fleet_rejects_precedence_naming_the_depot(client):
    matrix = _seven_point_fleet_matrix()
    resp = client.post("/api/solve_fleet", json={
        "matrix": matrix, "method": "classical", "precedence": [[0, 3]],
    })
    assert resp.status_code == 400


def test_solve_fleet_rejects_malformed_precedence(client):
    matrix = _seven_point_fleet_matrix()
    resp = client.post("/api/solve_fleet", json={
        "matrix": matrix, "method": "classical", "precedence": [[1]],
    })
    assert resp.status_code == 400


def test_solve_fleet_precedence_split_across_vehicles_is_a_clean_400(client):
    """When the fleet split happens to put the two stops on different
    vehicles, this must surface as a client-facing 400 with a clear
    explanation — not an unhandled 500 — since solve_multi_vehicle raises
    ValueError for exactly this case and app.py's except ValueError branch
    is what's supposed to turn that into a 400."""
    matrix = _seven_point_fleet_matrix()
    resp = client.post("/api/solve_fleet", json={
        "matrix": matrix, "method": "classical", "n_vehicles": 6,  # one stop per vehicle
        "precedence": [[1, 2]],
    })
    assert resp.status_code == 400
    assert "vehicle" in resp.get_json()["error"].lower()


# ---------- per-stop demand weights (demands + vehicle_capacity) ----------

def _six_stop_fleet_matrix():
    n = 7  # depot (0) + 6 stops
    return [[abs(i - j) * 80.0 for j in range(n)] for i in range(n)]


def test_solve_fleet_enforces_vehicle_capacity_by_demand(client):
    matrix = _six_stop_fleet_matrix()
    demands = {"1": 40, "2": 40, "3": 40, "4": 40, "5": 40, "6": 40}
    resp = client.post("/api/solve_fleet", json={
        "matrix": matrix, "method": "classical", "n_vehicles": 2,
        "demands": demands, "vehicle_capacity": 100,
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["vehicle_capacity"] == 100
    for v in data["vehicles"]:
        assert v["demand"] <= 100 + 1e-6
    assigned = [s for v in data["vehicles"] for s in v["order"][1:-1]]
    assert sorted(assigned) == [1, 2, 3, 4, 5, 6]


def test_solve_fleet_fills_in_missing_demands_as_default_weight_one(client):
    """A client that only sends weights for the stops the user actually
    edited (not every stop) should have the rest default to 1, not error
    or silently drop them."""
    matrix = _six_stop_fleet_matrix()
    resp = client.post("/api/solve_fleet", json={
        "matrix": matrix, "method": "classical", "n_vehicles": 2,
        "demands": {"1": 5}, "vehicle_capacity": 10,
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assigned = [s for v in data["vehicles"] for s in v["order"][1:-1]]
    assert sorted(assigned) == [1, 2, 3, 4, 5, 6]


def test_solve_fleet_rejects_demands_together_with_max_stops_per_vehicle(client):
    matrix = _six_stop_fleet_matrix()
    resp = client.post("/api/solve_fleet", json={
        "matrix": matrix, "method": "classical",
        "demands": {"1": 1}, "max_stops_per_vehicle": 2,
    })
    assert resp.status_code == 400


def test_solve_fleet_rejects_a_stop_heavier_than_vehicle_capacity(client):
    matrix = _six_stop_fleet_matrix()
    demands = {str(i): 10 for i in range(1, 7)}
    demands["3"] = 500  # impossible for any vehicle
    resp = client.post("/api/solve_fleet", json={
        "matrix": matrix, "method": "classical", "demands": demands, "vehicle_capacity": 100,
    })
    assert resp.status_code == 400


def test_solve_fleet_rejects_malformed_demands(client):
    matrix = _six_stop_fleet_matrix()
    resp = client.post("/api/solve_fleet", json={
        "matrix": matrix, "method": "classical", "demands": [1, 2, 3], "vehicle_capacity": 10,
    })
    assert resp.status_code == 400


def test_solve_fleet_without_demands_leaves_demand_field_null(client):
    matrix = _six_stop_fleet_matrix()
    resp = client.post("/api/solve_fleet", json={"matrix": matrix, "method": "classical", "n_vehicles": 2})
    assert resp.status_code == 200
    data = resp.get_json()
    assert all(v["demand"] is None for v in data["vehicles"])
    assert data["vehicle_capacity"] is None


def test_solve_fleet_without_incident_pairs_flags_it_false(client):
    matrix = _six_stop_fleet_matrix()
    resp = client.post("/api/solve_fleet", json={"matrix": matrix, "method": "classical", "n_vehicles": 2})
    assert resp.status_code == 200
    assert resp.get_json()["incident_applied"] is False


def test_solve_fleet_with_incident_pairs_flags_it_true_and_changes_the_solve(client):
    matrix = _six_stop_fleet_matrix()
    baseline = client.post(
        "/api/solve_fleet", json={"matrix": matrix, "method": "classical", "n_vehicles": 2}
    ).get_json()
    spiked = client.post("/api/solve_fleet", json={
        "matrix": matrix, "method": "classical", "n_vehicles": 2,
        "incident_pairs": [[0, 1]], "incident_multiplier": 50.0,
    })
    assert spiked.status_code == 200
    data = spiked.get_json()
    assert data["incident_applied"] is True
    # A 50x spike on a leg touching the depot should make the fleet's total
    # noticeably worse than the unspiked baseline — same "does this actually
    # change the solve, not just flip a flag" bar as /api/solve's own
    # incident tests use.
    assert data["total_cost_minutes"] > baseline["total_cost_minutes"]


def test_solve_fleet_rejects_malformed_incident_pairs(client):
    matrix = _six_stop_fleet_matrix()
    resp = client.post("/api/solve_fleet", json={
        "matrix": matrix, "method": "classical", "n_vehicles": 2, "incident_pairs": [[0]],
    })
    assert resp.status_code == 400


# ---------- /api/capabilities ----------

def test_capabilities_reports_qpu_not_configured_without_a_token(client, monkeypatch):
    monkeypatch.delenv("DWAVE_API_TOKEN", raising=False)
    resp = client.get("/api/capabilities")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "qpu" in data
    assert data["qpu"]["configured"] is False
    assert isinstance(data["qpu"]["installed"], bool)
    assert "note" in data["qpu"]


def test_capabilities_configured_requires_both_installed_and_token(client, monkeypatch):
    """configured can only be True if BOTH installed is True AND the token
    env var is set — setting just the token with dwave-system NOT
    installed (this sandbox's real state) must still report False, since
    a token with no client library to use it isn't actually usable."""
    monkeypatch.setenv("DWAVE_API_TOKEN", "fake-token-for-test")
    resp = client.get("/api/capabilities")
    data = resp.get_json()
    if not data["qpu"]["installed"]:
        assert data["qpu"]["configured"] is False
    else:
        assert data["qpu"]["configured"] is True


# ---------- /api/insights ----------

def test_insights_returns_all_six_experiment_keys(client):
    resp = client.get("/api/insights")
    assert resp.status_code == 200
    data = resp.get_json()
    for i in range(1, 7):
        assert f"experiment_{i}" in data
        assert isinstance(data[f"experiment_{i}"], list)


def test_insights_coerces_numbers_and_booleans_out_of_csv_strings(client):
    data = client.get("/api/insights").get_json()
    rows = data["experiment_2"]
    if not rows:
        pytest.skip("output/experiment_2_constrained.csv doesn't exist in this checkout")
    row = rows[0]
    assert isinstance(row["n_waypoints"], int)
    assert isinstance(row["qubo_sa_cost_min"], float)
    assert isinstance(row["qubo_sa_satisfies_rule"], bool)
    assert isinstance(row["precedence_rule"], str)  # e.g. "Indiranagar before MG Road" — stays a string


def test_insights_missing_csv_returns_empty_list_not_an_error(client, tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "_OUTPUT_DIR", str(tmp_path))  # a directory with no CSVs in it
    resp = client.get("/api/insights")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["experiment_1"] == []


# ---------- /api/analytics ----------

def test_analytics_starts_at_zero(client):
    resp = client.get("/api/analytics")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["total_solves"] == 0
    assert data["solves_by_endpoint"] == {"solve": 0, "solve_fleet": 0}
    assert data["solves_by_method"] == {"quantum": 0, "classical": 0}
    assert data["errors"] == 0
    assert data["avg_solve_ms"] is None
    assert "note" in data  # the honest-scope caveat must always be present, not just on request


def test_analytics_counts_a_successful_solve_by_endpoint_and_method(client):
    matrix = [[0, 300, 600], [300, 0, 400], [600, 400, 0]]
    client.post("/api/solve", json={"matrix": matrix, "method": "classical"})
    client.post("/api/solve", json={"matrix": matrix, "method": "quantum"})

    data = client.get("/api/analytics").get_json()
    assert data["total_solves"] == 2
    assert data["solves_by_endpoint"] == {"solve": 2, "solve_fleet": 0}
    assert data["solves_by_method"] == {"quantum": 1, "classical": 1}
    assert data["avg_solve_ms"] is not None and data["avg_solve_ms"] >= 0


def test_analytics_counts_a_successful_fleet_solve(client):
    matrix = _six_stop_fleet_matrix()
    client.post("/api/solve_fleet", json={"matrix": matrix, "method": "classical", "n_vehicles": 2})

    data = client.get("/api/analytics").get_json()
    assert data["total_solves"] == 1
    assert data["solves_by_endpoint"] == {"solve": 0, "solve_fleet": 1}


def test_analytics_counts_errors_from_early_validation_and_from_solver_exceptions(client):
    # Fails the earliest input check (too few points) — never reaches the try/except.
    client.post("/api/solve", json={"matrix": [[0, 1]]})
    # Fails a later, solver-layer ValueError (precedence above cluster size).
    client.post("/api/solve", json={
        "matrix": [[0] * 12 for _ in range(12)],
        "precedence": [[1, 2]],
    })

    data = client.get("/api/analytics").get_json()
    assert data["errors"] == 2
    assert data["total_solves"] == 0  # neither request should also count as a solve


def test_analytics_flags_incident_precedence_and_demand_weight_usage(client):
    matrix = [[0, 300, 600], [300, 0, 400], [600, 400, 0]]
    client.post("/api/solve", json={"matrix": matrix, "incident_pairs": [[0, 1]]})
    client.post("/api/solve", json={"matrix": matrix, "precedence": [[1, 2]]})

    fleet_matrix = _six_stop_fleet_matrix()
    client.post("/api/solve_fleet", json={
        "matrix": fleet_matrix, "method": "classical", "n_vehicles": 2,
        "demands": {str(i): 10 for i in range(1, 7)}, "vehicle_capacity": 100,
    })

    data = client.get("/api/analytics").get_json()
    assert data["incident_simulations"] == 1
    assert data["precedence_requests"] == 1
    assert data["demand_weight_requests"] == 1


def test_analytics_response_never_leaks_per_request_data(client):
    """The whole point of keeping this to aggregate counts: nothing about
    an individual request (its matrix, its IP, a timestamp) should ever
    show up in the snapshot, no matter what was just solved."""
    matrix = [[0, 300, 600], [300, 0, 400], [600, 400, 0]]
    client.post("/api/solve", json={"matrix": matrix, "method": "classical"})

    data = client.get("/api/analytics").get_json()
    expected_keys = {
        "since", "uptime_seconds", "total_solves", "solves_by_endpoint",
        "solves_by_method", "avg_solve_ms", "errors", "incident_simulations",
        "precedence_requests", "demand_weight_requests", "note",
    }
    assert set(data.keys()) == expected_keys


# ---------- explainability (src/explain.py wired into /api/solve*) ----------

def test_solve_response_includes_a_leg_by_leg_explanation(client):
    matrix = [[0, 300, 600], [300, 0, 400], [600, 400, 0]]
    resp = client.post("/api/solve", json={"matrix": matrix, "method": "classical"})
    assert resp.status_code == 200
    data = resp.get_json()
    explanation = data["explanation"]
    assert len(explanation["legs"]) == 2  # 3 stops, open path -> 2 legs
    assert explanation["total_cost"] == pytest.approx(data["cost_minutes"], abs=0.1)
    assert explanation["bottleneck_leg"]["cost"] == max(leg["cost"] for leg in explanation["legs"])


def test_solve_response_explanation_reports_precedence_positions(client):
    matrix = [[0, 300, 600, 500], [300, 0, 400, 350], [600, 400, 0, 250], [500, 350, 250, 0]]
    resp = client.post("/api/solve", json={
        "matrix": matrix, "method": "quantum", "precedence": [[1, 2]],
    })
    assert resp.status_code == 200
    data = resp.get_json()
    checks = data["explanation"]["precedence_checks"]
    assert len(checks) == 1
    assert checks[0]["u_index"] == 1 and checks[0]["v_index"] == 2
    assert checks[0]["satisfied"] is data["precedence_satisfied"]


def test_solve_fleet_response_includes_per_vehicle_explanation(client):
    matrix = [
        [0, 300, 400, 500],
        [300, 0, 200, 350],
        [400, 200, 0, 300],
        [500, 350, 300, 0],
    ]
    resp = client.post("/api/solve_fleet", json={"matrix": matrix, "method": "classical", "n_vehicles": 2})
    assert resp.status_code == 200
    data = resp.get_json()
    explanation = data["explanation"]
    assert len(explanation["vehicles"]) == data["n_vehicles_used"]
    summed = sum(v["total_cost"] for v in explanation["vehicles"])
    assert summed == pytest.approx(data["total_cost_minutes"], abs=0.2)


def test_solve_fleet_response_explanation_reports_capacity_margin(client):
    n = 6
    matrix = [[abs(i - j) * 100.0 for j in range(n)] for i in range(n)]
    resp = client.post("/api/solve_fleet", json={
        "matrix": matrix, "method": "classical", "n_vehicles": 2,
        "demands": {"1": 10, "2": 10, "3": 10, "4": 10, "5": 10},
        "vehicle_capacity": 30,
    })
    assert resp.status_code == 200
    data = resp.get_json()
    for v in data["explanation"]["vehicles"]:
        assert v["capacity_margin"] is not None
        assert v["capacity_margin"] >= -1e-6


# ---------- method="qpu" (real D-Wave hardware — src/qpu_solver.py) ----------
#
# This sandbox genuinely has no D-Wave Leap API token configured, so these
# tests exercise the REAL "no credentials" failure path end to end through
# the live app — not a mock. That failure must surface as a clean 4xx with
# a clear message, never a 500 crash, since a live deployment without a
# token configured would hit exactly this.

def test_solve_with_qpu_method_fails_cleanly_without_credentials(client):
    matrix = [[0, 300, 600], [300, 0, 400], [600, 400, 0]]
    resp = client.post("/api/solve", json={"matrix": matrix, "method": "qpu"})
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_solve_fleet_with_qpu_method_fails_cleanly_without_credentials(client):
    matrix = [
        [0, 300, 400, 500],
        [300, 0, 200, 350],
        [400, 200, 0, 300],
        [500, 350, 300, 0],
    ]
    resp = client.post("/api/solve_fleet", json={"matrix": matrix, "method": "qpu", "n_vehicles": 2})
    assert resp.status_code == 400
    assert "error" in resp.get_json()
