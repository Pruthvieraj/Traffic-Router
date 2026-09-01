"""
visualize.py
============
Two outputs a judge can actually look at in 10 seconds:

1. `route_map.html` — an interactive Leaflet map (via folium) of the demo
   city graph with a chosen route drawn on it, congestion-colored.
2. `comparison_chart.png` — a bar chart of Experiment 1 (2-opt vs QUBO+SA
   cost) so the honest finding from benchmark.py is visible at a glance.
"""

import os
import folium
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Free, no-API-key satellite imagery (Esri World Imagery) and a street
# basemap — both added as toggleable layers via folium.LayerControl, so a
# judge can flip between "satellite" and "map" view on the same page. The
# street layer uses CARTO Voyager rather than folium's built-in plain
# "OpenStreetMap" tiles — same free OSM road/place data underneath, but a
# noticeably crisper, more polished cartographic style (see
# templates/click_router.html and build_multi_city_map.py, which use the
# exact same upgrade, for the full rationale).
SATELLITE_TILES = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
SATELLITE_ATTR = "Tiles &copy; Esri &mdash; Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community"
STREET_TILES = "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png"
STREET_ATTR = (
    '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors '
    '&copy; <a href="https://carto.com/attributions">CARTO</a>'
)


def render_route_map(Gc, waypoints: list[str], tour: list[int], out_path: str, title: str = "Route") -> None:
    """Draw the full road network (thin grey lines, colored by congestion)
    plus the chosen route (thick blue line with numbered stops) as an
    interactive HTML map, with a satellite/street basemap toggle."""
    lats = [Gc.nodes[n]["lat"] for n in Gc.nodes]
    lons = [Gc.nodes[n]["lon"] for n in Gc.nodes]
    center = [sum(lats) / len(lats), sum(lons) / len(lons)]

    m = folium.Map(location=center, zoom_start=12, tiles=None)
    folium.TileLayer(tiles=SATELLITE_TILES, attr=SATELLITE_ATTR, name="Satellite", overlay=False).add_to(m)
    folium.TileLayer(
        tiles=STREET_TILES, attr=STREET_ATTR, name="Street map", overlay=False,
        subdomains="abcd", max_zoom=20, detect_retina=True,
    ).add_to(m)

    # underlying road network, colored by how congested each edge currently is
    for u, v, data in Gc.edges(data=True):
        mult = data.get("congestion_multiplier", 1.0)
        color = "#2ecc71" if mult < 1.5 else "#f39c12" if mult < 2.5 else "#e74c3c"
        folium.PolyLine(
            [ (Gc.nodes[u]["lat"], Gc.nodes[u]["lon"]), (Gc.nodes[v]["lat"], Gc.nodes[v]["lon"]) ],
            color=color, weight=3, opacity=0.5,
            tooltip=f"{u} - {v}: {mult:.2f}x congestion",
        ).add_to(m)

    # the chosen route, as straight hops between waypoints in tour order
    named_tour = [waypoints[i] for i in tour] + [waypoints[tour[0]]]
    route_latlon = [(Gc.nodes[name]["lat"], Gc.nodes[name]["lon"]) for name in named_tour]
    folium.PolyLine(route_latlon, color="#2c3e50", weight=5, opacity=0.9, dash_array="8,6").add_to(m)

    for order, name in enumerate(named_tour[:-1]):
        folium.Marker(
            (Gc.nodes[name]["lat"], Gc.nodes[name]["lon"]),
            icon=folium.DivIcon(html=f"""<div style="font-size:12pt;color:white;background:#2c3e50;
                border-radius:50%;width:24px;height:24px;text-align:center;line-height:24px;">{order+1}</div>"""),
            tooltip=name,
        ).add_to(m)

    title_html = f'<h3 style="position:fixed;top:10px;left:60px;z-index:9999;background:white;padding:6px 12px;border-radius:6px;">{title}</h3>'
    m.get_root().html.add_child(folium.Element(title_html))
    folium.LayerControl(collapsed=False).add_to(m)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    m.save(out_path)


def render_comparison_chart(rows1: list[dict], out_path: str) -> None:
    """Bar chart: 2-opt vs QUBO+SA cost across problem sizes (Experiment 1),
    plus a third Google OR-Tools bar whenever that optional comparison ran
    (see src/ortools_baseline.py / benchmark.py) — a real industrial solver
    alongside the hand-rolled 2-opt baseline, so the "even the strong
    baseline wins here" honest finding is visible at a glance too, not
    just in the CSV/markdown report."""
    sizes = [r["n_waypoints"] for r in rows1]
    two_opt = [r["2opt_cost_min"] for r in rows1]
    qubo = [r["qubo_sa_cost_min"] for r in rows1]
    has_ortools = all("ortools_cost_min" in r for r in rows1) and len(rows1) > 0

    x = range(len(sizes))
    fig, ax = plt.subplots(figsize=(7, 4.5))

    if has_ortools:
        ortools_costs = [r["ortools_cost_min"] for r in rows1]
        width = 0.25
        ax.bar([i - width for i in x], two_opt, width, label="Classical (2-opt)", color="#3498db")
        ax.bar(list(x), qubo, width, label="Quantum-inspired (QUBO + SA)", color="#9b59b6")
        ax.bar([i + width for i in x], ortools_costs, width, label="Google OR-Tools", color="#2ecc71")
    else:
        width = 0.35
        ax.bar([i - width / 2 for i in x], two_opt, width, label="Classical (2-opt)", color="#3498db")
        ax.bar([i + width / 2 for i in x], qubo, width, label="Quantum-inspired (QUBO + SA)", color="#9b59b6")

    ax.set_xticks(list(x))
    ax.set_xticklabels([str(s) for s in sizes])
    ax.set_xlabel("Number of waypoints")
    ax.set_ylabel("Total route time (minutes)")
    ax.set_title("Experiment 1: unconstrained routing — lower is better")
    ax.legend()
    fig.tight_layout()

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def render_constraint_chart(rows2: list[dict], out_path: str) -> None:
    """The chart that actually matters for the pitch: per-trial cost of
    QUBO+SA (always valid) vs the repaired classical route (sometimes valid
    only after a costly patch), with violated trials flagged."""
    trials = [r["trial"] for r in rows2]
    qubo_cost = [r["qubo_sa_cost_min"] for r in rows2]
    repaired_cost = [r["repaired_2opt_cost_min"] for r in rows2]
    violated = [r["plain_2opt_violates_rule"] for r in rows2]

    fig, ax = plt.subplots(figsize=(8, 4.5))
    width = 0.35
    x = range(len(trials))
    bars_repaired = ax.bar(
        [i - width / 2 for i in x], repaired_cost, width,
        label="Classical 2-opt + after-the-fact repair", color="#e67e22",
    )
    ax.bar(
        [i + width / 2 for i in x], qubo_cost, width,
        label="QUBO + SA (constraint built in)", color="#9b59b6",
    )
    # flag trials where the classical route needed a repair at all
    for i, was_violated in enumerate(violated):
        if was_violated:
            ax.text(i - width / 2, repaired_cost[i] + 5, "repair\nneeded", ha="center", fontsize=7, color="#c0392b")

    ax.set_xticks(list(x))
    ax.set_xticklabels([str(t + 1) for t in trials])
    ax.set_xlabel("Trial (random waypoint set + precedence rule)")
    ax.set_ylabel("Total route time (minutes)")
    ax.set_title("Experiment 2: routing with a real dispatch constraint — lower is better")
    ax.legend(fontsize=8)
    fig.tight_layout()

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    from city_graph import build_city_graph
    from congestion import apply_congestion
    from distance_matrix import build_travel_time_matrix
    from qubo_tsp import solve_quantum_inspired

    G = build_city_graph("Bengaluru")
    Gc = apply_congestion(G, hour=18.5)
    waypoints = ["Majestic", "Indiranagar", "Koramangala", "HSR Layout", "Silk Board", "Jayanagar"]
    W, _ = build_travel_time_matrix(Gc, waypoints)
    result = solve_quantum_inspired(W)
    render_route_map(Gc, waypoints, result["tour"], "../output/route_map.html", title="Quantum-inspired route (6:30pm)")
    print("wrote ../output/route_map.html")
