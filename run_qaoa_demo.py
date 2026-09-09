#!/usr/bin/env python3
"""
run_qaoa_demo.py — solve the SAME open-path QUBO this project uses with
QAOA (a gate-based quantum circuit algorithm), side by side with brute
force, the classical baseline, and this project's usual simulated-
annealing "quantum-inspired" solver.

WHY THIS EXISTS: qubo_tsp.py's main solver is quantum-INSPIRED via
simulated annealing — a classical algorithm, no quantum circuit involved.
QAOA is the other major paradigm quantum computing research targets for
this kind of problem, and src/qaoa_solver.py shows the exact same QUBO
formulation ports to it directly, no reformulation needed. This script is
the pitch-deck-ready side-by-side comparison, in the same spirit as
run_on_real_quantum_hardware.py (which does the analogous thing for real
D-Wave annealing hardware) — a credibility artifact you run once and
quote/screenshot, not part of the live demo's normal code path.

WHAT THIS NEEDS THAT THE MAIN APP DOESN'T: `pip install qiskit` (see
src/qaoa_solver.py's docstring for why only plain qiskit, not the heavier
qiskit-optimization/qiskit-algorithms wrapper packages).

RUN:
    python3 run_qaoa_demo.py

OUTPUT: prints all four methods' routes/costs side by side, and writes
output/qaoa_demo_result.md — meant to be quoted directly in a pitch deck,
including the honest caveats about what a classical circuit-simulator
comparison does and doesn't prove (see src/qaoa_solver.py's own docstring
for the full version of those caveats).
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

# Deliberately tiny — 3 "middle" stops is 9 qubits, near the practical top
# end for a classical statevector simulation (see src/qaoa_solver.py's
# honest-scope section on why), while still being a genuine 5-point,
# non-trivial routing problem with 6 possible orderings to search over.
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
    print(f"Brute-force optimal:       {[WAYPOINTS[i] for i in bf_path]}  ({bf_cost:.1f} min)")

    classical = nearest_neighbor_2opt_open_path(W, start_idx, end_idx)
    print(f"Classical (NN + 2-opt):    {[WAYPOINTS[i] for i in classical['path']]}  "
          f"({classical['cost']:.1f} min, {classical['wall_seconds']*1000:.1f} ms)")

    sa_result = solve_open_path_quantum_inspired(W, start_idx, end_idx, num_reads=500)
    print(f"Quantum-inspired (SA):     {[WAYPOINTS[i] for i in sa_result['path']]}  "
          f"({sa_result['cost']:.1f} min, {sa_result['wall_seconds']*1000:.1f} ms)")

    print("\nRunning QAOA on a classical statevector simulator...")
    try:
        from qaoa_solver import solve_open_path_with_qaoa
    except ImportError:
        print("\nqiskit isn't installed. Run:  pip install qiskit")
        print("(See src/qaoa_solver.py's docstring for the full honest-scope explanation.)")
        return

    qaoa_result = solve_open_path_with_qaoa(W, start_idx, end_idx, reps=2, maxiter=150)
    print("QAOA (p=2, simulated):     ", end="")
    if not qaoa_result["valid"]:
        print(f"sampled bitstring violated the QUBO's constraints (rare on a problem this "
              f"small, but genuinely possible with a single optimization run — see "
              f"src/qaoa_solver.py point 4 on why this is reported honestly rather than patched).")
    else:
        print(f"{[WAYPOINTS[i] for i in qaoa_result['path']]}  "
              f"({qaoa_result['cost']:.1f} min, {qaoa_result['wall_seconds']*1000:.1f} ms, "
              f"{qaoa_result['num_qubits']} qubits)")

    matches_optimal = qaoa_result["valid"] and abs(qaoa_result["cost"] - bf_cost) < 1e-6

    os.makedirs("output", exist_ok=True)
    with open("output/qaoa_demo_result.md", "w") as f:
        f.write("# QAOA (gate-based quantum circuit) comparison\n\n")
        f.write(f"Route: {START} -> ... -> {END}, via {middle_names} ({qaoa_result['num_qubits']} qubits)\n\n")
        f.write("| Method | Route order | Cost (min) |\n|---|---|---|\n")
        f.write(f"| Brute-force optimal | {' -> '.join(WAYPOINTS[i] for i in bf_path)} | {bf_cost:.1f} |\n")
        f.write(f"| Classical (NN + 2-opt) | {' -> '.join(WAYPOINTS[i] for i in classical['path'])} | {classical['cost']:.1f} |\n")
        f.write(f"| Quantum-inspired (simulated annealing) | {' -> '.join(WAYPOINTS[i] for i in sa_result['path'])} | {sa_result['cost']:.1f} |\n")
        if qaoa_result["valid"]:
            f.write(f"| **QAOA (p=2, gate-based, simulated)** | {' -> '.join(WAYPOINTS[i] for i in qaoa_result['path'])} | {qaoa_result['cost']:.1f} |\n")
        else:
            f.write("| **QAOA (p=2, gate-based, simulated)** | *invalid sample this run* | — |\n")
        f.write(f"\nQAOA found the optimal solution: "
                f"{'YES' if matches_optimal else 'not on this particular run'}\n")
        f.write(
            "\n_This solves the exact same `build_open_path_bqm` QUBO the live app and the "
            "simulated-annealing solver both use — the only thing that changes here is which "
            "quantum computing paradigm solves it: classical simulated annealing (mimicking a "
            "quantum annealer) vs. an actual gate-based variational quantum circuit (QAOA), run "
            "on a classical statevector simulator. See src/qaoa_solver.py's docstring for the "
            "full, honestly-stated scope of what a small simulated QAOA run does and doesn't "
            "prove — this is a portability demonstration (same QUBO, different quantum "
            "paradigm), not a claim that QAOA beats simulated annealing here._\n"
        )

    print("\nWrote output/qaoa_demo_result.md — quote or screenshot this in your pitch.")


if __name__ == "__main__":
    main()
