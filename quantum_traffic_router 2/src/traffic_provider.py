"""
traffic_provider.py
====================
A small, deliberately boring abstraction: anything that can turn a
free-flow travel-time matrix into a congestion-adjusted one is a "traffic
provider". app.py picks one by name (the TRAFFIC_PROVIDER environment
variable, default "simulated") and never calls congestion.py directly —
so replacing the simulated rush-hour model with a real one (Google Routes
API, TomTom Traffic, HERE Traffic, Mapbox traffic-aware directions) means
writing one new class in this file and changing one environment variable,
not touching app.py, the QUBO solver, or the clustering/scaling logic at
all, because none of those ever consume anything except a travel-time
matrix — they don't care where its numbers came from.

This turns the README's "honest upgrade path to real traffic" claim into
something you can point at in the code, rather than a promise in prose.
"""

from __future__ import annotations

import numpy as np

from congestion import apply_congestion_to_matrix


class TrafficProvider:
    """Interface every traffic provider implements: turn a free-flow
    travel-time matrix (minutes) into a congestion-adjusted one for a given
    simulated/real hour of day. `name` is what TRAFFIC_PROVIDER matches
    against."""

    name = "base"

    def get_congested_matrix(self, W_free_flow: np.ndarray, hour: float) -> np.ndarray:
        raise NotImplementedError


class SimulatedTrafficProvider(TrafficProvider):
    """The only provider actually implemented in this project today: the
    disclosed, reproducible rush-hour simulation in congestion.py. Every
    live demo of this app uses this provider unless TRAFFIC_PROVIDER is
    changed."""

    name = "simulated"

    def get_congested_matrix(self, W_free_flow: np.ndarray, hour: float) -> np.ndarray:
        return apply_congestion_to_matrix(W_free_flow, hour=hour)


class LiveTrafficProviderStub(TrafficProvider):
    """NOT a real integration — a placeholder showing exactly where a real,
    paid live-traffic API would plug in. A genuine implementation would
    call that provider's live-traffic endpoint for the same set of points
    (e.g. Google Routes API's traffic-aware ETAs, TomTom's Traffic Flow
    API, or HERE's Traffic API) and return ITS congested-duration matrix
    here instead of a simulated one. Nothing downstream of this class
    would need to change: the QUBO solver, the clustering/scaling logic,
    and the savings-vs-naive-order metric only ever consume a travel-time
    matrix.

    Selecting this provider (TRAFFIC_PROVIDER=live) raises clearly instead
    of silently pretending to have real traffic data it doesn't have — an
    honest failure instead of a fake success.
    """

    name = "live"

    def get_congested_matrix(self, W_free_flow: np.ndarray, hour: float) -> np.ndarray:
        raise NotImplementedError(
            "LiveTrafficProviderStub is a placeholder for a real paid live-traffic "
            "API integration (Google/TomTom/HERE/Mapbox) — it marks where that "
            "integration would go, but isn't wired up to a real provider yet. "
            "Set TRAFFIC_PROVIDER=simulated (the default) to run the app."
        )


_PROVIDERS = {
    "simulated": SimulatedTrafficProvider,
    "live": LiveTrafficProviderStub,
}


def get_traffic_provider(name: str) -> TrafficProvider:
    """Look up a traffic provider by name (from the TRAFFIC_PROVIDER env
    var). Raises ValueError on an unknown name rather than silently
    defaulting — a typo in a production config should be loud, not quietly
    fall back to the simulated model."""
    cls = _PROVIDERS.get(name)
    if cls is None:
        raise ValueError(f"Unknown TRAFFIC_PROVIDER '{name}' — choose one of {sorted(_PROVIDERS)}.")
    return cls()
