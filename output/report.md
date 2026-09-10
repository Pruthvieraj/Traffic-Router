# Benchmark results

## Experiment 1 — plain routing, no business constraints

| N waypoints | 2-opt (min) | QUBO+SA (min) | OR-Tools (min) | 2-opt time (ms) | QUBO+SA time (ms) | OR-Tools time (ms) |
|---|---|---|---|---|---|---|
| 6 | 186.7 | 186.7 | 186.7 | 0.05 | 347.22 | 2006.57 |
| 8 | 186.7 | 220.2 | 186.7 | 0.08 | 677.17 | 2001.24 |
| 10 | 260.6 | 301.7 | 260.6 | 0.07 | 1055.07 | 2000.53 |
| 12 | 412.3 | 561.7 | 412.3 | 0.11 | 1472.3 | 2000.49 |
| 14 | 538.0 | 725.8 | 538.0 | 0.21 | 2199.21 | 2000.37 |

**Honest finding:** on plain, unconstrained routing, classical nearest-neighbor+2-opt matches or beats the QUBO+simulated-annealing solver on both solution quality and speed. This matches well-established operations-research literature — 2-opt is a very strong heuristic for small-to-medium metric TSP, and a generic QUBO penalty formulation doesn't beat it here. We are not claiming otherwise; see Experiment 2 for where the QUBO framing earns its keep.

**A stronger comparison point:** the table above also includes Google OR-Tools' production routing solver — a real, widely-deployed industrial solver, not a hand-rolled student-project heuristic like the 2-opt baseline above. Where its cost is within a hair of `true_optimal_min` (see the CSV — OR-Tools is run with a short time budget and finds the exact optimum on every small instance we've tried), it confirms 2-opt beating our QUBO solver on plain unconstrained TSP isn't an artifact of a weak baseline: even the strongest practical classical solver available wins here too, for the same well-understood reason (plain metric TSP without extra constraints is exactly the regime classical local search already handles very well). This makes Experiment 2 the fair place to look for the quantum-inspired approach's actual advantage, not this one.

## Experiment 2 — routing with one real dispatch constraint added

- Trials run: **15**
- Plain 2-opt (constraint-unaware) violated the precedence rule in **8/15** trials
- QUBO+SA satisfied the rule by construction in **15/15** trials
- Average extra travel cost from patch-repairing a violated 2-opt route after the fact: **+8.4%**
- Worst-case repair cost observed: **+31.9%**

**A real, measurable effect — but read it as one ingredient, not the whole claim.** Once a routing problem has real dispatch constraints (pickup-before-dropoff, no-entry zones, priority stops, vehicle capacity — any rule beyond 'shortest path'), a classical local-search heuristic has no way to know about them and violates them more often than not unless a developer hand-writes a repair patch for every rule, which itself costs real distance. The QUBO formulation incorporates each new constraint as one additional composable penalty term in the same optimization and satisfies it by construction. **This single-constraint mechanism on its own is not the patent claim** — a February 2026 peer-reviewed paper (Curuliuc & Leon) already describes the same precedence-as-penalty-term mechanism (see "Patent Filing Readiness Research.docx"). Experiment 3 below is where the actual remaining claim — composing multiple constraint types together — gets tested.

## Experiment 3 — does solving constraints TOGETHER actually matter?

Same fleet-dispatch scenario, three ways: solved with both demand-weighted capacity AND a precedence rule at once (COMPOSED), solved capacity-aware but precedence-blind (CAPACITY-ONLY), and solved precedence-aware but demand-blind during the vehicle split itself (PRECEDENCE-ONLY). All three use the same public `solve_multi_vehicle` API — this tests composition, not a new solver.

- Trials run: **14** (trials where no precedence pair landed on a shared vehicle under the composed split were skipped, not counted)
- COMPOSED satisfied both precedence AND capacity in **14/14** trials
- CAPACITY-ONLY (precedence-blind) happened to violate the precedence rule anyway in **6/14** trials
- PRECEDENCE-ONLY (demand-blind split) put the two stops on **different vehicles entirely** in **1/14** trials (the split itself became incompatible with the rule — solve_multi_vehicle correctly refuses rather than silently dropping it), and additionally **overloaded a vehicle beyond capacity** in **13/13** of the remaining trials where the pair did stay together
- Worst observed overload from the demand-blind split (where it didn't separate the pair outright): **+51.5%** over `vehicle_capacity`

**This is the actual remaining patent-relevant finding.** Handling one constraint type correctly (proven above, and by prior art) does not imply the fleet-dispatch DECISION stays valid once a second constraint type is added — a demand-blind split can hand a capacity-respecting-looking result to a vehicle that's actually overloaded, or can split the stops in a way that makes an otherwise-satisfiable precedence rule impossible to honor at all, because the SPLIT itself, not just the route, was made without knowing about demand. Composing precedence and capacity into one solve_multi_vehicle call is what guarantees both hold together, which is the system-level claim ("Tier 2" in the patent-readiness report) that neither Finding #1 (single constraint type, no live fleet split) nor Finding #2 (capacity only, no precedence) in that report covers.

## Experiment 4 — is "multi-objective" a real trade-off?

For each random waypoint set, the TRUE fastest tour and the TRUE shortest tour are found by exhaustive search (no simulated-annealing noise), then each is evaluated against the OTHER objective's matrix to measure what optimizing for only one actually costs.

- Trials run: **12**
- Trials where optimizing for only one objective provably costs something on the other: **7/12**
- When they differ — extra distance from optimizing time only: avg **+1.0%**, worst **+1.9%**
- When they differ — extra time from optimizing distance only: avg **+0.8%**, worst **+2.4%**

**Finding:** time and distance are a genuine trade-off in this problem, not two names for the same number — optimizing for only one measurably costs the other. `qubo_tsp.combine_objectives` lets the SAME QUBO solver minimize a weighted sum of both with zero changes to `build_tsp_bqm`, and `tests/test_multi_objective.py` proves at the unit level (exact equality, not approximate) that the weighted-sum solve reduces to exactly this single-objective optimum at each extreme weight. Together, this is what turns "multi-objective routing" from a marketing word into a measured, provable property of the system.

## Experiment 5 — does time-window "position pruning" actually help?

time_windows.py is upfront that this project's position-based QUBO can't encode wall-clock arrival time directly — a real time-window guarantee needs a different formulation family (arc-based decision variables plus a time-propagation constraint), which is why this was flagged as the highest formulation-risk item on the roadmap. What IS implemented is a provably-safe pruning of tour POSITIONS that could never satisfy a window (`derive_position_window`), enforced in the QUBO exactly like precedence, then verified against the real solved schedule. This experiment measures the honest gap between "pruned" and "guaranteed" directly, on windows constructed to be a genuine ask (shifted meaningfully earlier than where the waypoint naturally landed with no constraint at all).

- Trials run: **15** (trials whose constructed window was provably infeasible for the instance were skipped, not counted)
- WITHOUT position pruning, the unconstrained solve's schedule already satisfied the window in **0/15** trials
- WITH position pruning (`solve_with_time_windows`), the window was actually satisfied in **3/15** trials

**Honest finding:** pruning helps — it never does worse than solving with no time-awareness at all — but it is NOT a satisfaction guarantee, and the numbers above show that plainly: two tours can place the same waypoint at the same allowed POSITION while arriving there at very different real times, because the position bound only rules out placements that could never work for ANY tour, not placements that simply didn't work out for the specific tour the solver found. **This is a partial, honestly-scoped answer to time windows, not a solved one** — full wall-clock guarantees remain a real reformulation, not yet attempted here.

## Experiment 6 — fleet mode vs. a real joint capacitated VRP solver

`clustering.solve_multi_vehicle`'s own docstring is upfront that fleet mode splits stops across vehicles and then routes each vehicle SEPARATELY (cluster-first/route-second) — it never searches for a better split once vehicles are assigned. This experiment compares that against Google OR-Tools' capacitated VRP solver (`src/ortools_vrp_baseline.py`), which decides the split and the routing JOINTLY, on identical capacity-only scenarios (no precedence — that composed-constraints question is Experiment 3's, not this one's).

- Trials run: **15**
- Our two-step split's total cost was on average **10.4% above** OR-Tools' joint solve, worst case **41.8% above** in a single trial, and **3/15** trials tied OR-Tools exactly (the two-step split already happened to be optimal)

**Honest finding:** a real joint solver never did worse than our cluster-first/route-second split, which is expected (it can always fall back to reproducing the same split) — the gap above is the genuine, measured cost of deciding the fleet split and the routing in two separate steps instead of one. It is a real gap, but a bounded one on these scenario sizes, not a case where fleet mode's output is unreasonable — see docs/benchmarks.md for the full picture alongside Experiments 1-5.
