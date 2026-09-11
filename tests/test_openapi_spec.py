"""Sanity checks on openapi.yaml — not a full OpenAPI validator, just
enough to catch the most common way docs silently rot: someone changes a
field name or status code in app.py and forgets the spec, or the YAML
itself becomes malformed. This won't catch every drift, but it locks in
that the file at least parses and still describes the two real endpoints
with their real request/response fields."""

import os

import pytest

yaml = pytest.importorskip("yaml", reason="pyyaml not installed")

_SPEC_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "openapi.yaml")


@pytest.fixture(scope="module")
def spec():
    with open(_SPEC_PATH) as f:
        return yaml.safe_load(f)


def test_spec_file_exists_and_parses(spec):
    assert spec["openapi"].startswith("3.")


def test_both_live_endpoints_are_documented(spec):
    assert "/api/solve" in spec["paths"]
    assert "/api/solve_fleet" in spec["paths"]
    assert "post" in spec["paths"]["/api/solve"]
    assert "post" in spec["paths"]["/api/solve_fleet"]


def test_analytics_endpoint_is_documented(spec):
    assert "/api/analytics" in spec["paths"]
    assert "get" in spec["paths"]["/api/analytics"]


def test_capabilities_endpoint_is_documented(spec):
    assert "/api/capabilities" in spec["paths"]
    assert "get" in spec["paths"]["/api/capabilities"]


def test_insights_endpoint_is_documented(spec):
    assert "/api/insights" in spec["paths"]
    assert "get" in spec["paths"]["/api/insights"]


@pytest.mark.parametrize("schema_name", [
    "SolveRequest", "SolveResponse", "SolveFleetRequest", "SolveFleetResponse",
    "AnalyticsResponse", "CapabilitiesResponse", "InsightsResponse", "ErrorResponse", "RouteExplanation",
])
def test_expected_schemas_are_defined(spec, schema_name):
    assert schema_name in spec["components"]["schemas"]


def test_solve_response_fields_match_the_real_app_py_response(spec):
    """These field names must match app.py's solve() jsonify(...) call
    exactly — this is the property most likely to silently drift."""
    props = set(spec["components"]["schemas"]["SolveResponse"]["properties"].keys())
    expected = {
        "order", "cost_minutes", "free_flow_minutes", "naive_order_minutes",
        "savings_vs_naive_pct", "hour_simulated", "method", "solve_ms",
        "clusters_used", "incident_applied", "precedence_applied", "precedence_satisfied",
        "explanation", "time_windows_applied", "time_window_checks", "all_time_windows_satisfied",
    }
    assert expected <= props


def test_solve_fleet_response_fields_match_the_real_app_py_response(spec):
    props = set(spec["components"]["schemas"]["SolveFleetResponse"]["properties"].keys())
    expected = {
        "vehicles", "total_cost_minutes", "total_free_flow_minutes",
        "n_vehicles_used", "hour_simulated", "method", "solve_ms", "max_stops_per_vehicle",
        "vehicle_capacity", "explanation", "incident_applied",
    }
    assert expected <= props


def test_analytics_response_fields_match_analytics_py_snapshot(spec):
    """Must match src/analytics.py's snapshot() dict keys exactly — this
    field list is small enough that drift would be easy to miss otherwise."""
    props = set(spec["components"]["schemas"]["AnalyticsResponse"]["properties"].keys())
    expected = {
        "since", "uptime_seconds", "total_solves", "solves_by_endpoint",
        "solves_by_method", "avg_solve_ms", "errors", "incident_simulations",
        "precedence_requests", "demand_weight_requests", "note",
    }
    assert expected == props
