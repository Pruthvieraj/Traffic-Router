# Benchmark results

## Experiment 1 — plain routing, no business constraints

| N waypoints | 2-opt (min) | QUBO+SA (min) | 2-opt time (ms) | QUBO+SA time (ms) |
|---|---|---|---|---|
| 6 | 186.7 | 186.7 | 0.04 | 361.82 |
| 8 | 186.7 | 220.2 | 0.06 | 711.77 |
| 10 | 260.6 | 301.7 | 0.08 | 1140.11 |
| 12 | 412.3 | 561.7 | 0.19 | 1714.57 |
| 14 | 538.0 | 725.8 | 0.26 | 2493.95 |

**Honest finding:** on plain, unconstrained routing, classical nearest-neighbor+2-opt matches or beats the QUBO+simulated-annealing solver on both solution quality and speed. This matches well-established operations-research literature — 2-opt is a very strong heuristic for small-to-medium metric TSP, and a generic QUBO penalty formulation doesn't beat it here. We are not claiming otherwise; see Experiment 2 for where the QUBO framing earns its keep.

## Experiment 2 — routing with one real dispatch constraint added

- Trials run: **15**
- Plain 2-opt (constraint-unaware) violated the precedence rule in **8/15** trials
- QUBO+SA satisfied the rule by construction in **15/15** trials
- Average extra travel cost from patch-repairing a violated 2-opt route after the fact: **+8.4%**
- Worst-case repair cost observed: **+31.9%**

**This is the project's real technical claim:** once a routing problem has real dispatch constraints (pickup-before-dropoff, no-entry zones, priority stops, vehicle capacity — any rule beyond 'shortest path'), a classical local-search heuristic has no way to know about them and violates them more often than not unless a developer hand-writes a repair patch for every rule, which itself costs real distance. The QUBO formulation incorporates each new constraint as one additional composable penalty term in the same optimization and satisfies it by construction. That is the measurable technical effect the patent description should center on — not raw speed on the unconstrained case.
