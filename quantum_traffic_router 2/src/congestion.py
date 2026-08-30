"""
congestion.py
=============
Turns the congestion-neutral road graph into a time-varying, congested one.

Two ingredients, both explained in the README's "how to make this more
real" section:

1. A rush-hour multiplier curve (time-of-day -> city-wide congestion factor).
2. Per-edge randomized variation, seeded for reproducibility, so different
   roads get hit differently by the same rush hour.

`apply_congestion()` is also where you would plug in something calibrated
from real data (e.g., vehicle-density counts from a UVH-26-style
CCTV/vision pipeline, or a live traffic-index API) instead of the
synthetic model — the rest of the pipeline (distance_matrix, qubo_tsp,
baseline) only ever consumes the resulting `congested_minutes` edge
attribute, so it doesn't care where that number came from.
"""

import math
import random
import networkx as nx


def rush_hour_multiplier(hour: float) -> float:
    """City-wide congestion multiplier for a given hour of day (0-24, float).

    1.0 = free flow. Peaks around 9am and 6:30pm, modeled as two Gaussian
    bumps on top of a mild all-day baseline — a standard, simple stand-in
    for a real traffic-index curve.
    """
    def bump(center, width, height):
        return height * math.exp(-((hour - center) ** 2) / (2 * width ** 2))

    baseline = 1.05
    morning_peak = bump(center=9.0, width=1.3, height=1.6)
    evening_peak = bump(center=18.5, width=1.5, height=1.9)
    return baseline + morning_peak + evening_peak


def apply_congestion(
    G: nx.Graph,
    hour: float = 18.5,
    seed: int = 42,
    spike_edges: list | None = None,
    spike_multiplier: float = 3.0,
) -> nx.Graph:
    """Return a COPY of G with a `congested_minutes` attribute on every edge.

    Args:
        G: congestion-neutral graph from city_graph.build_*_graph().
        hour: time of day (0-24) to simulate, e.g. 18.5 = 6:30pm.
        seed: RNG seed, so a given (hour, seed) always reproduces the same
              congestion pattern — important for fair before/after benchmarks.
        spike_edges: optional list of (u, v) edges to hit with an extra
              incident-style congestion spike (models an accident, a
              waterlogged underpass, a VIP-movement road closure, etc.) —
              this is what you use to demonstrate re-optimization when
              conditions change mid-route.
        spike_multiplier: how much worse the spiked edges get, on top of
              their normal rush-hour congestion.
    """
    Gc = G.copy()
    rng = random.Random(seed)
    city_multiplier = rush_hour_multiplier(hour)
    spike_edges = set(frozenset(e) for e in (spike_edges or []))

    for u, v, data in Gc.edges(data=True):
        per_edge_noise = rng.uniform(0.85, 1.25)  # some roads are just worse than others
        multiplier = city_multiplier * per_edge_noise
        if frozenset((u, v)) in spike_edges:
            multiplier *= spike_multiplier
        data["congestion_multiplier"] = round(multiplier, 3)
        data["congested_minutes"] = data["free_flow_minutes"] * multiplier

    Gc.graph["simulated_hour"] = hour
    Gc.graph["seed"] = seed
    return Gc


if __name__ == "__main__":
    from city_graph import build_demo_graph

    G = build_demo_graph()
    for hour, label in [(3.0, "3am (empty)"), (9.0, "9am (morning peak)"), (18.5, "6:30pm (evening peak)")]:
        Gc = apply_congestion(G, hour=hour)
        avg_mult = sum(d["congestion_multiplier"] for _, _, d in Gc.edges(data=True)) / Gc.number_of_edges()
        print(f"{label:20s} -> avg congestion multiplier {avg_mult:.2f}x")
