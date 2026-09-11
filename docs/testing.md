# Automated Tests

[← Back to README](../README.md)

## Automated tests

`tests/` has a pytest suite that enforces, in CI, the correctness claims
this README makes in prose rather than leaving them as one-time manual
checks — including the exact "verified against brute-force-optimal on
random trials" property claimed for the open-path solver below. Run it
with:

```
pip install pytest
pytest tests/ -v
```

**420 Python tests** (509 total including the layout suite below, plus a
separate 14-test Node.js frontend suite — see below), covering the QUBO
solver, the classical baselines, the multi-objective time/distance
trade-off (`combine_objectives`, real-vs-cosmetic-objective checks), route
explainability (`src/explain.py` — leg breakdowns, precedence-cost
attribution, per-vehicle capacity headroom), time-window position-pruning
(`src/time_windows.py` — the provable-bound rigor claims and the measured
pruning-helps-but-doesn't-guarantee gap), real-QPU wiring (`src/qpu_solver.py`
— decode/selection logic verified via an injected stand-in sampler, the
real no-token failure path checked unmocked), real-live-traffic wiring
(`src/traffic_provider.py`'s `GoogleRoutesTrafficProvider` — request
construction and response parsing verified via an injected fake HTTP
session, the real no-API-key failure path checked unmocked, plus the
`points`/`coords` plumbing through `/api/solve` and `/api/solve_fleet`,
and, at the Flask level, that BOTH live endpoints actually route through a
real injected `GoogleRoutesTrafficProvider` end-to-end — not just that the
provider class works in isolation — by monkeypatching `app.py`'s
`_traffic_provider` and asserting the returned route/cost match hand-
computed values and exactly one HTTP call was made), real-data congestion
calibration (`src/vehicle_density_calibration.py` — vehicle-count-per-image
extraction from COCO-format annotations, the density-to-multiplier mapping,
and blending a calibrated multiplier with the synthetic model, all checked
against a fixture matching IISc's UVH-26 dataset's documented schema — see
[`docs/live-app.md`](live-app.md) for why this project's own dev sandbox
can't run it against the real downloaded dataset),
the clustering/scaling logic,
the multi-vehicle dispatch demo (including the
real per-vehicle capacity cap — by stop count *or* by per-stop demand
weight — and its auto-raising of vehicle count in either mode), the
precedence ("visit X before Y") constraint on both the single-vehicle
open-path solver *and* the multi-vehicle dispatch demo (including that it
composes with incident-triggered re-optimization in a single request, that
a precedence pair split across two vehicles by the fleet clustering step
gets co-located onto one vehicle automatically rather than rejected —
including transitive chains — and that it still fails as a clean 400 in
the one case that genuinely can't be worked around: an active hard
capacity cap too small to absorb the co-located pair), the
congestion model (including the on-demand incident spike), the pluggable
traffic-provider interface, the pan-India city data (every city has valid
India-bounded coordinates, enough landmarks for a real route, and a fully
connected road graph), the OpenAPI spec staying in sync with the real
Flask responses, an optional Google OR-Tools comparison suite
(`tests/test_ortools_baseline.py` — matches true brute-force optimal on
small instances, never scores below it, skips cleanly rather than failing
when `ortools` isn't installed) plus a second, fleet-mode-specific one
(`tests/test_ortools_vrp_baseline.py` and `tests/test_benchmark_experiment6.py`
— a real capacitated VRP solve compared against `solve_multi_vehicle`'s
cluster-first/route-second split: every stop visited exactly once, capacity
actually respected on every vehicle, and the core claim that a genuine joint
solver never costs more than the two-step split, checked per-trial not just
on average; same clean-skip behavior when `ortools` isn't installed), an
optional QAOA comparison suite
(`tests/test_qaoa_solver.py` — same never-beats-true-optimal sanity bound,
plus reliably finding the true optimum on the tiny 1-2-interior-stop cases
small enough for both QAOA and brute force to be checked directly, skips
cleanly when `qiskit` isn't installed), and the live Flask endpoints —
including that a 20-stop
request (which the old 10-stop limit would have rejected) now succeeds
end-to-end, that the traffic-awareness fields come back correct for a
given simulated hour, that an incident spike can actually change the
chosen route order (not just the displayed number), and that
`/api/solve_fleet` assigns every stop to exactly one vehicle even under a
capacity constraint. `tests/test_analytics.py` covers the specific claim
`tests/test_app.py`'s Flask-level analytics tests can't (they never
actually restart a process): that `/api/analytics`' SQLite-backed counters
in `src/analytics.py` genuinely survive a process restart — checked by
running two independent Python subprocesses against the same database
file and confirming the second one starts from the first one's counts and
`since` timestamp, not from zero — plus that `_reset_for_tests()` really
does clear the underlying database rows, not just the in-memory dict.

There's also a **14-test frontend suite** (`tests/frontend/`) for the
frontend logic that used to have zero coverage — the turn-by-turn
direction-building/formatting helpers, the "Live re-optimize" demo's
tick-by-tick decision logic (advancing simulated time, picking whether/
where to inject an incident, phrasing the live feed), and the fleet
analogue of that decision logic (`fleetOrderChanged` — did ANY vehicle's
own stop order change tick-to-tick, not just the fleet total) — all in
`static/route_helpers.js`. It needs only Node.js 18+ (its built-in test
runner, no npm install):

```
node --test tests/frontend/*.test.js
```

**And a 75-test real-browser layout suite** (`tests/test_layout.py`),
added after a real bug shipped through a fully green test suite and
several rounds of manual screenshots: the topbar had a fixed height
combined with `flex-wrap`, so on a narrower browser window its second row
of controls (Solve route, Clear points) rendered outside the bar, on top
of the map. Nothing above could have caught that — every other test
verifies *logic* (routes, costs, API responses), not what a real browser
actually paints. This suite launches the real `app.py` as a subprocess and
drives real Chromium against it via Playwright, asserting properties like
"no topbar control ever renders outside the topbar's own box" at five
different window widths (375px through 1920px) — and, to prove that's not
a tautology, temporarily reintroducing the original bug during development
confirmed these exact tests fail against it. It also locks in a few
frontend *interaction* behaviors the earlier unit tests couldn't reach
(multi-vehicle mode relabeling the first pin "Depot," the capacity input
only appearing once fleet mode is selected, the incident-simulate button
rendering once per stop, the city dropdown actually offering all 18
pan-India cities, the voice-search mic button rendering as a clean icon
rather than inheriting a stray dropdown-chevron background from the
topbar's generic button styling, the search fallback finding a broader
match for an address like "Sukhwani Gracia C" while still surfacing a
clear message when nothing is found anywhere, and the redesigned info-icon
tooltip showing/hiding correctly and staying fully on-screen at narrow
widths — several of these are real bugs this suite caught once during
development, not just properties it happened to already satisfy). Three of
these tests exercise the "Live re-optimize" demo end-to-end through a real
browser against the real running app: the button only enabling after a
successful solve, a live tick actually logging a real solved cost (not
just the immediate "started" notice), and clearing points stopping the
loop and disabling the button — with OSRM and map-tile requests stubbed
via Playwright's own request interception (the same pattern the search
tests above already use for Nominatim) rather than needing real network
access to those external services; `/api/solve` itself is reached at the
real local `app.py` and is never stubbed. Needs
Playwright, which — like pytest — is intentionally not in
`requirements.txt` (dev/CI-only, and the test file skips itself cleanly if
it's missing rather than failing the rest of the suite):

```
pip install playwright && playwright install --with-deps chromium
pytest tests/test_layout.py -v
```

The same suite also covers everything added since the product-audit-driven
UI pass (see docs/live-app.md's "The product-audit pass" section): the
progressive-disclosure topbar/Options drawer (every moved control still
reachable, badges reflecting active rule counts); Route History &
Favorites (a solved route recorded to localStorage and reloaded through
the exact same restore path a shared link uses, star/delete wiring, and
that the eviction cap never touches a favorited entry); the `/` landing
page and `/app`/`/demo` split (cross-links round-tripping, and that the
first-run tour appears once for a genuinely new visitor, advances only on
real actions, never reappears once dismissed, and correctly stays silent
for a visitor who already has state); the on-map precedence connector and
time-window clock badge (drawn, followed on drag, and cleared correctly
when a rule or its pin is removed); the Quantum vs. Classical Arena's
countdown/race/winner-banner sequence (deterministic via stubbed
`/api/solve` responses, and confirmed to skip entirely under automation
so it doesn't slow down every other Compare-panel test); and the mobile
pass at 375px width (the Options drawer closing for its own launched
panels only at that width, every centered panel's entrance animation
never overflowing the viewport, and the Insights dashboard staying
reachable through the drawer specifically when its normal topbar entry
point hides).

All three suites run automatically on every push via
`.github/workflows/tests.yml` — that's the badge at the top of this
README. Worth running before a demo either way, and worth mentioning to
judges: the "verified" claims here are checked by an actual, continuously-run
test suite, not just narrated.

