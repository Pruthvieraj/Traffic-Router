#!/usr/bin/env python3
"""
app.py — the "click anywhere in the city" interactive routing server.

    python3 app.py

Then open http://127.0.0.1:5000 in a browser. Click on the map to drop a
Start pin, then an End pin, then (optionally) more stops in between — hit
"Solve route" and it computes the best visiting order between your actual
clicked points, using a REAL OpenStreetMap street network (not the fixed
dozen landmarks the static multi_city_map.html demo uses), and draws the
route following real streets.

Why this needs a running server (unlike multi_city_map.html, which is a
self-contained file you can just double-click): solving an arbitrary click
requires fetching/snapping against real street-network data and running
the QUBO solver on demand, which means real Python code has to run in
response to each click — a static HTML file can't do that on its own.

First click on a city takes a few seconds longer (fetching real street
data from OpenStreetMap over the internet); after that it's cached to
disk (data/street_graphs/<city>.graphml) and instant on every later run.
If OpenStreetMap's data API isn't reachable (blocked/flaky wifi), this
automatically falls back to the same curated dozen-landmark network the
static demo uses, and says so on the page.
"""

import os
import sys
import traceback

from flask import Flask, request, jsonify, render_template

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from city_graph import get_or_build_street_graph, nearest_node, list_cities, CITIES, _city_center
from congestion import apply_congestion
from distance_matrix import build_travel_time_matrix, path_to_coords
from qubo_tsp import solve_quantum_inspired, solve_open_path_quantum_inspired, open_path_length
from baseline import nearest_neighbor_2opt, nearest_neighbor_2opt_open_path
from build_multi_city_map import load_inline_leaflet

app = Flask(__name__)

MAX_STOPS = 10  # keeps the QUBO solve fast (N^2 binary variables) for a live in-browser demo
_GRAPH_CACHE: dict[str, object] = {}  # in-process cache so repeat clicks in one session don't re-fetch/re-load


def _graph_for(city: str):
    if city not in _GRAPH_CACHE:
        _GRAPH_CACHE[city] = get_or_build_street_graph(city)
    return _GRAPH_CACHE[city]


_LEAFLET_CSS, _LEAFLET_JS = load_inline_leaflet()


@app.route("/")
def index():
    return render_template(
        "click_router.html",
        cities=list_cities(),
        centers={c: list(_city_center(c)) for c in list_cities()},
        leaflet_css=_LEAFLET_CSS,
        leaflet_js=_LEAFLET_JS,
    )


@app.route("/api/solve", methods=["POST"])
def solve():
    body = request.get_json(force=True)
    city = body.get("city")
    points = body.get("points", [])
    method = body.get("method", "quantum")
    hour = float(body.get("hour", 18.5))

    if city not in CITIES:
        return jsonify({"error": f"Unknown city '{city}'"}), 400
    if len(points) < 2:
        return jsonify({"error": "Need at least a start and an end point."}), 400
    if len(points) > MAX_STOPS:
        return jsonify({"error": f"Please use at most {MAX_STOPS} points for a live demo-speed solve."}), 400

    try:
        G = _graph_for(city)
        Gc = apply_congestion(G, hour=hour, seed=42)

        # snap each click to the nearest real node in the (real-street or
        # fallback-curated) graph, and report how far off each click was so
        # the UI can be honest about "you clicked open ground, nearest real
        # junction was 350m away" rather than silently teleporting the pin
        snapped_nodes, snap_info = [], []
        for lat, lon in points:
            node, dist_km = nearest_node(Gc, lat, lon)
            snapped_nodes.append(node)
            snap_info.append({"node_lat": Gc.nodes[node]["lat"], "node_lon": Gc.nodes[node]["lon"],
                               "snap_distance_m": round(dist_km * 1000)})

        # de-duplicate while preserving order (two clicks can legitimately
        # snap to the same real intersection if they were close together)
        seen = set()
        unique_indices = [i for i, n in enumerate(snapped_nodes) if not (n in seen or seen.add(n))]
        if len(unique_indices) < 2:
            return jsonify({"error": "Your points all snapped to the same road junction — spread them out a bit more."}), 400

        waypoints = [snapped_nodes[i] for i in unique_indices]
        start_idx, end_idx = 0, len(waypoints) - 1
        W, paths = build_travel_time_matrix(Gc, waypoints)

        if method == "classical":
            result = nearest_neighbor_2opt_open_path(W, start_idx, end_idx)
        else:
            result = solve_open_path_quantum_inspired(W, start_idx, end_idx, num_reads=300)

        order = result["path"]  # indices into `waypoints`

        # stitch the full route as a real, street-following polyline by
        # concatenating each consecutive leg's actual shortest path
        full_route_coords = []
        for i in range(len(order) - 1):
            leg_key = (waypoints[order[i]], waypoints[order[i + 1]])
            leg_path = paths[leg_key]
            coords = path_to_coords(Gc, leg_path)
            full_route_coords.extend(coords if i == 0 else coords[1:])  # avoid duplicating the junction point

        return jsonify({
            "source": Gc.graph.get("source", "unknown"),
            "fallback_reason": Gc.graph.get("fallback_reason"),
            "order": order,
            "snap_info": [snap_info[i] for i in unique_indices],
            "route_path": full_route_coords,
            "cost_minutes": round(result["cost"], 1),
            "method": method,
            "solve_ms": round(result.get("wall_seconds", 0) * 1000),
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    # PORT is set automatically by cloud hosts (Render, Railway, etc.) — falls
    # back to 5000 for local runs on your own machine.
    port = int(os.environ.get("PORT", 5000))
    print(f"Starting the click-anywhere router at http://127.0.0.1:{port}")
    print("(First solve per city fetches real OpenStreetMap street data — a few seconds; cached after that.)")
    app.run(debug=False, host="0.0.0.0", port=port)
