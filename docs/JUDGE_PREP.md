# Judge Prep — 25 Hardest Questions

[← Back to README](../README.md)

This is a rehearsal sheet, not marketing copy. It came out of a second,
independent judge-style review of this project (an audit that actually ran
`app.py` in a network-restricted sandbox and scored it against the PS) and
every answer below is checked against the current code and docs, not
against how the review remembered them. Where the review's own numbers
were slightly off, the correction is noted — a judge who catches you citing
a wrong number is worse than one who catches a genuine limitation, because
the second one you can own and the first you can't.

Read this out loud as a team before Round 2. The "weak answer" column is
there because it's the answer that comes out under pressure if you haven't
rehearsed — not a strawman.

## Problem

**Q1 — Why does your solution cap at ~40 stops when real logistics fleets run 100+ stops a day?**

*Why asked:* the PS explicitly asks for large-scale VRP.

Weak: "It can handle more if you just increase the limit."

Strong: `MAX_STOPS = 40` (`app.py`) is a live-demo-speed ceiling, not the
solver's real limit — it exists so a Round-2 demo answers in seconds, not
minutes. The QUBO's variable count grows quadratically with stop count, so
above ~9 stops the app already switches to cluster-first/route-second
decomposition (`src/clustering.py`), the same strategy production VRP
systems use at scale. Say plainly that this is a heuristic decomposition
above 9 stops, not a guaranteed joint optimum — `tests/test_ortools_vrp_baseline.py`
is exactly the test that checks the split never costs more than a true
joint solve, per trial, not just on average.

**Q2 — Is your traffic model based on real data, or entirely made up?**

*Why asked:* "real-time traffic conditions" is in the PS.

Weak: implying it's live traffic when it isn't by default.

Strong: the default is a disclosed, reproducible time-of-day simulation
(`src/congestion.py`). A real live-traffic provider
(`src/traffic_provider.py`'s `GoogleRoutesTrafficProvider`) is already
wired in behind a pluggable interface end-to-end — including through
`/api/solve_fleet`, not just single-vehicle solve — it's just not enabled
in this free demo because it needs a paid Google API key. A real-data
calibration pipeline against IISc's UVH-26 vehicle-density dataset also
exists (`src/vehicle_density_calibration.py`, 16 tests) for whenever
someone with unrestricted internet access can download it and run
`calibrate_from_uvh26.py`.

## Innovation

**Q3 — What's genuinely novel here that a team couldn't build from a QUBO-TSP tutorial in a weekend?**

Weak: "We used quantum computing."

Strong: point to the *composed* multi-constraint system — precedence,
capacity, time windows, and live incidents, together, in one objective,
measured — not the base QUBO. `docs/benchmarks.md` Experiment 3 is
specifically the composed-constraint result; that combination, not the
underlying QUBO+SA pattern, is the actual contribution.

**Q4 — You found a paper that overlaps your core mechanism — doesn't that undercut your innovation claim?**

Weak: avoiding the question or downplaying the overlap.

Strong: own it directly. A Feb 2026 peer-reviewed paper (Curuliuc & Leon)
already describes precedence-as-a-penalty-term inside a QUBO, so that
mechanism alone can't anchor a patent claim (see `docs/patent-note.md`).
The narrower, still-open claim is the specific *composed* system —
precedence + capacity + live incidents handled together, with the
cross-cluster precedence co-location logic in `src/clustering.py` — which
that paper doesn't cover. Leading with "we found the closest prior art
ourselves" reads as rigor, not weakness.

## AI / ML

**Q5 — Where's the actual AI/ML in this — isn't this just classical optimization with a quantum label?**

Weak: claiming it's AI to fit the expectation.

Strong: correct the framing confidently. This is combinatorial
optimization inspired by quantum annealing — a distinct, PS-relevant field
from machine learning — and say so without apologizing for it.

**Q6 — The PS names QPSO specifically — why QUBO + simulated annealing instead?**

Weak: not knowing the PS names QPSO at all.

Strong: the PS says "approaches like QPSO" — QUBO+SA is also a legitimate
metaheuristic, and unlike QPSO it maps directly onto real quantum
annealing hardware (D-Wave), which is arguably the more literal reading of
"quantum-inspired." `src/qpu_solver.py` is the real-QPU wiring, tested
against an injected stand-in sampler plus an unmocked no-token failure
path.

## Dataset

**Q7 — What real-world dataset did you validate this against?**

Weak: implying real fleet data was used when it wasn't.

Strong: real OpenStreetMap road geometry via OSRM for every route drawn;
synthetic benchmark instances for the controlled experiments. State the
distinction plainly rather than letting it blur.

**Q8 — Does the problem statement come with an official dataset, and did you use it?**

Weak: not knowing whether one exists.

Strong: confirm with the organization directly before Round 2 whether
SIH26137 ships an official dataset. This is not something to guess at —
if one exists and isn't used yet, it's the single highest-priority item to
close, and only the team can make that phone call or check the portal.

## Accuracy

**Q9 — How do you know your solver is near-optimal at real scale, where you can't brute-force verify it?**

Weak: "We trust the algorithm."

Strong: the OR-Tools comparison (`tests/test_ortools_baseline.py`,
`tests/test_ortools_vrp_baseline.py`) is a much stronger benchmark than
brute force at larger sizes — it's a real production solver, not a
hand-rolled reference. Be upfront that the clustering heuristic above 9
stops has no optimality guarantee, only the never-worse-than-the-split
property checked per trial.

**Q10 — Your own benchmark shows classical beats you on plain routing — why should we trust the constrained numbers?**

*Why asked:* directly tests intellectual honesty under pressure.

Weak: getting defensive or minimizing the plain-routing result.

Strong: because the case where it loses is published too — that's exactly
why the case where it wins is credible rather than cherry-picked. The
actual number (correcting the review's "7/15"): classical 2-opt violated
an added precedence rule in **8/15** random trials, costing up to +43.8%
extra distance to patch after the fact; the QUBO solver satisfied it **by
construction, 15/15**, because the rule is a penalty term inside the same
objective being minimized (`docs/benchmarks.md`, `README.md`).

## Architecture

**Q11 — Why does mapping run client-side but optimization run server-side — isn't that an odd split?**

Weak: not having a reason ready.

Strong: cloud hosts get rate-limited or blocked by OSM's Overpass API as
datacenter traffic; moving map queries to the browser (a visitor's
ordinary residential IP) fixed a real deployment bug seen on Render. This
was a documented architecture change (`docs/architecture.md`), not an
accident.

**Q12 — What happens if two people hit Solve at the same instant on your single worker process?**

Weak: not having thought about it.

Strong: measured, not guessed — `loadtest.py` (`docs/benchmarks.md`'s
"Concurrency / load test" section) shows one gunicorn sync worker queues
requests rather than running them in parallel: quantum-method throughput
plateaus at ~6.2 req/s regardless of concurrency, and p50 latency climbs
almost linearly with it (167 ms at concurrency 1 → 2530 ms at concurrency
20). The analytics counters (`src/analytics.py`) are lock-protected
in-process and SQLite-backed so they survive a restart (verified by
`tests/test_analytics.py` running two independent subprocesses against the
same db file). Acknowledge honestly that scaling past one worker would
need shared state, which isn't built yet.

## Security

**Q13 — There's no authentication on your API — what stops abuse if this were deployed live?**

Weak: "We didn't think it needed it."

Strong: IP-based rate limiting is already in place (`@_rate_limit("20 per
minute")` on every solve/insights endpoint in `app.py`) for exactly this —
and it's verified, not just present: `loadtest.py`'s rate-limit mode fired
a 30-request burst at a normally configured server and measured exactly
20 succeed and 10 correctly rejected with `429` (`docs/benchmarks.md`). A
production deployment behind a real department would add operator auth on
top; the compute-abuse surface is already the smallest reasonable scope
since no PII is ever collected.

## Scalability

**Q14 — Your Procfile runs one gunicorn worker — how does this survive real traffic?**

Weak: not knowing what the Procfile does.

Strong: measured, not just acknowledged — `loadtest.py` against a real
gunicorn process (`docs/benchmarks.md`) shows throughput plateaus at ~6.2
req/s under the quantum method regardless of concurrency, because one sync
worker serves one request at a time. It doesn't survive real concurrent
traffic yet, and that's deliberate — a single worker keeps the in-process
analytics counters accurate for a demo. Scaling out needs shared state
(Redis or a real DB) — a known, named next step, not an oversight.

**Q15 — What's your plan for solving 500 stops in seconds instead of the ~40 you support today?**

Weak: "We'd just run it longer."

Strong: deeper hierarchical clustering, and potentially routing large
clusters to a real QPU/hybrid solver once classical clustering itself
becomes the bottleneck. Name this as future work, not something already
done.

## Cost

**Q16 — What would this actually cost a state transport department to run, including any real quantum hardware time?**

Weak: not having a number at all.

Strong: the default classical-hardware path costs only ordinary server
hosting. The optional D-Wave QPU path needs a paid Leap plan
(`docs/quantum-hardware.md`) and should be positioned as a future upgrade
for cases classical clustering can't handle, not a required cost today —
consistent with this project's standing "no paid infrastructure" build
constraint.

## Deployment

**Q17 — Your demo depends on three free external services with no SLA — what happens the day one rate-limits you mid-pilot?**

Weak: not having noticed this is a risk.

Strong: `README.md` already documents pointing `OSRM_BASE_URL` at a
self-hosted OSRM instance for production use — a free public demo server
is correct for a hackathon, not for a real pilot, and the swap is one
environment variable.

**Q18 — We just watched your map fail to load on this network — how would you handle that in front of judges?**

*Why asked:* this is a live, verified risk the review's own sandbox test hit.

Weak: being caught off guard.

Strong: this is now handled two ways instead of one. Lead with the
static, zero-dependency flagship demo (`index.html` /
`output/multi_city_map.html`) precisely for this reason — it has no
external network dependency at all. And the live app itself no longer
fails silently: a raw `Failed to fetch` now surfaces as a plain-language
message (`_friendlyErrorMessage()` in `templates/click_router.html`), and
a dismissible banner proactively tells the visitor when OSRM is
unreachable and links to `/demo` instead of leaving the page looking
broken (`_checkNetworkHealth()`).

## Government adoption

**Q19 — Which specific department would deploy this, and have you spoken to one?**

Weak: a vague "any logistics company."

Strong: name a concrete, plausible first customer — a municipal
delivery/waste-collection fleet, or a state logistics PSU — even if no
conversation has happened yet, and say so honestly rather than implying
one has. (See the note in the final delivery about this being a real,
outside-of-code action for the team, not something automatable.)

**Q20 — Your repository has no license — how would a government body legally adopt this code?**

*Status: fixed.* An MIT `LICENSE` file is already in the repository root.
If the answer to Q4/patent questions changes the plan (a more restrictive
license while a patent path is open), say that explicitly rather than
defaulting to "we hadn't thought about it."

## Competitors

**Q21 — How is this different from what Google Maps or OR-Tools already do in production?**

Weak: "We're better than Google Maps."

Strong: Google Maps answers "fastest A to B"; this answers "best order to
visit many stops with side constraints," a genuinely different,
harder combinatorial problem. OR-Tools is in fact used *inside* this
project as an optional comparison baseline, not a competitor to be beaten
— frame it as "we benchmark against the industry standard, not around it."

**Q22 — Fifty other teams are also doing "quantum-inspired routing" this year — why you specifically?**

*Why asked:* the exact test this whole review is built around.

Weak: repeating "quantum" louder.

Strong: real, reproducible numbers showing exactly where the approach
helps and where it doesn't — Experiment 1 (loses on plain routing, stated
plainly), Experiment 2 (15/15 vs 8/15 on a real dispatch rule), Experiment
3 (composed constraints). Most teams will show a demo; few will show a
result that admits where their own approach loses.

## Limitations

**Q23 — What's the single biggest thing your own documentation admits doesn't work yet?**

Weak: claiming there are no real limitations.

Strong: time windows are "pruned but not guaranteed" (`docs/features.md`)
— a provably safe filter on the search space, not a solved wall-clock
arrival guarantee. State it exactly as the codebase itself does, in those
words.

**Q24 — What does "pruned but not guaranteed" actually mean for a real delivery SLA?**

Weak: overstating what the feature actually guarantees.

Strong: cite the number directly rather than the softer word "helps" —
Experiment 5 (`docs/features.md`) shows the pruned solve only actually
satisfied the constructed time window in **3/15** trials; pruning never
does worse than no time-window awareness at all, but it is not a
guarantee of an on-time arrival.

## Future scope

**Q25 — What's the realistic path from this prototype to something a state transport corporation could actually run tomorrow?**

Weak: a vague "we'll add more features."

Strong: a concrete, sequenced list, not a wishlist — self-hosted OSRM
(one env var, already documented) + the real traffic provider (already
wired, just needs a paid API key the team would need to budget for) + one
real pilot with an actual operator's stop list. Say which of these is
code-ready today versus which needs the team's own outside action (see
the final delivery notes for exactly that split).

---

## What changed since this review was written

The review that produced these 25 questions also flagged several concrete
gaps against the *deployed* version of this project. Several of those were
already resolved in the local, unpushed git history at the time of the
review, and the remaining genuine gaps have since been closed:

- The `.github/workflows/tests.yml` CI workflow the review said was
  missing exists in this repo (`ls .github/workflows/`).
- An MIT `LICENSE` file exists.
- The capability-aware method selector exists — `/api/capabilities`
  disables "Real QPU" in the UI with an explanatory label instead of
  letting it dead-end into a raw error (`_applyCapabilities()` in
  `templates/click_router.html`).
- The in-app Insights view exists — `/api/insights` serves the five
  benchmark experiments as real charts inside the running app, not just
  as CSVs in `output/`.
- Friendly network-failure messaging and a network-health banner are new
  as of this pass (see Q18 above).
- A PS-alignment badge ("PS SIH26137") with an explanatory tooltip is now
  on both the live app's topbar and the static flagship demo.
- The review's "nice to have" concurrency/load test (Section 16, Top-10
  improvement #10) is also done — `loadtest.py`, real numbers in
  `docs/benchmarks.md`'s "Concurrency / load test" section, cited in Q12–15
  above.

What's genuinely still open, and needs a person rather than more code, is
covered in the project's final delivery notes: the local git history has
never been pushed to any remote, so a judge looking at the *published*
GitHub repo will still see it lagging behind; the patent-sensitive
research documents sitting in a public repository need the team's own
decision (make the repo private, or get IPR-cell sign-off) rather than a
unilateral file move; and an actual pilot conversation or a real paid
D-Wave QPU run both require outside-of-code action only the team can take.
