"""Flask endpoint tests for app.py — these exercise exactly the request
shapes the browser sends in templates/click_router.html, without needing a
running server or any network access (OSRM calls happen client-side, so
/api/solve itself is pure, network-free optimization)."""

import pytest

import app as app_module


@pytest.fixture
def client():
    app_module.app.testing = True
    return app_module.app.test_client()


def test_index_loads(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"Click-Anywhere Route Optimizer" in resp.data


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
