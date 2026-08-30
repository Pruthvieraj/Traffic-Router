#!/usr/bin/env python3
"""
main.py — run the whole demo end to end.

    python3 main.py

Produces, in ./output/:
    - route_map.html                    interactive map of a sample route
    - route_map_after_spike.html        the same route re-optimized after
                                         a simulated mid-route congestion spike
    - comparison_chart.png              Experiment 1 bar chart
    - experiment_1_unconstrained.csv    raw numbers, plain routing
    - experiment_2_constrained.csv      raw numbers, routing with a rule
    - report.md                         human-readable summary of both,
                                         written honestly (see benchmark.py)

Everything runs offline against the bundled demo road network
(src/city_graph.py) — no internet access or API keys required. See
README.md for how to point this at a real OpenStreetMap area instead.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from city_graph import build_city_graph
from congestion import apply_congestion
from distance_matrix import build_travel_time_matrix
from qubo_tsp import solve_quantum_inspired
from baseline import nearest_neighbor_2opt
from benchmark import run_experiment_1_unconstrained, run_experiment_2_constrained, summarize_and_save
from visualize import render_route_map, render_comparison_chart, render_constraint_chart
from build_multi_city_map import build_multi_city_map

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
DEMO_WAYPOINTS = ["Majestic", "Indiranagar", "Koramangala", "HSR Layout", "Silk Board", "Jayanagar"]


def section(title: str) -> None:
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def run_demo_route() -> None:
    section("1. Solving a sample 6-stop delivery route at 6:30pm (evening peak)")
    G = build_city_graph("Bengaluru")
    Gc = apply_congestion(G, hour=18.5, seed=42)
    W, _ = build_travel_time_matrix(Gc, DEMO_WAYPOINTS)

    result = solve_quantum_inspired(W, num_reads=500)
    named_tour = [DEMO_WAYPOINTS[i] for i in result["tour"]]
    print("Route:", " -> ".join(named_tour + [named_tour[0]]))
    print(f"Total time: {result['cost']:.1f} min  (solved in {result['wall_seconds']*1000:.0f} ms, "
          f"{result['feasible_reads']}/{result['total_reads']} reads were valid tours)")

    render_route_map(Gc, DEMO_WAYPOINTS, result["tour"],
                      os.path.join(OUTPUT_DIR, "route_map.html"),
                      title="6:30pm route (before disruption)")

    section("2. Simulating a mid-route disruption (accident on one leg of the route)")
    spike_edge_pair = (named_tour[2], named_tour[3])
    print(f"Injecting a congestion spike on: {spike_edge_pair[0]} <-> {spike_edge_pair[1]}")
    Gc_spike = apply_congestion(G, hour=18.5, seed=42, spike_edges=[spike_edge_pair], spike_multiplier=4.0)
    W_spike, _ = build_travel_time_matrix(Gc_spike, DEMO_WAYPOINTS)

    result2 = solve_quantum_inspired(W_spike, num_reads=500)
    named_tour2 = [DEMO_WAYPOINTS[i] for i in result2["tour"]]
    print("Re-optimized route:", " -> ".join(named_tour2 + [named_tour2[0]]))
    print(f"Total time: {result2['cost']:.1f} min (was {result['cost']:.1f} min before the spike)")

    render_route_map(Gc_spike, DEMO_WAYPOINTS, result2["tour"],
                      os.path.join(OUTPUT_DIR, "route_map_after_spike.html"),
                      title="Re-optimized route (after disruption)")


def run_benchmarks() -> None:
    section("3. Benchmark — Experiment 1: plain unconstrained routing (honest baseline check)")
    rows1 = run_experiment_1_unconstrained()
    for r in rows1:
        print(r)

    section("4. Benchmark — Experiment 2: routing with a real dispatch constraint")
    rows2 = run_experiment_2_constrained()
    n_violated = sum(1 for r in rows2 if r["plain_2opt_violates_rule"])
    n_valid = sum(1 for r in rows2 if r["qubo_sa_satisfies_rule"])
    print(f"Plain 2-opt violated the constraint in {n_violated}/{len(rows2)} trials")
    print(f"QUBO+SA satisfied the constraint by construction in {n_valid}/{len(rows2)} trials")

    section("5. Writing report + charts to ./output/")
    summary = summarize_and_save(rows1, rows2, out_dir=OUTPUT_DIR)
    with open(os.path.join(OUTPUT_DIR, "report.md"), "w") as f:
        f.write(summary)
    render_comparison_chart(rows1, os.path.join(OUTPUT_DIR, "comparison_chart.png"))
    render_constraint_chart(rows2, os.path.join(OUTPUT_DIR, "constraint_chart.png"))
    print("Wrote: report.md, comparison_chart.png, constraint_chart.png, experiment_1_unconstrained.csv, experiment_2_constrained.csv")


def run_multi_city_map() -> None:
    section("6. Building the multi-city interactive map (satellite toggle + city dropdown)")
    out_path = os.path.join(OUTPUT_DIR, "multi_city_map.html")
    build_multi_city_map(out_path)
    print(f"Wrote: {out_path}")


if __name__ == "__main__":
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    run_demo_route()
    run_benchmarks()
    run_multi_city_map()
    section("Done")
    print(f"All outputs are in: {OUTPUT_DIR}/")
    print("Open multi_city_map.html for the flagship demo: pick a city from the dropdown, toggle satellite/street view.")
    print("Open route_map.html and route_map_after_spike.html for the single-city (Bengaluru) before/after-disruption demo.")
    print("Open report.md for the numbers to quote in your pitch and in your patent's Form 2 description.")
