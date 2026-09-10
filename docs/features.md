# Route Explainability & Time Windows

[← Back to README](../README.md)

## Route explainability — why does the route look like this?

A solver that just hands back a list of stop indices leaves the real
questions unanswered: which leg of the trip is actually costing the most
time, is a business rule actually being honored (and by how much margin),
and — if it isn't obviously being honored — what would it have cost to
enforce it anyway? `src/explain.py` answers these by interpreting an
already-solved route, not by changing how routes are solved: it adds no new
solver logic and nothing about `qubo_tsp.py`/`clustering.py` changed for
this.

- **`explain_path(path, W, ...)`** — a leg-by-leg cost breakdown of any
  solved path (a single-vehicle open path, or one vehicle's closed
  depot-loop): each leg's cost and share of the total, the single
  most-expensive ("bottleneck") leg, and, when a `precedence` list is
  passed, a per-rule check of whether it's satisfied and at exactly which
  positions in the route.
- **`explain_precedence_impact(W, precedence, ...)`** — the per-instance
  version of what `benchmark.py`'s Experiment 2 measures in aggregate:
  solves the *same* instance with and without a precedence rule (both via
  the unchanged `solve_quantum_inspired`) and reports the real extra cost
  of enforcing it on *this specific* route, not an average across many
  random trials.
- **`explain_fleet(result, W, ...)`** — the multi-vehicle version: each
  vehicle's own leg breakdown, its remaining capacity headroom (when
  `demands`/`vehicle_capacity` were used for the solve), and which vehicle
  owns each precedence rule and whether that vehicle's own route satisfies
  it.

All three are covered by `tests/test_explain.py` (12 tests) — checked
against independently recomputed totals and percentages, not trusted as a
black box.

**Already wired into the live app:** both `/api/solve` and
`/api/solve_fleet` now return an `"explanation"` field built from the route
they just solved (see `app.py`) — covered by 4 tests in `tests/test_app.py`.
**Now rendered in the UI too:** a collapsible "Why this route?" panel in
the stats sidebar (`_explanationHtml()` in `templates/click_router.html`)
shows the bottleneck leg, per-rule precedence checks, and — in fleet
mode — each vehicle's own breakdown plus its capacity headroom, computed
from that vehicle's own path positions rather than the combined fleet's.
Also shown alongside it: each time-window rule's real checked outcome
(`_timeWindowChecksHtml()` — see "Time-window constraints" below) and a
clearly-labeled-as-an-estimate fuel/CO2 figure (`_fuelCo2Html()`, generic
average-petrol-car constants disclosed as such, not measured for any real
vehicle). **Honest gap:** `explain_precedence_impact`'s before/after
comparison still isn't called from either endpoint, since it means a
second solve (real added latency for a live click) — it's available as a
library function and demonstrated in `tests/test_explain.py`, not yet
exposed as its own API route or UI control.

## Time-window constraints — a partial, honestly-scoped answer, not a solved one

Real dispatch often has a real clock-time requirement — "the pharmacy pickup
must happen between 9am and 11am." This is the roadmap's highest
formulation-risk item, and the reason why is structural: `qubo_tsp.py`'s
QUBO encodes a tour as `x[v, t] = 1` iff waypoint `v` is at tour POSITION
`t`, not at any particular clock time — and a position-based QUBO has no
direct way to penalize "arrive after 11:00," because arrival time at
position `t` isn't a fixed function of `t` alone, it depends on which
specific edges the eventual tour uses to get there. Encoding TRUE wall-clock
windows exactly needs a different formulation family (arc-based decision
variables plus a time-propagation constraint per edge, e.g. an MTZ-style
scheme) — a genuinely bigger rewrite than this project's other constraint
additions (precedence, capacity, position windows), and `src/time_windows.py`
does **not** attempt that rewrite. It does something smaller, real, and
honestly bounded instead:

- **`derive_position_window(W, window)`** converts a real clock-time window
  into a tour-POSITION range that's *provably safe* to enforce: reaching
  position `t` always costs at least the sum of the `t` smallest edges in
  `W` and at most the sum of the `t` largest (summing any `t` distinct
  numbers can never beat the globally smallest `t`, or exceed the globally
  largest `t`) — so any position whose best-case cost already exceeds the
  window, or whose worst-case cost never reaches it, is mathematically
  impossible for *any* tour, not just the one eventually found. Excluding
  only those positions can never discard a solution that could have
  satisfied the window.
- **`qubo_tsp.add_position_window_penalty`** enforces that derived range as
  a hard QUBO constraint — the same mechanism as precedence, wired through
  a new `position_windows=` parameter on `build_tsp_bqm` /
  `build_open_path_bqm` / both solve functions (backward compatible: omitted
  by default, verified via `test_build_tsp_bqm_without_position_windows_is_unchanged`).
- **`compute_arrival_schedule` + `check_time_windows`** compute the REAL
  cumulative arrival time of whatever tour the solver actually returns and
  check it against the requested window — the ground truth this whole
  module is honest about needing, since the pruning above is necessary but
  not sufficient.
- **`solve_with_time_windows(...)`** ties all three together: derive safe
  bounds, solve with them enforced, verify the real result, and report
  exactly which windows (if any) are still violated.

**Measured, not just argued (`benchmark.py`'s Experiment 5, 15 trials, each
window deliberately shifted earlier than where the target waypoint landed
with no constraint at all, so it's a genuine ask):** without any
time-awareness, the unconstrained solve happened to satisfy the window in
**0/15** trials; with position-window pruning enforced, it was satisfied in
**3/15** trials. **Pruning helps — it never does worse than no time-
awareness at all (locked in by `test_with_pruning_never_does_worse_than_without_pruning`)
— but it is not a guarantee**, and the numbers say so plainly: two tours can
share the same allowed position for the target waypoint while arriving
there at very different real times, because the position bound only rules
out placements that could never work for *any* tour, not placements that
simply didn't pan out for the specific tour found. Run
`python3 src/benchmark.py` to regenerate `output/experiment_5_time_windows.csv`
and see the "Experiment 5" section of `output/report.md`; run
`python3 -m pytest tests/test_time_windows.py tests/test_benchmark_experiment5.py`
(19 tests) to re-verify the rigor claims and the measured gap above.

**Now wired into the live app and the UI.** `/api/solve` accepts an
optional `time_windows` field (`{"point_index": [earliest, latest]}`,
minutes from the Start point) — see app.py's `_validate_time_windows` and
`solve()`, which converts each window to a position bound via
`derive_position_window` against the ACTUAL congested matrix about to be
solved on, solves, then verifies the real result via
`compute_arrival_schedule`/`check_time_windows` and returns
`time_window_checks`/`all_time_windows_satisfied` — never just the pruning
guarantee. Same honest scope as everywhere else this restriction applies:
`method="quantum"`/`"qpu"` only (classical 2-opt has no notion of a
position constraint), and only up to `CLUSTER_SIZE` interior stops (7
tests in `tests/test_app.py`, 4 in `tests/test_clustering.py`). The
click-map UI's "Time windows" panel (`templates/click_router.html`,
mirroring the existing Precedence panel's UI pattern) lets you author
these rules directly — pick a stop, set an earliest/latest minute, Add —
and the checked outcome (met/missed, with slack or how much it missed by)
renders inside the "Why this route?" explanation panel after solving. Only
in single-vehicle mode, since `/api/solve_fleet` doesn't accept this
field. Covered by 4 Playwright layout tests in `tests/test_layout.py`
(add/remove a rule, reject an invalid range, hide in fleet mode, and the
remap/drop-on-removal helpers). Stated plainly because it's still the
honest conclusion of Experiment 5 above: **this is not a wall-clock
time-window guarantee** — it is real, tested, rigorous pruning that
measurably helps and is now checked against the real solved schedule on
every request, with the true reformulation needed for an unconditional
guarantee left as explicit future work rather than something this
iteration claims to have solved.

