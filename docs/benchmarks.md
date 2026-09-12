# Benchmarks — The Honest Findings

[← Back to README](../README.md)

## The honest finding — please read this before pitching it

**Experiment 1 (plain routing, no constraints):** classical
nearest-neighbor + 2-opt matches or beats the QUBO + simulated-annealing
solver on both solution quality and speed, and the gap widens as the
number of stops grows. We tuned the penalty weighting and annealing sweep
count and this held up — it isn't a bug in this implementation, it's a
well-established result in operations research: 2-opt is a very strong
heuristic for small-to-medium metric TSP, and a generic QUBO/annealing
formulation doesn't beat it on the plain problem. **Do not claim this
project is "faster than classical routing" — a judge or an examiner who
tests it will find the same result we did, and an unsupported speed claim
is the fastest way to lose credibility in the Q&A.**

**This isn't just losing to a weak strawman, either.** When `ortools` is
installed (`pip install ortools` — an optional dependency, see
`src/ortools_baseline.py`), Experiment 1 also runs Google OR-Tools' actual
production routing solver — the same solver family behind real-world route
optimization products, not a hand-rolled student-project heuristic. It
finds the exact optimum on every instance small enough for brute force to
verify, and matches or beats the hand-rolled 2-opt baseline throughout.
Reporting that honestly matters: it rules out "maybe a stronger classical
baseline would've lost" as an excuse, and confirms the real story is what
Experiment 2 says — the quantum-inspired formulation's advantage shows up
once real constraints enter the problem, not on plain TSP where classical
local search (of any quality) already excels.

**Experiment 2 (routing with one real dispatch rule added) — this is the
actual claim:** real delivery dispatch always has rules beyond "shortest
path" — a pickup before its matching drop-off, a stop that must happen
before a cutoff, a road that's off-limits for a hazmat vehicle. We added
one such rule ("visit A before B") and compared:

- **Classical 2-opt**, which only knows about travel time and has no
  concept of the rule, so it violates the rule whenever violating it
  happens to be shorter — **in our test, 8 out of 15 random trials**.
  Patching the route after the fact to fix the violation cost an average
  of **+8.9% extra travel time**, and as much as **+43.8%** in the worst
  observed case.
- **The QUBO solver**, where the rule is one additional penalty term in
  the same optimization — it satisfied the rule **by construction, in all
  15 out of 15 trials**, because an assignment that violates it is
  mathematically penalized inside the same objective the solver is already
  minimizing, not checked afterward.

That gap — constraints satisfied by construction vs. bolted on with
per-rule repair code that still costs real distance — is real and
reproducible (`python3 src/benchmark.py` regenerates it). **Read it as one
ingredient, though, not the whole patent story:** a February 2026
peer-reviewed paper (Curuliuc & Leon, in
`Patent Filing Readiness Research.docx`) already describes this
same "constraint as penalty term ⇒ satisfied by construction" mechanism
for precedence specifically, so on its own this can't anchor a patent
claim. Experiment 3, next, is where the finding that's actually still open
gets measured.

**Experiment 2.5 → Experiment 3 (does solving multiple constraint types
*together* actually matter?):** single-constraint correctness — proven
above, and by that prior paper — doesn't imply a multi-vehicle dispatch
DECISION stays valid once a second constraint type enters the picture.
`src/benchmark.py`'s `run_experiment_3_composed()` takes the same
fleet-dispatch scenario and solves it three ways through the existing,
already-tested `solve_multi_vehicle` API: with demand-weighted vehicle
capacity AND a precedence rule enforced together (**COMPOSED**), with
capacity enforced but the solver never told about the precedence rule
(**CAPACITY-ONLY**), and with precedence enforced but the vehicle SPLIT
itself made without any awareness of demand (**PRECEDENCE-ONLY**). On a
reproducible 14-trial run:

- **COMPOSED** satisfied both precedence AND capacity in **14/14** trials.
- **CAPACITY-ONLY** (precedence-blind) happened to violate the precedence
  rule anyway in **6/14** trials.
- **PRECEDENCE-ONLY** (demand-blind split) put the two stops on
  **different vehicles entirely** in 1/14 trials — the split itself became
  incompatible with the rule, not just costly — and additionally
  **overloaded a vehicle beyond capacity** in **13/13** of the remaining
  trials, by as much as **+51.5%** over the limit.

That's the actual remaining, defensible claim: composing constraint types
into one fleet-dispatch decision — not any single constraint type in
isolation — is what guarantees the whole result stays valid, and neither
prior-art finding in the patent-readiness report covers that combination.
See `output/report.md`'s "Experiment 3" section and
`tests/test_benchmark.py` for the reproducible, regression-tested version
of this claim.

## Multi-objective routing — time vs. distance is a real trade-off, not two names for one number

Every route above optimizes for a single number: congested travel time. Real
dispatch also cares about road distance — a genuine proxy for fuel and
emissions cost, and one that doesn't move the same way time does once
congestion enters the picture (a route can be the fastest without being the
shortest, and vice versa). `src/qubo_tsp.py`'s `combine_objectives()` lets
the *same* QUBO solver minimize a weighted sum of several cost matrices —
`objectives=[(W_time, w), (W_distance, 1 - w)]` — with **zero changes** to
`build_tsp_bqm`/`build_open_path_bqm` themselves, because every QUBO term in
this project's formulation is already linear in the cost matrix, so a
weighted sum of matrices is just another cost matrix. `solve_quantum_inspired`
and `solve_open_path_quantum_inspired` both accept `objectives=` as a direct
alternative to `W=` (passing both, or neither, is an error), and return an
`"objective_breakdown"` — the winning tour's cost under each individual
objective matrix, not just the combined score.

Two things had to be true for this to be a real feature rather than a
cosmetic knob, and both are checked, not just asserted:

- **Exact equivalence at the extremes.** `objectives=[(W, 1.0)]` must
  produce a byte-identical tour and cost to plain `W=W`, and
  `objectives=[(W1, 1.0), (W2, 0.0)]` must exactly recover the `W1`-only
  solve — not "close," `==`. `tests/test_multi_objective.py` asserts this
  with `==`, not `pytest.approx`, because that equivalence is the entire
  reason no change was needed to the QUBO-construction functions.
- **A genuine trade-off in the underlying problem**, not just in the
  solver's math. `src/benchmark.py`'s `run_experiment_4_multi_objective()`
  finds the *true* fastest tour and the *true* shortest tour for random
  waypoint sets by exhaustive search (`baseline.brute_force_optimal` — no
  simulated-annealing noise), then measures what optimizing for only one
  objective actually costs on the other. On a reproducible 12-trial run:
  optimizing for only one objective provably cost something on the other in
  **7/12** trials (average +1.0% extra distance / +0.8% extra time when it
  happened, worst case +1.9% / +2.4%). The other 5 trials happened to tie —
  reported honestly as ties, not folded into the "diverged" count.

Run `python3 src/benchmark.py` to regenerate `output/experiment_4_multi_objective.csv`
and the "Experiment 4" section of `output/report.md`; run
`python3 -m pytest tests/test_multi_objective.py tests/test_benchmark_experiment4.py`
to re-verify both properties above. **Not yet wired up:** the live app
(`app.py`) still solves for time only — `objectives=` is implemented and
tested at the solver/benchmark level, but there's no UI control yet to let a
user pick a time/distance weighting for a live route.

## Fleet mode vs. a real joint capacitated VRP solver

`clustering.solve_multi_vehicle`'s own docstring is upfront about a real
limitation: fleet mode splits stops across vehicles and then routes each
vehicle's stops **separately** (cluster-first/route-second) — once vehicles
are assigned, there's no search for a better overall split. An external
review pointed out a fair gap this left: Experiment 1's OR-Tools comparison
only covers plain single-vehicle TSP, so fleet mode never had an equivalent
"how does this compare to a real industrial solver" number.

`src/ortools_vrp_baseline.py` closes that gap with Google OR-Tools' actual
capacitated VRP solver (`AddDimensionWithVehicleCapacity` across a shared
vehicle pool, decided **jointly** with the routing — it can move a stop from
one vehicle's route to another's mid-search) — same optional-dependency
pattern as `ortools_baseline.py` (`pip install ortools`; degrades to a clear
`RuntimeError` when it isn't installed, never a silent skip of the
comparison). `run_experiment_6_cvrp_baseline()` runs the same demand-weighted,
capacity-only fleet scenario through both `solve_multi_vehicle` and
OR-Tools' CVRP solver and reports the gap directly — deliberately without a
precedence rule, since the composed-constraints question is Experiment 3's
claim, not this one's.

**Honest finding, stated before looking at results (and confirmed by a
15-trial run):** the joint solver never costs more than our two-step split —
expected, since it can always fall back to reproducing the same split if
nothing better exists — but it does find a real, measurable improvement on
most trials: our cluster-first/route-second split runs a few percent above
OR-Tools' joint solve on average, more on the worst individual trial, and
ties it exactly on the trials where the two-step split already happened to
be optimal. That is a genuine, bounded gap from solving the fleet split and
the routing in two separate steps instead of one — not evidence the fleet
mode's output is unreasonable, but not nothing either. See
`output/report.md`'s "Experiment 6" section for the exact numbers from the
most recent run.

Run `python3 src/benchmark.py` to regenerate `output/experiment_6_cvrp_baseline.csv`
and that report section; run `python3 -m pytest tests/test_benchmark_experiment6.py
tests/test_ortools_vrp_baseline.py` to re-verify (both files skip cleanly,
not fail, when `ortools` isn't installed). **Same scope limit as the rest of
this section:** OR-Tools supports precedence too (pickup-delivery pair
constraints), but wiring that in here would mean re-deriving a second,
parallel precedence implementation purely for benchmarking — not attempted,
since capacity alone already answers the specific question this experiment
exists to ask.

## Concurrency / load test — what one gunicorn worker actually does under load

The Procfile runs a single `gunicorn` sync worker (`web: gunicorn app:app
--bind 0.0.0.0:$PORT --timeout 120`), matching this project's own
"no paid infrastructure" build constraint — a second worker or a
Redis-backed queue would be real infra spend, not a free demo. A second,
independent judge review asked the fair question this repo had no real
number for: what actually happens under concurrent requests? `loadtest.py`
(repo root) answers it directly, run locally against a real `gunicorn app:app`
process — not simulated:

**Rate limiting works as documented.** A burst of 30 requests fired at once
against a normally-configured server (rate limiting on, the real deployed
posture) got exactly **20 `200 OK` and 10 `429 Too Many Requests`** —
`output/loadtest_rate_limit.json` — confirming the `20 per minute` IP-based
limit (`app.py`, `flask-limiter`) actually enforces, not just that the
package is installed.

**Latency scales roughly linearly with concurrency, because one worker
serves one request at a time — exactly as documented, not a bug this test
found.** With rate limiting deliberately disabled for this measurement only
(`DISABLE_RATE_LIMIT_FOR_LOADTEST=1`, an explicit opt-in — see `app.py`),
against an 8-stop classical solve:

| concurrency | p50 latency | p99 latency | throughput |
|---|---|---|---|
| 1  | 2 ms   | 3 ms   | 479 req/s |
| 5  | 7 ms   | 9 ms   | 620 req/s |
| 10 | 13 ms  | 17 ms  | 621 req/s |
| 20 | 21 ms  | 30 ms  | 556 req/s |

Classical 2-opt is fast enough that even 20 concurrent requests barely
register. The quantum method (simulated annealing via `dwave-samplers`) is
the more honest stress test, since it does real per-request work:

| concurrency | p50 latency | p99 latency | throughput |
|---|---|---|---|
| 1  | 167 ms  | 199 ms  | 5.96 req/s |
| 5  | 757 ms  | 795 ms  | 6.53 req/s |
| 10 | 1528 ms | 1589 ms | 6.46 req/s |
| 20 | 2530 ms | 3272 ms | 6.12 req/s |

Throughput plateaus at **~6.2 requests/second regardless of concurrency**,
while p50 latency climbs almost exactly linearly (167 ms → 2530 ms, roughly
1:15 for a 1:20 increase in concurrency) — the signature of a single sync
worker queuing requests rather than running them in parallel. This is
precisely the scaling limit `docs/live-app.md` and `README.md` already
named ("scaling out needs shared state, which isn't built yet") — now with
a real number instead of a guess. Full raw results:
`output/loadtest_capacity_classical.json`, `output/loadtest_capacity_quantum.json`.

Reproduce it yourself:

```bash
DISABLE_RATE_LIMIT_FOR_LOADTEST=1 python3 -m gunicorn app:app --bind 127.0.0.1:5001 &
python3 loadtest.py capacity --url http://127.0.0.1:5001 --stops 8 --method quantum
python3 loadtest.py rate-limit --url http://127.0.0.1:5000   # against a normal, rate-limited server
```

`loadtest.py`'s own module docstring has the full mode reference; its pure
helper functions (matrix generation, percentile math, payload shapes) are
covered by `tests/test_loadtest.py` — the network calls themselves are
deliberately not part of the automated suite, since the whole point is to
run it by hand against a real local server, not to make every CI run fire
HTTP bursts at itself.

