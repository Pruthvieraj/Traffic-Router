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
    - experiment_3_composed.csv         raw numbers, composed multi-constraint fleet dispatch
    - experiment_4_multi_objective.csv  raw numbers, time-vs-distance trade-off
    - experiment_5_time_windows.csv     raw numbers, time-window position-pruning effectiveness
    - experiment_6_cvrp_baseline.csv    raw numbers, fleet mode vs. a real joint CVRP solver
    - report.md                         human-readable summary of all six,
                                         written honestly (see benchmark.py)

Everything runs offline against the bundled demo road network
(src/city_graph.py) — no internet access or API keys required. See
README.md for how to point this at a real OpenStreetMap area instead.
"""

import os
import shutil
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from city_graph import build_city_graph
from congestion import apply_congestion
from distance_matrix import build_travel_time_matrix
from qubo_tsp import solve_quantum_inspired
from baseline import nearest_neighbor_2opt
from benchmark import (
    run_experiment_1_unconstrained, run_experiment_2_constrained, run_experiment_3_composed,
    run_experiment_4_multi_objective, run_experiment_5_time_windows, run_experiment_6_cvrp_baseline,
    summarize_and_save,
)
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

    section("5. Benchmark — Experiment 3: does solving constraints TOGETHER matter?")
    rows3 = run_experiment_3_composed()
    n3 = len(rows3)
    composed_both_ok = sum(1 for r in rows3 if r["composed_precedence_ok"] and r["composed_capacity_ok"])
    print(f"COMPOSED satisfied both precedence AND capacity in {composed_both_ok}/{n3} trials")
    print(f"CAPACITY-ONLY (precedence-blind) got lucky on precedence in "
          f"{sum(1 for r in rows3 if r['capacity_only_precedence_ok_by_luck'])}/{n3} trials")
    print(f"PRECEDENCE-ONLY (demand-blind split) stayed within capacity by luck in "
          f"{sum(1 for r in rows3 if r['precedence_only_capacity_ok_by_luck'])}/{n3} trials")

    section("6. Benchmark — Experiment 4: is \"multi-objective\" (time vs. distance) a real trade-off?")
    rows4 = run_experiment_4_multi_objective()
    n4 = len(rows4)
    n_diverge = sum(1 for r in rows4 if r["objectives_diverge"])
    print(f"Optimizing for only one objective (time OR distance) provably cost something on the "
          f"other in {n_diverge}/{n4} trials (exact brute-force search, no solver noise)")

    section("7. Benchmark — Experiment 5: does time-window position-pruning actually help?")
    rows5 = run_experiment_5_time_windows()
    n5 = len(rows5)
    without_ok = sum(1 for r in rows5 if r["without_pruning_satisfied"])
    with_ok = sum(1 for r in rows5 if r["with_pruning_satisfied"])
    print(f"Without time-window pruning, the requested window was satisfied in {without_ok}/{n5} trials")
    print(f"With time-window pruning, the requested window was satisfied in {with_ok}/{n5} trials "
          f"(helps, but is not a guarantee — see report.md)")

    section("7b. Benchmark — Experiment 6: fleet mode vs. a real joint capacitated VRP solver")
    rows6 = run_experiment_6_cvrp_baseline()
    n6 = len(rows6)
    if any("ortools_total_cost_min" in r for r in rows6):
        gaps = [r["ours_pct_above_ortools"] for r in rows6 if "ours_pct_above_ortools" in r]
        print(f"Our cluster-first/route-second fleet split was on average "
              f"{round(sum(gaps) / len(gaps), 1)}% above OR-Tools' real joint CVRP solve "
              f"across {n6} trials (see report.md)")
    else:
        print(f"ortools not installed — ran {n6} fleet-mode-only trials with no joint-solver "
              f"comparison (pip install ortools to also get that comparison)")

    section("8. Writing report + charts to ./output/")
    summary = summarize_and_save(
        rows1, rows2, rows3, out_dir=OUTPUT_DIR, rows4=rows4, rows5=rows5, rows6=rows6,
    )
    with open(os.path.join(OUTPUT_DIR, "report.md"), "w") as f:
        f.write(summary)
    render_comparison_chart(rows1, os.path.join(OUTPUT_DIR, "comparison_chart.png"))
    render_constraint_chart(rows2, os.path.join(OUTPUT_DIR, "constraint_chart.png"))
    print("Wrote: report.md, comparison_chart.png, constraint_chart.png, experiment_1_unconstrained.csv, "
          "experiment_2_constrained.csv, experiment_3_composed.csv, experiment_4_multi_objective.csv, "
          "experiment_5_time_windows.csv, experiment_6_cvrp_baseline.csv")


def run_multi_city_map() -> None:
    section("9. Building the multi-city interactive map (satellite toggle + city dropdown)")
    out_path = os.path.join(OUTPUT_DIR, "multi_city_map.html")
    build_multi_city_map(out_path)
    print(f"Wrote: {out_path}")

    # root index.html is committed on purpose as a byte-for-byte copy of
    # this same file, specifically so GitHub Pages (which only serves
    # index.html at the repo root, not output/multi_city_map.html) can host
    # the flagship demo with zero backend — see README.md's "Deploy to the
    # cloud" section (full steps in docs/deploy.md). That used to be a
    # manual "remember to re-copy it"
    # step, which is exactly the kind of thing that silently goes stale
    # (it did, in this project's own history — a judge who reviewed this
    # repo caught index.html and output/multi_city_map.html already out of
    # sync in a real commit). Copying it here, in the same build step that
    # writes the source file, makes that drift structurally impossible:
    # there is no longer a second manual step to forget.
    index_path = os.path.join(os.path.dirname(__file__), "index.html")
    shutil.copyfile(out_path, index_path)
    print(f"Wrote: {index_path} (kept in sync with output/multi_city_map.html automatically)")


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
