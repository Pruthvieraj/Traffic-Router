# QAOA (gate-based quantum circuit) comparison

Route: Majestic -> ... -> HSR Layout, via ['Indiranagar', 'Koramangala', 'Jayanagar'] (9 qubits)

| Method | Route order | Cost (min) |
|---|---|---|
| Brute-force optimal | Majestic -> Jayanagar -> Indiranagar -> Koramangala -> HSR Layout | 153.0 |
| Classical (NN + 2-opt) | Majestic -> Jayanagar -> Koramangala -> Indiranagar -> HSR Layout | 153.0 |
| Quantum-inspired (simulated annealing) | Majestic -> Jayanagar -> Koramangala -> Indiranagar -> HSR Layout | 153.0 |
| **QAOA (p=2, gate-based, simulated)** | Majestic -> Jayanagar -> Indiranagar -> Koramangala -> HSR Layout | 153.0 |

QAOA found the optimal solution: YES

_This solves the exact same `build_open_path_bqm` QUBO the live app and the simulated-annealing solver both use — the only thing that changes here is which quantum computing paradigm solves it: classical simulated annealing (mimicking a quantum annealer) vs. an actual gate-based variational quantum circuit (QAOA), run on a classical statevector simulator. See src/qaoa_solver.py's docstring for the full, honestly-stated scope of what a small simulated QAOA run does and doesn't prove — this is a portability demonstration (same QUBO, different quantum paradigm), not a claim that QAOA beats simulated annealing here._
