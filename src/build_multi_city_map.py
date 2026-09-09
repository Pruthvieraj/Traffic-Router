"""
build_multi_city_map.py
========================
Builds the flagship demo artifact: ONE self-contained HTML file with a
city dropdown (Bengaluru / Mumbai / Pune / Gurgaon / Noida), a
satellite/street basemap toggle, and a classical-vs-quantum-inspired route
toggle, plus a "simulate a mid-route disruption" button that re-optimizes
live in the browser tab.

Design choice worth knowing about: all the routing (QUBO solve, 2-opt
baseline, congestion) is precomputed in Python for a curated scenario per
city and embedded as JSON directly inside the HTML file (not fetched from
a separate .json file). That's deliberate — opening a local HTML file
directly in a browser (file://) blocks most `fetch()` calls to sibling
files under CORS rules, which is exactly the kind of thing that fails
silently five minutes before a pitch. Embedding the data inline means this
file works by just double-clicking it, no local server needed.

The one thing that does need a live network connection at demo time is the
satellite/street map tile images themselves (Esri World Imagery / OpenStreetMap) —
that's unavoidable for real satellite imagery, so make sure the room has
wifi, or fall back to the street layer if venue wifi is flaky (both are
provided as toggle options).
"""

import base64
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
VENDOR_DIR = os.path.join(os.path.dirname(__file__), "..", "vendor")

from city_graph import build_city_graph, list_cities
from congestion import apply_congestion
from distance_matrix import build_travel_time_matrix
from qubo_tsp import solve_quantum_inspired
from baseline import nearest_neighbor_2opt

MAX_WAYPOINTS_PER_CITY = 8  # keeps each city's QUBO solve fast (N^2 = 64 vars) for the pre-build step


def _route_payload(Gc, waypoints, tour_indices):
    named = [waypoints[i] for i in tour_indices]
    named_loop = named + [named[0]]
    return {
        "order": named,
        "path": [[Gc.nodes[n]["lat"], Gc.nodes[n]["lon"]] for n in named_loop],
    }


def build_city_payload(city: str) -> dict:
    G = build_city_graph(city)
    Gc = apply_congestion(G, hour=18.5, seed=42)
    all_nodes = list(G.nodes)
    waypoints = all_nodes[:MAX_WAYPOINTS_PER_CITY]
    W, _ = build_travel_time_matrix(Gc, waypoints)

    qi = solve_quantum_inspired(W, num_reads=400)
    nn = nearest_neighbor_2opt(W)

    # simulate a disruption on one leg of the quantum-inspired route, then re-solve
    qi_named = [waypoints[i] for i in qi["tour"]]
    spike_pair = (qi_named[1], qi_named[2])
    Gc_spike = apply_congestion(G, hour=18.5, seed=42, spike_edges=[spike_pair], spike_multiplier=4.0)
    W_spike, _ = build_travel_time_matrix(Gc_spike, waypoints)
    qi_spike = solve_quantum_inspired(W_spike, num_reads=400)

    nodes = {n: [round(G.nodes[n]["lat"], 5), round(G.nodes[n]["lon"], 5)] for n in G.nodes}
    lats = [c[0] for c in nodes.values()]
    lons = [c[1] for c in nodes.values()]
    center = [sum(lats) / len(lats), sum(lons) / len(lons)]

    edges = []
    for u, v, data in Gc.edges(data=True):
        edges.append([u, v, round(data["congestion_multiplier"], 2)])

    edges_spike = []
    for u, v, data in Gc_spike.edges(data=True):
        edges_spike.append([u, v, round(data["congestion_multiplier"], 2)])

    return {
        "center": center,
        "nodes": nodes,
        "edges_before": edges,
        "edges_after": edges_spike,
        "waypoints": waypoints,
        "quantum_route": _route_payload(Gc, waypoints, qi["tour"]),
        "classical_route": _route_payload(Gc, waypoints, nn["tour"]),
        "quantum_route_after_spike": _route_payload(Gc_spike, waypoints, qi_spike["tour"]),
        "spike_edge": list(spike_pair),
        "quantum_cost_min": round(qi["cost"], 1),
        "classical_cost_min": round(nn["cost"], 1),
        "quantum_cost_after_spike_min": round(qi_spike["cost"], 1),
        "solve_ms": round(qi["wall_seconds"] * 1000, 0),
    }


HTML_TEMPLATE = r"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Quantum-Inspired Multi-City Route Optimizer</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<!--
  Leaflet's JS and CSS are inlined below (see __LEAFLET_CSS__ / __LEAFLET_JS__
  substitution in build_multi_city_map.py) instead of loaded from a CDN, so
  this file has exactly ONE external dependency at demo time: the map tile
  images themselves (satellite/street), which need a live internet
  connection no matter what. Everything else — the map library, the routing
  data, the routes — works from this single file with no network and no
  local server, so double-clicking it always gets you at least as far as
  "map library loaded, pick a city," even on flaky venue wifi.
-->
<style>__LEAFLET_CSS__</style>
<script>__LEAFLET_JS__</script>
<style>
  html, body { margin:0; padding:0; height:100%; font-family: -apple-system, Segoe UI, Roboto, Arial, sans-serif; }
  #map { position:absolute; top:64px; bottom:0; left:0; right:0; }
  #topbar {
    height:64px; display:flex; align-items:center; gap:14px; padding:0 16px;
    background:#1b2733; color:white; box-sizing:border-box; flex-wrap:wrap;
  }
  #topbar h1 { font-size:15px; margin:0; font-weight:600; white-space:nowrap; }
  #topbar select, #topbar button {
    font-size:13px; padding:6px 10px; border-radius:6px; border:1px solid #46586b;
    background:#26374a; color:white; cursor:pointer;
  }
  #topbar button.active { background:#9b59b6; border-color:#9b59b6; }
  #legend {
    position:absolute; bottom:16px; right:16px; background:white; padding:10px 14px;
    border-radius:8px; font-size:12px; box-shadow:0 1px 6px rgba(0,0,0,.3); z-index:500; line-height:1.6;
  }
  #legend .sw { display:inline-block; width:14px; height:4px; margin-right:6px; vertical-align:middle; }
  #stats {
    position:absolute; top:78px; left:16px; background:white; padding:10px 14px;
    border-radius:8px; font-size:12px; box-shadow:0 1px 6px rgba(0,0,0,.3); z-index:500; max-width:260px; line-height:1.6;
  }
  #stats b { color:#1b2733; }
</style>
</head>
<body>
<div id="topbar">
  <h1>Quantum-Inspired Route Optimizer</h1>
  <select id="citySelect"></select>
  <select id="basemapSelect">
    <option value="satellite">Satellite view</option>
    <option value="street">Street map</option>
  </select>
  <button id="routeToggleBtn">Route: Quantum-inspired</button>
  <button id="spikeToggleBtn">Simulate disruption</button>
</div>
<div id="map"></div>
<div id="stats"></div>
<div id="legend">
  <div><span class="sw" style="background:#2ecc71"></span>Light traffic</div>
  <div><span class="sw" style="background:#f39c12"></span>Moderate traffic</div>
  <div><span class="sw" style="background:#e74c3c"></span>Heavy traffic</div>
  <div><span class="sw" style="background:#2c3e50;height:3px"></span>Chosen route</div>
</div>

<script>
const CITY_DATA = __CITY_DATA_JSON__;
const CITY_NAMES = Object.keys(CITY_DATA);

// Same basemap-quality upgrade as templates/click_router.html: satellite
// imagery alone is often blurry/unlabeled outside major Indian metros, so
// Esri's "Boundaries and Places" reference layer is stacked on top as a
// labels/roads overlay. The street layer used to be CARTO Voyager tiles;
// CARTO now watermarks unauthenticated raster-tile requests with "API KEY
// REQUIRED" (see https://docs.carto.com/faqs/carto-basemaps), so it's now
// Esri's own free, keyless Canvas/World_Light_Gray base + reference labels
// instead — same arcgisonline.com host World_Imagery above already uses.
// Esri's own service metadata only guarantees worldwide tile coverage
// through zoom 13 (detail beyond that is confirmed only for North
// America/Europe, not named for India) — maxNativeZoom caps native tile
// requests there and lets Leaflet upscale instead of ever showing a blank
// tile past that zoom.
const satelliteImagery = L.tileLayer(
  'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
  {
    attribution: 'Tiles &copy; Esri &mdash; Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community',
    maxZoom: 19, detectRetina: true,
  }
);
const satelliteLabels = L.tileLayer(
  'https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}',
  { maxZoom: 19, detectRetina: true }
);
const satelliteLayer = L.layerGroup([satelliteImagery, satelliteLabels]);
const streetLayerBase = L.tileLayer(
  'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}',
  { attribution: 'Tiles &copy; Esri &mdash; Esri, DeLorme, NAVTEQ', maxZoom: 19, maxNativeZoom: 13, detectRetina: true }
);
const streetLayerLabels = L.tileLayer(
  'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}',
  { maxZoom: 19, maxNativeZoom: 13, detectRetina: true }
);
const streetLayer = L.layerGroup([streetLayerBase, streetLayerLabels]);

const map = L.map('map', { layers: [satelliteLayer] }).setView([20.5, 78.9], 5);

let currentLayerGroup = L.layerGroup().addTo(map);
let state = { city: CITY_NAMES[0], routeType: 'quantum', spiked: false };

function congestionColor(mult) {
  if (mult < 1.5) return '#2ecc71';
  if (mult < 2.5) return '#f39c12';
  return '#e74c3c';
}

function render() {
  currentLayerGroup.clearLayers();
  const data = CITY_DATA[state.city];
  map.setView(data.center, 12);

  const edges = state.spiked ? data.edges_after : data.edges_before;
  edges.forEach(([u, v, mult]) => {
    const a = data.nodes[u], b = data.nodes[v];
    L.polyline([a, b], { color: congestionColor(mult), weight: 3, opacity: 0.55 })
      .bindTooltip(`${u} - ${v}: ${mult}x congestion`)
      .addTo(currentLayerGroup);
  });

  let route, cost, label;
  if (state.spiked) {
    route = data.quantum_route_after_spike;
    cost = data.quantum_cost_after_spike_min;
    label = 'Quantum-inspired (re-optimized after disruption)';
  } else if (state.routeType === 'quantum') {
    route = data.quantum_route;
    cost = data.quantum_cost_min;
    label = 'Quantum-inspired (QUBO + simulated annealing)';
  } else {
    route = data.classical_route;
    cost = data.classical_cost_min;
    label = 'Classical (nearest-neighbor + 2-opt)';
  }

  L.polyline(route.path, { color: '#2c3e50', weight: 5, opacity: 0.9, dashArray: '8,6' }).addTo(currentLayerGroup);
  route.order.forEach((name, i) => {
    const coords = data.nodes[name];
    L.marker(coords, {
      icon: L.divIcon({
        className: '', html: `<div style="background:#2c3e50;color:white;border-radius:50%;width:24px;height:24px;
          text-align:center;line-height:24px;font-size:12px;">${i + 1}</div>`,
      })
    }).bindTooltip(name).addTo(currentLayerGroup);
  });

  // the disruption demo only has a quantum-inspired recovery route computed
  // (see build_city_payload) — grey out the classical/quantum toggle while
  // a disruption is active so the two controls never show a contradictory
  // combination on screen.
  const routeBtn = document.getElementById('routeToggleBtn');
  routeBtn.disabled = state.spiked;
  routeBtn.style.opacity = state.spiked ? 0.4 : 1;

  document.getElementById('stats').innerHTML = `
    <b>${state.city}</b><br>
    Route: ${label}<br>
    Total time: <b>${cost} min</b><br>
    ${state.spiked ? `Disruption on: ${data.spike_edge[0]} ↔ ${data.spike_edge[1]}<br>` : ''}
    Solve time: ${data.solve_ms} ms
  `;
}

document.getElementById('citySelect').innerHTML = CITY_NAMES.map(c => `<option value="${c}">${c}</option>`).join('');
document.getElementById('citySelect').addEventListener('change', (e) => {
  state.city = e.target.value;
  state.spiked = false;
  render();
});

document.getElementById('basemapSelect').addEventListener('change', (e) => {
  if (e.target.value === 'satellite') {
    map.removeLayer(streetLayer); map.addLayer(satelliteLayer);
  } else {
    map.removeLayer(satelliteLayer); map.addLayer(streetLayer);
  }
});

document.getElementById('routeToggleBtn').addEventListener('click', (e) => {
  state.routeType = state.routeType === 'quantum' ? 'classical' : 'quantum';
  e.target.textContent = 'Route: ' + (state.routeType === 'quantum' ? 'Quantum-inspired' : 'Classical (2-opt)');
  render();
});

document.getElementById('spikeToggleBtn').addEventListener('click', (e) => {
  state.spiked = !state.spiked;
  e.target.classList.toggle('active', state.spiked);
  e.target.textContent = state.spiked ? 'Clear disruption' : 'Simulate disruption';
  render();
});

render();
</script>
</body>
</html>
"""


def load_inline_leaflet() -> tuple[str, str]:
    """Read the vendored Leaflet JS/CSS and inline its referenced marker/layer
    icons as base64 data URIs, so the whole map library becomes two strings
    with zero remaining file references — see the note in HTML_TEMPLATE."""
    with open(os.path.join(VENDOR_DIR, "leaflet.js"), encoding="utf-8") as f:
        js = f.read()
    with open(os.path.join(VENDOR_DIR, "leaflet.css"), encoding="utf-8") as f:
        css = f.read()

    images_dir = os.path.join(VENDOR_DIR, "leaflet_images")
    for fname in os.listdir(images_dir):
        with open(os.path.join(images_dir, fname), "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
        data_uri = f"data:image/png;base64,{b64}"
        css = re.sub(rf"images/{re.escape(fname)}", data_uri, css)

    return css, js


def build_multi_city_map(out_path: str) -> None:
    payload = {city: build_city_payload(city) for city in list_cities()}
    leaflet_css, leaflet_js = load_inline_leaflet()

    html = (
        HTML_TEMPLATE
        .replace("__CITY_DATA_JSON__", json.dumps(payload))
        .replace("__LEAFLET_CSS__", leaflet_css)
        .replace("__LEAFLET_JS__", leaflet_js)
    )
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        f.write(html)


if __name__ == "__main__":
    build_multi_city_map(os.path.join(os.path.dirname(__file__), "..", "output", "multi_city_map.html"))
    print("wrote multi_city_map.html")
