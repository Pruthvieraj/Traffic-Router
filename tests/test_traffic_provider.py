import datetime as dt

import numpy as np
import pytest

from congestion import apply_congestion_to_matrix
from traffic_provider import (
    GoogleRoutesTrafficProvider,
    LiveTrafficProviderStub,
    SimulatedTrafficProvider,
    get_traffic_provider,
    next_occurrence_of_hour,
)


def test_get_traffic_provider_simulated_matches_direct_call():
    W = np.array([[0, 10, 20], [10, 0, 15], [20, 15, 0]], dtype=float)
    provider = get_traffic_provider("simulated")
    assert isinstance(provider, SimulatedTrafficProvider)
    assert np.allclose(
        provider.get_congested_matrix(W, hour=18.5),
        apply_congestion_to_matrix(W, hour=18.5),
    )


def test_simulated_provider_ignores_coords_and_still_works():
    """coords is a new, optional parameter — a provider that doesn't need
    it (the simulated model) must keep behaving identically whether or not
    a caller passes it, so existing call sites (and tests) never break."""
    W = np.array([[0, 10, 20], [10, 0, 15], [20, 15, 0]], dtype=float)
    provider = SimulatedTrafficProvider()
    without_coords = provider.get_congested_matrix(W, hour=18.5)
    with_coords = provider.get_congested_matrix(W, hour=18.5, coords=[(1.0, 2.0), (3.0, 4.0), (5.0, 6.0)])
    assert np.allclose(without_coords, with_coords)


def test_get_traffic_provider_live_stub_raises_clearly():
    provider = get_traffic_provider("live")
    assert isinstance(provider, LiveTrafficProviderStub)
    W = np.array([[0, 10], [10, 0]], dtype=float)
    with pytest.raises(NotImplementedError):
        provider.get_congested_matrix(W, hour=9.0)


def test_get_traffic_provider_unknown_name_raises_value_error():
    with pytest.raises(ValueError):
        get_traffic_provider("some_provider_that_does_not_exist")


# --- GoogleRoutesTrafficProvider: the real live-traffic integration -------

def test_google_routes_provider_without_key_raises_clearly(monkeypatch):
    """This sandbox genuinely has no GOOGLE_ROUTES_API_KEY configured (see
    the QPU solver's analogous no-credentials test) — this is the REAL,
    unmocked failure path, not a simulated one."""
    monkeypatch.delenv("GOOGLE_ROUTES_API_KEY", raising=False)
    with pytest.raises(ValueError, match="GOOGLE_ROUTES_API_KEY"):
        GoogleRoutesTrafficProvider()


def test_get_traffic_provider_google_routes_without_key_raises_clearly(monkeypatch):
    monkeypatch.delenv("GOOGLE_ROUTES_API_KEY", raising=False)
    with pytest.raises(ValueError, match="GOOGLE_ROUTES_API_KEY"):
        get_traffic_provider("google_routes")


def test_google_routes_provider_accepts_explicit_key_without_env_var(monkeypatch):
    monkeypatch.delenv("GOOGLE_ROUTES_API_KEY", raising=False)
    provider = GoogleRoutesTrafficProvider(api_key="test-key-123", session=object())
    assert provider.api_key == "test-key-123"


def test_google_routes_provider_requires_coords():
    provider = GoogleRoutesTrafficProvider(api_key="test-key", session=object())
    W = np.array([[0, 10], [10, 0]], dtype=float)
    with pytest.raises(ValueError, match="coordinates"):
        provider.get_congested_matrix(W, hour=9.0)


def test_google_routes_provider_rejects_mismatched_coords_count():
    provider = GoogleRoutesTrafficProvider(api_key="test-key", session=object())
    W = np.array([[0, 10, 20], [10, 0, 15], [20, 15, 0]], dtype=float)
    with pytest.raises(ValueError, match="must describe the same set of waypoints|must match"):
        provider.get_congested_matrix(W, hour=9.0, coords=[(1.0, 2.0), (3.0, 4.0)])


class _FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


class _FakeSession:
    """Captures the request GoogleRoutesTrafficProvider builds and returns
    a canned response — the same dependency-injection pattern
    qpu_solver.py's test-only `sampler=` stand-in uses, so wiring
    correctness (request shape, response parsing) is verified without real
    network access or credentials."""

    def __init__(self, response):
        self._response = response
        self.last_call = None

    def post(self, url, headers=None, json=None, timeout=None):
        self.last_call = {"url": url, "headers": headers, "json": json, "timeout": timeout}
        return self._response


def _three_point_matrix_response():
    # A 3x3 matrix (excluding the diagonal, which Google's API omits by
    # default) with genuinely asymmetric durations — real one-way streets
    # make A->B and B->A different, unlike the simulated provider's
    # symmetric multiplier model.
    return [
        {"originIndex": 0, "destinationIndex": 1, "duration": "600s", "status": {}},
        {"originIndex": 0, "destinationIndex": 2, "duration": "900s", "status": {}},
        {"originIndex": 1, "destinationIndex": 0, "duration": "650s", "status": {}},
        {"originIndex": 1, "destinationIndex": 2, "duration": "500s", "status": {}},
        {"originIndex": 2, "destinationIndex": 0, "duration": "870s", "status": {}},
        {"originIndex": 2, "destinationIndex": 1, "duration": "480s", "status": {}},
    ]


def test_google_routes_provider_parses_response_into_correct_matrix():
    session = _FakeSession(_FakeResponse(200, _three_point_matrix_response()))
    provider = GoogleRoutesTrafficProvider(api_key="test-key", session=session)
    W = np.zeros((3, 3))
    coords = [(12.97, 77.59), (12.93, 77.62), (12.91, 77.63)]

    matrix = provider.get_congested_matrix(W, hour=18.5, coords=coords)

    expected = np.array([
        [0.0, 10.0, 15.0],
        [10.833333, 0.0, 8.333333],
        [14.5, 8.0, 0.0],
    ])
    assert np.allclose(matrix, expected, atol=1e-4)
    # A real traffic matrix need not be symmetric (one-way streets etc.) —
    # confirm this provider doesn't silently force symmetry the way the
    # simulated multiplier model does.
    assert matrix[0, 1] != matrix[1, 0]


def test_google_routes_provider_builds_a_traffic_aware_request():
    session = _FakeSession(_FakeResponse(200, _three_point_matrix_response()))
    provider = GoogleRoutesTrafficProvider(api_key="test-key-abc", session=session)
    W = np.zeros((3, 3))
    coords = [(12.97, 77.59), (12.93, 77.62), (12.91, 77.63)]

    provider.get_congested_matrix(W, hour=18.5, coords=coords)

    call = session.last_call
    assert call["url"] == "https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix"
    assert call["headers"]["X-Goog-Api-Key"] == "test-key-abc"
    body = call["json"]
    assert body["routingPreference"] == "TRAFFIC_AWARE_OPTIMAL"
    assert body["travelMode"] == "DRIVE"
    assert len(body["origins"]) == 3
    assert len(body["destinations"]) == 3
    assert body["origins"][0]["waypoint"]["location"]["latLng"]["latitude"] == 12.97
    # departureTime must be a real, future RFC3339 timestamp whose
    # hour-of-day matches the requested `hour` — see next_occurrence_of_hour.
    assert body["departureTime"].endswith("Z")
    assert "18:30:00" in body["departureTime"]


def test_google_routes_provider_raises_on_http_error():
    session = _FakeSession(_FakeResponse(403, {"error": {"message": "API key not authorized"}}))
    provider = GoogleRoutesTrafficProvider(api_key="bad-key", session=session)
    W = np.zeros((2, 2))
    with pytest.raises(RuntimeError, match="403"):
        provider.get_congested_matrix(W, hour=9.0, coords=[(1.0, 2.0), (3.0, 4.0)])


def test_google_routes_provider_raises_on_per_pair_error_status():
    payload = [
        {"originIndex": 0, "destinationIndex": 1, "status": {"code": 5, "message": "NOT_FOUND"}},
        {"originIndex": 1, "destinationIndex": 0, "duration": "300s", "status": {}},
    ]
    session = _FakeSession(_FakeResponse(200, payload))
    provider = GoogleRoutesTrafficProvider(api_key="test-key", session=session)
    W = np.zeros((2, 2))
    with pytest.raises(RuntimeError, match="NOT_FOUND"):
        provider.get_congested_matrix(W, hour=9.0, coords=[(1.0, 2.0), (3.0, 4.0)])


def test_google_routes_provider_raises_on_missing_pairs():
    # Only one of the two required off-diagonal pairs came back.
    payload = [{"originIndex": 0, "destinationIndex": 1, "duration": "300s", "status": {}}]
    session = _FakeSession(_FakeResponse(200, payload))
    provider = GoogleRoutesTrafficProvider(api_key="test-key", session=session)
    W = np.zeros((2, 2))
    with pytest.raises(RuntimeError, match="missing"):
        provider.get_congested_matrix(W, hour=9.0, coords=[(1.0, 2.0), (3.0, 4.0)])


# --- next_occurrence_of_hour: translating a simulated "hour" into a real,
# future timestamp a live-traffic-prediction API can actually answer for ---

def test_next_occurrence_of_hour_is_always_in_the_future():
    now = dt.datetime(2026, 3, 15, 20, 0, 0, tzinfo=dt.timezone.utc)
    # 6pm has already passed today at 8pm "now" -> must roll to tomorrow.
    result = next_occurrence_of_hour(18.0, now=now)
    assert result > now
    assert result.date() == dt.date(2026, 3, 16)
    assert result.hour == 18


def test_next_occurrence_of_hour_same_day_when_still_ahead():
    now = dt.datetime(2026, 3, 15, 8, 0, 0, tzinfo=dt.timezone.utc)
    result = next_occurrence_of_hour(18.5, now=now)
    assert result.date() == dt.date(2026, 3, 15)
    assert result.hour == 18
    assert result.minute == 30


def test_next_occurrence_of_hour_handles_fractional_hours():
    now = dt.datetime(2026, 3, 15, 0, 0, 0, tzinfo=dt.timezone.utc)
    result = next_occurrence_of_hour(9.25, now=now)
    assert result.hour == 9
    assert result.minute == 15
