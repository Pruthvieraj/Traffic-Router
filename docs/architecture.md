# Architecture & Scaling

[← Back to README](../README.md)

## What this project actually is

"Optimize traffic routing" is too broad to build in a few weeks, so this
implements one specific, real slice of it: **given a set of delivery/service
stops a vehicle must visit, and a road network whose travel times change
with congestion, find the best order to visit them in** — a classic
Traveling-Salesman-style routing problem, which is exactly how real
logistics dispatch systems reduce "optimize the route" down to something
solvable.

The pipeline:

1. **`src/city_graph.py`** — the road network. Ships with a small, offline,
   hand-built graph of real Bengaluru localities and approximate road
   distances, so the whole project runs with zero setup and no dependency
   on a live map API being reachable during a demo. Swap in a real
   OpenStreetMap network for any place with one function call — see
   "Using real map data" below.
2. **`src/congestion.py`** — turns the static road graph into a
   time-of-day-dependent one (rush-hour curve + per-road variation), and
   can inject a "spike" on specific roads to simulate an accident or
   closure — this is what the re-optimization demo uses.
3. **`src/distance_matrix.py`** — collapses the full road network down to
   just the pairwise travel times between the stops that actually matter
   (the delivery waypoints), each computed via Dijkstra over the current
   congested graph. This is what makes the next step tractable.
4. **`src/qubo_tsp.py`** — the core "quantum-inspired" piece. Formulates the
   waypoint-ordering problem as a QUBO (the standard representation used
   for D-Wave quantum annealers and QAOA) and solves it with
   `dwave.samplers.SimulatedAnnealingSampler` — a classical algorithm that
   searches the same energy landscape a quantum annealer would, so it's
   "quantum-inspired" without needing actual quantum hardware or a D-Wave
   account. Also supports adding real dispatch constraints (e.g. "pick up
   before drop-off") as extra penalty terms — this is the part that matters,
   see below.
5. **`src/baseline.py`** — a real classical baseline (nearest-neighbor
   construction + 2-opt local search) to compare against, plus a
   brute-force exact solver for small instances so we can measure "how far
   from truly optimal" each method gets.
6. **`src/ortools_baseline.py`** — an optional second, much stronger
   classical comparison point: Google OR-Tools' actual production routing
   solver, wired in the same shape as `baseline.py` so `benchmark.py` can
   drop it straight into Experiment 1. Not a required dependency — see its
   own docstring for why, and "The honest finding" below for what it adds.
7. **`src/benchmark.py`** + **`src/visualize.py`** — runs the two
   experiments below and produces the charts and report.
8. **`src/clustering.py`** — scales the fixed-endpoint solver past what a
   single QUBO can handle (see "Scaling past a dozen stops" below), and
   also implements the multi-vehicle dispatch demo (`solve_multi_vehicle`).
9. **`src/qaoa_solver.py`** — an optional second "quantum-inspired" solver
   for the same QUBO: QAOA, a gate-based variational quantum circuit,
   simulated classically via Qiskit instead of annealed. See "A second
   quantum computing paradigm" below for the full honest scope of what
   this does and doesn't prove.
10. **`src/traffic_provider.py`** — the pluggable interface between "a
   free-flow travel-time matrix" and "a congestion-adjusted one." Ships
   with the simulated model above AND a real, working live-traffic
   integration (`GoogleRoutesTrafficProvider`, `TRAFFIC_PROVIDER=google_routes`
   + your own `GOOGLE_ROUTES_API_KEY`) — see [Traffic-awareness](live-app.md) above for
   the full honest scope of what's genuinely wired up versus what still
   needs your own API key/credentials to run live.
11. **`src/qpu_solver.py`** — a real D-Wave quantum annealer as a first-class
   solver `method` (`method="qpu"`), alongside the classical/quantum-inspired
   methods above — see [Real quantum hardware validation](quantum-hardware.md) below for the
   full honest scope of what's genuinely wired up versus what needs your
   own D-Wave Leap account to run live.
12. **`src/explain.py`** — turns a solved route (or fleet split) into a
   plain-language, per-leg explanation (bottleneck leg, precedence checks,
   capacity margin), returned alongside every `/api/solve` and
   `/api/solve_fleet` response — see [Route explainability](features.md) below.
13. **`src/time_windows.py`** — position-range pruning for real clock-time
   arrival windows on top of the same QUBO — see [Time-window constraints](features.md)
   below for the full honest scope (a partial, disclosed answer, not a
   solved one).

## Scaling past a dozen stops

The open-path QUBO's variable count grows with the *square* of the number
of interior stops, so a single QUBO stays fast and exact up to about a
dozen stops but doesn't scale indefinitely — a real dispatch route can
easily have 20-50 stops in a day. `src/clustering.py` implements the
standard "cluster-first, route-second" strategy real Vehicle Routing
Problem systems use at this scale: stops are split into small groups
(clustered directly on the travel-time matrix — no coordinates needed),
each group's visiting order is solved *exactly* with the same
brute-force-verified solver used everywhere else in this project, and the
groups are stitched together start-to-end.

`app.py`'s `/api/solve` now accepts up to `MAX_STOPS = 40` (up from 10)
via this path — below `CLUSTER_SIZE` (9) interior stops it's an exact
passthrough with identical behavior to before; above it, the response
includes `clusters_used > 1` and the UI's stats panel says so, honestly.
This is a **heuristic decomposition, not a guarantee of the global
optimum** above the threshold — worth saying plainly to judges, because
exact optimization of a 50-stop TSP is intractable for classical and
quantum approaches alike, and every real routing system at that scale
makes the same trade.

