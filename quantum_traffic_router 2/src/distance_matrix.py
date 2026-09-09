"""
distance_matrix.py
===================
Reduces "find the best route visiting these delivery stops" on a big road
network down to a small pairwise travel-time matrix between just the
waypoints — which is what turns this into a clean Traveling-Salesman-style
problem that a QUBO can actually represent with a manageable number of
variables (N^2 binary variables for N waypoints).

For every pair of waypoints, we run Dijkstra on the full congested road
graph (so the "distance" between two delivery stops already accounts for
the best real route between them, congestion included, not just a straight
line) and cache the result in an N x N matrix.
"""

import itertools
import networkx as nx
import numpy as np


def build_travel_time_matrix(Gc: nx.Graph, waypoints: list[str]) -> np.ndarray:
    """Return an (N, N) numpy array of shortest congested travel time (minutes)
    between every pair of waypoints, using Dijkstra over `congested_minutes`.

    Gc must already have congestion applied (see congestion.apply_congestion).
    Raises if any waypoint is missing from the graph, or if two waypoints
    are not connected at all (shouldn't happen on a normal road network).
    """
    missing = [w for w in waypoints if w not in Gc.nodes]
    if missing:
        raise ValueError(f"Waypoints not found in graph: {missing}")

    n = len(waypoints)
    matrix = np.zeros((n, n))
    paths: dict[tuple[str, str], list[str]] = {}

    for i, j in itertools.combinations(range(n), 2):
        src, dst = waypoints[i], waypoints[j]
        try:
            length = nx.dijkstra_path_length(Gc, src, dst, weight="congested_minutes")
            path = nx.dijkstra_path(Gc, src, dst, weight="congested_minutes")
        except nx.NetworkXNoPath as e:
            raise ValueError(f"No route between {src} and {dst} in this graph.") from e
        matrix[i, j] = matrix[j, i] = length
        paths[(src, dst)] = path
        paths[(dst, src)] = list(reversed(path))

    return matrix, paths


def build_distance_matrix(Gc: nx.Graph, waypoints: list[str]) -> np.ndarray:
    """Return an (N, N) numpy array of shortest real-world road distance
    (km) between every pair of waypoints, using Dijkstra over `length_km` —
    every edge in this project's graphs already carries that attribute (see
    city_graph.py), so this needed no new data, just a different edge
    weight to route on.

    WHY THIS EXISTS: this is the project's second optimization objective
    (see qubo_tsp.py's multi-objective support / "Multi-objective routing"
    in README.md) — a genuinely different quantity from travel TIME, not a
    scaled copy of it. Congestion changes which route is fastest without
    changing which route is shortest, so the distance-shortest path and the
    time-shortest path between the same two waypoints can legitimately
    differ (and often do, once congestion.apply_congestion has been
    applied to Gc) — that's what makes "minimize time" and "minimize
    distance" (a real proxy for fuel/emissions, which scale primarily with
    distance traveled, not time spent) an actual multi-objective trade-off
    rather than two names for the same number.

    Same shape and same waypoint ordering as build_travel_time_matrix's
    output, so the two matrices can be combined directly (see
    qubo_tsp.combine_objectives) or compared entry-by-entry.
    """
    missing = [w for w in waypoints if w not in Gc.nodes]
    if missing:
        raise ValueError(f"Waypoints not found in graph: {missing}")

    n = len(waypoints)
    matrix = np.zeros((n, n))

    for i, j in itertools.combinations(range(n), 2):
        src, dst = waypoints[i], waypoints[j]
        try:
            length = nx.dijkstra_path_length(Gc, src, dst, weight="length_km")
        except nx.NetworkXNoPath as e:
            raise ValueError(f"No route between {src} and {dst} in this graph.") from e
        matrix[i, j] = matrix[j, i] = length

    return matrix


def path_to_coords(Gc: nx.Graph, path: list[str]) -> list[list[float]]:
    """Turn a node-id path (as returned in the `paths` dict above) into a
    list of [lat, lon] pairs — this is what makes the map draw a route that
    actually follows real streets, instead of a straight line jumping
    between waypoints."""
    return [[Gc.nodes[n]["lat"], Gc.nodes[n]["lon"]] for n in path]


if __name__ == "__main__":
    from city_graph import build_demo_graph
    from congestion import apply_congestion

    G = build_demo_graph()
    Gc = apply_congestion(G, hour=18.5)
    waypoints = ["Majestic", "Indiranagar", "Koramangala", "HSR Layout", "Silk Board", "Jayanagar"]
    matrix, paths = build_travel_time_matrix(Gc, waypoints)
    print("Waypoints:", waypoints)
    print("Travel-time matrix (minutes):")
    print(np.round(matrix, 1))
