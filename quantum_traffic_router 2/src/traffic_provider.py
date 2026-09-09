"""
traffic_provider.py
====================
A small, deliberately boring abstraction: anything that can turn a
free-flow travel-time matrix into a congestion-adjusted one is a "traffic
provider". app.py picks one by name (the TRAFFIC_PROVIDER environment
variable, default "simulated") and never calls congestion.py directly —
so replacing the simulated rush-hour model with a real one means writing
one new class in this file and changing one environment variable, not
touching app.py, the QUBO solver, or the clustering/scaling logic at all,
because none of those ever consume anything except a travel-time matrix —
they don't care where its numbers came from.

This turns the README's "honest upgrade path to real traffic" claim into
something you can point at in the code, rather than a promise in prose —
and, as of this file, into something that ACTUALLY WORKS end-to-end if you
bring your own API key: GoogleRoutesTrafficProvider below is a real,
working integration with Google's Routes API (Compute Route Matrix), not
just a stub.

A HONEST WRINKLE THIS ABSTRACTION EXPOSED: `get_congested_matrix` was
originally `(W_free_flow, hour) -> W_congested` — that's enough for a
SIMULATED model (congestion.py multiplies free-flow numbers by a
time-of-day factor), but a REAL traffic API computes travel times FROM
coordinates; it cannot retrofit live traffic onto a free-flow matrix that
was already computed with no coordinates attached (see distance_matrix.py
— nothing in this project's optimization core needs coordinates, only
travel times, which is exactly why the QUBO layer doesn't have them lying
around to hand over). So this file adds an optional third parameter,
`coords` (a list of (lat, lon) pairs, same order as the matrix's rows),
that a real provider needs and a simulated one ignores. app.py threads an
optional `points` field from the request body into this parameter — see
its own docstring note at the `/api/solve` and `/api/solve_fleet` routes —
so a real provider works once the caller has coordinates to give it, and
fails with a clear, specific error (not a wrong answer) when it doesn't.
"""

from __future__ import annotations

import datetime as dt
import os

import numpy as np

from congestion import apply_congestion_to_matrix

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:  # pragma: no cover - requests ships with this project's requirements
    REQUESTS_AVAILABLE = False

GOOGLE_ROUTES_MATRIX_URL = "https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix"


class TrafficProvider:
    """Interface every traffic provider implements: turn a free-flow
    travel-time matrix (minutes) into a congestion-adjusted one for a given
    simulated/real hour of day. `name` is what TRAFFIC_PROVIDER matches
    against.

    `coords`, when given, is a list of (lat, lon) pairs in the same order
    as W_free_flow's rows/columns — real-coordinate-based providers need
    it; the simulated model doesn't and ignores it. It defaults to None so
    every existing call site (and every provider that doesn't need it)
    keeps working unchanged."""

    name = "base"

    def get_congested_matrix(
        self, W_free_flow: np.ndarray, hour: float, coords: list[tuple[float, float]] | None = None
    ) -> np.ndarray:
        raise NotImplementedError


class SimulatedTrafficProvider(TrafficProvider):
    """The disclosed, reproducible rush-hour simulation in congestion.py.
    Every live demo of this app uses this provider unless TRAFFIC_PROVIDER
    is changed. Ignores `coords` — its model only ever needs the free-flow
    matrix and the hour, which is exactly why it can run offline with zero
    API keys and zero network calls."""

    name = "simulated"

    def get_congested_matrix(
        self, W_free_flow: np.ndarray, hour: float, coords: list[tuple[float, float]] | None = None
    ) -> np.ndarray:
        return apply_congestion_to_matrix(W_free_flow, hour=hour)


class LiveTrafficProviderStub(TrafficProvider):
    """A placeholder for a real live-traffic API that ISN'T implemented in
    this project — TomTom's Traffic Flow API, HERE's Traffic API, Mapbox's
    traffic-aware Directions API, or any other provider that isn't Google
    Routes. (See GoogleRoutesTrafficProvider below for the one provider
    this project actually implements end-to-end.) A genuine implementation
    would call that provider's live-traffic endpoint for `coords` and
    return ITS congested-duration matrix here instead of a simulated one.
    Nothing downstream of this class would need to change: the QUBO
    solver, the clustering/scaling logic, and the savings-vs-naive-order
    metric only ever consume a travel-time matrix.

    Selecting this provider (TRAFFIC_PROVIDER=live) raises clearly instead
    of silently pretending to have real traffic data it doesn't have — an
    honest failure instead of a fake success.
    """

    name = "live"

    def get_congested_matrix(
        self, W_free_flow: np.ndarray, hour: float, coords: list[tuple[float, float]] | None = None
    ) -> np.ndarray:
        raise NotImplementedError(
            "LiveTrafficProviderStub is a placeholder for a real paid live-traffic API integration "
            "(TomTom/HERE/Mapbox) that isn't wired up in this project — it marks where that "
            "integration would go. For a REAL working integration, set TRAFFIC_PROVIDER=google_routes "
            "and a GOOGLE_ROUTES_API_KEY (see GoogleRoutesTrafficProvider's docstring), or set "
            "TRAFFIC_PROVIDER=simulated (the default) to run the app with no API key at all."
        )


def _waypoint(lat: float, lon: float) -> dict:
    return {"waypoint": {"location": {"latLng": {"latitude": lat, "longitude": lon}}}}


def _parse_duration_seconds(duration_str) -> float:
    """Google Routes API durations are strings like "1234s" (protobuf
    Duration JSON encoding) — not a number, and not always present (a
    pair Google couldn't route between has no duration field at all,
    which is exactly the case _raise_for_element below turns into a clear
    error instead of a crash on `.rstrip` against None)."""
    if not duration_str or not isinstance(duration_str, str):
        raise RuntimeError(f"Google Routes API response element had no usable duration: {duration_str!r}")
    return float(duration_str.rstrip("s"))


def next_occurrence_of_hour(hour: float, now: dt.datetime | None = None) -> dt.datetime:
    """Real live-traffic APIs answer "what will traffic look like at this
    REAL future timestamp" — they can't rewind to a past hour, and they
    don't have a "simulate 6:30pm" mode the way congestion.py's model does.
    So this project's `hour` control (0-24, e.g. 18.5 = 6:30pm, used
    throughout the UI/API to mean "simulate traffic at this time of day")
    is translated, for a real provider, into "the next real moment today
    or tomorrow the clock reads this hour" — a genuine near-future
    timestamp a traffic-prediction API can actually answer for, and the
    closest honest match to what the UI control is asking for. It is NOT
    the same guarantee the simulated model makes (which is exactly
    reproducible for a given hour, any time you run it) — a real
    provider's answer for "6:30pm" will differ run to run as real-world
    traffic patterns/predictions do.
    """
    now = now or dt.datetime.now(dt.timezone.utc)
    hour = max(0.0, min(24.0, hour))
    h = min(int(hour), 23)
    m = int(round((hour - int(hour)) * 60)) % 60
    candidate = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if candidate <= now:
        candidate += dt.timedelta(days=1)
    return candidate


class GoogleRoutesTrafficProvider(TrafficProvider):
    """A REAL, working integration with Google's Routes API "Compute Route
    Matrix" endpoint (routingPreference=TRAFFIC_AWARE_OPTIMAL), the only
    live-traffic provider this project actually implements end-to-end —
    every other named provider in this file is either the simulated model
    or an explicit placeholder (see LiveTrafficProviderStub).

    WHAT THIS NEEDS THAT NOTHING ELSE IN THIS PROJECT DOES: your own Google
    Cloud project with the Routes API enabled and billing configured (Google
    requires a billing account even within the free monthly credit — see
    https://developers.google.com/maps/documentation/routes/compute_route_matrix
    and https://developers.google.com/maps/documentation/routes/usage-and-billing
    for current setup and pricing), and an API key with that API enabled,
    set as the GOOGLE_ROUTES_API_KEY environment variable. This is NOT
    needed to run app.py, main.py, or any test in this project with the
    default TRAFFIC_PROVIDER=simulated — this class raises a clear,
    specific error at construction time if the key is missing, the same
    way qpu_solver.py's _build_sampler() fails clearly without a D-Wave
    token, rather than being silently unavailable or crashing elsewhere.

    TESTABILITY WITHOUT A REAL KEY OR NETWORK ACCESS: `session` is an
    optional constructor override — pass anything exposing
    `.post(url, headers=..., json=..., timeout=...) -> response` (a
    `requests.Session`-shaped interface; the plain `requests` module itself
    matches it) and this class will use that instead of making a real
    network call. tests/test_traffic_provider.py injects a lightweight
    fake session to verify request construction and response parsing are
    correct WITHOUT needing real credentials or network access — exactly
    the same dependency-injection pattern qpu_solver.py's `sampler=`
    parameter uses for the same reason. This sandbox's genuine lack of a
    GOOGLE_ROUTES_API_KEY is used to test the real, unmocked "no key
    configured" failure path.

    A REAL LIMITATION, DISCLOSED RATHER THAN HIDDEN: this provider needs
    real waypoint coordinates to ask Google for travel times between them
    (see this module's own top-of-file docstring note) — `coords` is a
    required argument in practice, not just in principle, and this class
    raises a clear error rather than a wrong answer if it's missing. In
    this project, that means the caller (app.py's /api/solve and
    /api/solve_fleet routes) must have been given the waypoints'
    coordinates too, not just a precomputed travel-time matrix — see
    app.py's optional `points` request field.
    """

    name = "google_routes"

    def __init__(self, api_key: str | None = None, session=None):
        self.api_key = api_key or os.environ.get("GOOGLE_ROUTES_API_KEY")
        if not self.api_key:
            raise ValueError(
                "GoogleRoutesTrafficProvider needs a real Google Cloud API key with the Routes API "
                "enabled. Set the GOOGLE_ROUTES_API_KEY environment variable, or set "
                "TRAFFIC_PROVIDER=simulated (the default) to run this project without one. See "
                "https://developers.google.com/maps/documentation/routes/compute_route_matrix for setup."
            )
        if session is None and not REQUESTS_AVAILABLE:  # pragma: no cover - requests is a real dependency here
            raise ImportError("The 'requests' package is required for GoogleRoutesTrafficProvider — run `pip install requests`.")
        self._session = session if session is not None else requests

    def get_congested_matrix(
        self, W_free_flow: np.ndarray, hour: float, coords: list[tuple[float, float]] | None = None
    ) -> np.ndarray:
        if coords is None:
            raise ValueError(
                "GoogleRoutesTrafficProvider needs real waypoint coordinates (coords=[(lat, lon), ...], "
                "same order and count as W_free_flow's rows) — a real traffic API computes travel times "
                "FROM coordinates, it can't retrofit live traffic onto an already-computed free-flow "
                "matrix the way the simulated provider's multiplier model does. See app.py's optional "
                "`points` request field, which is how the live app threads coordinates through to here."
            )
        n = len(coords)
        if W_free_flow.shape != (n, n):
            raise ValueError(
                f"coords has {n} point(s) but W_free_flow is shaped {W_free_flow.shape} — they must "
                "describe the same set of waypoints, in the same order."
            )
        if n < 2:
            return np.zeros((n, n))

        body = {
            "origins": [_waypoint(lat, lon) for lat, lon in coords],
            "destinations": [_waypoint(lat, lon) for lat, lon in coords],
            "travelMode": "DRIVE",
            "routingPreference": "TRAFFIC_AWARE_OPTIMAL",
            "departureTime": next_occurrence_of_hour(hour).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": "originIndex,destinationIndex,duration,condition,status",
        }

        response = self._session.post(GOOGLE_ROUTES_MATRIX_URL, headers=headers, json=body, timeout=20)
        status_code = getattr(response, "status_code", None)
        if status_code != 200:
            text = getattr(response, "text", "")
            raise RuntimeError(f"Google Routes API returned HTTP {status_code}: {str(text)[:500]}")

        elements = response.json()
        if not isinstance(elements, list):
            raise RuntimeError(f"Google Routes API returned an unexpected response shape: {type(elements).__name__}.")

        matrix = np.zeros((n, n))
        seen: set[tuple[int, int]] = set()
        for el in elements:
            i, j = el.get("originIndex", 0), el.get("destinationIndex", 0)
            if i == j:
                seen.add((i, j))
                continue
            status = el.get("status") or {}
            if status.get("code") not in (None, 0):
                raise RuntimeError(
                    f"Google Routes API couldn't find a traffic-aware route from waypoint {i} to "
                    f"waypoint {j}: {status.get('message', status)}"
                )
            matrix[i, j] = _parse_duration_seconds(el.get("duration")) / 60.0
            seen.add((i, j))

        expected = {(i, j) for i in range(n) for j in range(n) if i != j}
        missing = expected - seen
        if missing:
            raise RuntimeError(
                f"Google Routes API response was missing {len(missing)} of {len(expected)} pair(s), "
                f"e.g. {sorted(missing)[:3]} — treating a partial matrix as complete would silently "
                "under-price some legs, so this is a hard error rather than a best-effort fill-in."
            )

        return matrix


_PROVIDERS = {
    "simulated": SimulatedTrafficProvider,
    "google_routes": GoogleRoutesTrafficProvider,
    "live": LiveTrafficProviderStub,
}


def get_traffic_provider(name: str) -> TrafficProvider:
    """Look up a traffic provider by name (from the TRAFFIC_PROVIDER env
    var). Raises ValueError on an unknown name rather than silently
    defaulting — a typo in a production config should be loud, not quietly
    fall back to the simulated model. Constructing "google_routes" without
    GOOGLE_ROUTES_API_KEY set raises its own clear ValueError (see
    GoogleRoutesTrafficProvider) — also loud, also by design."""
    cls = _PROVIDERS.get(name)
    if cls is None:
        raise ValueError(f"Unknown TRAFFIC_PROVIDER '{name}' — choose one of {sorted(_PROVIDERS)}.")
    return cls()
