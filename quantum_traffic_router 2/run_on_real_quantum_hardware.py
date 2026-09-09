#!/usr/bin/env python3
"""
run_on_real_quantum_hardware.py — solve the SAME open-path QUBO this
project uses, on an ACTUAL quantum annealer (a D-Wave QPU), not a
classical simulation of one.

WHY THIS EXISTS: everything else in this project that's labeled "quantum"
is quantum-INSPIRED — the QUBO formulation is real, but it's solved by
classical simulated annealing (dwave-samplers' SimulatedAnnealingSampler)
because that's fast, free, and needs no special hardware access. That's an
honest and defensible thing to build a hackathon project on, but nearly
every other "quantum" SIH project makes the same choice, for the same
reasons. This script is the extra step that most teams skip: taking the
exact same BQM (`qubo_tsp.build_open_path_bqm`) and submitting it to a
real D-Wave quantum annealer, so you can show judges an actual QPU chip
ID, an actual hardware annealing time, and a real hardware result sitting
next to the classical one — independently checkable, not just claimed.

This script is now a thin demo/report wrapper around
`src/qpu_solver.solve_open_path_on_qpu` — the SAME function
`method="qpu"` uses everywhere else in this project (the live app via
`clustering.solve_open_path_scalable` / `solve_multi_vehicle`), so a real
QPU is a first-class solver mode here, not a one-off script with its own
separate hardware-submission logic to keep in sync.

WHAT THIS NEEDS THAT NOTHING ELSE HERE DOES: a free D-Wave Leap account.
This is NOT required to run app.py, main.py, or anything else in this
project — it's a one-time credibility artifact for your pitch deck, run
once on your own machine, not part of the live demo's normal code path.

SETUP (one-time, a few minutes):
  1. Sign up free at https://cloud.dwavesys.com/leap/ (no credit card
     needed). New accounts get a small monthly allotment of real QPU
     access time — check the current details on signup, but it's measured
     in seconds, because real quantum hardware time is scarce/expensive.
     This script's settings (100 reads on a ~9-variable problem) use a
     tiny fraction of a typical allotment.
  2. Install the SDK (only needed for this script and method="qpu"):
         pip install dwave-system
  3. Get your API token from the Leap dashboard (top right, "API Token"),
     then either run the interactive setup:
         dwave setup
     or just set an environment variable before running this script:
         export DWAVE_API_TOKEN="your-token-from-the-Leap-dashboard"

RUN:
    python3 run_on_real_quantum_hardware.py

OUTPUT: prints brute-force-optimal vs classical (NN + 2-opt) vs
quantum-inspired (simulated annealing) vs REAL QPU results side by side,
and writes output/real_quantum_hardware_result.md — meant to be quoted or
screenshotted directly in your pitch deck.
"""

import itertools
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from city_graph import build_demo_graph  # noqa: E402
from congestion import apply_congestion  # noqa: E402
from distance_matrix import build_travel_time_matrix  # noqa: E402
from qubo_tsp import open_path_length, solve_open_path_quantum_inspired  # noqa: E402
from baseline import nearest_neighbor_2opt_open_path  # noqa: E402
from qpu_solver import solve_open_path_on_qpu, QPU_AVAILABLE  # noqa: E402

# A small, fixed, reproducible example — 3 "middle" stops means only 9
# binary variables in the QUBO, tiny by QPU standards, embeds easily, and
# still genuinely exercises the same fixed-endpoint formulation the live
# app uses for every real solve.
WAYPOINTS = ["Majestic", "Indiranagar", "Koramangala", "Jayanagar", "HSR Layout"]
START, END = "Majestic", "HSR Layout"


def brute_force_open_path(W, start_idx, end_idx):
    n = W.shape[0]
    middle = [v for v in range(n) if v not in (start_idx, end_idx)]
    best_path, best_cost = None, float("inf")
    for perm in itertools.permutations(middle):
        path = [start_idx, *perm, end_idx]
        cost = open_path_length(path, W)
        if cost < best_cost:
            best_path, best_cost = path, cost
    return best_path, best_cost


def main():
    print("Building the example route (same style as this project's own qubo_tsp.py demo)...\n")
    G = build_demo_graph()
    Gc = apply_congestion(G, hour=18.5)
    W, _ = build_travel_time_matrix(Gc, WAYPOINTS)
    start_idx, end_idx = WAYPOINTS.index(START), WAYPOINTS.index(END)
    middle_names = [w for w in WAYPOINTS if w not in (START, END)]
    print(f"Route: {START} -> ... -> {END}, visiting {middle_names} in some order\n")

    bf_path, bf_cost = brute_force_open_path(W, start_idx, end_idx)
    print(f"Brute-force optimal:      {[WAYPOINTS[i] for i in bf_path]}  ({bf_cost:.1f} min)")

    classical = nearest_neighbor_2opt_open_path(W, start_idx, end_idx)
    print(f"Classical (NN + 2-opt):   {[WAYPOINTS[i] for i in classical['path']]}  "
          f"({classical['cost']:.1f} min, {classical['wall_seconds']*1000:.1f} ms)")

    sa_result = solve_open_path_quantum_inspired(W, start_idx, end_idx, num_reads=500)
    print(f"Quantum-inspired (SA):    {[WAYPOINTS[i] for i in sa_result['path']]}  "
          f"({sa_result['cost']:.1f} min, {sa_result['wall_seconds']*1000:.1f} ms)")

    print("\nConnecting to a real D-Wave quantum annealer (needs your Leap API token)...")
    if not QPU_AVAILABLE:
        print("\ndwave-system isn't installed. Run:  pip install dwave-system")
        print("(See this script's docstring for the full one-time setup.)")
        return

    try:
        qpu_result = solve_open_path_on_qpu(W, start_idx, end_idx, num_reads=100)
    except Exception as e:
        print(f"\nCouldn't get a result from a real D-Wave QPU: {e}")
        print("Check that your API token is set — see this script's docstring for setup steps.")
        return

    print(f"Connected to real QPU: {qpu_result['chip_id']}")

    best_path, best_cost = qpu_result["path"], qpu_result["cost"]
    feasible_count = qpu_result["feasible_reads"]
    qpu_access_us = qpu_result["qpu_access_time_us"]
    chip_id = qpu_result["chip_id"]

    matches_optimal = best_path is not None and abs(best_cost - bf_cost) < 1e-6
    print("\nREAL QPU RESULT:          ", end="")
    if best_path is None:
        print("no feasible sample in 100 reads (rare on a problem this small — try rerunning).")
    else:
        print(f"{[WAYPOINTS[i] for i in best_path]}  ({best_cost:.1f} min)")
    print(f"Feasible reads: {feasible_count}/100 | wall time (incl. network+queue): {qpu_result['wall_seconds']*1000:.0f} ms")
    if qpu_access_us:
        print(f"Actual QPU hardware time billed: {qpu_access_us/1000:.2f} ms "
              f"(out of your free monthly allotment)")

    os.makedirs("output", exist_ok=True)
    with open("output/real_quantum_hardware_result.md", "w") as f:
        f.write("# Real quantum hardware validation\n\n")
        f.write(f"QPU used: `{chip_id}`\n\n")
        f.write(f"Route: {START} -> ... -> {END}, via {middle_names}\n\n")
        f.write("| Method | Route order | Cost (min) |\n|---|---|---|\n")
        f.write(f"| Brute-force optimal | {' -> '.join(WAYPOINTS[i] for i in bf_path)} | {bf_cost:.1f} |\n")
        f.write(f"| Classical (NN + 2-opt) | {' -> '.join(WAYPOINTS[i] for i in classical['path'])} | {classical['cost']:.1f} |\n")
        f.write(f"| Quantum-inspired (simulated annealing) | {' -> '.join(WAYPOINTS[i] for i in sa_result['path'])} | {sa_result['cost']:.1f} |\n")
        if best_path is not None:
            f.write(f"| **Real D-Wave QPU** | {' -> '.join(WAYPOINTS[i] for i in best_path)} | {best_cost:.1f} |\n")
        f.write(f"\nFeasible reads on real hardware: {feasible_count}/100\n")
        if qpu_access_us:
            f.write(f"\nActual QPU hardware time: {qpu_access_us/1000:.2f} ms\n")
        f.write(f"\nReal QPU found the optimal solution: "
                f"{'YES' if matches_optimal else 'not on this particular run — annealing is probabilistic, rerunning often finds it'}\n")
        f.write("\n_This solves the exact same `build_open_path_bqm` QUBO the live app uses via "
                "`src/qpu_solver.solve_open_path_on_qpu` — the same function `method=\"qpu\"` calls "
                "everywhere else in this project (see README.md's \"Real quantum hardware "
                "validation\" section) — the only thing that changes here is which sampler solves "
                "it: classical simulated annealing vs. a physical D-Wave quantum annealer._\n")

    print("\nWrote output/real_quantum_hardware_result.md — quote or screenshot this in your pitch.")


if __name__ == "__main__":
    main()
