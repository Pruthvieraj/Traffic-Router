#!/usr/bin/env python3
"""
app.py — the "click anywhere in the city" interactive routing server.

    python3 app.py

Then open http://127.0.0.1:5000 in a browser. Click on the map (or search a
place name) to drop a Start pin, then an End pin, then optionally more
stops in between — hit "Solve route" and it computes the best visiting
order and draws a real, street-following route.

ARCHITECTURE (rewritten to be reliable on cloud hosts): earlier versions of
this file fetched OpenStreetMap street data on the SERVER using osmnx,
which depends on reaching the public Overpass API from wherever app.py is
running. That works fine from a laptop but routinely fails from cloud
hosts (Render, AWS, etc.) — Overpass's operators rate-limit or block
traffic from datacenter IP ranges to protect the service from bots, so the
exact same code that worked locally would silently fall back to a tiny
curated landmark network once deployed, producing straight-line "routes."

The fix: real road-network queries now happen in the BROWSER, not on this
server, using OSRM (router.project-osrm.org) — the same class of public
routing engine real map apps use, which is designed for and permits
client-side use, and which the browser reaches from the visitor's own
ordinary internet connection rather than a flagged datacenter IP. Two OSRM
calls happen client-side (see templates/click_router.html):
  1. Table API — a real, road-network-based travel-time matrix between all
     clicked/searched points (not a straight-line estimate).
  2. Route API — the actual street-following geometry, in the solved
     visiting order, for drawing the route on the map.

This server's only job is the part that genuinely needs a backend: solving
the visiting-order optimization (the QUBO / quantum-inspired step, or the
classical baseline) given a travel-time matrix the browser already
computed. No osmnx, no Overpass, no local street graph, no "snapped Nm
from the nearest known junction" — OSRM handles real-world snapping to the
road network itself, so any point on/near an actual road works, anywhere.
"""

import os
import sys
import traceback

import numpy as np
from flask import Flask, request, jsonify, render_template

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from city_graph import list_cities, _city_center  # noqa: E402  (just city names + map centers, no network calls)
from clustering import solve_open_path_scalable  # noqa: E402
from build_multi_city_map import load_inline_leaflet  # noqa: E402

app = Flask(__name__)

# A single QUBO stays exact and fast up to about a dozen stops (its variable
# count grows with the square of the interior stop count). Past that,
# solve_open_path_scalable() automatically clusters stops into groups of
# CLUSTER_SIZE and solves each group exactly, stitching the results — see
# src/clustering.py. MAX_STOPS is a live-demo-speed ceiling, not a hard
# QUBO limit; raise it further if you're comfortable with slower solves.
MAX_STOPS = 40
CLUSTER_SIZE = 9

_LEAFLET_CSS, _LEAFLET_JS = load_inline_leaflet()


@app.route("/")
def index():
    return render_template(
        "click_router.html",
        cities=list_cities(),
        centers={c: list(_city_center(c)) for c in list_cities()},
        leaflet_css=_LEAFLET_CSS,
        leaflet_js=_LEAFLET_JS,
        max_stops=MAX_STOPS,
    )


@app.route("/api/solve", methods=["POST"])
def solve():
    """Takes a travel-time matrix the browser already computed via OSRM
    and returns the optimal fixed-start/fixed-end visiting order. This
    endpoint does no mapping/geocoding/street-data work at all — it's pure
    optimization, which is why it's fast and has nothing left to fail on
    a cloud host."""
    body = request.get_json(force=True)
    matrix = body.get("matrix")
    method = body.get("method", "quantum")

    if not isinstance(matrix, list) or len(matrix) < 2:
        return jsonify({"error": "Need a travel-time matrix for at least 2 points."}), 400
    n = len(matrix)
    if n > MAX_STOPS:
        return jsonify({"error": f"Please use at most {MAX_STOPS} points for a live demo-speed solve."}), 400
    if any(not isinstance(row, list) or len(row) != n for row in matrix):
        return jsonify({"error": "Matrix must be square (NxN)."}), 400

    try:
        # OSRM durations are in seconds; the solver/report everywhere else
        # in this project works in minutes, so convert once here.
        W = np.array(matrix, dtype=float) / 60.0
        start_idx, end_idx = 0, n - 1

        # solve_open_path_scalable is an exact passthrough to the direct
        # QUBO/classical solver at or below CLUSTER_SIZE interior stops, and
        # automatically clusters-and-stitches above that — see
        # src/clustering.py for why and how.
        result = solve_open_path_scalable(W, start_idx, end_idx, method=method, cluster_size=CLUSTER_SIZE)

        return jsonify({
            "order": result["path"],
            "cost_minutes": round(result["cost"], 1),
            "method": method,
            "solve_ms": round(result.get("wall_seconds", 0) * 1000),
            "clusters_used": result.get("clusters_used", 1),
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    # PORT is set automatically by cloud hosts (Render, Railway, etc.) — falls
    # back to 5000 for local runs on your own machine.
    port = int(os.environ.get("PORT", 5000))
    print(f"Starting the click-anywhere router at http://127.0.0.1:{port}")
    app.run(debug=False, host="0.0.0.0", port=port)
