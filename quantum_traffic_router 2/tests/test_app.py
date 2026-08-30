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
